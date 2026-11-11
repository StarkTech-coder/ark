"""Cross-platform runtime path resolution for ARK."""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "ARK"


def _env_path(name: str) -> Path | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    expanded = Path(value).expanduser()
    if expanded.is_absolute():
        return Path(os.path.abspath(str(expanded)))
    return Path(os.path.abspath(str(expanded)))


def get_project_root() -> Path:
    env_root = _env_path("ARK_PROJECT_ROOT")
    if env_root:
        return env_root

    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        bundle_resources = executable.parent.parent / "Resources"
        if bundle_resources.exists():
            return bundle_resources

        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidate = Path(str(meipass)).resolve()
            if candidate.exists():
                return candidate

    return Path(__file__).resolve().parents[1]


def get_default_data_dir() -> Path:
    override = _env_path("ARK_APP_DATA_DIR")
    if override:
        return override

    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        appdata = os.getenv("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / APP_NAME
        return home / "AppData" / "Roaming" / APP_NAME

    xdg = os.getenv("XDG_DATA_HOME", "").strip()
    if xdg:
        return Path(xdg) / APP_NAME.lower()
    return home / ".local" / "share" / APP_NAME.lower()


def get_default_config_dir() -> Path:
    override = _env_path("ARK_APP_CONFIG_DIR")
    if override:
        return override

    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        appdata = os.getenv("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / APP_NAME
        return home / "AppData" / "Roaming" / APP_NAME

    xdg = os.getenv("XDG_CONFIG_HOME", "").strip()
    if xdg:
        return Path(xdg) / APP_NAME.lower()
    return home / ".config" / APP_NAME.lower()


def get_default_cache_dir() -> Path:
    override = _env_path("ARK_APP_CACHE_DIR")
    if override:
        return override

    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Caches" / APP_NAME
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / APP_NAME / "Cache"
        return home / "AppData" / "Local" / APP_NAME / "Cache"

    xdg = os.getenv("XDG_CACHE_HOME", "").strip()
    if xdg:
        return Path(xdg) / APP_NAME.lower()
    return home / ".cache" / APP_NAME.lower()


def resolve_config_path() -> Path:
    explicit = _env_path("ARK_CONFIG_PATH")
    if explicit:
        return explicit

    root_candidate = get_project_root() / "config.json"
    if root_candidate.exists():
        return root_candidate

    return get_default_config_dir() / "config.json"


def resolve_sqlite_path() -> Path:
    explicit = _env_path("ARK_MEMORY_DB_PATH")
    if explicit:
        return explicit

    legacy = get_project_root() / "ark_memory.db"
    if legacy.exists():
        return legacy

    return get_default_data_dir() / "ark_memory.db"


def resolve_lancedb_path() -> Path:
    explicit = _env_path("ARK_LANCEDB_PATH")
    if explicit:
        return explicit

    legacy = get_project_root() / ".lancedb"
    if legacy.exists():
        return legacy

    return get_default_data_dir() / "lancedb"


def resolve_model_dir_path() -> Path:
    explicit = _env_path("ARK_VOSK_MODEL_DIR")
    if explicit:
        return explicit

    legacy = get_project_root() / "model"
    if legacy.exists():
        return legacy

    return get_default_data_dir() / "model"


def resolve_model_tr_dir_path() -> Path:
    explicit = _env_path("ARK_VOSK_MODEL_TR_DIR")
    if explicit:
        return explicit

    legacy = get_project_root() / "model_tr"
    if legacy.exists():
        return legacy

    return get_default_data_dir() / "model_tr"


@dataclass(frozen=True)
class RuntimePaths:
    project_root: Path
    data_dir: Path
    config_dir: Path
    cache_dir: Path
    logs_dir: Path
    temp_dir: Path
    config_path: Path
    sqlite_path: Path
    lancedb_path: Path
    docs_dir: Path
    assets_dir: Path
    model_dir: Path
    model_tr_dir: Path
    public_dir: Path
    ark_bin_path: Path


_cached_paths: RuntimePaths | None = None


def get_runtime_paths() -> RuntimePaths:
    global _cached_paths
    if _cached_paths is not None:
        return _cached_paths

    root = get_project_root()
    data_dir = get_default_data_dir()
    config_dir = get_default_config_dir()
    cache_dir = get_default_cache_dir()
    logs_dir = data_dir / "logs"
    temp_dir = data_dir / "tmp"

    ark_bin_override = _env_path("ARK_BIN_PATH")
    ark_bin_path = ark_bin_override if ark_bin_override else root / "ark_bin"

    _cached_paths = RuntimePaths(
        project_root=root,
        data_dir=data_dir,
        config_dir=config_dir,
        cache_dir=cache_dir,
        logs_dir=logs_dir,
        temp_dir=temp_dir,
        config_path=resolve_config_path(),
        sqlite_path=resolve_sqlite_path(),
        lancedb_path=resolve_lancedb_path(),
        docs_dir=root / "documents",
        assets_dir=root / "assets",
        model_dir=resolve_model_dir_path(),
        model_tr_dir=resolve_model_tr_dir_path(),
        public_dir=root / "public",
        ark_bin_path=ark_bin_path,
    )
    return _cached_paths


def ensure_runtime_dirs(paths: RuntimePaths | None = None) -> None:
    p = paths or get_runtime_paths()
    for directory in [p.data_dir, p.config_dir, p.cache_dir, p.logs_dir, p.temp_dir]:
        directory.mkdir(parents=True, exist_ok=True)


def get_temp_dir() -> Path:
    override = _env_path("ARK_APP_TEMP_DIR")
    if override:
        override.mkdir(parents=True, exist_ok=True)
        return override
    return Path(tempfile.gettempdir()) / "ark"
