"""Bundled backend entrypoint for ARK desktop app.

Starts Chainlit server for chat_ui.py using environment-driven host/port.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from chainlit.cli import run_chainlit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ARK Chainlit backend")
    parser.add_argument("--target", required=True, help="Path to chat_ui.py")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = Path(args.target).resolve()
    if not target.exists():
        raise FileNotFoundError(f"Missing Chainlit target file: {target}")

    os.environ["CHAINLIT_HOST"] = str(args.host)
    os.environ["CHAINLIT_PORT"] = str(max(1, int(args.port)))

    run_chainlit(str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
