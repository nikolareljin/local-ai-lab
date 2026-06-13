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
# Fill the two placeholders in the manifest (kept simple: TITLE / SLUG).
# Portable in-place edit (BSD/macOS sed needs a backup suffix; GNU accepts it too).
sed -i.bak "s/\"TITLE\"/\"${title//\//\\/}\"/; s/\"SLUG\"/\"${slug}\"/" "$dest/lesson.json"
rm -f "$dest/lesson.json.bak"

echo "Created $dest"
echo "Next: add code under python/ node/ dotnet/, edit lesson.json elements, then:  ./run -l $1 show"
