"""Compatibility facade for ARK persistent memory and conversation history.

This module preserves existing imports used by the chat layer while delegating
to the production memory service architecture.
"""

from __future__ import annotations

from typing import Any

from memory.connection import MemoryDatabaseError
from memory.service import MemoryService

_SERVICE: MemoryService | None = None


def _get_service() -> MemoryService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = MemoryService()
    return _SERVICE


def init_db() -> None:
    """Initialize the memory service and apply pending migrations."""
    _get_service()


def save_message(
    role: str,
    content: str,
    thread_id: str = "default",
    user_id: str = "anonymous",
) -> None:
    """Persist a conversation message without exposing content in logs."""
    if not content:
        return
    try:
        _get_service().add_conversation_message(
            session_id=thread_id,
            role=role,
            content=content,
            user_id=user_id or thread_id or "anonymous",
            source="chat_ui",
        )
    except MemoryDatabaseError:
        # Memory storage failure should not crash unrelated app functionality.
        return


def get_recent_history(
    limit: int = 10,
    thread_id: str = "default",
    user_id: str | None = None,
) -> list[dict[str, str]]:
    """Retrieve recent conversation history for a specific session."""
    try:
        rows = _get_service().get_recent_conversation(
            session_id=thread_id,
            user_id=user_id,
            limit=limit,
        )
    except MemoryDatabaseError:
        return []

    return [{"role": row["role"], "content": row["content"]} for row in rows]


def set_memory(key: str, value: str, *, domain: str = "personal") -> None:
    """Store or update a key/value memory fact in long-term memory."""
    if not key:
        return

    service = _get_service()
    existing = service.search_memories(
        query=key,
        domain=domain,
        memory_type="personal_memory",
    )
    matches = [
        item for item in existing if str(item.get("metadata", {}).get("legacy_key", "")) == key
    ]
    if matches:
        service.update_memory(
            matches[0]["id"],
            domain=domain,
            content=value,
            metadata={"legacy_key": key},
        )
        return

    service.create_memory(
        memory_type="personal_memory",
        content=value,
        domain=domain,
        source="legacy_kv",
        metadata={"legacy_key": key},
    )


def get_memory(key: str, *, domain: str = "personal") -> str:
    """Retrieve a key/value style persistent memory fact by key."""
    if not key:
        return ""

    matches = _get_service().search_memories(
        query=key,
        domain=domain,
        memory_type="personal_memory",
    )
    for item in matches:
        if str(item.get("metadata", {}).get("legacy_key", "")) == key:
            return str(item.get("content", ""))
    return ""


def get_memory_service() -> MemoryService:
    """Expose the underlying memory service for internal integrations/tests."""
    return _get_service()


# Initialize database tables and migrations upon module import.
init_db()
