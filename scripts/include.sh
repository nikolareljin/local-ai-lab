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

# Create the venv (first run) and install dependencies if anything is missing.
VENV_DIR="${VENV_DIR:-$ROOT_DIR/venv}"
ensure_venv() {
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    log_info "Creating virtualenv (first run) at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
  fi
  PYTHON_BIN="$VENV_DIR/bin/python"
  if ! "$PYTHON_BIN" -c "import flask, rank_bm25, pypdf, docx, numpy, mcp" >/dev/null 2>&1; then
    log_info "Installing dependencies (one-time) ..."
    "$PYTHON_BIN" -m pip install -q --upgrade pip >/dev/null 2>&1 || true
    "$PYTHON_BIN" -m pip install -q -r "$ROOT_DIR/requirements.txt"
  fi
}

# Find a free TCP port starting from $1 (default 5000).
port_in_use() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && { exec 3>&-; return 0; } || return 1; }
find_free_port() {
  local p="${1:-5000}" tries=0
  while port_in_use "$p" && [[ $tries -lt 50 ]]; do p=$((p + 1)); tries=$((tries + 1)); done
  echo "$p"
}
