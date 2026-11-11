import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import lancedb

from rag import vector_store as vs


def _embed_text(text: str, dim: int = 1024) -> list[float]:
    vec = [0.0] * dim
    lower = text.lower()
    # Deterministic lightweight semantic buckets for tests.
    if "quantum" in lower or "physics" in lower:
        vec[0] = 1.0
    if "roadmap" in lower or "sprint" in lower or "project" in lower:
        vec[1] = 1.0
    if "private" in lower or "chat" in lower or "message" in lower:
        vec[2] = 1.0
    if "stark" in lower:
        vec[3] = 1.0
    if all(v == 0.0 for v in vec):
        vec[4] = 1.0
    return vec


class RagEnhancementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.tmp.name) / "lancedb"
        self.db_dir.mkdir(parents=True, exist_ok=True)

        self.orig_db = vs.db
        self.orig_db_path = vs.DB_PATH
        self.orig_meta_path = vs.EMBEDDING_META_PATH

        vs.DB_PATH = str(self.db_dir)
        vs.db = lancedb.connect(str(self.db_dir))
        vs.EMBEDDING_META_PATH = str(self.db_dir / "embedding_meta.json")

    def tearDown(self):
        vs.db = self.orig_db
        vs.DB_PATH = self.orig_db_path
        vs.EMBEDDING_META_PATH = self.orig_meta_path
        self.tmp.cleanup()

    def _insert_fixture_docs(self):
        with patch("rag.vector_store.get_embedding_model_name", return_value="bge-m3"), patch(
            "rag.vector_store.get_embedding_dimension", return_value=1024
        ), patch("rag.vector_store.get_embeddings_batch") as batch_embed:
            def _batch(texts):
                return [_embed_text(t) for t in texts]

            batch_embed.side_effect = _batch
            vs.insert_documents(
                ["Quantum physics lecture notes on wave functions"],
                source_name="university_notes.pdf",
                page="12",
                category="university",
            )
            vs.insert_documents(
                ["Project roadmap sprint planning for Q4"],
                source_name="project_plan.md",
                page="1",
                category="code",
            )
            vs.insert_documents(
                ["Private chat message archive entry"],
                source_name="chat_archive.txt",
                page="chat_1",
                category="relationship",
            )

    def test_source_attribution_fields_present(self):
        self._insert_fixture_docs()

        with patch("rag.vector_store.get_embedding") as embed_query:
            embed_query.side_effect = lambda text: _embed_text(text)
            results = vs.retrieve_context_with_sources(
                "quantum wave",
                top_k=3,
                authorized_domains=["university"],
                allow_cross_domain=False,
                retrieval_mode="hybrid",
                target_intent_override=vs.UNIVERSITY_TABLE,
            )

        self.assertGreaterEqual(len(results), 1)
        row = results[0]
        self.assertIn("source", row)
        self.assertIn("title", row)
        self.assertIn("page", row)
        self.assertIn("domain", row)
        self.assertIn("category", row)
        self.assertIn("document_id", row)
        self.assertIn("score", row)

    def test_domain_isolation_default_and_cross_domain_authorization(self):
        self._insert_fixture_docs()

        with patch("rag.vector_store.get_embedding") as embed_query:
            embed_query.side_effect = lambda text: _embed_text(text)

            # all-intent defaults to a single authorized domain (projects)
            default_results = vs.retrieve_context_with_sources(
                "project sprint",
                top_k=5,
                authorized_domains=None,
                allow_cross_domain=False,
                retrieval_mode="hybrid",
                target_intent_override="all",
            )
            self.assertTrue(all(r["domain"] == "projects" for r in default_results))

            with self.assertRaises(PermissionError):
                vs.retrieve_context_with_sources(
                    "project sprint",
                    top_k=5,
                    authorized_domains=["projects", "university"],
                    allow_cross_domain=False,
                    retrieval_mode="hybrid",
                    target_intent_override="all",
                )

            allowed = vs.retrieve_context_with_sources(
                "project sprint quantum",
                top_k=5,
                authorized_domains=["projects", "university"],
                allow_cross_domain=True,
                retrieval_mode="hybrid",
                target_intent_override="all",
            )
            self.assertGreaterEqual(len(allowed), 2)
            self.assertTrue({"projects", "university"}.issuperset({r["domain"] for r in allowed}))

    def test_keyword_vector_and_hybrid_retrieval(self):
        self._insert_fixture_docs()

        with patch("rag.vector_store.get_embedding") as embed_query:
            embed_query.side_effect = lambda text: _embed_text(text)

            keyword_only = vs.retrieve_context_with_sources(
                "wave functions",
                top_k=3,
                authorized_domains=["university"],
                retrieval_mode="keyword",
                target_intent_override=vs.UNIVERSITY_TABLE,
            )
            self.assertGreaterEqual(len(keyword_only), 1)

            vector_only = vs.retrieve_context_with_sources(
                "quantum physics",
                top_k=3,
                authorized_domains=["university"],
                retrieval_mode="vector",
                target_intent_override=vs.UNIVERSITY_TABLE,
            )
            self.assertGreaterEqual(len(vector_only), 1)

            hybrid = vs.retrieve_context_with_sources(
                "quantum wave functions",
                top_k=3,
                authorized_domains=["university"],
                retrieval_mode="hybrid",
                target_intent_override=vs.UNIVERSITY_TABLE,
            )
            self.assertGreaterEqual(len(hybrid), 1)

    def test_duplicate_suppression_between_vector_and_keyword(self):
        self._insert_fixture_docs()
        with patch("rag.vector_store.get_embedding") as embed_query:
            embed_query.side_effect = lambda text: _embed_text(text)
            results = vs.retrieve_context_with_sources(
                "project roadmap sprint",
                top_k=10,
                authorized_domains=["projects"],
                retrieval_mode="hybrid",
                target_intent_override=vs.CODE_TABLE,
            )

        doc_ids = [r["document_id"] for r in results]
        self.assertEqual(len(doc_ids), len(set(doc_ids)))

    def test_embedding_compatibility_model_mismatch_rejected(self):
        self._insert_fixture_docs()
        with patch("rag.vector_store.get_embedding_model_name", return_value="new-model"):
            with self.assertRaises(RuntimeError):
                vs._assert_embedding_compatibility(vs.UNIVERSITY_TABLE, 1024)

    def test_embedding_compatibility_legacy_table_without_metadata_rejected(self):
        # create table and add row directly, without metadata file
        table = vs.get_or_create_table(vs.UNIVERSITY_TABLE)
        table.add(
            [
                {
                    "vector": _embed_text("legacy row"),
                    "text": "legacy row",
                    "source": "legacy.txt",
                    "page": "1",
                    "category": "university",
                }
            ]
        )

        # remove metadata sidecar to simulate legacy collection without metadata
        meta_path = Path(vs.EMBEDDING_META_PATH)
        if meta_path.exists():
            meta_path.unlink()

        with patch("rag.vector_store.get_embedding_model_name", return_value="bge-m3"), patch(
            "rag.vector_store.get_embedding_dimension", return_value=1024
        ):
            with self.assertRaises(RuntimeError):
                vs._assert_embedding_compatibility(vs.UNIVERSITY_TABLE, 1024)

    def test_text_only_compatibility_api(self):
        self._insert_fixture_docs()
        with patch("rag.vector_store.get_embedding") as embed_query, patch(
            "rag.vector_store.route_query_intent", new=AsyncMock(return_value=vs.UNIVERSITY_TABLE)
        ):
            embed_query.side_effect = lambda text: _embed_text(text)
            snippets = vs.query_context("quantum wave", top_k=2)
            self.assertTrue(isinstance(snippets, list))
            self.assertTrue(all(isinstance(s, str) for s in snippets))


if __name__ == "__main__":
    unittest.main()
