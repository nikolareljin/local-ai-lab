#!/usr/bin/env bash
# SCRIPT: node/lesson-1/run.sh
# DESCRIPTION: Run the Node.js port of Lesson 1 (RAG app) locally.
# DEFAULT AI: the Claude Code CLI (no API key needed). Override with RAG_PROVIDER.
# CREATOR: Nik Reljin
set -euo pipefail

# Resolve repo root (node/lesson-1 -> repo root) and this lesson's directory.
here="$(cd "$(dirname "$0")" && pwd)"
rootDir="$(cd "$here/../.." && pwd)"

# Shared helpers: log_info / find_free_port (with a safe fallback if missing).
if [[ -f "$rootDir/scripts/include.sh" ]]; then
  # shellcheck source=/dev/null
  source "$rootDir/scripts/include.sh"
else
  log_info() { echo "[INFO] $*"; }
  log_warn() { echo "[WARN] $*" >&2; }
  log_error() { echo "[ERROR] $*" >&2; }
  find_free_port() { echo "${1:-5000}"; }
fi

command -v node >/dev/null 2>&1 || { log_error "Node.js (>=18) is required but not on PATH."; exit 1; }

cd "$here"

# Install dependencies on first run.
if [[ ! -d "node_modules" ]]; then
  log_info "Installing Node dependencies (one-time) ..."
  npm install --silent --no-fund --no-audit
fi

# First arg is the action (default: web). The dispatcher passes the action as $1.
action="${1:-web}"
[[ $# -gt 0 ]] && shift || true

case "$action" in
  web|"")
    port="$(find_free_port "${WEB_PORT:-5000}")"
    log_info "Lesson 1 (Node) · RAG web UI → http://127.0.0.1:${port}    (Ctrl-C to stop)"
    exec node src/cli.js web --port "$port"
    ;;
  ask)
    exec node src/cli.js ask "$@"
    ;;
  repl)
    exec node src/cli.js ask
    ;;
  index)
    exec node src/cli.js index --reindex
    ;;
  test)
    # Smoke test: rebuild the index over the committed sample corpus. Exit 0 offline.
    exec node src/cli.js index --reindex
    ;;
  *)
    log_error "Lesson 1 (Node) actions:  web | ask \"q\" | repl | index | test"
    exit 1
    ;;
esac
