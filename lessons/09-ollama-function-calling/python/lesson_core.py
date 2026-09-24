"""Lesson 9 - paths, the corpus, and the retriever, all borrowed.

The retriever is Lesson 1's BM25 over Lesson 7's corpus, by path, exactly as
Lesson 8 does it. One file is added on top: `data/notes/ticket_9001.md`, a
support ticket whose body tries to order the model to call a tool. It is the
Lesson 4 attack pointed at a tool instead of at the answer.

Nothing in this lesson changes how retrieval works. Every arm is arguing about
who picks the tool, and nothing else.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

# this file -> python -> 09-ollama-function-calling -> lessons -> repo root
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from localrag.chunk import Chunk, chunk_pages  # noqa: E402
from localrag.config import load_config  # noqa: E402
from localrag.extract import Page, discover_files, extract_pages  # noqa: E402
from localrag.retriever import Bm25Retriever  # noqa: E402

LESSON_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = LESSON_DIR / "data"
CASSETTE_DIR = DATA_DIR / "cassettes"

# Lesson 7's corpus by path (see Lesson 8's rag_core for why not a copy), plus
# this lesson's one poisoned note.
CORPUS_DIR = ROOT / "lessons" / "07-langchain-rag" / "data" / "corpus"
NOTES_DIR = DATA_DIR / "notes"

# Lesson 4's detector, imported by path rather than copied: a rule written twice drifts.
LESSON4_DIR = ROOT / "lessons" / "04-rag-safety-prompt-injection" / "python"

CHUNK_SIZE = 700
CHUNK_OVERLAP = 120
TOP_K = 3


def load_tasks() -> dict:
    """The lesson's settings and its task set, from `data/tasks.json`."""
    return json.loads((DATA_DIR / "tasks.json").read_text(encoding="utf-8"))


def load_pages(*dirs: Path) -> List[Page]:
    pages: List[Page] = []
    for d in dirs:
        for path in discover_files(d):
            pages.extend(extract_pages(path))
    return pages


def build_retriever(*dirs: Path) -> Bm25Retriever:
    """BM25 over the given folders (default: the corpus plus the notes)."""
    dirs = dirs or (CORPUS_DIR, NOTES_DIR)
    chunks: List[Chunk] = chunk_pages(load_pages(*dirs), size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    return Bm25Retriever(chunks)


def ollama_settings() -> tuple[str, str]:
    """(url, model) from the course config: `OLLAMA_URL` and `OLLAMA_MODEL`."""
    config = load_config()
    return config.ollama_url, config.ollama_model
