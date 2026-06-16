"""Offline smoke tests for the shared engine cache and the Flask status route.

No network and no LLM: BM25 retrieval over the committed sample corpus, plus the
``/api/status`` endpoint that just reports config + the indexed files.
"""

import dataclasses
from pathlib import Path

from localrag import engine
from localrag.config import load_config
from localrag.web import create_app

DOCS = Path(__file__).resolve().parent.parent / "documents"


def _config(tmp_path):
    """Sample corpus as the docs dir, with a throwaway cache dir per test."""
    return dataclasses.replace(
        load_config(), docs_dir=DOCS, cache_dir=tmp_path, retriever="bm25"
    )


def test_engine_builds_and_reuses_bm25_retriever(tmp_path):
    config = _config(tmp_path)
    engine.refresh_index(config)  # public reset: build the index and clear the cache

    retriever = engine.get_retriever(config)
    assert retriever.search("how do I reset the device", k=3), "expected BM25 hits"
    # Docs haven't changed, so a second call returns the very same cached object.
    assert engine.get_retriever(config) is retriever


def test_status_endpoint_reports_config_and_files(tmp_path):
    client = create_app(_config(tmp_path)).test_client()

    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["provider"] and data["retriever"] == "bm25"
    assert any("sample_manual.md" in f for f in data["files"])
    assert data["supported"], "expected a non-empty list of supported extensions"
