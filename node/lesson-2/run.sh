#!/usr/bin/env bash
# SCRIPT: node/lesson-2/run.sh
# DESCRIPTION: Run the Node.js port of Lesson 2 (an MCP server) locally.
# CREATOR: Nik Reljin
set -euo pipefail

# Resolve repo root (node/lesson-2 -> repo root) and this lesson's directory.
here="$(cd "$(dirname "$0")" && pwd)"
rootDir="$(cd "$here/../.." && pwd)"

# Shared helpers: log_info / log_error (with a safe fallback if missing).
if [[ -f "$rootDir/scripts/include.sh" ]]; then
  # shellcheck source=/dev/null
  source "$rootDir/scripts/include.sh"
else
  log_info() { echo "[INFO] $*"; }
  log_warn() { echo "[WARN] $*" >&2; }
  log_error() { echo "[ERROR] $*" >&2; }
fi

# This wrapper can be launched as an MCP stdio server command (`run.sh serve`),
# where stdout is reserved for the JSON-RPC stream. Force our own diagnostics to
# stderr (the shared log_info writes to stdout) so they can never corrupt the
# protocol handshake during setup or startup.
log_info() { echo "[INFO] $*" >&2; }

command -v node >/dev/null 2>&1 || { log_error "Node.js (>=18) is required but not on PATH."; exit 1; }

cd "$here"

# Install this lesson's own dependencies (MCP SDK + zod) on first run. Send npm's
# stdout to stderr too: this wrapper can be the MCP server command, where stdout
# is the JSON-RPC stream and install chatter would corrupt the handshake.
if [[ ! -d "node_modules" ]]; then
  log_info "Installing Lesson 2 Node dependencies (one-time) ..."
  npm install --silent --no-fund --no-audit >&2
fi

# The server reuses Lesson 1's engine (config/engine/extract). Its extractor
# dynamically imports pdf-parse/mammoth, which resolve from node/lesson-1's own
# node_modules — so any corpus with a .pdf/.docx fails on a fresh checkout unless
# Lesson 1 is installed too. Install it here so Lesson 2 is runnable standalone.
lesson1_dir="$rootDir/node/lesson-1"
if [[ -f "$lesson1_dir/package.json" && ! -d "$lesson1_dir/node_modules" ]]; then
  log_info "Installing Lesson 1 Node dependencies (reused by the MCP server) ..."
  (cd "$lesson1_dir" && npm install --silent --no-fund --no-audit >&2)
fi

action="${1:-demo}"
[[ $# -gt 0 ]] && shift || true

server="$here/src/server.js"

case "$action" in
  demo|"")
    log_info "Lesson 2 (Node) · MCP — spawning the server over stdio and calling its tools ..."
    exec node "$here/src/demo.js" "$@"
    ;;
  serve)
    log_info "Lesson 2 (Node) · MCP server over stdio (a host/client connects to this; Ctrl-C to stop)."
    exec node "$server"
    ;;
  register)
    command -v claude >/dev/null 2>&1 || { log_error "The 'claude' CLI is not on your PATH."; exit 1; }
    log_info "Registering the Node MCP server with Claude Code ..."
    exec claude mcp add local-ai-lab-docs-node -- node "$server"
    ;;
  test)
    # Offline smoke test: drive the server through the demo client (no LLM).
    exec node "$here/src/demo.js" "How do I reset the device?"
    ;;
  *)
    log_error "Lesson 2 (Node) actions:  demo | serve | register | test"
    exit 1
    ;;
esac
