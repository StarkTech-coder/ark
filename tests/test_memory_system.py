import importlib
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from memory.connection import DatabaseManager
from memory.migrations import CURRENT_SCHEMA_VERSION, get_schema_version
from memory.repository import DomainAuthorizationError, ValidationError
from memory.service import MemoryService


class MemorySystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_memory.db"
        self.service = MemoryService(db_path=self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_database_initialization_and_schema_version(self):
        self.assertTrue(self.db_path.exists())
        version = get_schema_version(DatabaseManager(self.db_path))
        self.assertEqual(version, CURRENT_SCHEMA_VERSION)

    def test_memory_crud(self):
        rec_id = self.service.create_memory(
            memory_type="note",
            content="hello",
            domain="personal",
            tags=["x"],
            metadata={"a": 1},
        )
        row = self.service.get_memory(rec_id, domain="personal")
        self.assertIsNotNone(row)
        self.assertEqual(row["content"], "hello")

        updated = self.service.update_memory(
            rec_id,
            domain="personal",
            content="hello2",
            tags=["y"],
        )
        self.assertTrue(updated)
        row2 = self.service.get_memory(rec_id, domain="personal")
        self.assertEqual(row2["content"], "hello2")
        self.assertEqual(row2["tags"], ["y"])

        deleted = self.service.delete_memory(rec_id, domain="personal", permanent=False)
        self.assertTrue(deleted)
        self.assertIsNone(self.service.get_memory(rec_id, domain="personal"))

    def test_permanent_delete(self):
        rec_id = self.service.create_memory(
            memory_type="fact",
            content="permanent",
            domain="projects",
        )
        self.assertTrue(self.service.delete_memory(rec_id, domain="projects", permanent=True))
        stats = self.service.get_memory_stats(domain="projects")
        self.assertEqual(stats["total"], 0)

    def test_search_pagination_and_filters(self):
        for i in range(15):
            self.service.create_memory(
                memory_type="task" if i % 2 == 0 else "note",
                content=f"project item {i}",
                domain="projects",
                tags=["alpha"] if i % 3 == 0 else ["beta"],
            )

        page1 = self.service.list_memories(domain="projects", page=1, page_size=5)
        page2 = self.service.list_memories(domain="projects", page=2, page_size=5)
        self.assertEqual(len(page1["items"]), 5)
        self.assertEqual(len(page2["items"]), 5)
        self.assertEqual(page1["total"], 15)

        tasks = self.service.list_memories(
            domain="projects",
            memory_type="task",
            page=1,
            page_size=20,
        )
        self.assertTrue(all(item["memory_type"] == "task" for item in tasks["items"]))

        search = self.service.search_memories(query="item 1", domain="projects")
        self.assertTrue(len(search) >= 1)

    def test_domain_isolation_and_unauthorized_cross_domain(self):
        self.service.create_memory(memory_type="note", content="p1", domain="personal")
        self.service.create_memory(memory_type="note", content="u1", domain="university")

        personal_rows = self.service.search_memories(query="1", domain="personal")
        self.assertTrue(all(r["domain"] == "personal" for r in personal_rows))

        with self.assertRaises(DomainAuthorizationError):
            self.service.search_memories(
                query="1",
                domains=["personal", "university"],
                authorize_cross_domain=False,
            )

        cross_rows = self.service.search_memories(
            query="1",
            domains=["personal", "university"],
            authorize_cross_domain=True,
        )
        domains = {r["domain"] for r in cross_rows}
        self.assertIn("personal", domains)
        self.assertIn("university", domains)

    def test_export_import_and_duplicate_handling(self):
        self.service.create_memory(memory_type="note", content="row-a", domain="starktech")
        exported = self.service.export_memories(domain="starktech", fmt="json")
        data = json.loads(exported)
        self.assertEqual(len(data), 1)

        target_db = Path(self.tmp.name) / "import_target.db"
        target_service = MemoryService(db_path=target_db)

        imported = target_service.import_memories(
            domain="starktech",
            payload=exported,
            fmt="json",
            allow_overwrite=False,
        )
        self.assertEqual(imported["imported"], 1)

        # Import the same payload again; should skip duplicates by default.
        imported2 = target_service.import_memories(
            domain="starktech",
            payload=exported,
            fmt="json",
            allow_overwrite=False,
        )
        self.assertEqual(imported2["skipped"], 1)

        csv_payload = target_service.export_memories(domain="starktech", fmt="csv")
        self.assertIn("memory_type", csv_payload)

    def test_import_validation(self):
        with self.assertRaises(ValidationError):
            self.service.import_memories(domain="personal", payload="{bad}", fmt="json")
        with self.assertRaises(ValidationError):
            self.service.import_memories(domain="personal", payload="{}", fmt="json")

    def test_transaction_rollback(self):
        db = DatabaseManager(self.db_path)
        with self.assertRaises(Exception):
            with db.transaction() as conn:
                conn.execute("INSERT INTO memory_records(id, memory_type, content, domain, source, tags_json, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, '[]', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                             ("fixed", "note", "a", "personal", "test"))
                conn.execute("INSERT INTO memory_records(id, memory_type, content, domain, source, tags_json, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, '[]', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                             ("fixed", "note", "b", "personal", "test"))

        with db.read_only() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM memory_records WHERE id = ?", ("fixed",)).fetchone()
            self.assertEqual(row["c"], 0)

    def test_persistence_across_reconnection(self):
        rec_id = self.service.create_memory(
            memory_type="fact",
            content="persist-me",
            domain="projects",
        )
        second = MemoryService(db_path=self.db_path)
        row = second.get_memory(rec_id, domain="projects")
        self.assertIsNotNone(row)
        self.assertEqual(row["content"], "persist-me")

    def test_concurrent_access(self):
        def worker(idx: int):
            self.service.add_conversation_message(
                session_id="s1",
                user_id="u1",
                role="user",
                content=f"m{idx}",
            )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        messages = self.service.get_recent_conversation(session_id="s1", user_id="u1", limit=50)
        self.assertEqual(len(messages), 20)

    def test_legacy_migration_preserves_data(self):
        legacy_path = Path(self.tmp.name) / "legacy.db"
        conn = sqlite3.connect(str(legacy_path))
        conn.execute(
            "CREATE TABLE chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "CREATE TABLE user_memory (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO chat_history(thread_id, role, content) VALUES ('t1', 'user', 'legacy message')"
        )
        conn.execute(
            "INSERT INTO user_memory(key, value) VALUES ('nickname', 'tony')"
        )
        conn.commit()
        conn.close()

        migrated = MemoryService(db_path=legacy_path)
        conv = migrated.get_recent_conversation(session_id="t1", limit=10)
        self.assertEqual(len(conv), 1)
        self.assertEqual(conv[0]["content"], "legacy message")

        records = migrated.search_memories(query="tony", domain="personal")
        self.assertEqual(len(records), 1)

    def test_chainlit_compatibility_functions(self):
        db_file = Path(self.tmp.name) / "chat_wrapper.db"
        os.environ["ARK_MEMORY_DB_PATH"] = str(db_file)
        try:
            import memory.db as memory_db

            importlib.reload(memory_db)
            memory_db.save_message("user", "hello", thread_id="thr-1", user_id="u-1")
            memory_db.save_message("assistant", "merhaba", thread_id="thr-1", user_id="u-1")

            rows = memory_db.get_recent_history(limit=10, thread_id="thr-1", user_id="u-1")
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["role"], "user")
            self.assertEqual(rows[1]["role"], "assistant")
        finally:
            os.environ.pop("ARK_MEMORY_DB_PATH", None)


if __name__ == "__main__":
    unittest.main()
