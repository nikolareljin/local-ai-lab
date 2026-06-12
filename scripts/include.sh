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
VENV_DIR="${VENV_DIR:-$ROOT_DIR/venv}"

# Resolve the venv's Python across layouts: POSIX (bin/python) and Windows/Git
# Bash (Scripts/python.exe). Echoes an empty string if no venv exists yet.
venv_python() {
  if [[ -x "$VENV_DIR/bin/python" ]]; then echo "$VENV_DIR/bin/python"
  elif [[ -x "$VENV_DIR/Scripts/python.exe" ]]; then echo "$VENV_DIR/Scripts/python.exe"
  else echo ""; fi
}

PYTHON_BIN="${PYTHON_BIN:-$(venv_python)}"
[[ -n "$PYTHON_BIN" && -x "$PYTHON_BIN" ]] || PYTHON_BIN="$(command -v python3 || command -v python)"
WEB_PORT="${WEB_PORT:-5000}"
PID_FILE="${PID_FILE:-$ROOT_DIR/.localrag/web.pid}"

web_pid() { [[ -f "$PID_FILE" ]] && cat "$PID_FILE" 2>/dev/null || true; }
web_running() {
  local pid; pid="$(web_pid)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

# Create the venv (first run) and install dependencies if anything is missing.
ensure_venv() {
  if [[ -z "$(venv_python)" ]]; then
    log_info "Creating virtualenv (first run) at $VENV_DIR ..."
    "$(command -v python3 || command -v python)" -m venv "$VENV_DIR"
  fi
  PYTHON_BIN="$(venv_python)"
  [[ -n "$PYTHON_BIN" ]] || { log_error "Could not locate the venv Python (looked in bin/ and Scripts/)."; exit 1; }
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

# --- discover lesson processes (used by ./status and ./stop) ---------------
# Print one TAB-separated line per running local-ai-lab process started from
# THIS checkout:   <pid>\t<kind>\t<port-or-->\t<command>
# Covers all three languages (python / node / csharp), the MCP server, and a
# local docs preview server. When /proc is available (Linux) candidates are
# scoped to processes whose working directory is under this repo, so other
# checkouts or unrelated processes on the machine are never matched.
lesson_procs() {
  # Without pgrep (rare), fall back to the PID-file web app so ./status and
  # ./stop still manage the ./start-launched server instead of finding nothing.
  if ! command -v pgrep >/dev/null 2>&1; then
    local wpid; wpid="$(web_pid)"
    if [[ -n "$wpid" ]] && kill -0 "$wpid" 2>/dev/null; then
      printf '%s\t%s\t%s\t%s\n' "$wpid" "python" "${WEB_PORT:-5000}" \
        "$(ps -o args= -p "$wpid" 2>/dev/null || echo 'python -m localrag web')"
    fi
    return 0
  fi
  local self=$$
  # kind:regex — regex is matched against the full command line via `pgrep -f`.
  local sigs=(
    "python:-m localrag"
    "mcp:mcp_server\.py"
    "node:cli\.js"
    "csharp:LocalRag"
    "csharp:dotnet run"
    "docs:http\.server"
  )
  local seen=" " entry kind rx pid cwd cmd port prog
  for entry in "${sigs[@]}"; do
    kind="${entry%%:*}"; rx="${entry#*:}"
    # `--` so a regex starting with '-' (e.g. "-m localrag") is the pattern,
    # not parsed as a pgrep option.
    while read -r pid; do
      [[ -n "$pid" && "$pid" != "$self" ]] || continue
      [[ "$seen" == *" $pid "* ]] && continue
      # Scope to THIS checkout by working directory. Require a verifiable cwd
      # (via /proc, else lsof) under the repo; if it cannot be determined, skip
      # the candidate so we never signal an unrelated process — e.g. on macOS or
      # Windows where /proc is absent.
      cwd=""
      if [[ -r "/proc/$pid/cwd" ]]; then
        cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || true)"
      elif command -v lsof >/dev/null 2>&1; then
        cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
      fi
      case "$cwd" in
        "$ROOT_DIR"|"$ROOT_DIR"/*) ;;
        *) continue ;;
      esac
      cmd="$(ps -o args= -p "$pid" 2>/dev/null || true)"
      [[ -n "$cmd" ]] || continue
      # Match the real interpreter, not a shell wrapper that merely launched it
      # (e.g. `bash -c '... http.server ...'`), so we never kill a launcher shell.
      prog="$(basename "${cmd%% *}")"
      case "$kind" in
        python|mcp|docs) [[ "$prog" == *python* ]] || continue ;;
        node)            [[ "$prog" == *node* ]]   || continue ;;
        csharp)          [[ "$prog" == dotnet* || "$prog" == *LocalRag* ]] || continue ;;
      esac
      port="$(printf '%s' "$cmd" | grep -oE -- '--port[= ]+[0-9]+' | grep -oE '[0-9]+' | head -1)"
      [[ -n "$port" ]] || port="-"
      seen+="$pid "
      printf '%s\t%s\t%s\t%s\n' "$pid" "$kind" "$port" "$cmd"
    done < <(pgrep -f -- "$rx" 2>/dev/null || true)
  done
}
