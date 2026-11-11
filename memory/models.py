"""Data models for ARK persistent memory entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


VALID_DOMAINS = {"personal", "messages", "university", "starktech", "projects"}


@dataclass
class MemoryRecord:
    id: str
    memory_type: str
    content: str
    domain: str
    source: str
    created_at: str
    updated_at: str
    tags: list[str]
    metadata: dict[str, Any]
    importance_score: float | None
    expires_at: str | None
    is_active: bool
    is_deleted: bool
    deleted_at: str | None


@dataclass
class ConversationMessage:
    id: str
    session_id: str
    user_id: str
    role: str
    content: str
    domain: str
    source: str
    created_at: str
    metadata: dict[str, Any]
    is_deleted: bool


def utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
