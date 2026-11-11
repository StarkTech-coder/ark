import unittest
from unittest.mock import MagicMock, patch

from desktop.launcher import ARKDesktopLauncher, DesktopLauncherConfig, DesktopLauncherError


class DesktopLauncherTests(unittest.TestCase):
    def setUp(self):
        self.launcher = ARKDesktopLauncher(
            DesktopLauncherConfig(open_browser=False),
            python_executable="/usr/bin/python3",
        )

    def test_chainlit_command_is_localhost_only(self):
        cmd = self.launcher._build_chainlit_command(port=8123)  # noqa: SLF001
        self.assertIn("--host", cmd)
        self.assertIn("127.0.0.1", cmd)
        self.assertIn("--port", cmd)
        self.assertIn("8123", cmd)

    def test_port_conflict_auto_selection(self):
        with patch.object(
            self.launcher,
            "_is_port_free",
            side_effect=[False, True],
        ):
            port = self.launcher._resolve_launch_port()  # noqa: SLF001
        self.assertEqual(port, 8001)

    def test_startup_failure_raises(self):
        proc = MagicMock()
        proc.poll.return_value = None
        proc.stderr = MagicMock()
        proc.stderr.read.return_value = "bind failed"

        with patch.object(self.launcher, "_resolve_launch_port", return_value=8000), patch.object(
            self.launcher, "_probe_optional_dependencies", return_value=[]
        ), patch.object(self.launcher, "_wait_until_ready", return_value=False), patch(
            "desktop.launcher.subprocess.Popen", return_value=proc
        ):
            with self.assertRaises(DesktopLauncherError):
                self.launcher.start()

    def test_start_and_stop_lifecycle(self):
        proc = MagicMock()
        proc.poll.return_value = None

        with patch.object(self.launcher, "_resolve_launch_port", return_value=8000), patch.object(
            self.launcher, "_probe_optional_dependencies", return_value=[]
        ), patch.object(self.launcher, "_wait_until_ready", return_value=True), patch(
            "desktop.launcher.subprocess.Popen", return_value=proc
        ):
            result = self.launcher.start()

        self.assertEqual(result.url, "http://127.0.0.1:8000")
        self.launcher.stop()
        proc.terminate.assert_called_once()

    def test_non_loopback_host_rejected(self):
        with self.assertRaises(DesktopLauncherError):
            ARKDesktopLauncher(
                DesktopLauncherConfig(host="0.0.0.0", open_browser=False),
                python_executable="/usr/bin/python3",
            )

    def test_port_conflict_without_auto_select_raises(self):
        strict_launcher = ARKDesktopLauncher(
            DesktopLauncherConfig(open_browser=False, auto_select_port=False),
            python_executable="/usr/bin/python3",
        )
        with patch.object(strict_launcher, "_is_port_free", return_value=False):
            with self.assertRaises(DesktopLauncherError):
                strict_launcher._resolve_launch_port()  # noqa: SLF001

    def test_frozen_mode_uses_bundled_backend_executable(self):
        fake_executable = "/tmp/ARKDesktop.app/Contents/MacOS/ARKDesktop"
        with patch("desktop.launcher.sys.frozen", True, create=True), patch(
            "desktop.launcher.sys.executable", fake_executable
        ), patch("desktop.launcher.Path.exists", return_value=True):
            cmd = self.launcher._build_chainlit_command(port=8123)  # noqa: SLF001

        self.assertTrue(cmd[0].endswith("/ARKDesktop.app/Contents/MacOS/ARKBackend"))
        self.assertIn("--target", cmd)
        self.assertIn("--host", cmd)
        self.assertIn("127.0.0.1", cmd)
        self.assertIn("--port", cmd)
        self.assertIn("8123", cmd)


if __name__ == "__main__":
    unittest.main()
