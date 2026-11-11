"""MCP server registry, lifecycle, and permission enforcement for ARK."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from memory.connection import DatabaseManager
from memory.migrations import apply_migrations


class PermissionLevel(str, Enum):
    disabled = "disabled"
    read = "read"
    write = "write"
    admin = "admin"


class ServerKind(str, Enum):
    local = "local"
    protocol = "protocol"


class MCPError(RuntimeError):
    """Base MCP management exception."""


class MCPNotFoundError(MCPError):
    """Raised when an MCP server or tool does not exist."""


class MCPAuthorizationError(MCPError):
    """Raised when a sensitive authorization requirement fails."""


@dataclass(frozen=True)
class MCPToolSpec:
    server_id: str
    tool_name: str
    description: str
    required_permission: PermissionLevel = PermissionLevel.read
    is_sensitive: bool = False


@dataclass(frozen=True)
class MCPServerSpec:
    server_id: str
    display_name: str
    description: str
    kind: ServerKind
    enabled: bool = True
    command: list[str] | None = None
    env: dict[str, str] | None = None


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    reason: str
    required_permission: PermissionLevel
    granted_permission: PermissionLevel
    requires_confirmation: bool


_PERMISSION_RANK = {
    PermissionLevel.disabled: 0,
    PermissionLevel.read: 1,
    PermissionLevel.write: 2,
    PermissionLevel.admin: 3,
}


class MCPManager:
    """Registry, lifecycle manager, and authorization engine for MCP tools."""

    def __init__(self, db_path: str | Path | None = None):
        self.db = DatabaseManager(db_path=db_path)
        apply_migrations(self.db)
        self._processes: dict[str, subprocess.Popen[Any]] = {}

    def bootstrap_defaults(self) -> None:
        self.register_server(
            MCPServerSpec(
                server_id="local.filesystem",
                display_name="Local Filesystem Tools",
                description="Local read-only document discovery and file parsing helpers.",
                kind=ServerKind.local,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.filesystem",
                tool_name="scan_documents_directory",
                description="List ingestible files from ARK documents folders.",
                required_permission=PermissionLevel.read,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.filesystem",
                tool_name="read_document_content",
                description="Read local document content for indexing workflows.",
                required_permission=PermissionLevel.read,
            )
        )

        self.register_server(
            MCPServerSpec(
                server_id="local.router",
                display_name="Local Routing Tools",
                description="Local LLM-assisted intent and document routing helpers.",
                kind=ServerKind.local,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.router",
                tool_name="classify_document",
                description="Classify a document into relationship/university/code domain.",
                required_permission=PermissionLevel.read,
            )
        )

        self.register_server(
            MCPServerSpec(
                server_id="local.lancedb",
                display_name="Local LanceDB Tools",
                description="Local vector indexing and storage tools.",
                kind=ServerKind.local,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.lancedb",
                tool_name="process_and_store_document",
                description="Chunk and persist document embeddings into LanceDB.",
                required_permission=PermissionLevel.write,
            )
        )

        self.register_server(
            MCPServerSpec(
                server_id="local.system",
                display_name="Local System Tools",
                description="Local command-dispatching automation bridge.",
                kind=ServerKind.local,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.system",
                tool_name="execute_command",
                description="Execute mapped ARK automation commands.",
                required_permission=PermissionLevel.admin,
                is_sensitive=True,
            )
        )

        self.register_server(
            MCPServerSpec(
                server_id="local.webresearch",
                display_name="Local Web Research Tools",
                description="Secure web search, source extraction, and optional RAG indexing tools.",
                kind=ServerKind.local,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.webresearch",
                tool_name="search_web",
                description="Perform safe multi-source web search discovery.",
                required_permission=PermissionLevel.read,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.webresearch",
                tool_name="read_web_source",
                description="Fetch and sanitize web source content safely.",
                required_permission=PermissionLevel.read,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.webresearch",
                tool_name="index_web_source",
                description="Index selected web research sources into RAG with metadata.",
                required_permission=PermissionLevel.write,
                is_sensitive=True,
            )
        )

        self.register_server(
            MCPServerSpec(
                server_id="local.github",
                display_name="Local GitHub Read-Only Tools",
                description="Read-only GitHub repository inspection, commits, issues, and PR analysis.",
                kind=ServerKind.local,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.github",
                tool_name="list_repositories",
                description="List repositories accessible to the authenticated GitHub user.",
                required_permission=PermissionLevel.read,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.github",
                tool_name="inspect_repository_structure",
                description="Read repository file/folder structure metadata.",
                required_permission=PermissionLevel.read,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.github",
                tool_name="read_repository_file",
                description="Read source file content from a repository path.",
                required_permission=PermissionLevel.read,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.github",
                tool_name="list_commits",
                description="List repository commit history.",
                required_permission=PermissionLevel.read,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.github",
                tool_name="list_issues",
                description="List repository issues.",
                required_permission=PermissionLevel.read,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.github",
                tool_name="list_pull_requests",
                description="List repository pull requests.",
                required_permission=PermissionLevel.read,
            )
        )
        self.register_tool(
            MCPToolSpec(
                server_id="local.github",
                tool_name="read_pull_request_diff",
                description="Read unified diff text for a pull request.",
                required_permission=PermissionLevel.read,
            )
        )

    def register_server(self, server: MCPServerSpec) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO mcp_servers(
                    server_id, display_name, description, kind, enabled,
                    command_json, env_json, last_status, last_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'stopped', '')
                ON CONFLICT(server_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    description = excluded.description,
                    kind = excluded.kind,
                    enabled = excluded.enabled,
                    command_json = excluded.command_json,
                    env_json = excluded.env_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    server.server_id,
                    server.display_name,
                    server.description,
                    server.kind.value,
                    1 if server.enabled else 0,
                    json.dumps(server.command or [], ensure_ascii=False),
                    json.dumps(server.env or {}, ensure_ascii=False),
                ),
            )

    def register_tool(self, tool: MCPToolSpec) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO mcp_tools(
                    server_id, tool_name, description,
                    required_permission, is_sensitive
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(server_id, tool_name) DO UPDATE SET
                    description = excluded.description,
                    required_permission = excluded.required_permission,
                    is_sensitive = excluded.is_sensitive,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    tool.server_id,
                    tool.tool_name,
                    tool.description,
                    tool.required_permission.value,
                    1 if tool.is_sensitive else 0,
                ),
            )

    def list_servers(self) -> list[dict[str, Any]]:
        with self.db.read_only() as conn:
            rows = conn.execute(
                """
                SELECT server_id, display_name, description, kind, enabled,
                       command_json, env_json, last_status, last_error,
                       created_at, updated_at
                FROM mcp_servers
                ORDER BY server_id ASC
                """
            ).fetchall()
        payload: list[dict[str, Any]] = []
        for row in rows:
            payload.append(
                {
                    "server_id": row["server_id"],
                    "display_name": row["display_name"],
                    "description": row["description"],
                    "kind": row["kind"],
                    "is_protocol": row["kind"] == ServerKind.protocol.value,
                    "enabled": bool(row["enabled"]),
                    "command": json.loads(row["command_json"] or "[]"),
                    "env": json.loads(row["env_json"] or "{}"),
                    "last_status": row["last_status"],
                    "last_error": row["last_error"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return payload

    def list_tools(self, server_id: str | None = None) -> list[dict[str, Any]]:
        query = (
            """
            SELECT t.server_id, t.tool_name, t.description,
                   t.required_permission, t.is_sensitive,
                   s.kind AS server_kind, s.enabled AS server_enabled
            FROM mcp_tools t
            JOIN mcp_servers s ON s.server_id = t.server_id
            """
        )
        args: tuple[Any, ...] = ()
        if server_id:
            query += " WHERE t.server_id = ?"
            args = (server_id,)
        query += " ORDER BY t.server_id ASC, t.tool_name ASC"

        with self.db.read_only() as conn:
            rows = conn.execute(query, args).fetchall()

        return [
            {
                "server_id": row["server_id"],
                "tool_name": row["tool_name"],
                "description": row["description"],
                "required_permission": row["required_permission"],
                "is_sensitive": bool(row["is_sensitive"]),
                "server_kind": row["server_kind"],
                "server_enabled": bool(row["server_enabled"]),
            }
            for row in rows
        ]

    def set_server_enabled(self, server_id: str, enabled: bool) -> None:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT 1 FROM mcp_servers WHERE server_id = ?", (server_id,)
            ).fetchone()
            if row is None:
                raise MCPNotFoundError(f"Unknown server: {server_id}")
            conn.execute(
                "UPDATE mcp_servers SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE server_id = ?",
                (1 if enabled else 0, server_id),
            )

    def set_permission(
        self,
        *,
        session_id: str,
        user_id: str,
        server_id: str,
        tool_name: str,
        permission_level: PermissionLevel,
        confirmed: bool = False,
    ) -> None:
        if permission_level == PermissionLevel.admin and not confirmed:
            raise MCPAuthorizationError(
                "Admin permission assignment requires explicit confirmation"
            )

        with self.db.transaction() as conn:
            self._assert_tool_exists(conn, server_id=server_id, tool_name=tool_name)
            conn.execute(
                """
                INSERT INTO mcp_permissions(
                    session_id, user_id, server_id, tool_name, permission_level
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, user_id, server_id, tool_name) DO UPDATE SET
                    permission_level = excluded.permission_level,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    session_id,
                    user_id,
                    server_id,
                    tool_name,
                    permission_level.value,
                ),
            )

        self._log_audit(
            session_id=session_id,
            user_id=user_id,
            server_id=server_id,
            tool_name=tool_name,
            action="set_permission",
            decision="allowed",
            reason=f"permission set to {permission_level.value}",
            metadata={"permission_level": permission_level.value},
        )

    def cleanup_session(self, session_id: str) -> int:
        with self.db.transaction() as conn:
            result = conn.execute(
                "DELETE FROM mcp_permissions WHERE session_id = ?",
                (session_id,),
            )
            deleted = int(result.rowcount or 0)
        self._log_audit(
            session_id=session_id,
            user_id="system",
            server_id="*",
            tool_name="*",
            action="cleanup_session",
            decision="allowed",
            reason=f"removed {deleted} session permission rows",
            metadata={"deleted_permissions": deleted},
        )
        return deleted

    def get_audit_logs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 1000))
        with self.db.read_only() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, user_id, server_id, tool_name,
                       action, decision, reason, metadata_json, created_at
                FROM mcp_audit_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "user_id": row["user_id"],
                "server_id": row["server_id"],
                "tool_name": row["tool_name"],
                "action": row["action"],
                "decision": row["decision"],
                "reason": row["reason"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def authorize_tool_execution(
        self,
        *,
        session_id: str,
        user_id: str,
        server_id: str,
        tool_name: str,
        confirmed: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> AuthorizationResult:
        with self.db.read_only() as conn:
            tool_row = conn.execute(
                """
                SELECT t.required_permission, t.is_sensitive,
                       s.enabled, s.kind
                FROM mcp_tools t
                JOIN mcp_servers s ON s.server_id = t.server_id
                WHERE t.server_id = ? AND t.tool_name = ?
                """,
                (server_id, tool_name),
            ).fetchone()
            if tool_row is None:
                raise MCPNotFoundError(f"Unknown tool: {server_id}/{tool_name}")

            grant_row = conn.execute(
                """
                SELECT permission_level
                FROM mcp_permissions
                WHERE session_id = ? AND user_id = ? AND server_id = ? AND tool_name = ?
                """,
                (session_id, user_id, server_id, tool_name),
            ).fetchone()

        required = PermissionLevel(tool_row["required_permission"])
        granted = (
            PermissionLevel(grant_row["permission_level"])
            if grant_row is not None
            else PermissionLevel.admin
        )

        if not bool(tool_row["enabled"]):
            result = AuthorizationResult(
                allowed=False,
                reason="server_disabled",
                required_permission=required,
                granted_permission=granted,
                requires_confirmation=False,
            )
            self._log_authorization(
                session_id=session_id,
                user_id=user_id,
                server_id=server_id,
                tool_name=tool_name,
                result=result,
                metadata=metadata,
            )
            return result

        if _PERMISSION_RANK[granted] < _PERMISSION_RANK[required]:
            result = AuthorizationResult(
                allowed=False,
                reason="insufficient_permission",
                required_permission=required,
                granted_permission=granted,
                requires_confirmation=False,
            )
            self._log_authorization(
                session_id=session_id,
                user_id=user_id,
                server_id=server_id,
                tool_name=tool_name,
                result=result,
                metadata=metadata,
            )
            return result

        is_sensitive = bool(tool_row["is_sensitive"])
        if is_sensitive and not confirmed:
            result = AuthorizationResult(
                allowed=False,
                reason="confirmation_required",
                required_permission=required,
                granted_permission=granted,
                requires_confirmation=True,
            )
            self._log_authorization(
                session_id=session_id,
                user_id=user_id,
                server_id=server_id,
                tool_name=tool_name,
                result=result,
                metadata=metadata,
            )
            return result

        result = AuthorizationResult(
            allowed=True,
            reason="authorized",
            required_permission=required,
            granted_permission=granted,
            requires_confirmation=False,
        )
        self._log_authorization(
            session_id=session_id,
            user_id=user_id,
            server_id=server_id,
            tool_name=tool_name,
            result=result,
            metadata=metadata,
        )
        return result

    def start_server(self, server_id: str) -> dict[str, Any]:
        server = self._get_server(server_id)
        if not server["enabled"]:
            self._set_server_status(server_id, status="stopped", error="server disabled")
            return self._server_status_payload(server_id)

        if server["kind"] == ServerKind.local.value:
            self._set_server_status(server_id, status="running", error="")
            return self._server_status_payload(server_id)

        command = server["command"]
        if not command:
            self._set_server_status(server_id, status="error", error="protocol command missing")
            return self._server_status_payload(server_id)

        if server_id in self._processes:
            proc = self._processes[server_id]
            if proc.poll() is None:
                self._set_server_status(server_id, status="running", error="")
                return self._server_status_payload(server_id)

        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, **server["env"]},
            )
            self._processes[server_id] = proc
            self._set_server_status(server_id, status="running", error="")
        except Exception as exc:
            self._set_server_status(server_id, status="error", error=str(exc))

        return self._server_status_payload(server_id)

    def stop_server(self, server_id: str) -> dict[str, Any]:
        server = self._get_server(server_id)
        if server["kind"] == ServerKind.local.value:
            self._set_server_status(server_id, status="stopped", error="")
            return self._server_status_payload(server_id)

        proc = self._processes.pop(server_id, None)
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        self._set_server_status(server_id, status="stopped", error="")
        return self._server_status_payload(server_id)

    def reconnect_server(self, server_id: str) -> dict[str, Any]:
        self.stop_server(server_id)
        return self.start_server(server_id)

    def _get_server(self, server_id: str) -> dict[str, Any]:
        with self.db.read_only() as conn:
            row = conn.execute(
                """
                SELECT server_id, display_name, kind, enabled,
                       command_json, env_json, last_status, last_error
                FROM mcp_servers
                WHERE server_id = ?
                """,
                (server_id,),
            ).fetchone()
        if row is None:
            raise MCPNotFoundError(f"Unknown server: {server_id}")
        return {
            "server_id": row["server_id"],
            "display_name": row["display_name"],
            "kind": row["kind"],
            "enabled": bool(row["enabled"]),
            "command": json.loads(row["command_json"] or "[]"),
            "env": json.loads(row["env_json"] or "{}"),
            "last_status": row["last_status"],
            "last_error": row["last_error"],
        }

    def _server_status_payload(self, server_id: str) -> dict[str, Any]:
        server = self._get_server(server_id)
        return {
            "server_id": server["server_id"],
            "display_name": server["display_name"],
            "kind": server["kind"],
            "is_protocol": server["kind"] == ServerKind.protocol.value,
            "enabled": server["enabled"],
            "status": server["last_status"],
            "error": server["last_error"],
        }

    def _set_server_status(self, server_id: str, *, status: str, error: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE mcp_servers
                SET last_status = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE server_id = ?
                """,
                (status, error, server_id),
            )

    def _assert_tool_exists(self, conn: Any, *, server_id: str, tool_name: str) -> None:
        row = conn.execute(
            "SELECT 1 FROM mcp_tools WHERE server_id = ? AND tool_name = ?",
            (server_id, tool_name),
        ).fetchone()
        if row is None:
            raise MCPNotFoundError(f"Unknown tool: {server_id}/{tool_name}")

    def _log_authorization(
        self,
        *,
        session_id: str,
        user_id: str,
        server_id: str,
        tool_name: str,
        result: AuthorizationResult,
        metadata: dict[str, Any] | None,
    ) -> None:
        self._log_audit(
            session_id=session_id,
            user_id=user_id,
            server_id=server_id,
            tool_name=tool_name,
            action="authorize",
            decision="allowed" if result.allowed else "denied",
            reason=result.reason,
            metadata={
                "required_permission": result.required_permission.value,
                "granted_permission": result.granted_permission.value,
                "requires_confirmation": result.requires_confirmation,
                **(metadata or {}),
            },
        )

    def _log_audit(
        self,
        *,
        session_id: str,
        user_id: str,
        server_id: str,
        tool_name: str,
        action: str,
        decision: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO mcp_audit_logs(
                    session_id, user_id, server_id, tool_name,
                    action, decision, reason, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    server_id,
                    tool_name,
                    action,
                    decision,
                    reason,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )


__all__ = [
    "AuthorizationResult",
    "MCPAuthorizationError",
    "MCPError",
    "MCPManager",
    "MCPNotFoundError",
    "MCPServerSpec",
    "MCPToolSpec",
    "PermissionLevel",
    "ServerKind",
]
