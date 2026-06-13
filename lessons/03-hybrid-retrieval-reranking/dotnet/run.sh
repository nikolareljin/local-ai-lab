#!/usr/bin/env bash
# Run the Lesson 3 hybrid retrieval demo (C# / .NET 8). No external packages.
set -euo pipefail
cd "$(dirname "$0")"
command -v dotnet >/dev/null 2>&1 || { echo ".NET 8 SDK is required (https://dotnet.microsoft.com)." >&2; exit 1; }
dotnet run -c Release --nologo
