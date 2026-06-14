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
    "arms":   [ {"label": str, "ranking": [doc_name, ...], "highlight": bool}, ... ],
    "blocks": [ <block>, ... ]      # the "why" breakdown, rendered top-to-bottom
  }
arms[].highlight is optional (default false); set it on the arm to emphasise (e.g. the
fused result). Position is not used, so a single-arm lesson is never mis-highlighted.
where each <block> is one of:
  {"kind": "stats",  "items": [{"v": str, "l": str}, ...]}
  {"kind": "tokens", "title": str, "items": [{"text": str, "note": str, "muted": bool}, ...]}
  {"kind": "table",  "title": str, "columns": [str, ...],
                     "rows": [[{"v": str, "cls": "num"|"miss"|"text"}, ...], ...]}
  {"kind": "note",   "text": str}
"""

from __future__ import annotations

import socket
import traceback
from pathlib import Path
from typing import Callable

from flask import Flask, Response, jsonify, request

TEMPLATE = Path(__file__).resolve().parent / "templates" / "lesson-gui.html"


def _free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))  # pick a port free on the same interface serve() binds
        return s.getsockname()[1]


def _coerce(params, raw):
    """Turn the raw JSON param values from the browser into typed Python values,
    falling back to each param's declared default when missing or unparsable."""
    if not isinstance(raw, dict):
        raw = {}  # defensive: a non-dict `params` falls back to all defaults, never raises
    out = {}
    for p in params:
        name = p["name"]
        value = raw.get(name, p.get("default"))
        if p.get("kind") == "range":
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = float(p.get("default") or 0)  # `or 0` so a missing/None default can't 500
        elif p.get("kind") == "toggle":
            # Coerce strings explicitly so "false"/"0"/"off"/"no"/"" read as False
            # (plain bool("false") is True, which would silently invert the toggle).
            if isinstance(value, str):
                value = value.strip().lower() not in ("", "false", "0", "off", "no")
            else:
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
        # Tolerate a malformed body (a JSON array/string, or non-dict `params`) — read
        # what we can and let `search` run rather than 500-ing before the UI sees anything.
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            data = {}
        query = str(data.get("query") or "").strip()
        raw_params = data.get("params")
        values = _coerce(params, raw_params if isinstance(raw_params, dict) else {})
        try:
            return jsonify(search(query, values))
        except Exception as exc:  # surface compute errors to the UI instead of 500-ing blank
            traceback.print_exc()  # full stack to the server console for local debugging
            message = f"{type(exc).__name__}: {exc}"
            return jsonify({"arms": [], "blocks": [{"kind": "note", "text": f"Error — {message}"}]}), 200

    chosen = port or _free_port(host)
    print(f"{title} → http://{host}:{chosen}  (Ctrl-C to stop)", flush=True)
    app.run(host=host, port=chosen, debug=False)
