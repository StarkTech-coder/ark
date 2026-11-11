import os
import unittest
from unittest.mock import MagicMock, patch

from mcp_servers.github_mcp import (
    GitHubIntegrationError,
    GitHubNotConfiguredError,
    GitHubRateLimitError,
    inspect_repository_structure,
    list_commits,
    list_issues,
    list_pull_requests,
    list_repositories,
    parse_repo_reference,
    read_pull_request_diff,
    read_repository_file,
)


class GitHubMcpTests(unittest.TestCase):
    def test_missing_token_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(GitHubNotConfiguredError):
                list_repositories()

    @patch.dict(os.environ, {"ARK_GITHUB_TOKEN": "x"}, clear=True)
    @patch("mcp_servers.github_mcp.httpx.Client")
    def test_list_repositories(self, client_cls):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = [
            {
                "name": "ark",
                "full_name": "tony/ark",
                "private": True,
                "default_branch": "main",
                "updated_at": "2026-11-11T00:00:00Z",
                "html_url": "https://github.com/tony/ark",
            }
        ]
        cm = MagicMock()
        cm.__enter__.return_value.get.return_value = resp
        cm.__exit__.return_value = None
        client_cls.return_value = cm

        rows = list_repositories(limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["full_name"], "tony/ark")

    @patch.dict(os.environ, {"ARK_GITHUB_TOKEN": "x"}, clear=True)
    @patch("mcp_servers.github_mcp.httpx.Client")
    def test_read_repository_file(self, client_cls):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "path": "README.md",
            "sha": "abc",
            "size": 5,
            "html_url": "https://github.com/tony/ark/blob/main/README.md",
            "encoding": "base64",
            "content": "aGVsbG8=",
        }
        cm = MagicMock()
        cm.__enter__.return_value.get.return_value = resp
        cm.__exit__.return_value = None
        client_cls.return_value = cm

        payload = read_repository_file("tony", "ark", "README.md")
        self.assertEqual(payload["content"], "hello")

    @patch.dict(os.environ, {"ARK_GITHUB_TOKEN": "x"}, clear=True)
    @patch("mcp_servers.github_mcp.httpx.Client")
    def test_commits_issues_prs_and_diff(self, client_cls):
        commit_resp = MagicMock()
        commit_resp.status_code = 200
        commit_resp.json.return_value = [
            {
                "sha": "abcdef012345",
                "commit": {"message": "msg", "author": {"name": "A", "date": "2026"}},
                "html_url": "u",
            }
        ]

        issues_resp = MagicMock()
        issues_resp.status_code = 200
        issues_resp.json.return_value = [
            {
                "number": 1,
                "title": "bug",
                "state": "open",
                "user": {"login": "u"},
                "updated_at": "x",
                "html_url": "h",
            }
        ]

        prs_resp = MagicMock()
        prs_resp.status_code = 200
        prs_resp.json.return_value = [
            {
                "number": 2,
                "title": "pr",
                "state": "open",
                "user": {"login": "u"},
                "updated_at": "x",
                "html_url": "h",
            }
        ]

        diff_resp = MagicMock()
        diff_resp.status_code = 200
        diff_resp.text = "diff --git a/a b/a"

        cm = MagicMock()
        cm.__enter__.return_value.get.side_effect = [commit_resp, issues_resp, prs_resp, diff_resp]
        cm.__exit__.return_value = None
        client_cls.return_value = cm

        commits = list_commits("tony", "ark")
        issues = list_issues("tony", "ark")
        prs = list_pull_requests("tony", "ark")
        diff = read_pull_request_diff("tony", "ark", 2)

        self.assertEqual(commits[0]["sha"], "abcdef012345")
        self.assertEqual(issues[0]["number"], 1)
        self.assertEqual(prs[0]["number"], 2)
        self.assertIn("diff --git", diff)

    @patch.dict(os.environ, {"ARK_GITHUB_TOKEN": "x"}, clear=True)
    @patch("mcp_servers.github_mcp.httpx.Client")
    def test_rate_limit_handled(self, client_cls):
        resp = MagicMock()
        resp.status_code = 403
        resp.headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "123"}
        cm = MagicMock()
        cm.__enter__.return_value.get.return_value = resp
        cm.__exit__.return_value = None
        client_cls.return_value = cm

        with self.assertRaises(GitHubRateLimitError):
            list_repositories()

    @patch.dict(os.environ, {"ARK_GITHUB_TOKEN": "x"}, clear=True)
    @patch("mcp_servers.github_mcp.httpx.Client")
    def test_structure_reader(self, client_cls):
        repo_meta = MagicMock()
        repo_meta.status_code = 200
        repo_meta.json.return_value = {"default_branch": "main"}

        branch_meta = MagicMock()
        branch_meta.status_code = 200
        branch_meta.json.return_value = {"commit": {"sha": "abc"}}

        tree_meta = MagicMock()
        tree_meta.status_code = 200
        tree_meta.json.return_value = {
            "tree": [
                {"path": "src", "type": "tree", "sha": "1", "size": 0},
                {"path": "src/main.py", "type": "blob", "sha": "2", "size": 100},
            ]
        }

        cm = MagicMock()
        cm.__enter__.return_value.get.side_effect = [repo_meta, branch_meta, tree_meta]
        cm.__exit__.return_value = None
        client_cls.return_value = cm

        rows = inspect_repository_structure("tony", "ark")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["path"], "src/main.py")

    def test_parse_repo_reference(self):
        repos = [{"name": "ark", "full_name": "tony/ark"}]
        ref = parse_repo_reference("latest commits in tony/ark", repos)
        self.assertIsNotNone(ref)
        self.assertEqual(ref.owner, "tony")

        ref2 = parse_repo_reference("commits in ark repository", repos)
        self.assertIsNotNone(ref2)
        self.assertEqual(ref2.repo, "ark")


if __name__ == "__main__":
    unittest.main()
