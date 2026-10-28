"""
ARK Chainlit user interface & offline audio controller with LanceDB RAG & SQLite Memory.
Optimized for M2 MacBook Air (16 GB RAM) with global state synchronization and debug logging.
"""

import asyncio
import glob
import json
import os
import re
import subprocess
import threading
import time
from urllib.parse import quote_plus

import chainlit as cl
from chainlit.server import app
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
from ollama import AsyncClient
import pyaudio
from vosk import KaldiRecognizer, Model

# Import optimized local RAG and Memory controllers
from rag.vector_store import insert_documents, query_context, smart_chunk_pdf_text
from memory.db import save_message, get_recent_history, set_memory, get_memory

# ============================================================================
# PATHS & CONFIG
# ============================================================================

BASE_DIR = os.path.expanduser("~/Desktop/ark")
DOCS_DIR = os.path.join(BASE_DIR, "documents")

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MODEL_PATH = os.path.join(BASE_DIR, "model")
MODEL_TR_PATH = os.path.join(BASE_DIR, "model_tr")
ARK_BIN = os.path.join(BASE_DIR, "ark_bin")


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


config_data = load_config()
AI_CONFIG = config_data.get("ai", {})
DEFAULT_ACTIVE_MODEL = AI_CONFIG.get("active_model", "qwen3:8b")

LISTENING_AUDIO_PATH = os.path.join(
    BASE_DIR,
    "assets",
    config_data.get("assets", {}).get("listening_sound", "ark_listening.wav"),
)

# ============================================================================
# FASTAPI STATIC MOUNT
# ============================================================================

app.mount(
    "/public",
    StaticFiles(directory=os.path.join(BASE_DIR, "public")),
    name="public",
)

# ============================================================================
# GLOBAL & SESSION STATE DEFAULTS (Single-User Optimized)
# ============================================================================

_vosk_model = None
_vosk_model_tr = None
stop_event = threading.Event()

# Global state to prevent FastAPI / Chainlit session sync mismatches
GLOBAL_APP_STATE = {
    "web_search_active": False,
    "rag_search_active": True,  # RAG default active for seamless document querying
}

# ============================================================================
# AUTOMATIC DOCUMENTS FOLDER INGESTOR
# ============================================================================


def auto_ingest_documents():
    """Automatically scans and ingests PDFs found in ~/Desktop/ark/documents/ directory upon startup."""
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR, exist_ok=True)
        return

    pdf_files = glob.glob(os.path.join(DOCS_DIR, "*.pdf"))
    for pdf_path in pdf_files:
        pdf_name = os.path.basename(pdf_path)
        try:
            import pypdf

            reader = pypdf.PdfReader(pdf_path)
            file_content = ""
            for page_idx, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    file_content += f"\n[Page {page_idx + 1}]\n" + page_text + "\n\n"

            if file_content.strip():
                chunks = smart_chunk_pdf_text(file_content, source_name=pdf_name)
                if chunks:
                    texts = [c["text"] for c in chunks]
                    insert_documents(texts, source_name=pdf_name, is_academic=True)
                    print(f"[ARK DOCS AUTO-INGEST] Successfully indexed: {pdf_name}")
        except Exception as e:
            print(f"[ARK DOCS AUTO-INGEST ERROR] {pdf_name}: {e}")


# ============================================================================
# GO WEB SCRAPING BRIDGE & SMART INTENT ROUTER
# ============================================================================


def call_ark_api(service: str, param: str = "") -> str:
    """Executes Go ark_bin API or pipeline tool."""
    try:
        cmd = [ARK_BIN, service]
        if param:
            cmd.append(param)
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=10
        )
        return result.stdout.strip()
    except Exception as e:
        return f"[API Call Error ({service}): {str(e)}]"


def fetch_web_content(url: str) -> str:
    """Scrapes target URL using Go ark_bin tool with detailed debugging logs."""
    try:
        result = subprocess.run(
            [ARK_BIN, "web", url],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        output = result.stdout.strip()
        print("[ARK WEB] URL:", url)
        print("[ARK WEB] Return code:", result.returncode)
        print("[ARK WEB] Stdout length:", len(output))
        print("[ARK WEB] Stdout preview:", repr(output[:500]))
        print("[ARK WEB] Stderr:", result.stderr[:1000])
        return output
    except subprocess.CalledProcessError as e:
        print("[ARK WEB ERROR] Return code:", e.returncode)
        print("[ARK WEB ERROR] Stdout:", e.stdout)
        print("[ARK WEB ERROR] Stderr:", e.stderr)
        return f"[Web Scraping Error (Go): {e.stderr.strip()}]"
    except Exception as e:
        print("[ARK WEB ERROR]", repr(e))
        return f"[Web Connection Error: {str(e)}]"


def clean_search_query(user_prompt: str) -> str:
    clean_prompt = re.sub(r'["\']', "", user_prompt)
    return " ".join(clean_prompt.split())


def process_user_prompt_with_rag_and_web(user_prompt: str, rag_active: bool) -> str:
    """Conditional Pipeline: Queries LanceDB RAG only if globally toggled on."""
    web_search_active = GLOBAL_APP_STATE.get("web_search_active", False)
    collected_contexts = []

    print(
        f"[ARK PIPELINE] Evaluating prompt. RAG Active: {rag_active}, Web Active: {web_search_active}"
    )

    # 1. Retrieve relevant context from local LanceDB RAG (Explicitly search academic collection)
    if rag_active:
        try:
            rag_snippets = query_context(user_prompt, top_k=3, search_academic=True)
            print(f"[ARK RAG] Retrieved snippets count: {len(rag_snippets)}")
            if rag_snippets:
                rag_text = "\n".join(rag_snippets)
                collected_contexts.append(
                    f"[LOCAL DOCUMENTS / KNOWLEDGE BASE (RAG)]\n{rag_text}"
                )
        except Exception as e:
            print(f"[ARK RAG ERROR] Failed to query vector store: {e}")

    # 2. Go Engine Pipeline
    try:
        go_intent_data = call_ark_api("pipeline", user_prompt)
        if (
            go_intent_data
            and "HATA" not in go_intent_data
            and len(go_intent_data.strip()) > 0
        ):
            collected_contexts.append(go_intent_data)
    except Exception as e:
        print(f"[ARK ROUTER ERROR] Go pipeline call error: {e}")

    # 3. General Web Search
    url_match = re.search(r"https?://[^\s]+", user_prompt)
    target_url = None

    if url_match:
        target_url = url_match.group(0)
    elif web_search_active:
        search_query = clean_search_query(user_prompt)
        query = quote_plus(search_query)
        target_url = f"https://html.duckduckgo.com/html/?q={query}"

    if target_url:
        scraped_text = fetch_web_content(target_url)
        if (
            scraped_text
            and "HATA" not in scraped_text
            and scraped_text != "[Web içeriği boş veya kazınamadı]"
        ):
            collected_contexts.append(f"[WEB RESULTS]\n{scraped_text}")

    # 4. Context Injection
    if collected_contexts:
        combined_context = "\n\n----------------------------------------\n\n".join(
            collected_contexts
        )
        system_instruction = (
            "[STARK HUD PROTOCOL - CONTEXT INJECTION]\n"
            "- Below is retrieved knowledge from local RAG database, live services, and web results.\n"
            "- RULE 1: Answer the user's request primarily based on this provided context.\n"
            "- RULE 2: If specific facts are missing in the context, do not hallucinate."
        )
        return (
            f"{system_instruction}\n\n{combined_context}\n\nUser Request: {user_prompt}"
        )

    pasif_instruction = (
        "[SYSTEM INSTRUCTION]\n"
        "No external or RAG context was retrieved. Answer directly using your internal knowledge base."
    )
    return f"{pasif_instruction}\n\nUser Request: {user_prompt}"


# ============================================================================
# VOSK MODELS
# ============================================================================


def get_vosk_model():
    global _vosk_model
    if _vosk_model is None and os.path.exists(MODEL_PATH):
        _vosk_model = Model(MODEL_PATH)
    return _vosk_model


def get_vosk_model_tr():
    global _vosk_model_tr
    if _vosk_model_tr is None and os.path.exists(MODEL_TR_PATH):
        _vosk_model_tr = Model(MODEL_TR_PATH)
    return _vosk_model_tr


def record_and_recognize(phrase_limit_sec=15, use_tr=False):
    global stop_event
    stop_event.clear()
    model = get_vosk_model_tr() if use_tr else get_vosk_model()
    if not model:
        return "[ERROR: Vosk Model not found]"

    rec = KaldiRecognizer(model, 16000)
    p = pyaudio.PyAudio()
    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=2000,
        )
    except Exception as e:
        p.terminate()
        return f"[ERROR: Microphone Access - {str(e)}]"

    start_time = time.time()
    try:
        while True:
            if stop_event.is_set() or (time.time() - start_time > phrase_limit_sec):
                break
            try:
                data = stream.read(2000, exception_on_overflow=False)
                if not data:
                    break
                rec.AcceptWaveform(data)
            except Exception:
                break
        res = json.loads(rec.FinalResult())
        return res.get("text", "")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


# ============================================================================
# LOCAL API ENDPOINTS (STT, CMD, WEB TOGGLE, RAG TOGGLE)
# ============================================================================


@app.post("/ark/listen/stt")
async def api_listen_stt():
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, record_and_recognize, 20, True)
    return JSONResponse({"text": text})


@app.post("/ark/listen/stop")
async def api_listen_stop():
    global stop_event
    stop_event.set()
    return JSONResponse({"status": "stopped"})


@app.post("/ark/listen/cmd")
async def api_listen_cmd():
    loop = asyncio.get_event_loop()
    if os.path.exists(LISTENING_AUDIO_PATH):
        await loop.run_in_executor(
            None, lambda: subprocess.run(["afplay", LISTENING_AUDIO_PATH])
        )
    cmd_text = await loop.run_in_executor(None, record_and_recognize, 6, False)
    cmd_text_clean = cmd_text.strip().lower()

    if not cmd_text_clean or "hata" in cmd_text_clean:
        return JSONResponse({"text": cmd_text, "status": "no_input"})

    config = load_config()
    commands = config.get("commands", {})
    dispatched_cmd = None

    for cmd_id, meta in commands.items():
        if any(kw in cmd_text_clean for kw in meta.get("keywords", [])):
            subprocess.Popen([ARK_BIN, cmd_id], cwd=BASE_DIR)
            dispatched_cmd = meta.get("name")
            break

    if dispatched_cmd:
        return JSONResponse(
            {"text": cmd_text, "command": dispatched_cmd, "status": "executed"}
        )
    else:
        return JSONResponse({"text": cmd_text, "status": "unrecognized"})


@app.post("/ark/web/toggle")
async def api_web_toggle():
    current_state = GLOBAL_APP_STATE.get("web_search_active", False)
    new_state = not current_state
    GLOBAL_APP_STATE["web_search_active"] = new_state
    print(f"[ARK STATE] Web Search Toggled: {new_state}")
    return JSONResponse({"active": new_state})


@app.post("/ark/rag/toggle")
async def api_rag_toggle():
    """Updated to use GLOBAL_APP_STATE to avoid session mismatches."""
    new_state = not GLOBAL_APP_STATE["rag_search_active"]
    GLOBAL_APP_STATE["rag_search_active"] = new_state
    print(f"[ARK STATE] RAG Search Toggled: {new_state}")
    return JSONResponse({"active": new_state})


# ============================================================================
# CHAT START & SETTINGS
# ============================================================================


@cl.on_chat_start
async def start():
    thread_id = cl.user_session.get("id", "default_thread")
    cl.user_session.set("thread_id", thread_id)

    models = [DEFAULT_ACTIVE_MODEL]
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/tags", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                raw_models = data.get("models", [])
                valid_models = [
                    m.get("name")
                    for m in raw_models
                    if not any(
                        kw in m.get("name", "").lower()
                        for kw in ["bge", "embed", "embedding", "rerank"]
                    )
                ]
                if valid_models:
                    models = valid_models
    except Exception as e:
        print(f"[ARK MODEL FETCH ERROR] {e}")

    if DEFAULT_ACTIVE_MODEL not in models:
        models.insert(0, DEFAULT_ACTIVE_MODEL)

    settings = await cl.ChatSettings(
        [
            cl.input_widget.Select(
                id="ModelSelect",
                label="ARK Model Selection",
                values=models,
                initial_value=(
                    DEFAULT_ACTIVE_MODEL
                    if DEFAULT_ACTIVE_MODEL in models
                    else models[0]
                ),
            )
        ]
    ).send()

    selected_model = settings.get("ModelSelect", DEFAULT_ACTIVE_MODEL)
    cl.user_session.set("current_model", selected_model)

    # Otomatik Documents Klasörü Tarayıcısını Çalıştır
    auto_ingest_documents()

    await cl.Message(
        content=(
            "🛡️ **ARK SYSTEM ONLINE (Stark HUD Protocol - RAG & Memory Enabled)**\n\n"
            f"Active Model: `{selected_model}` | System fully operational. `documents/` auto-indexed."
        ),
        author="ARK",
    ).send()


@cl.on_settings_update
async def settings_update(settings):
    selected_model = settings.get("ModelSelect", DEFAULT_ACTIVE_MODEL)
    cl.user_session.set("current_model", selected_model)
    await cl.Message(
        content=f"⚙️ **ARK System Updated:** Active Model set to `{selected_model}`.",
        author="ARK",
    ).send()


# ============================================================================
# MAIN CHAT (LLM, RAG, SQLite Memory & Command Router)
# ============================================================================


@cl.on_message
async def main(message: cl.Message):
    raw_text = message.content.strip() if message.content else ""
    active_model = cl.user_session.get("current_model", DEFAULT_ACTIVE_MODEL)
    thread_id = cl.user_session.get("thread_id", "default_thread")

    # Read RAG status from global state instead of session
    rag_active = GLOBAL_APP_STATE["rag_search_active"]

    # 1. COMMAND HANDLER (/cmd)
    if raw_text.startswith("/cmd "):
        cmd_text = raw_text.replace("/cmd ", "", 1).lower()
        if not cmd_text:
            return
        config = load_config()
        commands = config.get("commands", {})
        dispatched = False

        for cmd_id, meta in commands.items():
            if any(kw in cmd_text for kw in meta.get("keywords", [])):
                subprocess.Popen([ARK_BIN, cmd_id], cwd=BASE_DIR)
                await cl.Message(
                    content=f"🚀 **Command Executed:** {meta.get('name')} (`{cmd_id}`)",
                    author="ARK",
                ).send()
                dispatched = True
                break

        if not dispatched:
            await cl.Message(
                content=f"❓ **Unrecognized Voice Command:** '{cmd_text}'",
                author="ARK",
            ).send()
        return

    # Save user message to thread-isolated SQLite history
    save_message("user", raw_text, thread_id=thread_id)

    # 2. CONTEXT ENRICHMENT & DIAGNOSTIC LOGS
    processed_prompt = process_user_prompt_with_rag_and_web(raw_text, rag_active)

    print("[ARK DEBUG] RAG active:", rag_active)
    print("[ARK DEBUG] Web active:", GLOBAL_APP_STATE["web_search_active"])
    print("[ARK DEBUG] Processed prompt length:", len(processed_prompt))
    print("[ARK DEBUG] Processed prompt preview:", repr(processed_prompt[:1500]))

    recent_history = get_recent_history(limit=6, thread_id=thread_id)

    messages = []
    for hist in recent_history[:-1]:
        messages.append({"role": hist["role"], "content": hist["content"]})
    messages.append({"role": "user", "content": processed_prompt})

    print("[ARK DEBUG] Active model:", active_model)
    print("[ARK DEBUG] Message count:", len(messages))

    # 3. LLM RESPONSE WITH STABLE STREAMING & THINKING STATUS
    msg = cl.Message(content="", author="ARK")
    await msg.send()

    full_response = ""
    thinking = False
    first_token_received = False
    client = AsyncClient(host="http://127.0.0.1:11434")

    try:
        response = await client.chat(
            model=active_model,
            messages=messages,
            stream=True,
            options={
                "num_predict": 4096,  # Cevabın yarıda kesilmesini önlemek için maksimum çıkış token sınırı
                "num_ctx": 8192,  # Geniş RAG metinleri ve geçmişi rahatça sığdırmak için bağlam penceresi
                "temperature": 0.3,  # Daha net ve tutarlı yanıtlar için
            },
        )

        async for chunk in response:
            token = chunk.get("message", {}).get("content", "")
            if not token:
                continue

            if not first_token_received:
                first_token_received = True
                msg.content = ""

            full_response += token

            if "<think>" in token:
                thinking = True
                msg.content = "💭 **ARK is thinking / reasoning...**"
                await msg.update()
                token = re.sub(r"<think>.*", "", token, flags=re.DOTALL)

            if "</think>" in token:
                thinking = False
                msg.content = ""
                await msg.update()
                token = re.sub(r".*?</think>", "", token, flags=re.DOTALL)

            if not thinking and token:
                await msg.stream_token(token)

        if not full_response:
            msg.content = "[ERROR: No response generated from model]"
            await msg.update()

    except Exception as e:
        full_response = f"[ERROR: LLM Stream Error - {str(e)}]"
        print(f"[ARK STREAM ERROR] {e}")
        msg.content = full_response
        await msg.update()

    finally:
        try:
            await client.close()
        except Exception:
            pass

    clean_response = (
        re.sub(r"<think>.*?</think>", "", full_response, flags=re.DOTALL).strip()
        if "<think>" in full_response
        else full_response
    )
    if not clean_response:
        clean_response = full_response

    save_message("assistant", clean_response, thread_id=thread_id)
    msg.content = clean_response
    await msg.update()
