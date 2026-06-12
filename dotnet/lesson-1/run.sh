#!/usr/bin/env bash
# SCRIPT: run.sh
# DESCRIPTION: Run the C# / .NET 8 port of Lesson 1 (the RAG app).
# CREATOR: Nik Reljin
set -euo pipefail

# Repo root is two levels up from this script (dotnet/lesson-1/run.sh).
root_dir="$(cd "$(dirname "$0")/../.." && pwd)"
project_dir="$root_dir/dotnet/lesson-1"

# Reuse the shared helpers (log_info / find_free_port) with a safe fallback.
if [[ -f "$root_dir/scripts/include.sh" ]]; then
  # shellcheck source=/dev/null
  source "$root_dir/scripts/include.sh"
else
  log_info() { echo "[INFO] $*"; }
  find_free_port() { echo "${1:-5000}"; }
fi

cd "$project_dir"

action="${1:-web}"
[[ $# -gt 0 ]] && shift || true

case "$action" in
  web|"")
    port="$(find_free_port "${WEB_PORT:-5000}")"
    log_info "Lesson 1 (C#) · RAG web UI → http://127.0.0.1:${port}    (Ctrl-C to stop)"
    exec dotnet run -c Release -- web --port "$port"
    ;;
  ask)
    exec dotnet run -c Release -- ask "$@"
    ;;
  index)
    exec dotnet run -c Release -- index "$@"
    ;;
  test)
    # Offline smoke test: rebuild the index over the committed samples so the
    # "Indexed N file(s) ..." line always prints, then exit 0.
    dotnet run -c Release -- index --reindex
    ;;
  *)
    log_info "Lesson 1 (C#) actions:  web | ask \"question\" | index | test"
    exit 1
    ;;
esac
