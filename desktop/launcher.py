"""Lightweight desktop launcher for local ARK Chainlit runtime on macOS."""

from __future__ import annotations

import atexit
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import httpx

from runtime.paths import get_runtime_paths


class DesktopLauncherError(RuntimeError):
    """Raised when ARK desktop launcher startup fails."""


@dataclass(frozen=True)
class DesktopLaunchResult:
    host: str
    port: int
    url: str
    warnings: list[str]


@dataclass
class DesktopLauncherConfig:
    host: str = "127.0.0.1"
    preferred_port: int = 8000
    readiness_timeout_sec: float = 45.0
    auto_select_port: bool = True
    open_browser: bool = True


class ARKDesktopLauncher:
    """Starts/stops Chainlit backend safely for desktop usage."""

    def __init__(
        self,
        config: DesktopLauncherConfig | None = None,
        *,
        python_executable: str | None = None,
    ):
        self.config = config or DesktopLauncherConfig()
        self._assert_loopback_host(self.config.host)
        self.paths = get_runtime_paths()
        self.python_executable = python_executable or sys.executable
        self._process: subprocess.Popen[str] | None = None
        self._selected_port: int | None = None

    @property
    def process(self) -> subprocess.Popen[str] | None:
        return self._process

    @property
    def selected_port(self) -> int | None:
        return self._selected_port

    @property
    def app_url(self) -> str:
        port = self._selected_port or self.config.preferred_port
        return f"http://{self.config.host}:{port}"

    def start(self) -> DesktopLaunchResult:
        if self._process is not None and self._process.poll() is None:
            raise DesktopLauncherError("Launcher is already running")

        warnings = self._probe_optional_dependencies()
        port = self._resolve_launch_port()
        self._selected_port = port

        cmd = self._build_chainlit_command(port=port)
        env = self._build_env()

        self._process = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=str(self.paths.project_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if not self._wait_until_ready(port=port):
            stderr_output = ""
            if self._process is not None and self._process.stderr is not None:
                try:
                    stderr_output = self._process.stderr.read()[-4000:]
                except Exception:
                    stderr_output = ""
            self.stop()
            raise DesktopLauncherError(
                "ARK backend failed to become ready on localhost. "
                f"Last stderr output: {stderr_output.strip() or 'n/a'}"
            )

        url = f"http://{self.config.host}:{port}"
        if self.config.open_browser:
            webbrowser.open(url)

        self._register_shutdown_hooks()
        return DesktopLaunchResult(
            host=self.config.host,
            port=port,
            url=url,
            warnings=warnings,
        )

    def stop(self) -> None:
        proc = self._process
        if proc is None:
            return

        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

        self._process = None

    def _resolve_launch_port(self) -> int:
        preferred = int(self.config.preferred_port)
        if self._is_port_free(preferred):
            return preferred

        if not self.config.auto_select_port:
            raise DesktopLauncherError(
                f"Preferred port {preferred} is already in use."
            )

        for candidate in self._candidate_ports(preferred + 1, preferred + 30):
            if self._is_port_free(candidate):
                return candidate

        raise DesktopLauncherError("No available localhost port found for ARK launcher")

    def _build_chainlit_command(self, *, port: int) -> list[str]:
        app_file = self.paths.project_root / "chat_ui.py"
        if not app_file.exists():
            raise DesktopLauncherError(f"Missing app entry file: {app_file}")

        if getattr(sys, "frozen", False):
            backend_exec = Path(sys.executable).resolve().parent / "ARKBackend"
            if not backend_exec.exists():
                raise DesktopLauncherError(
                    f"Missing bundled backend executable: {backend_exec}"
                )
            return [
                str(backend_exec),
                "--target",
                str(app_file),
                "--host",
                self.config.host,
                "--port",
                str(port),
            ]

        return [
            self.python_executable,
            "-m",
            "chainlit",
            "run",
            str(app_file),
            "--host",
            self.config.host,
            "--port",
            str(port),
            "--headless",
        ]

    def _build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("CHAINLIT_APP_ROOT", str(self.paths.project_root))
        env.setdefault("ARK_PROJECT_ROOT", str(self.paths.project_root))
        return env

    def _wait_until_ready(self, *, port: int) -> bool:
        deadline = time.time() + max(5.0, self.config.readiness_timeout_sec)
        target = f"http://{self.config.host}:{port}"

        while time.time() < deadline:
            if self._process is None:
                return False
            if self._process.poll() is not None:
                return False

            try:
                response = httpx.get(target, timeout=2.0)
                if response.status_code < 500:
                    return True
            except Exception:
                pass

            time.sleep(0.5)

        return False

    def _probe_optional_dependencies(self) -> list[str]:
        warnings: list[str] = []

        try:
            response = httpx.get("http://127.0.0.1:11434/api/tags", timeout=2.0)
            if response.status_code != 200:
                warnings.append("Ollama is reachable but returned a non-200 status")
        except Exception:
            warnings.append(
                "Ollama runtime is not reachable at http://127.0.0.1:11434. "
                "ARK will start, but model responses may fail until Ollama is running."
            )

        return warnings

    def _register_shutdown_hooks(self) -> None:
        atexit.register(self.stop)

        def _handle_signal(signum: int, _frame: object) -> None:  # pragma: no cover
            self.stop()
            raise SystemExit(0)

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, _handle_signal)
            except Exception:
                continue

    def _is_port_free(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return sock.connect_ex((self.config.host, port)) != 0

    def _candidate_ports(self, start: int, end: int) -> Iterable[int]:
        for value in range(start, end + 1):
            yield value

    @staticmethod
    def _assert_loopback_host(host: str) -> None:
        normalized = (host or "").strip().lower()
        if normalized not in {"127.0.0.1", "localhost", "::1"}:
            raise DesktopLauncherError(
                "Desktop launcher host must be loopback-only (127.0.0.1/localhost/::1)."
            )
