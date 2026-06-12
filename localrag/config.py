"""Configuration loaded from environment / .env. No hard-coded paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv is optional at runtime
    pass


def _root() -> Path:
    # Project root is the parent of this package directory.
    return Path(__file__).resolve().parent.parent


@dataclass
class Config:
    provider: str
    retriever: str
    embed_provider: str
    docs_dir: Path
    cache_dir: Path
    top_k: int

    # Social / course links surfaced in the web UI
    linkedin_url: str
    github_url: str
    tutorial_url: str
    # Base URL of the docs site (trailing slash). Override (e.g.
    # http://localhost:8000/) to point the app's Troubleshooting links at a
    # LOCAL copy of docs/ while testing, before publishing to GitHub Pages.
    docs_base_url: str

    # Provider settings
    claude_bin: str
    ollama_url: str
    ollama_model: str
    ollama_embed_model: str
    gemini_api_key: str
    gemini_model: str
    gemini_embed_model: str
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    openai_embed_model: str


def load_config() -> Config:
    root = _root()
    docs_dir = Path(os.getenv("RAG_DOCS_DIR", "documents"))
    if not docs_dir.is_absolute():
        docs_dir = root / docs_dir

    return Config(
        provider=os.getenv("RAG_PROVIDER", "claude").lower(),
        retriever=os.getenv("RAG_RETRIEVER", "bm25").lower(),
        embed_provider=os.getenv("RAG_EMBED_PROVIDER", "ollama").lower(),
        docs_dir=docs_dir,
        cache_dir=root / ".localrag",
        top_k=int(os.getenv("RAG_TOP_K", "5")),
        linkedin_url=os.getenv("LINKEDIN_URL", "https://www.linkedin.com/in/nikolareljin"),
        github_url=os.getenv("GITHUB_URL", "https://github.com/nikolareljin/local-ai-lab"),
        tutorial_url=os.getenv("TUTORIAL_URL", "https://nikolareljin.github.io/local-ai-lab/"),
        docs_base_url=os.getenv("DOCS_BASE_URL", "https://nikolareljin.github.io/local-ai-lab/").rstrip("/") + "/",
        claude_bin=os.getenv("CLAUDE_BIN", "claude"),
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
        ollama_embed_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_embed_model=os.getenv("GEMINI_EMBED_MODEL", "text-embedding-004"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_embed_model=os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
    )
