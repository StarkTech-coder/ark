"""Read-only GitHub integration helpers for ARK MCP workflows."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx


class GitHubIntegrationError(RuntimeError):
    """Base GitHub integration error."""


class GitHubNotConfiguredError(GitHubIntegrationError):
    """Raised when GitHub token is missing."""


class GitHubRateLimitError(GitHubIntegrationError):
    """Raised on GitHub API rate limit exhaustion."""


@dataclass(frozen=True)
class GitHubRepoRef:
    owner: str
    repo: str


def _github_token() -> str:
    token = os.getenv("ARK_GITHUB_TOKEN", "").strip()
    if token:
        return token
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        return token
    raise GitHubNotConfiguredError(
        "GitHub integration is not configured. Set ARK_GITHUB_TOKEN or GITHUB_TOKEN."
    )


def _build_headers(*, token: str, accept: str = "application/vnd.github+json") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ARK-GitHub-ReadOnly-Client",
    }


def _raise_for_github_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return

    remaining = response.headers.get("X-RateLimit-Remaining", "")
    if response.status_code == 403 and remaining == "0":
        reset_at = response.headers.get("X-RateLimit-Reset", "")
        raise GitHubRateLimitError(
            f"GitHub API rate limit exceeded. Reset: {reset_at or 'unknown'}"
        )

    if response.status_code in {401, 403}:
        raise GitHubIntegrationError("GitHub API authorization failed.")
    if response.status_code == 404:
        raise GitHubIntegrationError("GitHub resource not found or inaccessible.")

    try:
        payload = response.json()
        message = str(payload.get("message", "GitHub API request failed"))
    except Exception:
        message = f"GitHub API request failed with status {response.status_code}"
    raise GitHubIntegrationError(message)


def _get_json(path: str, *, params: dict[str, Any] | None = None) -> Any:
    token = _github_token()
    url = f"https://api.github.com{path}"
    with httpx.Client(timeout=12.0) as client:
        response = client.get(url, headers=_build_headers(token=token), params=params)
    _raise_for_github_error(response)
    return response.json()


def list_repositories(*, limit: int = 20) -> list[dict[str, Any]]:
    data = _get_json("/user/repos", params={"sort": "updated", "per_page": max(1, min(limit, 100))})
    rows: list[dict[str, Any]] = []
    for item in data if isinstance(data, list) else []:
        rows.append(
            {
                "name": item.get("name", ""),
                "full_name": item.get("full_name", ""),
                "private": bool(item.get("private", False)),
                "default_branch": item.get("default_branch", "main"),
                "updated_at": item.get("updated_at", ""),
                "html_url": item.get("html_url", ""),
            }
        )
    return rows


def list_commits(owner: str, repo: str, *, limit: int = 10) -> list[dict[str, Any]]:
    data = _get_json(
        f"/repos/{owner}/{repo}/commits",
        params={"per_page": max(1, min(limit, 100))},
    )
    rows: list[dict[str, Any]] = []
    for item in data if isinstance(data, list) else []:
        commit = item.get("commit", {}) or {}
        author = commit.get("author", {}) or {}
        rows.append(
            {
                "sha": item.get("sha", ""),
                "message": commit.get("message", ""),
                "author": author.get("name", ""),
                "date": author.get("date", ""),
                "url": item.get("html_url", ""),
            }
        )
    return rows


def list_issues(owner: str, repo: str, *, state: str = "open", limit: int = 10) -> list[dict[str, Any]]:
    data = _get_json(
        f"/repos/{owner}/{repo}/issues",
        params={"state": state, "per_page": max(1, min(limit, 100))},
    )
    rows: list[dict[str, Any]] = []
    for item in data if isinstance(data, list) else []:
        if item.get("pull_request"):
            continue
        rows.append(
            {
                "number": item.get("number"),
                "title": item.get("title", ""),
                "state": item.get("state", ""),
                "user": (item.get("user", {}) or {}).get("login", ""),
                "updated_at": item.get("updated_at", ""),
                "url": item.get("html_url", ""),
            }
        )
    return rows


def list_pull_requests(owner: str, repo: str, *, state: str = "open", limit: int = 10) -> list[dict[str, Any]]:
    data = _get_json(
        f"/repos/{owner}/{repo}/pulls",
        params={"state": state, "per_page": max(1, min(limit, 100))},
    )
    rows: list[dict[str, Any]] = []
    for item in data if isinstance(data, list) else []:
        rows.append(
            {
                "number": item.get("number"),
                "title": item.get("title", ""),
                "state": item.get("state", ""),
                "user": (item.get("user", {}) or {}).get("login", ""),
                "updated_at": item.get("updated_at", ""),
                "url": item.get("html_url", ""),
            }
        )
    return rows


def read_pull_request_diff(owner: str, repo: str, pr_number: int) -> str:
    token = _github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{int(pr_number)}"
    with httpx.Client(timeout=12.0) as client:
        response = client.get(
            url,
            headers=_build_headers(token=token, accept="application/vnd.github.v3.diff"),
        )
    _raise_for_github_error(response)
    return response.text


def read_repository_file(owner: str, repo: str, file_path: str, *, ref: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if ref:
        params["ref"] = ref
    data = _get_json(f"/repos/{owner}/{repo}/contents/{file_path.lstrip('/')}", params=params)
    if isinstance(data, list):
        raise GitHubIntegrationError("Path points to a directory, not a file.")

    encoded = str(data.get("content", ""))
    if data.get("encoding") == "base64":
        decoded = base64.b64decode(encoded.encode("utf-8"), validate=False).decode(
            "utf-8", errors="replace"
        )
    else:
        decoded = encoded

    return {
        "path": data.get("path", file_path),
        "sha": data.get("sha", ""),
        "size": data.get("size", 0),
        "url": data.get("html_url", ""),
        "content": decoded,
    }


def inspect_repository_structure(owner: str, repo: str, *, branch: str | None = None, max_entries: int = 500) -> list[dict[str, Any]]:
    repo_meta = _get_json(f"/repos/{owner}/{repo}")
    default_branch = branch or str(repo_meta.get("default_branch", "main"))
    branch_meta = _get_json(f"/repos/{owner}/{repo}/branches/{default_branch}")
    tree_sha = ((branch_meta.get("commit", {}) or {}).get("sha", ""))
    if not tree_sha:
        raise GitHubIntegrationError("Repository default branch commit could not be resolved.")

    tree = _get_json(f"/repos/{owner}/{repo}/git/trees/{tree_sha}", params={"recursive": 1})
    entries = tree.get("tree", []) if isinstance(tree, dict) else []
    rows: list[dict[str, Any]] = []
    for item in entries[: max(1, min(max_entries, 5000))]:
        rows.append(
            {
                "path": item.get("path", ""),
                "type": item.get("type", ""),
                "size": item.get("size", 0),
                "sha": item.get("sha", ""),
            }
        )
    return rows


def parse_repo_reference(text: str, repos: list[dict[str, Any]]) -> GitHubRepoRef | None:
    raw = (text or "").strip()
    for token in raw.replace("\n", " ").split():
        candidate = token.strip().strip(".,:;()[]{}")
        if "/" in candidate and candidate.count("/") == 1:
            owner, repo = candidate.split("/", 1)
            if owner and repo:
                return GitHubRepoRef(owner=owner, repo=repo)

    lowered = raw.lower()
    for repo in repos:
        name = str(repo.get("name", "")).lower()
        full_name = str(repo.get("full_name", "")).lower()
        if name and name in lowered:
            owner, rname = str(repo.get("full_name", "")).split("/", 1)
            return GitHubRepoRef(owner=owner, repo=rname)
        if full_name and full_name in lowered:
            owner, rname = str(repo.get("full_name", "")).split("/", 1)
            return GitHubRepoRef(owner=owner, repo=rname)
    return None
