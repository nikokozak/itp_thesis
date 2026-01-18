#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="${ROOT_DIR}/.venv/bin/python"
TUI="${ROOT_DIR}/tools/terminal/codignity_tui.py"

if [[ -x "${VENV_PY}" ]]; then
  exec "${VENV_PY}" "${TUI}" "$@"
fi

if command -v python3 >/dev/null 2>&1; then
  echo "Warning: ${VENV_PY} not found; using system python3." >&2
  exec python3 "${TUI}" "$@"
fi

echo "Error: python3 not found." >&2
echo "Create the venv:" >&2
echo "  python3 -m venv .venv && .venv/bin/python -m pip install -r tools/terminal/requirements.txt" >&2
exit 1

