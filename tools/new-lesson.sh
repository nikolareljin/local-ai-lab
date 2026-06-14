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
python3 - "$dest/lesson.json" "$title" "$slug" <<'PY'
import json, sys
path, title, slug = sys.argv[1:4]
data = json.load(open(path, encoding="utf-8"))
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
