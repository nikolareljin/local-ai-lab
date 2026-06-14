"""Reusable local-GUI scaffold for the lessons.

A lesson's `python/web.py` calls `serve(...)` with a small declarative spec — a
title, a list of tunable **parameters** (sliders / toggles), a few **example**
queries, and a `search(query, values)` function — and gets the same L1-style dark
GUI every lesson shares: a query box, a live parameter panel, the ranked results,
and a "why" score breakdown. The page itself is `tools/templates/lesson-gui.html`
(self-contained, no course assets), filled at runtime from `/api/config`.

This keeps every lesson's experiment GUI consistent and to-the-point: the lesson
supplies only its retrieval/compute and what numbers to surface; the look, the
controls and the wiring live here once.

`search(query, values)` returns a dict the shell renders:
  {
    "arms":   [ {"label": str, "ranking": [doc_name, ...]}, ... ],
    "blocks": [ <block>, ... ]      # the "why" breakdown, rendered top-to-bottom
  }
where each <block> is one of:
  {"kind": "stats",  "items": [{"v": str, "l": str}, ...]}
  {"kind": "tokens", "title": str, "items": [{"text": str, "note": str, "muted": bool}, ...]}
  {"kind": "table",  "title": str, "columns": [str, ...],
                     "rows": [[{"v": str, "cls": "num"|"miss"|"text"}, ...], ...]}
  {"kind": "note",   "text": str}
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Callable

from flask import Flask, Response, jsonify, request

TEMPLATE = Path(__file__).resolve().parent / "templates" / "lesson-gui.html"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _coerce(params, raw):
    """Turn the raw JSON param values from the browser into typed Python values,
    falling back to each param's declared default when missing or unparsable."""
    out = {}
    for p in params:
        name = p["name"]
        value = raw.get(name, p.get("default"))
        if p.get("kind") == "range":
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = float(p.get("default", 0))
        elif p.get("kind") == "toggle":
            value = bool(value)
        out[name] = value
    return out


def serve(
    *,
    title: str,
    subtitle: str,
    hint: str,
    params: list,
    examples: list,
    search: Callable[[str, dict], dict],
    host: str = "127.0.0.1",
    port: int | None = None,
) -> None:
    """Start the shared experiment GUI for a lesson.

    title/subtitle/hint — page header text.
    params  — list of {name, label, kind:"range"|"toggle", default, [min,max,step]}.
    examples— list of {label, query} shown as one-click chips.
    search  — fn(query, values) -> {"arms": [...], "blocks": [...]} (see module docs).
    """
    app = Flask(__name__)
    config = {
        "title": title,
        "subtitle": subtitle,
        "hint": hint,
        "params": params,
        "examples": examples,
    }

    @app.get("/")
    def index():
        # Read the shell each request so the template can be edited live in dev.
        return Response(TEMPLATE.read_text(encoding="utf-8"), mimetype="text/html")

    @app.get("/api/config")
    def api_config():
        return jsonify(config)

    @app.post("/api/search")
    def api_search():
        data = request.get_json(silent=True) or {}
        query = (data.get("query") or "").strip()
        values = _coerce(params, data.get("params") or {})
        try:
            return jsonify(search(query, values))
        except Exception as exc:  # surface compute errors to the UI instead of 500-ing blank
            return jsonify({"arms": [], "blocks": [{"kind": "note", "text": f"Error: {exc}"}]}), 200

    chosen = port or _free_port()
    print(f"{title} → http://{host}:{chosen}  (Ctrl-C to stop)", flush=True)
    app.run(host=host, port=chosen, debug=False)
