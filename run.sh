#!/usr/bin/env bash
# PLC Trigger Camera — startup script for Linux / Raspberry Pi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Sync dependencies (creates .venv if needed)
uv sync

# Launch application
uv run src/main.py "$@"
