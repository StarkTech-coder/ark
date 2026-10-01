"""ARK Chainlit user interface & offline audio controller."""

import asyncio
import json
import os
import subprocess
import threading
import time
import pyaudio
from vosk import KaldiRecognizer, Model

import chainlit as cl
from chainlit.server import app
from fastapi.responses import JSONResponse

# ============================================================================
# PATHS & CONFIG
# ============================================================================
BASE_DIR = os.path.expanduser("~/Desktop/ark")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MODEL_PATH = os.path.join(BASE_DIR, "model")
ARK_BIN = os.path.join(BASE_DIR, "ark_bin")


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


config_data = load_config()
LISTENING_AUDIO_PATH = os.path.join(
    BASE_DIR,
    "assets",
    config_data.get("assets", {}).get("listening_sound", "ark_listening.wav"),
)

_vosk_model = None
stop_event = threading.Event()


def get_vosk_model():
    global _vosk_model
    if _vosk_model is None and os.path.exists(MODEL_PATH):
        _vosk_model = Model(MODEL_PATH)
    return _vosk_model


# ============================================================================
# CORE HARDWARE AUDIO SYSTEM (PYAUDIO + VOSK STREAM)
# ============================================================================
def record_and_recognize(phrase_limit_sec=15):
    """PyAudio akışı ile mikrofonu açar ve stop_event tetiklendiğinde anında sonlandırır."""
    global stop_event
    stop_event.clear()

    model = get_vosk_model()
    if not model:
        return "[HATA: Vosk Modeli 'model' klasöründe bulunamadı]"

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

    print(f"[ARK AUDIO] Dinleme aktif (Max Süre: {phrase_limit_sec}s)...")
    start_time = time.time()

    try:
        while True:
            if stop_event.is_set():
                print("[ARK AUDIO] Dinleme kullanıcı tarafından durduruldu.")
                break
            if time.time() - start_time > phrase_limit_sec:
                print("[ARK AUDIO] Zaman aşımına ulaşıldı.")
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
        print(f"[ARK AUDIO] Algılanan: '{text}'")
        return text
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


# ============================================================================
# LOCAL API ENDPOINTS (JavaScript Köprüleri)
# ============================================================================
@app.post("/ark/listen/stt")
async def api_listen_stt():
    """Uzun Metin Dikte Etme Rotası (Tekrar basılana veya 20s dolana kadar dinler)"""
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, record_and_recognize, 20)
    return JSONResponse({"text": text})


@app.post("/ark/listen/stop")
async def api_listen_stop():
    """Mikrofon Dinlemesini Anında Durdurma Rotası"""
    global stop_event
    stop_event.set()
    return JSONResponse({"status": "stopped"})


@app.post("/ark/listen/cmd")
async def api_listen_cmd():
    """Hızlı Komut Rotası (Bip sesi çalar, BİTTİKTEN SONRA mikrofon açılır)"""
    loop = asyncio.get_event_loop()

    # 1. Bildirim sesini çal ve bitmesini bekle (Mikrofonun kendi sesini kaydetmesini engeller)
    if os.path.exists(LISTENING_AUDIO_PATH):
        await loop.run_in_executor(
            None, lambda: subprocess.run(["afplay", LISTENING_AUDIO_PATH])
        )

    # 2. Bip bittiği an mikrofonu aç ve 6 saniye dinle
    text = await loop.run_in_executor(None, record_and_recognize, 6)
    return JSONResponse({"text": text})


# ============================================================================
# CHAT LOGIC & SYSTEM AGENT
# ============================================================================
@cl.on_chat_start
async def start():
    await cl.Message(
        content="**ARK SYSTEM ONLINE**\n\nOffline RAG, STT API & Command Hub Ready.",
        author="ARK",
    ).send()


@cl.on_message
async def main(message: cl.Message):
    text = message.content.strip()

    # 1. GİZLİ KOMUT YAKALAYICI
    if text.startswith("/cmd "):
        cmd_text = text.replace("/cmd ", "", 1).lower()
        if not cmd_text:
            return

        config = load_config()
        commands = config.get("commands", {})
        dispatched = False

        for cmd_id, meta in commands.items():
            if any(kw in cmd_text for kw in meta.get("keywords", [])):
                subprocess.Popen([ARK_BIN, cmd_id], cwd=BASE_DIR)
                await cl.Message(
                    content=f"🚀 **Komut İcra Edildi:** {meta.get('name')} (`{cmd_id}`)",
                    author="ARK",
                ).send()
                dispatched = True
                break

        if not dispatched:
            await cl.Message(
                content=f"❓ **Bilinmeyen Sesli Komut:** '{cmd_text}'", author="ARK"
            ).send()
        return

    # 2. NORMAL CHAT AKIŞI
    if message.elements:
        for element in message.elements:
            if isinstance(element, cl.File):
                await cl.Message(
                    content=f"📄 **İÇE AKTARILIYOR:** `{element.name}`\n\nLocal vektör db hazırlanıyor...",
                    author="ARK",
                ).send()

    full_response = "Sistem hazır. Yeni direktifleri bekliyorum."
    msg = cl.Message(content="")
    await msg.send()
    for token in full_response.split():
        await msg.stream_token(token + " ")
        await asyncio.sleep(0.05)

    msg.actions = [
        cl.Action(name="read_aloud", value=msg.content, label="🔊 Oku"),
        cl.Action(name="copy_text", value=msg.content, label="📋 Kopyala"),
    ]
    await msg.update()


@cl.action_callback("read_aloud")
async def on_read_aloud(action: cl.Action):
    await cl.Message(content="🎙️ **XTTS MOTORU DEVREDE...**", author="ARK").send()
