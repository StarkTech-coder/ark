#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SPEC_FILE="$ROOT_DIR/desktop/ARKDesktop.spec"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"

if [[ "${1:-}" == "--check" ]]; then
  if ! command -v pyinstaller >/dev/null 2>&1; then
    echo "[ARK DESKTOP] pyinstaller not found. Install with: pip install pyinstaller"
    exit 1
  fi
  echo "[ARK DESKTOP] Build prerequisites look available."
  exit 0
fi

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "[ARK DESKTOP] pyinstaller not found. Install with: pip install pyinstaller"
  exit 1
fi

rm -rf "$BUILD_DIR/ARKDesktop" "$DIST_DIR/ARKDesktop" "$DIST_DIR/ARKDesktop.app"

cd "$ROOT_DIR"
pyinstaller --noconfirm "$SPEC_FILE"

echo "[ARK DESKTOP] Build complete: $DIST_DIR/ARKDesktop.app"
