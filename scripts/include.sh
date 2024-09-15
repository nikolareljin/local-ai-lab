#!/usr/bin/env bash
# SCRIPT: include.sh
# DESCRIPTION: Load shared script-helpers modules, with a safe fallback when the
#              submodule has not been fetched yet (e.g. before ./update).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_HELPERS_DIR="${SCRIPT_HELPERS_DIR:-$SCRIPT_DIR/script-helpers}"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$SCRIPT_HELPERS_DIR/helpers.sh" ]]; then
  # shellcheck source=/dev/null
  source "$SCRIPT_HELPERS_DIR/helpers.sh"
  export SHLIB_CALLER_SCRIPT="${BASH_SOURCE[1]:-$0}"
  shlib_import logging env help
else
  # Minimal fallback so the wrapper scripts work before `./update` is run.
  log_info()  { echo "[INFO] $*"; }
  log_warn()  { echo "[WARN] $*" >&2; }
  log_error() { echo "[ERROR] $*" >&2; }
  parse_common_args() { :; }
fi

# --- project-specific helpers ---------------------------------------------
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/venv/bin/python}"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN="python3"
WEB_PORT="${WEB_PORT:-5000}"
PID_FILE="${PID_FILE:-$ROOT_DIR/.localrag/web.pid}"

web_pid() { [[ -f "$PID_FILE" ]] && cat "$PID_FILE" 2>/dev/null || true; }
web_running() {
  local pid; pid="$(web_pid)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}
