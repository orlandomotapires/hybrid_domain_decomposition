#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/ocean/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
	echo "Missing repo-local Python environment at $PYTHON_BIN" >&2
	exit 1
fi

exec "$PYTHON_BIN" "$ROOT_DIR/qlm_inspect.py" "$@"