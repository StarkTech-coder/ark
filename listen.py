"""ARK Offline Voice Control System - Core Audio & Dispatcher Module.

This script runs locally on macOS, providing a core voice command engine
that can be triggered either via a global keyboard shortcut (when run standalone)
or imported/invoked modularly (e.g., via Chainlit UI buttons).
It captures offline audio via PyAudio/SpeechRecognition, transcribes it using
Vosk, matches commands against config.json, and asynchronously dispatches
the target binary payload (ark_bin).
"""

from typing import Any
import json
import os
import subprocess
from pynput import keyboard
import speech_recognition as sr
from vosk import KaldiRecognizer, Model

# --- Dynamic Path Resolution ---
BASE_DIR = os.path.expanduser("~/Desktop/ark")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MODEL_PATH = os.path.join(BASE_DIR, "model")
ARK_BIN = os.path.join(BASE_DIR, "ark_bin")


def load_config() -> dict[str, Any]:
    """Load system configuration and dynamic voice command mappings from config.json.

    Terminates execution immediately using Fail-Fast pattern if the config is missing.
    """
    if not os.path.exists(CONFIG_PATH):
        print(f"CRITICAL ERROR: Configuration file not found at -> {CONFIG_PATH}")
        exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# Load global configuration dictionary
config = load_config()

LISTENING_AUDIO_PATH = os.path.join(
    BASE_DIR,
    "assets",
    config.get("assets", {}).get("listening_sound", "ark_listening.wav"),
)

# --- Vosk Model Initialization & Validation ---
if not os.path.exists(MODEL_PATH):
    print(f"CRITICAL ERROR: Vosk model directory not found at -> {MODEL_PATH}")
    print(
        "Please download and extract the model directory as 'model' under the root folder."
    )
    exit(1)

print("ARK: Loading offline speech recognition model into RAM...")
model = Model(MODEL_PATH)
print("ARK: System initialized successfully. Cloud connectivity: DISABLED.")


def listen_once() -> None:
    """Capture audio input offline, transcribe via Vosk, match config commands,

    and dispatch the corresponding binary asynchronously. Can be called programmatically
    from external modules (such as chat_ui.py) or via hotkey.
    """
    print("ARK: Listening process triggered...")

    # 1. Play auditory feedback synchronously
    if os.path.exists(LISTENING_AUDIO_PATH):
        subprocess.run(["afplay", LISTENING_AUDIO_PATH])
    else:
        print(
            f"[ARK WARN] Listening sound missing at '{LISTENING_AUDIO_PATH}'. Proceeding silently..."
        )

    # 2. Initialize speech recognizer and open microphone safely
    r = sr.Recognizer()
    print("ARK: Listening (Offline mode active)... Speak now!")

    source = None
    try:
        source = sr.Microphone()
        with source:
            # Calibrate ambient noise floor and set threshold boundaries
            r.adjust_for_ambient_noise(source, duration=0.1)
            r.energy_threshold = max(r.energy_threshold, 300)

            # Allocate a 5-second timeout window with a 4-second phrase limit
            audio = r.listen(source, phrase_time_limit=4, timeout=5)
            pcm_data = audio.get_raw_data(convert_rate=16000, convert_width=2)

            # Process PCM stream through Vosk local recognizer engine
            rec = KaldiRecognizer(model, 16000)
            rec.AcceptWaveform(pcm_data)
            result = json.loads(rec.FinalResult())

            cmd = result.get("text", "").lower()
            print(f"Command received: '{cmd}'")

            if not cmd:
                print("Audio unrecognized or empty input received.")
                return

            # Match transcribed keywords dynamically against config rules
            command_dispatched = False
            commands = config.get("commands", {})

            for cmd_id, meta in commands.items():
                keywords = meta.get("keywords", [])
                if any(kw in cmd for kw in keywords):
                    print(
                        f"Dispatching {meta.get('name', '').capitalize()} Mode ({cmd_id})..."
                    )
                    # Asynchronously launch the Go binary engine without blocking the main loop
                    subprocess.Popen([ARK_BIN, cmd_id], cwd=BASE_DIR)
                    command_dispatched = True
                    break

            if not command_dispatched:
                print(f"Unrecognized command context: '{cmd}'")

    except Exception as e:
        print(f"Listening error or timeout encountered: {e}")

    finally:
        # HARDWARE SAFETY NET: Force-release CoreAudio/PortAudio stream locks to prevent driver freezes
        if source and hasattr(source, "stream") and source.stream:
            try:
                if hasattr(source.stream, "pyaudio_stream"):
                    source.stream.pyaudio_stream.stop_stream()
                    source.stream.pyaudio_stream.close()
            except Exception:
                pass


if __name__ == "__main__":
    # Register global system-wide hotkey listener using pynput (Only active when run standalone)
    with keyboard.GlobalHotKeys({"<cmd>+<shift>+<ctrl>+a": listen_once}) as h:
        print("ARK Offline Remote Control Active... Press Cmd+Shift+Ctrl+A")
        h.join()
