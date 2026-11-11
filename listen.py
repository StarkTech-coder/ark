"""ARK Offline Voice Control System - Core Audio & Dispatcher Module.

This script runs locally on macOS, providing a core voice command engine
that can be triggered either via a global keyboard shortcut (when run standalone)
or imported/invoked modularly (e.g., via Chainlit UI buttons).
It captures offline audio via PyAudio/SpeechRecognition, transcribes it using
Vosk, matches commands against config.json, and asynchronously dispatches
the target binary payload (ark_bin).
"""

from typing import Any
import logging
import os
import subprocess
from pynput import keyboard

from runtime.config import load_runtime_config
from runtime.logging_config import configure_logging
from runtime.paths import get_runtime_paths
from runtime.platform_ops import play_audio_file
from runtime.voice import (
    VoiceMicrophoneError,
    VoiceModelNotAvailableError,
    VoiceRecognitionManager,
    VoiceSessionBusyError,
)

# --- Dynamic Path Resolution ---
PATHS = get_runtime_paths()
BASE_DIR = str(PATHS.project_root)
CONFIG_PATH = str(PATHS.config_path)
ARK_BIN = str(PATHS.ark_bin_path)

configure_logging()
logger = logging.getLogger("ark.listen")


def load_config() -> dict[str, Any]:
    """Load system configuration and dynamic voice command mappings from config.json.

    Terminates execution immediately using Fail-Fast pattern if the config is missing.
    """
    cfg = load_runtime_config().raw
    if not cfg:
        print(f"CRITICAL ERROR: Configuration file not found at -> {CONFIG_PATH}")
        exit(1)
    return cfg


# Load global configuration dictionary
config = load_config()

LISTENING_AUDIO_PATH = os.path.join(
    str(PATHS.assets_dir),
    config.get("assets", {}).get("listening_sound", "ark_listening.wav"),
)

VOICE_MANAGER = VoiceRecognitionManager(
    model_en_dir=PATHS.model_dir,
    model_tr_dir=PATHS.model_tr_dir,
)


def listen_once() -> None:
    """Capture audio input offline, transcribe via Vosk, match config commands,

    and dispatch the corresponding binary asynchronously. Can be called programmatically
    from external modules (such as chat_ui.py) or via hotkey.
    """
    print("ARK: Listening process triggered...")

    # 1. Play auditory feedback synchronously
    if os.path.exists(LISTENING_AUDIO_PATH):
        play_audio_file(LISTENING_AUDIO_PATH)
    else:
        logger.warning("Listening sound missing; proceeding silently")

    try:
        cmd = VOICE_MANAGER.recognize(
            session_id="hotkey-listener",
            phrase_limit_sec=5,
            language="en",
        ).lower()
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

    except VoiceModelNotAvailableError as exc:
        logger.error(str(exc))
    except VoiceMicrophoneError as exc:
        logger.error(str(exc))
    except VoiceSessionBusyError:
        logger.warning("Voice session already active")
    except Exception as e:
        print(f"Listening error or timeout encountered: {e}")


if __name__ == "__main__":
    # Register global system-wide hotkey listener using pynput (Only active when run standalone)
    with keyboard.GlobalHotKeys({"<cmd>+<shift>+<ctrl>+a": listen_once}) as h:
        print("ARK Offline Remote Control Active... Press Cmd+Shift+Ctrl+A")
        h.join()
