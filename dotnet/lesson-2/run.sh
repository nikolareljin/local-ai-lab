#!/usr/bin/env bash
# SCRIPT: run.sh
# DESCRIPTION: Run the C# / .NET 8 port of Lesson 2 (an MCP server).
# CREATOR: Nik Reljin
set -euo pipefail

# Repo root is two levels up from this script (dotnet/lesson-2/run.sh).
root_dir="$(cd "$(dirname "$0")/../.." && pwd)"
project_dir="$root_dir/dotnet/lesson-2"

# Reuse the shared helpers (log_info) with a safe fallback.
if [[ -f "$root_dir/scripts/include.sh" ]]; then
  # shellcheck source=/dev/null
  source "$root_dir/scripts/include.sh"
else
  log_info() { echo "[INFO] $*"; }
  log_error() { echo "[ERROR] $*" >&2; }
fi

command -v dotnet >/dev/null 2>&1 || { log_error ".NET SDK (>=8) is required but not on PATH."; exit 1; }

cd "$project_dir"

action="${1:-demo}"
[[ $# -gt 0 ]] && shift || true

# Build once so both the server and the demo client run the same compiled binary
# (the client re-launches `dotnet <dll> serve` as the server subprocess).
build_once() {
  log_info "Building the C# MCP server (one-time) ..."
  dotnet build -c Release --nologo -v quiet >/dev/null
}

case "$action" in
  demo|""|test)
    build_once
    log_info "Lesson 2 (C#) · MCP — spawning the server over stdio and calling its tools ..."
    exec dotnet run -c Release --no-build -- demo "$@"
    ;;
  serve)
    build_once
    log_info "Lesson 2 (C#) · MCP server over stdio (a host/client connects to this; Ctrl-C to stop)."
    exec dotnet run -c Release --no-build -- serve
    ;;
  register)
    command -v claude >/dev/null 2>&1 || { log_error "The 'claude' CLI is not on your PATH."; exit 1; }
    build_once
    dll="$project_dir/bin/Release/net8.0/LocalRagMcp.dll"
    log_info "Registering the C# MCP server with Claude Code ..."
    exec claude mcp add local-ai-lab-docs-dotnet -- dotnet "$dll" serve
    ;;
  *)
    log_info "Lesson 2 (C#) actions:  demo | serve | register | test"
    exit 1
    ;;
esac
