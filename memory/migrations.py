"""Schema versioning and migration runner for ARK memory database."""

from __future__ import annotations

import json
from typing import Callable

from memory.connection import DatabaseManager

CURRENT_SCHEMA_VERSION = 4


Migration = Callable[[DatabaseManager], None]


def _ensure_migration_table(db: DatabaseManager) -> None:
    with db.transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _is_applied(db: DatabaseManager, version: int) -> bool:
    with db.read_only() as conn:
        row = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
        ).fetchone()
        return row is not None


def _mark_applied(db: DatabaseManager, version: int) -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (version,)
        )


def _migration_1(db: DatabaseManager) -> None:
    with db.transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_records (
                id TEXT PRIMARY KEY,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                domain TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                importance_score REAL,
                expires_at TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                legacy_key TEXT UNIQUE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'anonymous',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                domain TEXT NOT NULL DEFAULT 'messages',
                source TEXT NOT NULL DEFAULT 'chat',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                legacy_chat_id INTEGER UNIQUE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_domain_type_active ON memory_records(domain, memory_type, is_deleted, is_active)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_created_at ON memory_records(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversation_session_created ON conversation_messages(session_id, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversation_domain ON conversation_messages(domain, is_deleted)"
        )


def _migration_2(db: DatabaseManager) -> None:
    """Import legacy chat_history and user_memory rows without deleting originals."""

    with db.read_only() as conn:
        has_chat_history = (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_history'"
            ).fetchone()
            is not None
        )
        has_user_memory = (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_memory'"
            ).fetchone()
            is not None
        )

    if has_chat_history:
        with db.transaction() as conn:
            rows = conn.execute(
                "SELECT id, COALESCE(thread_id, 'default') AS thread_id, role, content, COALESCE(timestamp, CURRENT_TIMESTAMP) AS timestamp FROM chat_history ORDER BY id ASC"
            ).fetchall()
            for row in rows:
                message_id = f"legacy-chat-{row['id']}"
                conn.execute(
                    """
                    INSERT OR IGNORE INTO conversation_messages(
                        id, session_id, user_id, role, content, domain, source,
                        metadata_json, created_at, legacy_chat_id
                    ) VALUES (?, ?, ?, ?, ?, 'messages', 'legacy_chat_history', ?, ?, ?)
                    """,
                    (
                        message_id,
                        row["thread_id"] or "default",
                        row["thread_id"] or "anonymous",
                        row["role"],
                        row["content"],
                        "{}",
                        row["timestamp"],
                        row["id"],
                    ),
                )

    if has_user_memory:
        with db.transaction() as conn:
            rows = conn.execute(
                "SELECT key, value, COALESCE(updated_at, CURRENT_TIMESTAMP) AS updated_at FROM user_memory"
            ).fetchall()
            for row in rows:
                memory_id = f"legacy-memory-{row['key']}"
                metadata = json.dumps({"legacy_key": row["key"]}, ensure_ascii=False)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO memory_records(
                        id, memory_type, content, domain, source, tags_json, metadata_json,
                        is_active, is_deleted, created_at, updated_at, legacy_key
                    ) VALUES (?, 'personal_memory', ?, 'personal', 'legacy_user_memory', '[]', ?, 1, 0, ?, ?, ?)
                    """,
                    (
                        memory_id,
                        row["value"],
                        metadata,
                        row["updated_at"],
                        row["updated_at"],
                        row["key"],
                    ),
                )


def _migration_3(db: DatabaseManager) -> None:
    with db.transaction() as conn:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_domain_updated ON memory_records(domain, updated_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_expires ON memory_records(expires_at)"
        )


def _migration_4(db: DatabaseManager) -> None:
    with db.transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mcp_servers (
                server_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                command_json TEXT NOT NULL DEFAULT '[]',
                env_json TEXT NOT NULL DEFAULT '{}',
                last_status TEXT NOT NULL DEFAULT 'stopped',
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mcp_tools (
                server_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                required_permission TEXT NOT NULL DEFAULT 'read',
                is_sensitive INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (server_id, tool_name),
                FOREIGN KEY (server_id) REFERENCES mcp_servers(server_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mcp_permissions (
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                server_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                permission_level TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, user_id, server_id, tool_name),
                FOREIGN KEY (server_id, tool_name)
                    REFERENCES mcp_tools(server_id, tool_name) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mcp_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                server_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                action TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mcp_servers_kind_enabled ON mcp_servers(kind, enabled)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mcp_permissions_session_user ON mcp_permissions(session_id, user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mcp_audit_session_created ON mcp_audit_logs(session_id, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mcp_audit_decision_created ON mcp_audit_logs(decision, created_at DESC)"
        )


MIGRATIONS: list[tuple[int, Migration]] = [
    (1, _migration_1),
    (2, _migration_2),
    (3, _migration_3),
    (4, _migration_4),
]


def apply_migrations(db: DatabaseManager) -> None:
    _ensure_migration_table(db)
    for version, migration in MIGRATIONS:
        if _is_applied(db, version):
            continue
        migration(db)
        _mark_applied(db, version)


def get_schema_version(db: DatabaseManager) -> int:
    _ensure_migration_table(db)
    with db.read_only() as conn:
        row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
        return int(row["v"] or 0)
