"""Runtime lifecycle helpers for startup and shutdown reliability."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from memory.db import init_db
from runtime.config import load_runtime_config
from runtime.logging_config import configure_logging
from runtime.paths import ensure_runtime_dirs

logger = logging.getLogger("ark.runtime.lifecycle")


@dataclass
class ServiceStatus:
    critical_ready: bool
    sqlite_ready: bool
    lancedb_ready: bool
    ollama_ready: bool | None
    details: dict[str, str]


_INITIALIZED = False


async def initialize_runtime(chat_provider: Any | None = None) -> ServiceStatus:
    global _INITIALIZED
    details: dict[str, str] = {}

    configure_logging()
    cfg = load_runtime_config()
    ensure_runtime_dirs(cfg.paths)

    sqlite_ready = False
    lancedb_ready = False
    ollama_ready: bool | None = None

    # Critical service: SQLite memory
    try:
        init_db()
        sqlite_ready = True
    except Exception as exc:
        logger.error("SQLite initialization failed: %s", exc)
        details["sqlite"] = "failed"

    # Optional service: LanceDB availability probe
    try:
        from rag import vector_store as vs

        _ = vs._safe_table_names()  # noqa: SLF001 - internal probe for readiness
        lancedb_ready = True
    except Exception as exc:
        logger.warning("LanceDB probe failed: %s", exc)
        details["lancedb"] = "unavailable"

    # Optional service: Ollama runtime
    if chat_provider is not None:
        try:
            if asyncio.iscoroutinefunction(chat_provider.check_provider_health):
                ollama_ready = await chat_provider.check_provider_health()
            else:
                ollama_ready = bool(chat_provider.check_provider_health())
        except Exception as exc:
            logger.warning("LLM provider health check failed: %s", exc)
            ollama_ready = False
            details["llm_provider"] = "unavailable"

    _INITIALIZED = sqlite_ready
    return ServiceStatus(
        critical_ready=sqlite_ready,
        sqlite_ready=sqlite_ready,
        lancedb_ready=lancedb_ready,
        ollama_ready=ollama_ready,
        details=details,
    )


async def shutdown_runtime(chat_provider: Any | None = None) -> None:
    if chat_provider is None:
        return

    close_fn = getattr(chat_provider, "close", None)
    if close_fn is None:
        return

    try:
        result = close_fn()
        if asyncio.iscoroutine(result):
            await result
    except Exception as exc:
        logger.warning("LLM provider shutdown had an error: %s", exc)
