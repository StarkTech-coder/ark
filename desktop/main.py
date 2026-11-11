"""Desktop entry point for ARK local launcher."""

from __future__ import annotations

import argparse
import time

from desktop.launcher import ARKDesktopLauncher, DesktopLauncherConfig, DesktopLauncherError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch ARK as a local desktop workflow")
    parser.add_argument("--port", type=int, default=8000, help="Preferred localhost port")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open the local browser interface",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Backend readiness timeout in seconds",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    launcher = ARKDesktopLauncher(
        DesktopLauncherConfig(
            host="127.0.0.1",
            preferred_port=max(1, args.port),
            readiness_timeout_sec=max(5.0, float(args.timeout)),
            open_browser=not args.no_browser,
        )
    )

    try:
        result = launcher.start()
    except DesktopLauncherError as exc:
        print(f"[ARK DESKTOP ERROR] {exc}")
        return 1

    print(f"[ARK DESKTOP] Ready at {result.url}")
    for warning in result.warnings:
        print(f"[ARK DESKTOP WARNING] {warning}")

    try:
        while launcher.process is not None and launcher.process.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        launcher.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
