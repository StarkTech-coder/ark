"""
ARK Chainlit user interface & offline audio controller (Stark HUD - Lean Core).
"""

import asyncio
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
from ollama import AsyncClient
import pyaudio
from vosk import KaldiRecognizer, Model

# ============================================================================
# PATHS & CONFIG
# ============================================================================

BASE_DIR = os.path.expanduser("~/Desktop/ark")

CONFIG_PATH = os.path.join(
    BASE_DIR,
    "config.json",
)

MODEL_PATH = os.path.join(
    BASE_DIR,
    "model",
)

MODEL_TR_PATH = os.path.join(
    BASE_DIR,
    "model_tr",
)

ARK_BIN = os.path.join(
    BASE_DIR,
    "ark_bin",
)


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


config_data = load_config()

# Config'den aktif model ismini dinamik çekiyoruz (Tak-çıkar mimari)
AI_CONFIG = config_data.get("ai", {})
ACTIVE_MODEL = AI_CONFIG.get("active_model", "qwen3:8b")

LISTENING_AUDIO_PATH = os.path.join(
    BASE_DIR,
    "assets",
    config_data.get("assets", {}).get(
        "listening_sound",
        "ark_listening.wav",
    ),
)


# ============================================================================
# FASTAPI STATIC MOUNT (Public Klasörü / Logo ve Favicon Erişimi)
# ============================================================================

app.mount(
    "/public",
    StaticFiles(directory=os.path.join(BASE_DIR, "public")),
    name="public",
)


# ============================================================================
# GLOBAL STATE (CHAINLIT CONTEXT BAGIMSIZLIGI)
# ============================================================================

_vosk_model = None
_vosk_model_tr = None
stop_event = threading.Event()

# Web arama modunu Chainlit session yerine güvenli global state'de tutuyoruz
GLOBAL_APP_STATE = {"web_search_active": False}


# ============================================================================
# GO WEB SCRAPING BRIDGE & SMART INTENT ROUTER (Go Motoru Entegrasyonu)
# ============================================================================


def call_ark_api(service: str, param: str = "") -> str:
    """Go ark_bin üzerindeki API veya pipeline aracını çalıştırır."""
    try:
        cmd = [ARK_BIN, service]
        if param:
            cmd.append(param)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"[API Çağrı Hatası ({service}): {str(e)}]"


def fetch_web_content(url: str) -> str:
    """Go ile yazılmış ark_bin aracını kullanarak hedef URL'yi kazır ve temiz metni hazırlar."""
    try:
        result = subprocess.run(
            [ARK_BIN, "web", url],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"[Web Kazıma Hatası (Go): {e.stderr.strip()}]"
    except Exception as e:
        return f"[Web Bağlantı Hatası: {str(e)}]"


def clean_search_query(user_prompt: str) -> str:
    """Kullanıcının sorgusundaki gereksiz tırnakları ve fazla boşlukları temizler."""
    clean_prompt = re.sub(r'["\']', "", user_prompt)
    clean_prompt = " ".join(clean_prompt.split())
    return clean_prompt


def process_user_prompt_with_web(user_prompt: str) -> str:
    """Go Native Pipeline & Dynamic Context Injector."""
    web_search_active = GLOBAL_APP_STATE.get("web_search_active", False)
    collected_contexts = []

    # 1. Go Engine Üzerinden Tüm Intent'leri Paralel Çalıştır ve Çek
    try:
        go_intent_data = call_ark_api("pipeline", user_prompt)
        if (
            go_intent_data
            and "HATA" not in go_intent_data
            and len(go_intent_data.strip()) > 0
        ):
            collected_contexts.append(go_intent_data)
    except Exception as e:
        print(f"[ARK ROUTER ERROR] Go pipeline çağrı hatası: {e}")

    # 2. Genel Web Araması (Eğer Web Modu Aktifse veya URL İçeriyorsa)
    url_match = re.search(r"https?://[^\s]+", user_prompt)
    target_url = None

    if url_match:
        target_url = url_match.group(0)
    elif web_search_active:
        search_query = clean_search_query(user_prompt)
        query = quote_plus(search_query)
        target_url = f"https://html.duckduckgo.com/html/?q={query}"
        print(f"[ARK HUD] Genel Web Araması Yapılıyor - Sorgu: {search_query}")

    if target_url:
        scraped_text = fetch_web_content(target_url)

        # --- DEBUG LOGLARI (VERİ KONTROLÜ) ---
        print("\n" + "=" * 50)
        print(f"[DEBUG WEB SEARCH OUTPUT]:\n{scraped_text}")
        print("=" * 50 + "\n")

        if (
            scraped_text
            and "HATA" not in scraped_text
            and scraped_text != "[Web içeriği boş veya kazınamadı]"
        ):
            collected_contexts.append(f"[WEB RESULTS]\n{scraped_text}")

    # 3. Context Injection ve Prompt Bağlama
    if collected_contexts:
        combined_context = "\n\n----------------------------------------\n\n".join(
            collected_contexts
        )
        system_instruction = (
            "[STARK HUD PROTOCOL - CANLI VERİ VE WEB BAĞLAMI]\n"
            "- Aşağıda anlık sistem servislerinden ve web arama sonuçlarından çekilen bilgiler yer almaktadır.\n"
            "- KURAL 1: Kullanıcının sorusunu öncelikle sana sağlanan bu [WEB RESULTS] ve canlı verileri baz alarak yanıtla.\n"
            "- KURAL 2: Eğer arama sonuçlarında spesifik bir mekan, güncel bilgi veya veri açıkça geçmiyorsa KENDİ BİLGİNDEN UYDURMA. Bilginin sonuçlarda olmadığını belirt."
        )
        return f"{system_instruction}\n\n{combined_context}\n\nKullanıcı İsteği: {user_prompt}"

    # CANLI VERİ ÇEKİLMEDİYSE (Pasif Guardrail - Modeli Kısıtlamaz)
    pasif_instruction = (
        "[SİSTEM TALİMATI]\n"
        "Özel bir canlı veri çekilmedi. Soruyu kendi geniş bilgi birikimini kullanarak doğrudan ve özgüvenle yanıtla. "
        "Sakın 'Arama modum kapalı' veya 'Erişimim yok' gibi ifadeler KULLANMA."
    )
    return f"{pasif_instruction}\n\nKullanıcı İsteği: {user_prompt}"


# ============================================================================
# VOSK MODELS (Offline English & Turkish STT)
# ============================================================================


def get_vosk_model():
    global _vosk_model
    if _vosk_model is None and os.path.exists(MODEL_PATH):
        print("[ARK VOSK EN] İngilizce model yükleniyor...")
        _vosk_model = Model(MODEL_PATH)
        print("[ARK VOSK EN] İngilizce model hazır.")
    return _vosk_model


def get_vosk_model_tr():
    global _vosk_model_tr
    if _vosk_model_tr is None and os.path.exists(MODEL_TR_PATH):
        print("[ARK VOSK TR] Türkçe model yükleniyor...")
        _vosk_model_tr = Model(MODEL_TR_PATH)
        print("[ARK VOSK TR] Türkçe model hazır.")
    return _vosk_model_tr


def record_and_recognize(phrase_limit_sec=15, use_tr=False):
    global stop_event
    stop_event.clear()

    model = get_vosk_model_tr() if use_tr else get_vosk_model()
    if not model:
        model_name = "model_tr" if use_tr else "model"
        return f"[HATA: Vosk Modeli '{model_name}' klasöründe bulunamadı]"

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
        return f"[HATA: Mikrofon Erişimi - {str(e)}]"

    lang_label = "TÜRKÇE" if use_tr else "İNGİLİZCE"
    print(
        f"[ARK AUDIO - {lang_label}] Dinleme aktif (Max Süre: {phrase_limit_sec}s)..."
    )
    start_time = time.time()

    try:
        while True:
            if stop_event.is_set():
                break
            if time.time() - start_time > phrase_limit_sec:
                break
            try:
                data = stream.read(2000, exception_on_overflow=False)
                if not data:
                    break
                rec.AcceptWaveform(data)
            except Exception:
                break

        res = json.loads(rec.FinalResult())
        text = res.get("text", "")
        print(f"[ARK AUDIO - {lang_label}] Algılanan: '{text}'")
        return text
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


# ============================================================================
# LOCAL API ENDPOINTS
# ============================================================================


@app.post("/ark/listen/stt")
async def api_listen_stt():
    """Normal sohbet mikrofonu: Türkçe STT kullanır."""
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
    """Hızlı Sistem Komutları (Yıldırım Butonu): İngilizce Vosk modeli kullanır."""
    loop = asyncio.get_event_loop()

    # 1. Bip / Dinleme sesi çal
    if os.path.exists(LISTENING_AUDIO_PATH):
        await loop.run_in_executor(
            None,
            lambda: subprocess.run(["afplay", LISTENING_AUDIO_PATH]),
        )

    # 2. İNGİLİZCE Vosk modeli ile dinleme (use_tr=False)
    cmd_text = await loop.run_in_executor(None, record_and_recognize, 6, False)
    cmd_text_clean = cmd_text.strip().lower()

    if not cmd_text_clean or "hata" in cmd_text_clean:
        return JSONResponse({"text": cmd_text, "status": "no_input"})

    # 3. Config içindeki komut anahtar kelimeleri ile eşleştir
    config = load_config()
    commands = config.get("commands", {})
    dispatched_cmd = None

    for cmd_id, meta in commands.items():
        if any(kw in cmd_text_clean for kw in meta.get("keywords", [])):
            print(f"[ARK CMD] Eşleşen Komut Bulundu: {meta.get('name')} (`{cmd_id}`)")
            subprocess.Popen([ARK_BIN, cmd_id], cwd=BASE_DIR)
            dispatched_cmd = meta.get("name")
            break

    if dispatched_cmd:
        return JSONResponse(
            {"text": cmd_text, "command": dispatched_cmd, "status": "executed"}
        )
    else:
        print(f"[ARK CMD] Tanımsız Sesli Komut: '{cmd_text_clean}'")
        return JSONResponse({"text": cmd_text, "status": "unrecognized"})


@app.post("/ark/web/toggle")
async def api_web_toggle():
    """Chainlit context gerektirmeyen güvenli web arama modu toggle endpoint'i."""
    current_state = GLOBAL_APP_STATE.get("web_search_active", False)
    new_state = not current_state
    GLOBAL_APP_STATE["web_search_active"] = new_state
    print(f"[ARK HUD] Web Arama Modu değiştirildi: {'AKTİF' if new_state else 'PASİF'}")
    return JSONResponse({"active": new_state})


# ============================================================================
# CHAT START (Stark HUD Başlangıç)
# ============================================================================


@cl.on_chat_start
async def start():
    GLOBAL_APP_STATE["web_search_active"] = False

    await cl.Message(
        content=(
            "🛡️ **ARK SYSTEM ONLINE (Stark HUD Protocol)**\n\n"
            f"Aktif Model: `{ACTIVE_MODEL}` | Sistem tam operasyonel."
        ),
        author="ARK",
    ).send()


# ============================================================================
# MAIN CHAT (LLM & Komut Yürütücü)
# ============================================================================


@cl.on_message
async def main(message: cl.Message):
    raw_text = message.content.strip()

    # 1. GİZLİ KOMUT YAKALAYICI (/cmd)
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
                    content=(
                        f"🚀 **Komut İcra Edildi:** {meta.get('name')} " f"(`{cmd_id}`)"
                    ),
                    author="ARK",
                ).send()
                dispatched = True
                break

        if not dispatched:
            await cl.Message(
                content=f"❓ **Bilinmeyen Sesli Komut:** '{cmd_text}'",
                author="ARK",
            ).send()
        return

    # 2. DOSYA / DOKÜMAN BİLDİRİMİ
    if message.elements:
        for element in message.elements:
            if isinstance(element, cl.File):
                await cl.Message(
                    content=(
                        f"📄 **İÇE AKTARILIYOR:** `{element.name}`\n\n"
                        "Local vektör tabanı hazırlanıyor..."
                    ),
                    author="ARK",
                ).send()

    # 3. WEB KONTROLÜ VE PROMPT ZENGİNLEŞTİRME
    text = process_user_prompt_with_web(raw_text)

    # 4. LLM RESPONSE
    msg = cl.Message(content="", author="ARK")
    await msg.send()

    full_response = ""
    thinking = False
    client = AsyncClient(host="http://127.0.0.1:11434")

    try:
        print(f"[ARK LLM] Model ({ACTIVE_MODEL}) isteği gönderiliyor...")
        stream = await client.chat(
            model=ACTIVE_MODEL,
            messages=[{"role": "user", "content": text}],
            stream=True,
            keep_alive=-1,
        )

        async for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if not token:
                continue

            full_response += token

            if "<think>" in token:
                thinking = True
                token = re.sub(r"<think>.*", "", token, flags=re.DOTALL)

            if "</think>" in token:
                thinking = False
                token = re.sub(r".*?</think>", "", token, flags=re.DOTALL)

            if not thinking and token:
                await msg.stream_token(token)

        print("[ARK LLM] Cevap tamamlandı.")

    except Exception as e:
        print(f"[ARK LLM HATA] {e}")
        full_response = f"[HATA: Local LLM Bağlantı Hatası - {str(e)}]"
        await msg.stream_token(full_response)

    finally:
        try:
            await client.close()
        except Exception:
            pass

    clean_response = re.sub(
        r"<think>.*?</think>", "", full_response, flags=re.DOTALL
    ).strip()
    if not clean_response:
        clean_response = full_response

    await msg.update()
