import unittest
from types import SimpleNamespace
from unittest.mock import patch

import chat_ui
from mcp_servers.web_research_mcp import WebResearchError, WebResearchResult, WebSource


class UnifiedWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def test_normal_chat_analysis(self):
        decision = chat_ui._analyze_request_workflow("Merhaba nasılsın?")
        self.assertEqual(decision["request_type"], "general_chat")
        self.assertFalse(decision["use_web"])

    def test_personal_memory_analysis(self):
        decision = chat_ui._analyze_request_workflow("Benim kişisel tercihlerimi hatırla")
        self.assertEqual(decision["domain"], "personal")
        self.assertTrue(decision["use_memory"])

    def test_project_rag_analysis(self):
        decision = chat_ui._analyze_request_workflow("Projedeki API bugını açıkla")
        self.assertEqual(decision["domain"], "projects")
        self.assertTrue(decision["use_rag"])

    def test_multi_source_analysis(self):
        decision = chat_ui._analyze_request_workflow("Projedeki bug için güncel web araştırması yap")
        self.assertEqual(decision["request_type"], "multi_source")
        self.assertTrue(decision["use_web"])
        self.assertTrue(decision["use_rag"])

    def test_github_workflow_analysis(self):
        decision = chat_ui._analyze_request_workflow("github repo commitlerini göster")
        self.assertEqual(decision["request_type"], "multi_source")
        self.assertTrue(decision["use_github"])

    def test_collect_github_context_blocked(self):
        with patch.object(
            chat_ui.MCP_MANAGER,
            "authorize_tool_execution",
            return_value=SimpleNamespace(allowed=False),
        ):
            context, used_mcp, used_sources = chat_ui._collect_github_context(
                prompt="github repos",
                session_id="s1",
                user_id="u1",
            )

        self.assertIn("GITHUB BLOCKED", context)
        self.assertEqual(used_mcp[0]["status"], "blocked")
        self.assertEqual(used_sources, [])

    def test_collect_github_context_repo_listing(self):
        with patch.object(
            chat_ui.MCP_MANAGER,
            "authorize_tool_execution",
            return_value=SimpleNamespace(allowed=True),
        ), patch(
            "chat_ui.list_repositories",
            return_value=[
                {
                    "name": "ark",
                    "full_name": "tony/ark",
                    "updated_at": "2026-11-11T00:00:00Z",
                }
            ],
        ):
            context, used_mcp, used_sources = chat_ui._collect_github_context(
                prompt="list github repos",
                session_id="s1",
                user_id="u1",
            )

        self.assertIn("GITHUB REPOSITORIES", context)
        self.assertEqual(used_mcp[0]["status"], "used")
        self.assertEqual(used_sources[0]["label"], "repo")

    def test_collect_github_context_pr_diff(self):
        with patch.object(
            chat_ui.MCP_MANAGER,
            "authorize_tool_execution",
            return_value=SimpleNamespace(allowed=True),
        ), patch(
            "chat_ui.list_repositories",
            return_value=[{"name": "ark", "full_name": "tony/ark", "updated_at": "x"}],
        ), patch(
            "chat_ui.read_pull_request_diff",
            return_value="diff --git a/file b/file",
        ):
            context, used_mcp, used_sources = chat_ui._collect_github_context(
                prompt="show diff for pr #12 in tony/ark",
                session_id="s1",
                user_id="u1",
            )

        self.assertIn("GITHUB PR DIFF", context)
        self.assertTrue(any(item.get("tool") == "local.github/read_pull_request_diff" for item in used_mcp))
        self.assertTrue(any(item.get("label") == "pull_request" for item in used_sources))

    async def test_web_research_sources_are_included(self):
        with patch.dict(chat_ui.GLOBAL_APP_STATE, {"web_search_active": False, "rag_search_active": False}, clear=False):
            fake_result = WebResearchResult(
                user_query="q",
                search_query="q",
                access_date="2026-11-11T00:00:00+00:00",
                sources=[
                    WebSource(
                        source_title="Source A",
                        source_url="https://example.com/a",
                        domain="example.com",
                        publication_date="2026-11-10",
                        access_date="2026-11-11T00:00:00+00:00",
                        extracted_content="content",
                        relevant_excerpt="excerpt",
                    )
                ],
                warnings=[],
            )
            with patch("chat_ui.perform_web_research", return_value=fake_result), patch(
                "chat_ui.query_context_with_sources", return_value=[]
            ):
                prompt, used_sources = await chat_ui.process_user_prompt_with_rag_and_web(
                    "güncel bilgi ver",
                    rag_active=False,
                    active_model="qwen3:8b",
                    web_allowed=True,
                    rag_domains=None,
                    memory_context=None,
                    force_web=True,
                )

        self.assertIn("WEB RESEARCH SOURCES", prompt)
        self.assertEqual(len(used_sources["web"]), 1)

    async def test_mcp_unauthorized_web_blocked(self):
        with patch.dict(chat_ui.GLOBAL_APP_STATE, {"web_search_active": False, "rag_search_active": False}, clear=False):
            with patch("chat_ui.query_context_with_sources", return_value=[]):
                prompt, used_sources = await chat_ui.process_user_prompt_with_rag_and_web(
                    "güncel bilgi ver",
                    rag_active=False,
                    active_model="qwen3:8b",
                    web_allowed=False,
                    rag_domains=None,
                    memory_context=None,
                    force_web=True,
                )

        self.assertIn("WEB RESEARCH BLOCKED", prompt)
        self.assertTrue(any(item.get("status") == "blocked" for item in used_sources["mcp"]))

    async def test_optional_service_failure_does_not_crash(self):
        with patch.dict(chat_ui.GLOBAL_APP_STATE, {"web_search_active": False, "rag_search_active": False}, clear=False):
            with patch("chat_ui.query_context_with_sources", side_effect=RuntimeError("rag down")), patch(
                "chat_ui.perform_web_research", side_effect=WebResearchError("web down")
            ):
                prompt, used_sources = await chat_ui.process_user_prompt_with_rag_and_web(
                    "güncel proje bilgisi",
                    rag_active=True,
                    active_model="qwen3:8b",
                    web_allowed=True,
                    rag_domains=["projects"],
                    memory_context=None,
                    force_web=True,
                )

        self.assertIn("WEB RESEARCH ERROR", prompt)
        self.assertIsInstance(used_sources, dict)

    def test_source_format_uses_real_categories(self):
        summary = chat_ui._format_used_sources(
            {
                "memory": [{"domain": "personal", "source": "sqlite_memory"}],
                "rag": [{"source": "doc.pdf", "page": "p.1", "domain": "projects"}],
                "web": [{"title": "News", "url": "https://example.com"}],
                "mcp": [{"tool": "local.webresearch/search_web", "status": "used"}],
            }
        )
        self.assertIn("KULLANILAN KAYNAKLAR", summary)
        self.assertIn("Memory", summary)
        self.assertIn("RAG / Belgeler", summary)
        self.assertIn("Web", summary)
        self.assertIn("MCP Araçları", summary)


if __name__ == "__main__":
    unittest.main()
