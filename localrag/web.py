"""Tiny Flask web UI: drag-and-drop documents + ask questions.

Reuses the same engine as the CLI. Endpoints:
  GET  /             -> the single-page UI
  GET  /api/status   -> current provider/retriever defaults + indexed files
  POST /api/upload   -> save dropped files into the docs folder, reindex
  POST /api/ask      -> answer a question grounded in the documents
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import List

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from .config import Config, load_config
from .engine import answer_question, get_retriever, refresh_index
from .extract import SUPPORTED_EXTS, discover_files


def _list_files(config: Config) -> List[str]:
    return [p.name for p in discover_files(config.docs_dir)]


def create_app(base_config: Config | None = None) -> Flask:
    base_config = base_config or load_config()
    base_config.docs_dir.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB upload cap

    def _request_config() -> Config:
        """Per-request config with optional provider/retriever overrides."""
        data = request.get_json(silent=True) or {}
        overrides = {}
        if data.get("provider"):
            overrides["provider"] = str(data["provider"]).lower()
        if data.get("retriever"):
            overrides["retriever"] = str(data["retriever"]).lower()
        return dataclasses.replace(base_config, **overrides) if overrides else base_config

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def status():
        return jsonify(
            {
                "provider": base_config.provider,
                "retriever": base_config.retriever,
                "docs_dir": str(base_config.docs_dir),
                "files": _list_files(base_config),
                "supported": sorted(SUPPORTED_EXTS),
                "links": {
                    "linkedin": base_config.linkedin_url,
                    "github": base_config.github_url,
                    "tutorial": base_config.tutorial_url,
                    "troubleshooting": base_config.docs_base_url + "troubleshooting.html",
                },
            }
        )

    @app.post("/api/upload")
    def upload():
        saved: List[str] = []
        skipped: List[str] = []
        for f in request.files.getlist("files"):
            if not f.filename:
                continue
            name = secure_filename(f.filename)
            if Path(name).suffix.lower() not in SUPPORTED_EXTS:
                skipped.append(f.filename)
                continue
            f.save(base_config.docs_dir / name)
            saved.append(name)

        chunks, n_files = refresh_index(base_config)
        return jsonify(
            {
                "saved": saved,
                "skipped": skipped,
                "files": _list_files(base_config),
                "indexed_files": n_files,
                "chunks": len(chunks),
            }
        )

    @app.post("/api/ask")
    def ask():
        data = request.get_json(silent=True) or {}
        question = (data.get("question") or "").strip()
        if not question:
            return jsonify({"error": "Please enter a question."}), 400
        try:
            result = answer_question(_request_config(), question)
            return jsonify(result)
        except Exception as exc:  # surface provider/network errors to the UI
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/peek")
    def peek():
        """The raw numbers behind the index: how the system 'sees' your data
        after BM25 finishes. Optional ?q= adds the per-chunk scoring for a query.
        """
        config = _request_config()
        question = (request.args.get("q") or "").strip()
        try:
            retriever = get_retriever(config)  # may rebuild the index — can fail
            peek_fn = getattr(retriever, "peek", None)
            if peek_fn is None:
                name = getattr(retriever, "name", config.retriever)
                return (
                    jsonify(
                        {"error": f"The '{name}' retriever has no peek view yet — switch to BM25."}
                    ),
                    400,
                )
            return jsonify(peek_fn(question or None, config.top_k))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    return app


def run(host: str = "127.0.0.1", port: int = 5000, config: Config | None = None) -> None:
    app = create_app(config)
    print(f"[localrag] Web UI on http://{host}:{port}  (Ctrl-C to stop)")
    app.run(host=host, port=port, debug=False)
