"""SQLite connection and transaction management for ARK memory."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from memory.paths import ensure_parent_dir, resolve_db_path


class MemoryDatabaseError(RuntimeError):
    """Raised when memory database operations fail."""


class DatabaseManager:
    """Manage SQLite connections with safe defaults for concurrent local sessions."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path).expanduser().resolve() if db_path else resolve_db_path()
        ensure_parent_dir(self.db_path)

    def connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10,
                isolation_level=None,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA busy_timeout = 10000")
            return conn
        except sqlite3.Error as exc:
            raise MemoryDatabaseError("Unable to connect to memory database") from exc

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise MemoryDatabaseError("Memory database transaction failed") from exc
        finally:
            conn.close()

    @contextmanager
    def read_only(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        except sqlite3.Error as exc:
            raise MemoryDatabaseError("Memory database read failed") from exc
        finally:
            conn.close()
