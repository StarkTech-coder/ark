"""Business logic service for ARK persistent memory management."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from memory.connection import DatabaseManager
from memory.migrations import apply_migrations, get_schema_version
from memory.repository import (
    ConversationRepository,
    DomainAuthorizationError,
    MemoryRepository,
    ValidationError,
)


class MemoryService:
    """High-level API for persistent memory and conversation storage."""

    def __init__(self, db_path: str | Path | None = None):
        self.db = DatabaseManager(db_path=db_path)
        apply_migrations(self.db)
        self.memory_repo = MemoryRepository(self.db)
        self.conversation_repo = ConversationRepository(self.db)

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "schema_version": get_schema_version(self.db),
            "db_path": str(self.db.db_path),
        }

    # Long-term memory operations
    def create_memory(
        self,
        *,
        memory_type: str,
        content: str,
        domain: str,
        source: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        importance_score: float | None = None,
        expires_at: str | None = None,
    ) -> str:
        return self.memory_repo.create(
            memory_type=memory_type,
            content=content,
            domain=domain,
            source=source,
            tags=tags,
            metadata=metadata,
            importance_score=importance_score,
            expires_at=expires_at,
        )

    def get_memory(self, record_id: str, *, domain: str) -> dict[str, Any] | None:
        return self.memory_repo.get_by_id(record_id, domain=domain)

    def update_memory(self, record_id: str, *, domain: str, **fields: Any) -> bool:
        return self.memory_repo.update(record_id, domain=domain, **fields)

    def delete_memory(self, record_id: str, *, domain: str, permanent: bool = False) -> bool:
        return self.memory_repo.delete(record_id, domain=domain, permanent=permanent)

    def list_memories(self, *, domain: str, **filters: Any) -> dict[str, Any]:
        return self.memory_repo.list_memories(domain=domain, **filters)

    def search_memories(
        self,
        *,
        query: str,
        domain: str | None = None,
        domains: list[str] | None = None,
        memory_type: str | None = None,
        include_deleted: bool = False,
        authorize_cross_domain: bool = False,
    ) -> list[dict[str, Any]]:
        return self.memory_repo.search(
            query=query,
            domain=domain,
            domains=domains,
            memory_type=memory_type,
            include_deleted=include_deleted,
            allow_cross_domain=authorize_cross_domain,
        )

    def get_memory_stats(self, *, domain: str | None = None) -> dict[str, Any]:
        return self.memory_repo.stats(domain=domain)

    def export_memories(self, *, domain: str, fmt: str = "json") -> str:
        payload = self.list_memories(domain=domain, include_deleted=True, page=1, page_size=100000)
        items = payload["items"]

        if fmt == "json":
            return json.dumps(items, ensure_ascii=False, indent=2)
        if fmt == "csv":
            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "id",
                    "memory_type",
                    "content",
                    "domain",
                    "source",
                    "created_at",
                    "updated_at",
                    "tags",
                    "metadata",
                    "importance_score",
                    "expires_at",
                    "is_active",
                    "is_deleted",
                    "deleted_at",
                ],
            )
            writer.writeheader()
            for item in items:
                writer.writerow(
                    {
                        **item,
                        "tags": json.dumps(item.get("tags", []), ensure_ascii=False),
                        "metadata": json.dumps(item.get("metadata", {}), ensure_ascii=False),
                    }
                )
            return output.getvalue()
        raise ValidationError("Unsupported export format")

    def import_memories(
        self,
        *,
        domain: str,
        payload: str,
        fmt: str = "json",
        allow_overwrite: bool = False,
    ) -> dict[str, int]:
        imported = 0
        skipped = 0

        if fmt != "json":
            raise ValidationError("Only JSON import is currently supported")

        try:
            records = json.loads(payload)
        except Exception as exc:
            raise ValidationError("Invalid JSON import payload") from exc

        if not isinstance(records, list):
            raise ValidationError("Import payload must be a list of memory records")

        for item in records:
            if not isinstance(item, dict):
                skipped += 1
                continue

            record_id = str(item.get("id", "")).strip()
            existing = self.memory_repo.get_by_id(record_id, domain=domain) if record_id else None
            if existing and not allow_overwrite:
                skipped += 1
                continue

            if existing and allow_overwrite:
                updated = self.memory_repo.update(
                    record_id,
                    domain=domain,
                    content=str(item.get("content", existing["content"])),
                    tags=item.get("tags", existing.get("tags", [])),
                    metadata=item.get("metadata", existing.get("metadata", {})),
                    importance_score=item.get("importance_score", existing.get("importance_score")),
                    expires_at=item.get("expires_at", existing.get("expires_at")),
                    is_active=bool(item.get("is_active", existing.get("is_active", True))),
                )
                if updated:
                    imported += 1
                else:
                    skipped += 1
                continue

            try:
                self.memory_repo.create(
                    record_id=record_id or None,
                    memory_type=str(item.get("memory_type", "note")),
                    content=str(item.get("content", "")),
                    domain=domain,
                    source=str(item.get("source", "import")),
                    tags=item.get("tags", []),
                    metadata=item.get("metadata", {}),
                    importance_score=item.get("importance_score"),
                    expires_at=item.get("expires_at"),
                )
                imported += 1
            except ValidationError:
                skipped += 1

        return {"imported": imported, "skipped": skipped}

    # Conversation operations
    def add_conversation_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        user_id: str = "anonymous",
        source: str = "chat",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self.conversation_repo.add_message(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            domain="messages",
            source=source,
            metadata=metadata,
        )

    def get_recent_conversation(
        self,
        *,
        session_id: str,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return self.conversation_repo.get_recent(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
            domain="messages",
        )

    def delete_conversation_session(self, *, session_id: str, permanent: bool = False) -> int:
        return self.conversation_repo.delete_session(session_id=session_id, permanent=permanent)


__all__ = [
    "MemoryService",
    "DomainAuthorizationError",
    "ValidationError",
]
