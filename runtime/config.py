"""Centralized runtime configuration loading and validation for ARK."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from runtime.paths import RuntimePaths, get_runtime_paths

VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


@dataclass(frozen=True)
class RuntimeConfig:
    paths: RuntimePaths
    raw: dict[str, Any]
    log_level: str


_cached_config: RuntimeConfig | None = None


def _load_json(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _resolve_log_level(raw: dict[str, Any]) -> str:
    env_level = os.getenv("ARK_LOG_LEVEL", "").strip().upper()
    if env_level in VALID_LOG_LEVELS:
        return env_level

    runtime = raw.get("runtime", {}) if isinstance(raw.get("runtime"), dict) else {}
    value = str(runtime.get("log_level", "INFO")).upper().strip()
    if value in VALID_LOG_LEVELS:
        return value
    return "INFO"


def load_runtime_config(force_reload: bool = False) -> RuntimeConfig:
    global _cached_config
    if _cached_config is not None and not force_reload:
        return _cached_config

    paths = get_runtime_paths()
    raw = _load_json(str(paths.config_path))
    _cached_config = RuntimeConfig(
        paths=paths,
        raw=raw,
        log_level=_resolve_log_level(raw),
    )
    return _cached_config


def get_ai_config() -> dict[str, Any]:
    cfg = load_runtime_config().raw.get("ai", {})
    return cfg if isinstance(cfg, dict) else {}


def get_runtime_settings() -> dict[str, Any]:
    cfg = load_runtime_config().raw.get("runtime", {})
    return cfg if isinstance(cfg, dict) else {}
