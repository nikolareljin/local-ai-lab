"""Lesson 10 - is this machine ready? One table, yes or no per row, and what to do.

    ./run -l 10 check

Needed for the local, simulated session (exit 1 if any is missing):
  - Ollama is running
  - the model the adapter and the LLM arm use is pulled (qwen3:1.7b)
  - that model returns log-probabilities (the adapter reads them)

Optional:
  - a bigger model for the second adapter row (qwen3.5:4b)
  - TYPESAFE_API_KEY, for the one real call (./run -l 10 hello)
  - the official SDK (./run -l 10 install-sdk), Node.js and .NET for the other languages

The demo (./run -l 10 demo) needs none of this: it replays recordings.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

import local_adapter
import systemone

LESSON = Path(__file__).resolve().parents[1]
# The model the live commands will use: OLLAMA_MODEL if set, as in python/jev.py.
REQUIRED_MODEL = os.environ.get("OLLAMA_MODEL", local_adapter.DEFAULT_MODEL)
OPTIONAL_MODEL = "qwen3.5:4b"


# Anything a missing, old or half-started Ollama can answer with.
CHECK_ERRORS = (RuntimeError, OSError, ValueError, KeyError, TypeError, AttributeError,
                http.client.HTTPException)


def _get(url: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def ollama_rows(url: str) -> tuple[list[tuple], bool]:
    """(rows, ready). A row is (status, what, detail); status is yes, no or -- (optional)."""
    rows = []
    try:
        version = _get(url.rstrip("/") + "/api/version").get("version", "?")
        models = {m.get("name") for m in _get(url.rstrip("/") + "/api/tags").get("models") or []}
    except CHECK_ERRORS:
        rows.append(("no", f"Ollama running at {url}",
                     "install: https://ollama.com/download   then start it: ollama serve"))
        return rows, False
    rows.append(("yes", f"Ollama running at {url}", f"version {version}"))
    has_model = REQUIRED_MODEL in models
    rows.append(("yes" if has_model else "no", f"model {REQUIRED_MODEL} (needed)",
                 "pulled" if has_model else f"run: ollama pull {REQUIRED_MODEL}"))
    has_big = OPTIONAL_MODEL in models
    rows.append(("yes" if has_big else "--", f"model {OPTIONAL_MODEL} (optional, slower, better)",
                 "pulled" if has_big else f"run: ollama pull {OPTIONAL_MODEL}"))
    ready = has_model
    if has_model:
        try:
            top = local_adapter.ollama_first_token(
                [{"role": "user", "content": "Answer with one letter: A or B."}],
                REQUIRED_MODEL, url, keep_alive="1m")
            ok = bool(top)
            detail = f"{len(top)} candidates for the first token" if ok else "none returned"
        except CHECK_ERRORS as err:
            ok, detail = False, (f"{err} - if Ollama is older than 0.12.11, update it: "
                                 "https://ollama.com/download")
        rows.append(("yes" if ok else "no", "log-probabilities from the model", detail))
        ready = ready and ok
    return rows, ready


def other_rows(env: dict) -> list[tuple]:
    key = bool(env.get("TYPESAFE_API_KEY"))
    sdk = any((LESSON / ".venv-sdk" / rel).exists()
              for rel in ("bin/python", "Scripts/python.exe"))
    return [
        ("yes" if key else "--", "TYPESAFE_API_KEY (for ./run -l 10 hello)",
         "set" if key else "create one: https://console.typesafe.ai/keys"),
        ("yes" if sdk else "--", "official Python SDK (for ./run -l 10 sdk)",
         "installed in .venv-sdk" if sdk else "run: ./run -l 10 install-sdk"),
        ("yes" if shutil.which("node") else "--", "Node.js (for --lang node)",
         "found" if shutil.which("node") else "https://nodejs.org"),
        ("yes" if shutil.which("dotnet") else "--", ".NET 8 SDK (for --lang csharp)",
         "found" if shutil.which("dotnet") else "https://dotnet.microsoft.com/download"),
    ]


def main(out=None) -> int:
    out = out or sys.stdout
    systemone.load_typesafe_env(LESSON.parents[1] / ".env")
    url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    rows, ready = ollama_rows(url)
    rows += other_rows(dict(os.environ))
    print("Lesson 10 setup check   (yes = ready, no = needed and missing, -- = optional)",
          file=out)
    print(file=out)
    for status, what, detail in rows:
        print(f"  {status:<4}{what:<48}{detail}", file=out)
    print(file=out)
    if ready:
        print("Ready for the local session: ./run -l 10 live --backend keywords,llm-json,local",
              file=out)
    else:
        print("Not ready for the local session yet - fix the 'no' rows above. "
              "The demo still works: ./run -l 10 demo", file=out)
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
