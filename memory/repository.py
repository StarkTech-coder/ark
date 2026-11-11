"""Repository layer for ARK persistent memory entities."""

from __future__ import annotations

import json
import uuid
from typing import Any

from memory.connection import DatabaseManager
from memory.models import VALID_DOMAINS, utcnow_iso


class DomainAuthorizationError(PermissionError):
    """Raised when a request attempts unauthorized cross-domain access."""


class ValidationError(ValueError):
    """Raised on invalid memory payloads or filters."""


def _validate_domain(domain: str) -> str:
    normalized = (domain or "").strip().lower()
    if normalized not in VALID_DOMAINS:
        raise ValidationError("Invalid memory domain")
    return normalized


def _safe_json_dumps(value: Any, fallback: str) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return fallback


class MemoryRepository:
    """CRUD repository for long-term memory records."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def create(
        self,
        *,
        record_id: str | None = None,
        memory_type: str,
        content: str,
        domain: str,
        source: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        importance_score: float | None = None,
        expires_at: str | None = None,
    ) -> str:
        if not memory_type.strip() or not content.strip():
            raise ValidationError("memory_type and content are required")

        domain_value = _validate_domain(domain)
        final_record_id = record_id.strip() if isinstance(record_id, str) and record_id.strip() else str(uuid.uuid4())
        now = utcnow_iso()

        tags_json = _safe_json_dumps(tags or [], "[]")
        metadata_json = _safe_json_dumps(metadata or {}, "{}")

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_records(
                    id, memory_type, content, domain, source,
                    tags_json, metadata_json, importance_score, expires_at,
                    is_active, is_deleted, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
                """,
                (
                    final_record_id,
                    memory_type.strip(),
                    content,
                    domain_value,
                    source.strip(),
                    tags_json,
                    metadata_json,
                    importance_score,
                    expires_at,
                    now,
                    now,
                ),
            )
        return final_record_id

    def get_by_id(self, record_id: str, *, domain: str | None = None) -> dict[str, Any] | None:
        sql = "SELECT * FROM memory_records WHERE id = ? AND is_deleted = 0"
        params: list[Any] = [record_id]
        if domain is not None:
            sql += " AND domain = ?"
            params.append(_validate_domain(domain))

        with self.db.read_only() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def update(
        self,
        record_id: str,
        *,
        content: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        importance_score: float | None = None,
        expires_at: str | None = None,
        is_active: bool | None = None,
        domain: str,
    ) -> bool:
        _validate_domain(domain)
        fields: list[str] = []
        params: list[Any] = []

        if content is not None:
            fields.append("content = ?")
            params.append(content)
        if tags is not None:
            fields.append("tags_json = ?")
            params.append(_safe_json_dumps(tags, "[]"))
        if metadata is not None:
            fields.append("metadata_json = ?")
            params.append(_safe_json_dumps(metadata, "{}"))
        if importance_score is not None:
            fields.append("importance_score = ?")
            params.append(importance_score)
        if expires_at is not None:
            fields.append("expires_at = ?")
            params.append(expires_at)
        if is_active is not None:
            fields.append("is_active = ?")
            params.append(1 if is_active else 0)

        if not fields:
            return False

        fields.append("updated_at = ?")
        params.append(utcnow_iso())
        params.extend([record_id, domain])

        with self.db.transaction() as conn:
            cur = conn.execute(
                f"UPDATE memory_records SET {', '.join(fields)} WHERE id = ? AND domain = ? AND is_deleted = 0",
                tuple(params),
            )
            return cur.rowcount > 0

    def delete(self, record_id: str, *, domain: str, permanent: bool = False) -> bool:
        domain_value = _validate_domain(domain)
        with self.db.transaction() as conn:
            if permanent:
                cur = conn.execute(
                    "DELETE FROM memory_records WHERE id = ? AND domain = ?",
                    (record_id, domain_value),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE memory_records
                    SET is_deleted = 1, is_active = 0, deleted_at = ?, updated_at = ?
                    WHERE id = ? AND domain = ? AND is_deleted = 0
                    """,
                    (utcnow_iso(), utcnow_iso(), record_id, domain_value),
                )
            return cur.rowcount > 0

    def list_memories(
        self,
        *,
        domain: str,
        memory_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        tags: list[str] | None = None,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        domain_value = _validate_domain(domain)
        page = max(1, page)
        page_size = max(1, min(500, page_size))
        offset = (page - 1) * page_size

        filters = ["domain = ?"]
        params: list[Any] = [domain_value]

        if not include_deleted:
            filters.append("is_deleted = 0")
        if memory_type:
            filters.append("memory_type = ?")
            params.append(memory_type)
        if start_date:
            filters.append("created_at >= ?")
            params.append(start_date)
        if end_date:
            filters.append("created_at <= ?")
            params.append(end_date)

        where = " AND ".join(filters)

        with self.db.read_only() as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_records WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(params + [page_size, offset]),
            ).fetchall()

            total = conn.execute(
                f"SELECT COUNT(*) AS c FROM memory_records WHERE {where}", tuple(params)
            ).fetchone()["c"]

        items = [self._row_to_dict(r) for r in rows]
        if tags:
            tag_set = {t.strip().lower() for t in tags if t.strip()}
            items = [
                i for i in items if tag_set.intersection({t.lower() for t in i["tags"]})
            ]

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": int(total),
        }

    def search(
        self,
        *,
        query: str,
        domain: str | None = None,
        domains: list[str] | None = None,
        memory_type: str | None = None,
        include_deleted: bool = False,
        allow_cross_domain: bool = False,
    ) -> list[dict[str, Any]]:
        query_value = (query or "").strip()
        if not query_value:
            return []

        if domains and len(domains) > 1 and not allow_cross_domain:
            raise DomainAuthorizationError("Cross-domain search requires explicit authorization")

        if domains is None:
            if domain is None:
                raise DomainAuthorizationError("Domain must be explicit for memory search")
            domains = [_validate_domain(domain)]
        else:
            domains = [_validate_domain(d) for d in domains]

        if len(domains) > 1 and not allow_cross_domain:
            raise DomainAuthorizationError("Cross-domain search requires explicit authorization")

        placeholders = ",".join("?" for _ in domains)
        filters = [f"domain IN ({placeholders})", "(content LIKE ? OR source LIKE ?)"]
        params: list[Any] = list(domains) + [f"%{query_value}%", f"%{query_value}%"]

        if not include_deleted:
            filters.append("is_deleted = 0")
        if memory_type:
            filters.append("memory_type = ?")
            params.append(memory_type)

        where = " AND ".join(filters)

        with self.db.read_only() as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_records WHERE {where} ORDER BY updated_at DESC LIMIT 200",
                tuple(params),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def stats(self, *, domain: str | None = None) -> dict[str, Any]:
        filters = []
        params: list[Any] = []
        if domain:
            filters.append("domain = ?")
            params.append(_validate_domain(domain))

        where = f"WHERE {' AND '.join(filters)}" if filters else ""

        with self.db.read_only() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS c FROM memory_records {where}", tuple(params)
            ).fetchone()["c"]
            active = conn.execute(
                f"SELECT COUNT(*) AS c FROM memory_records {where + (' AND ' if where else 'WHERE ') }is_deleted = 0",
                tuple(params),
            ).fetchone()["c"]
            deleted = int(total) - int(active)
            by_domain_rows = conn.execute(
                "SELECT domain, COUNT(*) AS c FROM memory_records GROUP BY domain"
            ).fetchall()
            by_type_rows = conn.execute(
                "SELECT memory_type, COUNT(*) AS c FROM memory_records GROUP BY memory_type"
            ).fetchall()

        return {
            "total": int(total),
            "active": int(active),
            "deleted": int(deleted),
            "by_domain": {r["domain"]: int(r["c"]) for r in by_domain_rows},
            "by_type": {r["memory_type"]: int(r["c"]) for r in by_type_rows},
        }

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        tags = []
        metadata: dict[str, Any] = {}
        try:
            tags_raw = row["tags_json"] or "[]"
            loaded_tags = json.loads(tags_raw)
            if isinstance(loaded_tags, list):
                tags = [str(t) for t in loaded_tags]
        except Exception:
            tags = []
        try:
            metadata_raw = row["metadata_json"] or "{}"
            loaded_meta = json.loads(metadata_raw)
            if isinstance(loaded_meta, dict):
                metadata = loaded_meta
        except Exception:
            metadata = {}

        return {
            "id": row["id"],
            "memory_type": row["memory_type"],
            "content": row["content"],
            "domain": row["domain"],
            "source": row["source"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "tags": tags,
            "metadata": metadata,
            "importance_score": row["importance_score"],
            "expires_at": row["expires_at"],
            "is_active": bool(row["is_active"]),
            "is_deleted": bool(row["is_deleted"]),
            "deleted_at": row["deleted_at"],
        }


class ConversationRepository:
    """Repository for conversation persistence."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def add_message(
        self,
        *,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        domain: str = "messages",
        source: str = "chat",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        domain_value = _validate_domain(domain)
        if domain_value != "messages":
            raise ValidationError("Conversation messages must use 'messages' domain")
        message_id = str(uuid.uuid4())

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO conversation_messages(
                    id, session_id, user_id, role, content, domain, source, metadata_json, is_deleted, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    message_id,
                    session_id or "default",
                    user_id or "anonymous",
                    role,
                    content,
                    domain_value,
                    source,
                    _safe_json_dumps(metadata or {}, "{}"),
                    utcnow_iso(),
                ),
            )
        return message_id

    def get_recent(
        self,
        *,
        session_id: str,
        user_id: str | None = None,
        limit: int = 10,
        domain: str = "messages",
    ) -> list[dict[str, Any]]:
        domain_value = _validate_domain(domain)
        if domain_value != "messages":
            raise ValidationError("Conversation history reads must use 'messages' domain")

        limit_value = max(1, min(500, int(limit)))
        filters = ["session_id = ?", "domain = ?", "is_deleted = 0"]
        params: list[Any] = [session_id or "default", domain_value]
        if user_id:
            filters.append("user_id = ?")
            params.append(user_id)

        where = " AND ".join(filters)
        with self.db.read_only() as conn:
            rows = conn.execute(
                f"SELECT role, content, created_at FROM conversation_messages WHERE {where} ORDER BY created_at DESC LIMIT ?",
                tuple(params + [limit_value]),
            ).fetchall()
        rows = list(rows)
        rows.reverse()
        return [{"role": r["role"], "content": r["content"], "created_at": r["created_at"]} for r in rows]

    def delete_session(self, *, session_id: str, permanent: bool = False) -> int:
        with self.db.transaction() as conn:
            if permanent:
                cur = conn.execute(
                    "DELETE FROM conversation_messages WHERE session_id = ?",
                    (session_id,),
                )
            else:
                cur = conn.execute(
                    "UPDATE conversation_messages SET is_deleted = 1 WHERE session_id = ?",
                    (session_id,),
                )
            return int(cur.rowcount)
