"""Structured logging setup for ARK runtime."""

from __future__ import annotations

import logging
from pathlib import Path

from runtime.config import load_runtime_config
from runtime.paths import ensure_runtime_dirs

_CONFIGURED = False


def configure_logging(force: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    cfg = load_runtime_config(force_reload=force)
    ensure_runtime_dirs(cfg.paths)

    log_file: Path = cfg.paths.logs_dir / "ark.log"

    level = getattr(logging, cfg.log_level, logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    if force:
        for handler in list(root.handlers):
            root.removeHandler(handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)

    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    _CONFIGURED = True
