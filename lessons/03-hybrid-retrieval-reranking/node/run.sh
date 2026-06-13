#!/usr/bin/env bash
# Run the Lesson 3 hybrid retrieval demo (Node.js). No dependencies to install.
set -euo pipefail
cd "$(dirname "$0")"
command -v node >/dev/null 2>&1 || { echo "Node.js is required (https://nodejs.org)." >&2; exit 1; }
node hybrid_demo.mjs
