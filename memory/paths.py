"""Path resolution utilities for ARK persistent memory storage."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from runtime.paths import get_project_root, resolve_sqlite_path

APP_NAME = "ark"
DB_FILENAME = "ark_memory.db"


def get_legacy_db_path() -> Path:
    return get_project_root() / DB_FILENAME


def get_default_app_data_dir() -> Path:
    env_dir = os.getenv("ARK_APP_DATA_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "ARK"
    if os.name == "nt":
        appdata = os.getenv("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / "ARK"
        return home / "AppData" / "Roaming" / "ARK"
    return home / ".local" / "share" / APP_NAME


def resolve_db_path() -> Path:
    return resolve_sqlite_path()


def ensure_parent_dir(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
