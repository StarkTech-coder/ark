import json
import os
from typing import Any
import subprocess
import speech_recognition as sr
from pynput import keyboard
from vosk import KaldiRecognizer, Model

# Dynamic paths resolution
BASE_DIR = os.path.expanduser("~/Desktop/ark") 
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MODEL_PATH = os.path.join(BASE_DIR, "model")
ARK_BIN = os.path.join(BASE_DIR, "ark_bin")


def load_config() -> dict[str, Any]:
    """Loads configuration and dynamic voice command mappings from config.json."""
    if not os.path.exists(CONFIG_PATH):
        print(f"ERROR: Configuration file not found at {CONFIG_PATH}")
        exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


config = load_config()
LISTENING_AUDIO_PATH = os.path.join(
    BASE_DIR,
    "assets",
    config.get("assets", {}).get("listening_sound", "ark_listening.wav"),
)

# Validate Vosk speech recognition model
if not os.path.exists(MODEL_PATH):
    print(f"ERROR: Vosk model directory not found at -> {MODEL_PATH}")
    print(
        "Please download and extract the model directory as 'model' under the root folder."
    )
    exit(1)

print("ARK: Loading offline speech recognition model...")
model = Model(MODEL_PATH)
print("ARK: System initialized. Cloud connectivity: DISABLED.")


def listen_once() -> None:
    """Captures audio input offline, matches configured commands, and dispatches asynchronously."""
    print("ARK: Listening process triggered...")

    # 1. Play notification sound synchronously FIRST (Block until audio finishes)
    if os.path.exists(LISTENING_AUDIO_PATH):
        subprocess.run(["afplay", LISTENING_AUDIO_PATH])
    else:
        print(
            f"[ARK WARN] Listening sound missing at '{LISTENING_AUDIO_PATH}'. Proceeding silently..."
        )

    # 2. Open microphone ONLY AFTER the listening sound has finished playing
    r = sr.Recognizer()
    print("ARK: Listening (Offline)... Speak now!")

    with sr.Microphone() as source:
        # Dynamically measure noise floor and set a safe lower threshold bound  ne    s
        r.adjust_for_ambient_noise(source, duration=0.1)
        r.energy_threshold = max(r.energy_threshold, 300)

        try:
            # User now gets the full 5 seconds window after the sound finishes!
            audio = r.listen(source, phrase_time_limit=4, timeout=5)
            pcm_data = audio.get_raw_data(convert_rate=16000, convert_width=2)

            rec = KaldiRecognizer(model, 16000)
            rec.AcceptWaveform(pcm_data)
            result = json.loads(rec.FinalResult())

            cmd = result.get("text", "").lower()
            print(f"Command received: '{cmd}'")

            if not cmd: 
                print("Audio unrecognized or empty input.")
                return

            # Match keyword dynamically against config.json definitions
            command_dispatched = False
            commands = config.get("commands", {})

            for cmd_id, meta in commands.items():
                keywords = meta.get("keywords", [])
                if any(kw in cmd for kw in keywords):
                    print(
                        f"Dispatching {meta.get('name', '').capitalize()} Mode ({cmd_id})..."
                    )
                    # Asynchronous execution (Fire-and-Forget) for the Go binary
                    subprocess.Popen([ARK_BIN, cmd_id], cwd=BASE_DIR)
                    command_dispatched = True
                    break

            if not command_dispatched:
                print(f"Unrecognized command context: '{cmd}'")

        except Exception as e:
            print(f"Listening error or timeout: {e}")


if __name__ == "__main__":
    with keyboard.GlobalHotKeys({"<cmd>+<shift>+<ctrl>+a": listen_once}) as h:
        print("ARK Offline Remote Control Active... Press Cmd+Shift+Ctrl+A")
        h.join()
