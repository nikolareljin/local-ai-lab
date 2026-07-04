#!/usr/bin/env bash
# Rebuild the notes index from scratch.
set -euo pipefail

: "${NOTES_DB:?set NOTES_DB to the index path}"
rm -f "$NOTES_DB"
python -m notes_api.index --rebuild
