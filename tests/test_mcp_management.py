import sys
import tempfile
import unittest
from pathlib import Path

from mcp_servers.management import (
    MCPAuthorizationError,
    MCPManager,
    MCPServerSpec,
    MCPToolSpec,
    PermissionLevel,
    ServerKind,
)


class MCPManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "mcp_test.db"
        self.manager = MCPManager(db_path=self.db_path)
        self.manager.bootstrap_defaults()

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_registry_and_tool_discovery(self):
        servers = self.manager.list_servers()
        server_ids = {item["server_id"] for item in servers}
        self.assertIn("local.filesystem", server_ids)
        self.assertIn("local.router", server_ids)
        self.assertIn("local.lancedb", server_ids)
        self.assertIn("local.system", server_ids)
        self.assertIn("local.webresearch", server_ids)
        self.assertIn("local.github", server_ids)
        self.assertTrue(all(item["kind"] == "local" for item in servers))
        self.assertTrue(all(item["is_protocol"] is False for item in servers))

        tools = self.manager.list_tools(server_id="local.lancedb")
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["tool_name"], "process_and_store_document")
        self.assertEqual(tools[0]["required_permission"], PermissionLevel.write.value)

        github_tools = self.manager.list_tools(server_id="local.github")
        github_tool_names = {tool["tool_name"] for tool in github_tools}
        self.assertIn("list_repositories", github_tool_names)
        self.assertIn("read_repository_file", github_tool_names)
        self.assertIn("list_commits", github_tool_names)
        self.assertIn("list_issues", github_tool_names)
        self.assertIn("list_pull_requests", github_tool_names)
        self.assertIn("read_pull_request_diff", github_tool_names)
        self.assertTrue(all(tool["required_permission"] == PermissionLevel.read.value for tool in github_tools))

    def test_permission_enforcement_blocks_disabled_access(self):
        self.manager.set_permission(
            session_id="s1",
            user_id="u1",
            server_id="local.lancedb",
            tool_name="process_and_store_document",
            permission_level=PermissionLevel.disabled,
        )

        result = self.manager.authorize_tool_execution(
            session_id="s1",
            user_id="u1",
            server_id="local.lancedb",
            tool_name="process_and_store_document",
            confirmed=True,
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "insufficient_permission")

    def test_sensitive_action_requires_confirmation(self):
        result_without_confirmation = self.manager.authorize_tool_execution(
            session_id="s1",
            user_id="u1",
            server_id="local.system",
            tool_name="execute_command",
            confirmed=False,
        )
        self.assertFalse(result_without_confirmation.allowed)
        self.assertEqual(result_without_confirmation.reason, "confirmation_required")

        result_with_confirmation = self.manager.authorize_tool_execution(
            session_id="s1",
            user_id="u1",
            server_id="local.system",
            tool_name="execute_command",
            confirmed=True,
        )
        self.assertTrue(result_with_confirmation.allowed)

        web_index_without_confirmation = self.manager.authorize_tool_execution(
            session_id="s1",
            user_id="u1",
            server_id="local.webresearch",
            tool_name="index_web_source",
            confirmed=False,
        )
        self.assertFalse(web_index_without_confirmation.allowed)
        self.assertEqual(web_index_without_confirmation.reason, "confirmation_required")

    def test_admin_permission_assignment_requires_confirmation(self):
        with self.assertRaises(MCPAuthorizationError):
            self.manager.set_permission(
                session_id="s1",
                user_id="u1",
                server_id="local.filesystem",
                tool_name="scan_documents_directory",
                permission_level=PermissionLevel.admin,
                confirmed=False,
            )

        self.manager.set_permission(
            session_id="s1",
            user_id="u1",
            server_id="local.filesystem",
            tool_name="scan_documents_directory",
            permission_level=PermissionLevel.admin,
            confirmed=True,
        )

    def test_session_isolation_and_cleanup(self):
        self.manager.set_permission(
            session_id="session-a",
            user_id="u1",
            server_id="local.lancedb",
            tool_name="process_and_store_document",
            permission_level=PermissionLevel.disabled,
        )

        denied = self.manager.authorize_tool_execution(
            session_id="session-a",
            user_id="u1",
            server_id="local.lancedb",
            tool_name="process_and_store_document",
            confirmed=True,
        )
        self.assertFalse(denied.allowed)

        allowed_other_session = self.manager.authorize_tool_execution(
            session_id="session-b",
            user_id="u1",
            server_id="local.lancedb",
            tool_name="process_and_store_document",
            confirmed=True,
        )
        self.assertTrue(allowed_other_session.allowed)

        deleted_rows = self.manager.cleanup_session("session-a")
        self.assertGreaterEqual(deleted_rows, 1)

        allowed_after_cleanup = self.manager.authorize_tool_execution(
            session_id="session-a",
            user_id="u1",
            server_id="local.lancedb",
            tool_name="process_and_store_document",
            confirmed=True,
        )
        self.assertTrue(allowed_after_cleanup.allowed)

    def test_protocol_server_lifecycle_start_stop(self):
        self.manager.register_server(
            MCPServerSpec(
                server_id="protocol.test",
                display_name="Protocol Test",
                description="Test protocol-backed MCP server process",
                kind=ServerKind.protocol,
                command=[sys.executable, "-c", "import time; time.sleep(2)"],
            )
        )
        self.manager.register_tool(
            MCPToolSpec(
                server_id="protocol.test",
                tool_name="ping",
                description="Health check",
                required_permission=PermissionLevel.read,
            )
        )

        started = self.manager.start_server("protocol.test")
        self.assertEqual(started["status"], "running")
        self.assertTrue(started["is_protocol"])

        stopped = self.manager.stop_server("protocol.test")
        self.assertEqual(stopped["status"], "stopped")

    def test_audit_logs_capture_authorization_events(self):
        self.manager.authorize_tool_execution(
            session_id="s-audit",
            user_id="u-audit",
            server_id="local.filesystem",
            tool_name="scan_documents_directory",
            confirmed=True,
        )
        logs = self.manager.get_audit_logs(limit=20)
        self.assertGreaterEqual(len(logs), 1)
        self.assertIn("decision", logs[0])
        self.assertIn("action", logs[0])


if __name__ == "__main__":
    unittest.main()
