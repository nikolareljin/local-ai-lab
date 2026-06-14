#!/usr/bin/env bash
# Scaffold a new lesson from lessons/_template.
# Usage:  tools/new-lesson.sh <NN> <slug> ["Title"]
#   e.g.  tools/new-lesson.sh 4 rag-safety-prompt-injection "RAG Safety & Prompt Injection"
set -euo pipefail

[[ $# -ge 2 ]] || { echo "usage: $0 <NN> <slug> [\"Title\"]" >&2; exit 1; }
nn="$(printf '%02d' "$1")"
slug="$2"
title="${3:-$slug}"

root="$(cd "$(dirname "$0")/.." && pwd)"
dest="$root/lessons/${nn}-${slug}"
[[ -e "$dest" ]] && { echo "already exists: $dest" >&2; exit 1; }

cp -r "$root/lessons/_template" "$dest"
# Fill the TITLE/SLUG placeholders. Done in Python so the values are JSON-escaped
# correctly (a title with quotes or backslashes won't corrupt lesson.json).
# Resolve Python 3: prefer python3, fall back to python only when it is actually
# Python 3 (on some systems `python` is Python 2). `|| true` keeps the lookup from
# aborting under `set -e` so we reach the explicit error below.
py="$(command -v python3 || command -v python || true)"
if [[ -z "$py" ]] || ! "$py" -c 'import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)' 2>/dev/null; then
  echo "Python 3 is required." >&2; exit 1
fi
"$py" - "$dest/lesson.json" "$title" "$slug" <<'PY'
import json, sys
path, title, slug = sys.argv[1:4]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
if data.get("title") == "TITLE":
    data["title"] = title
if data.get("slug") == "SLUG":
    data["slug"] = slug
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
PY

echo "Created $dest"
echo "Next: add code under python/ node/ dotnet/, edit lesson.json elements, then:  ./run -l $1 show"
