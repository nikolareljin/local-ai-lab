"""Lesson 2 - interactive MCP tool GUI (experiment locally).

The MCP server (`mcp_server.py`) exposes two tools an MCP host like Claude Code can
call over stdio: `search_docs(query, k)` and `list_documents()`. This GUI lets you
call them yourself, from a browser, and see exactly what the host receives — the
same cited passages, grounded in your local `documents/` folder. It reuses the very
same retriever the tools wrap (no duplication, and no stdio server to spawn).

Run:  ./run -l 2        (or:  ./run -l 2 web)

This is the interactive twin of `./run -l 2 demo`, which makes the identical tool
calls over a real stdio MCP connection and prints the results to the terminal.
"""

import sys
from pathlib import Path

# Resolve the repo root from this file so the imports work no matter the cwd, then
# expose both the project modules and the shared GUI scaffold under tools/.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))            # localrag, mcp_server
sys.path.insert(0, str(ROOT / "tools"))  # lesson_web (shared scaffold)

from lesson_web import serve  # the shared L1-style experiment GUI

from localrag.config import load_config
from localrag.engine import get_retriever
from mcp_server import list_documents  # the real MCP tool, called as-is

# Build the retriever once — it is exactly what `search_docs` wraps, so the GUI and
# an MCP host return identical passages.
CONFIG = load_config()
RETRIEVER = get_retriever(CONFIG)

PARAMS = [
    {"name": "k", "label": "search_docs · k — passages to return", "kind": "range",
     "min": 1, "max": 10, "step": 1, "default": 5},
    {"name": "full", "label": "Show full passages (not snippets)", "kind": "toggle",
     "default": False},
]

EXAMPLES = [
    {"label": "Reset the device", "query": "How do I reset the device?"},
    {"label": "BM25 vs embeddings", "query": "How does BM25 retrieval compare to embeddings?"},
    {"label": "Turtle astronaut", "query": "How did the turtle become an astronaut?"},
]


def _corpus_block():
    """The list_documents() tool output, shown as chips — the corpus the server sees."""
    names = [n for n in list_documents().splitlines() if n.strip()]
    return {"kind": "tokens",
            "title": "list_documents() — the corpus this MCP server exposes",
            "items": [{"text": n} for n in names] or [{"text": "(no documents indexed)", "muted": True}]}


def _passage(text, full):
    flat = " ".join(text.split())
    return flat if full else (flat[:240] + ("…" if len(flat) > 240 else ""))


def search(query, values):
    """Call the same retrieval `search_docs` wraps and present what the MCP host gets:
    the cited sources as an arm, the returned passages as a table, and the corpus."""
    k = int(values["k"])
    full = values["full"]
    if not query:
        return {"arms": [], "blocks": [
            {"kind": "note", "text": "Type a question. The GUI makes the same search_docs call an "
                                     "MCP host (e.g. Claude Code) would make over stdio, and shows what it returns."},
            _corpus_block()]}

    hits = RETRIEVER.search(query, k)
    sources = [f'{h["source"]}:{h["page_number"]}' for h in hits]
    arms = [{"label": f"search_docs → {len(sources)} cited passage(s)", "ranking": sources}]
    if hits:
        results = {"kind": "table",
                   "title": "Returned passages — exactly what the model is handed (each tagged [source:page])",
                   "columns": ["source:page", "passage"],
                   "rows": [[{"v": s, "cls": "text"}, {"v": _passage(h["text"], full), "cls": "text"}]
                            for s, h in zip(sources, hits)]}
    else:
        results = {"kind": "note", "text": "search_docs returned no passages — try another question, "
                                           "or drop files into documents/ and rerun."}
    blocks = [
        {"kind": "note", "text": f'MCP tool call:  search_docs(query="{query}", k={k})'},
        results,
        _corpus_block(),
    ]
    return {"arms": arms, "blocks": blocks}


def main():
    serve(
        title="Lesson 2 · MCP — call your document tools",
        subtitle="search_docs and list_documents are the two tools this MCP server exposes. Type a "
                 "question and watch search_docs return cited passages grounded in your local files — "
                 "the same call an MCP host like Claude Code makes over stdio.",
        hint="Drag k to change how many passages the tool returns; toggle full passages to see the raw text.",
        params=PARAMS,
        examples=EXAMPLES,
        search=search,
    )


if __name__ == "__main__":
    main()
