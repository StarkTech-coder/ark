"""Centralized AI provider and model configuration utilities for ARK."""

from __future__ import annotations

import ctypes
import os
from typing import Any
from urllib.parse import urlparse

from runtime.config import load_runtime_config
from runtime.paths import get_runtime_paths

BASE_DIR = str(get_runtime_paths().project_root)
CONFIG_PATH = str(get_runtime_paths().config_path)

DEFAULT_PROVIDER = "ollama"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_CHAT_MODEL = "qwen3:8b"
DEFAULT_EMBEDDING_MODEL = "bge-m3"
DEFAULT_VISION_MODEL = "llava"
DEFAULT_PROFILE_16GB = "m2_16gb"
DEFAULT_PROFILE_HIGH_MEMORY = "high_memory"

DEFAULT_EMBEDDING_DIMENSIONS: dict[str, int] = {
    "bge-m3": 1024,
}

HARDWARE_PROFILES: dict[str, dict[str, Any]] = {
    DEFAULT_PROFILE_16GB: {
        "num_ctx": 8192,
        "num_predict": 4096,
        "max_concurrency": 1,
    },
    DEFAULT_PROFILE_HIGH_MEMORY: {
        "num_ctx": 32768,
        "num_predict": 8192,
        "max_concurrency": 4,
    },
}


def load_config() -> dict:
    """Load global ARK configuration from config.json."""
    return load_runtime_config().raw


def get_ai_config() -> dict:
    """Return the nested AI configuration map."""
    return load_config().get("ai", {})


def get_provider_name() -> str:
    """Resolve active provider name from config."""
    env_provider = os.getenv("ARK_PROVIDER", "").strip()
    if env_provider:
        return env_provider.lower()

    provider = get_ai_config().get("provider", DEFAULT_PROVIDER)
    if isinstance(provider, str) and provider.strip():
        return provider.strip().lower()
    return DEFAULT_PROVIDER


def get_active_chat_model() -> str:
    """Resolve active chat model from config."""
    env_model = os.getenv("ARK_ACTIVE_MODEL", "").strip()
    if env_model:
        return env_model

    model = get_ai_config().get("active_model", DEFAULT_CHAT_MODEL)
    if isinstance(model, str) and model.strip():
        return model.strip()
    return DEFAULT_CHAT_MODEL


def get_embedding_model() -> str:
    """Resolve embedding model from config."""
    env_embedding_model = os.getenv("ARK_EMBEDDING_MODEL", "").strip()
    if env_embedding_model:
        return env_embedding_model

    model = get_ai_config().get("embedding_model", DEFAULT_EMBEDDING_MODEL)
    if isinstance(model, str) and model.strip():
        return model.strip()
    return DEFAULT_EMBEDDING_MODEL


def get_vision_model() -> str:
    """Resolve vision model from config."""
    model = get_ai_config().get("vision_model", DEFAULT_VISION_MODEL)
    if isinstance(model, str) and model.strip():
        return model.strip()
    return DEFAULT_VISION_MODEL


def get_embedding_dimensions() -> dict[str, int]:
    """Return known embedding dimensions by model name."""
    cfg = get_ai_config().get("embedding_dimensions", {})
    if not isinstance(cfg, dict):
        return dict(DEFAULT_EMBEDDING_DIMENSIONS)

    dims = dict(DEFAULT_EMBEDDING_DIMENSIONS)
    for model_name, value in cfg.items():
        if isinstance(model_name, str) and isinstance(value, int) and value > 0:
            dims[model_name] = value
    return dims


def get_embedding_dimension(model_name: str | None = None) -> int:
    """Return expected embedding vector dimension for a model."""
    model = (model_name or get_embedding_model()).strip()
    return get_embedding_dimensions().get(
        model,
        DEFAULT_EMBEDDING_DIMENSIONS[DEFAULT_EMBEDDING_MODEL],
    )


def is_valid_ollama_url(value: str) -> bool:
    """Validate Ollama URL format and supported schemes."""
    try:
        parsed = urlparse(value.strip())
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.hostname:
        return False
    if parsed.path not in {"", "/"}:
        return False
    if parsed.params or parsed.query or parsed.fragment:
        return False
    return True


def get_ollama_host() -> str:
    """Resolve Ollama endpoint from environment/config with safe fallback."""
    env_host = os.getenv("OLLAMA_HOST", "").strip()
    if env_host:
        return env_host if is_valid_ollama_url(env_host) else DEFAULT_OLLAMA_HOST

    cfg_host = get_ai_config().get("ollama_host", "")
    if isinstance(cfg_host, str) and cfg_host.strip():
        candidate = cfg_host.strip()
        return candidate if is_valid_ollama_url(candidate) else DEFAULT_OLLAMA_HOST

    return DEFAULT_OLLAMA_HOST


def get_total_system_ram_gb() -> int:
    """Best-effort total system RAM detection in GiB."""
    try:
        if hasattr(os, "sysconf"):
            page_size = os.sysconf("SC_PAGE_SIZE")
            total_pages = os.sysconf("SC_PHYS_PAGES")
            if isinstance(page_size, int) and isinstance(total_pages, int):
                if page_size > 0 and total_pages > 0:
                    return max(1, int((page_size * total_pages) / (1024**3)))
    except Exception:
        pass

    if os.name == "nt":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return max(1, int(stat.ullTotalPhys / (1024**3)))
        except Exception:
            pass

    return 16


def _normalize_profile_name(profile_name: str) -> str:
    return (profile_name or "").strip().lower()


def get_hardware_profile_name(total_ram_gb: int | None = None) -> str:
    """Resolve active hardware profile from override or detected RAM."""
    override = os.getenv("ARK_HARDWARE_PROFILE", "").strip()
    if not override:
        cfg_override = get_ai_config().get("hardware_profile", "")
        if isinstance(cfg_override, str):
            override = cfg_override.strip()

    if override:
        normalized = _normalize_profile_name(override)
        if normalized in HARDWARE_PROFILES:
            return normalized

    ram_gb = (
        total_ram_gb
        if isinstance(total_ram_gb, int) and total_ram_gb > 0
        else get_total_system_ram_gb()
    )
    if ram_gb >= 128:
        return DEFAULT_PROFILE_HIGH_MEMORY
    return DEFAULT_PROFILE_16GB


def get_hardware_profile(profile_name: str | None = None) -> dict[str, Any]:
    """Return effective hardware profile settings."""
    selected = _normalize_profile_name(profile_name or get_hardware_profile_name())
    base = HARDWARE_PROFILES.get(selected, HARDWARE_PROFILES[DEFAULT_PROFILE_16GB])

    profile = dict(base)
    profile["name"] = selected
    profile["total_ram_gb"] = get_total_system_ram_gb()

    runtime_cfg = get_ai_config().get("runtime", {})
    if isinstance(runtime_cfg, dict):
        if isinstance(runtime_cfg.get("num_ctx"), int) and runtime_cfg["num_ctx"] > 0:
            profile["num_ctx"] = runtime_cfg["num_ctx"]
        if isinstance(runtime_cfg.get("num_predict"), int) and runtime_cfg["num_predict"] > 0:
            profile["num_predict"] = runtime_cfg["num_predict"]
        if (
            isinstance(runtime_cfg.get("max_concurrency"), int)
            and runtime_cfg["max_concurrency"] > 0
        ):
            profile["max_concurrency"] = runtime_cfg["max_concurrency"]

    env_num_ctx = os.getenv("ARK_NUM_CTX", "").strip()
    if env_num_ctx.isdigit() and int(env_num_ctx) > 0:
        profile["num_ctx"] = int(env_num_ctx)

    env_num_predict = os.getenv("ARK_NUM_PREDICT", "").strip()
    if env_num_predict.isdigit() and int(env_num_predict) > 0:
        profile["num_predict"] = int(env_num_predict)

    return profile
