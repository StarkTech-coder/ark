"""Platform-aware runtime operations."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("ark.runtime.platform")


def play_audio_file(path: str | Path) -> bool:
    audio_path = Path(path)
    if not audio_path.exists():
        logger.warning("Audio file missing: %s", audio_path)
        return False

    system_name = os.name
    try:
        if system_name == "posix":
            if shutil.which("afplay"):
                subprocess.run(["afplay", str(audio_path)], check=False)
                return True
            if shutil.which("paplay"):
                subprocess.run(["paplay", str(audio_path)], check=False)
                return True
            if shutil.which("aplay"):
                subprocess.run(["aplay", str(audio_path)], check=False)
                return True
        elif system_name == "nt":
            powershell = shutil.which("powershell") or shutil.which("pwsh")
            if powershell:
                command = f"(New-Object Media.SoundPlayer '{audio_path}').PlaySync();"
                subprocess.run([powershell, "-NoProfile", "-Command", command], check=False)
                return True
    except Exception as exc:
        logger.warning("Audio playback failed on current platform: %s", exc)
        return False

    logger.info("Audio playback is not supported on this platform setup")
    return False
