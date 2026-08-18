"""Lesson 7 - the playground: watch the two splitters disagree.

The demo compares the pipelines at one fixed setting. This page lets you move the
setting. The single most instructive control is **chunk size**: Lesson 1's
`chunk.py` collapses all whitespace and then breaks on sentence punctuation, while
`RecursiveCharacterTextSplitter` keeps the text as written and walks a separator
list. Push chunk size around and watch two pipelines that agreed a moment ago
start citing different files.

That divergence is the lesson in one screen. "Drop-in replacement" is doing a lot
of work in most framework write-ups.

Launch it with:  ./run -l 7
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import handrolled_pipeline as handrolled  # noqa: E402
import langchain_rag  # noqa: E402
from lesson_web import serve  # noqa: E402

LESSON_DIR = Path(__file__).resolve().parent.parent
SETTINGS = json.loads((LESSON_DIR / "data" / "questions.json").read_text(encoding="utf-8"))

# Defaults match data/questions.json, so the page opens on exactly the result the
# demo prints and the test pins.
PARAMS = [
    {"name": "chunk_size", "label": "Chunk size", "kind": "range",
     "min": 200, "max": 2000, "step": 100, "default": SETTINGS["chunk_size"]},
    {"name": "chunk_overlap", "label": "Chunk overlap", "kind": "range",
     "min": 0, "max": 400, "step": 20, "default": SETTINGS["chunk_overlap"]},
    {"name": "top_k", "label": "Top k", "kind": "range",
     "min": 1, "max": 6, "step": 1, "default": SETTINGS["top_k"]},
    {"name": "show_prompt", "label": "Show the rendered prompt", "kind": "toggle",
     "default": False},
]

EXAMPLES = [{"label": q, "query": q} for q in SETTINGS["questions"]]


def _import_langchain():
    """Same narrow guard as the demo: only a missing LangChain package means
    "not installed". A real import-time failure in `lc_pipeline` propagates
    rather than being misreported to the reader as a missing dependency."""
    try:
        import lc_pipeline
        return lc_pipeline
    except ModuleNotFoundError as exc:
        if (exc.name or "").split(".")[0] in langchain_rag.LANGCHAIN_PACKAGES:
            return None
        raise


def search(query, values):
    if not query:
        note = "Ask something the manual covers, then move the chunk size."
        return {"arms": [], "blocks": [{"kind": "note", "text": note}]}

    size = int(values.get("chunk_size", SETTINGS["chunk_size"]))
    overlap = int(values.get("chunk_overlap", SETTINGS["chunk_overlap"]))
    k = int(values.get("top_k", SETTINGS["top_k"]))
    if overlap >= size:
        overlap = max(0, size // 4)

    hand_chunks = handrolled.split(handrolled.load(), size, overlap)
    hand_hits = handrolled.retrieve(handrolled.build_retriever(hand_chunks), query, k)
    hand_sources = handrolled.sources(hand_hits)

    lc = _import_langchain()
    if lc is None:
        return {
            "arms": [{"label": "hand-rolled (Lesson 1)", "ranking": hand_sources}],
            "blocks": [{"kind": "note",
                        "text": "LangChain is not installed, so only the hand-rolled arm ran. "
                                "Install it with: pip install -r "
                                "lessons/07-langchain-rag/requirements.txt"}],
        }

    lc_chunks = lc.split(lc.load(), size, overlap)
    lc_hits = lc.bm25_retriever(lc_chunks, k).invoke(query)
    lc_sources = lc.sources(lc_hits)

    agree = hand_sources == lc_sources
    blocks = [
        {"kind": "stats", "items": [
            {"v": str(len(hand_chunks)), "l": "chunks · hand-rolled"},
            {"v": str(len(lc_chunks)), "l": "chunks · LangChain"},
            {"v": "same" if agree else "different", "l": "sources cited"},
        ]},
        {"kind": "table", "title": "What each arm retrieved",
         "columns": ["#", "hand-rolled (chunk.py)", "LangChain (RecursiveCharacterTextSplitter)"],
         "rows": [
             [{"v": str(i + 1), "cls": "num"},
              {"v": hand_sources[i] if i < len(hand_sources) else "-",
               "cls": "text" if i < len(hand_sources) else "miss"},
              {"v": lc_sources[i] if i < len(lc_sources) else "-",
               "cls": "text" if i < len(lc_sources) else "miss"}]
             for i in range(max(len(hand_sources), len(lc_sources)))
         ]},
    ]

    if agree:
        blocks.append({"kind": "note", "text":
                       "Same citations from different chunk boundaries. The pipelines agree here, "
                       "which is the result you would hope for - but it is a result, "
                       "not a guarantee."})
    else:
        blocks.append({"kind": "note", "text":
                       "The two splitters carved the corpus differently and retrieval followed. "
                       "Neither is wrong; they are different tools. This is what 'drop-in "
                       "replacement' hides."})

    if values.get("show_prompt"):
        _, hand_user = handrolled.render_prompt(query, hand_hits)
        _, lc_user = lc.render_prompt(query, lc_hits)
        blocks.append({"kind": "tokens", "title": "Rendered user prompt (first 300 characters)",
                       "items": [
                           {"text": hand_user[:300], "note": "hand-rolled"},
                           {"text": lc_user[:300], "note": "LangChain"},
                       ]})
        blocks.append({"kind": "note", "text":
                       "Same system prompt, same template, same citation instruction - only the "
                       "retrieved text differs. That is what makes the comparison fair."})

    return {
        "arms": [
            {"label": "hand-rolled (Lesson 1)", "ranking": hand_sources},
            {"label": "LangChain (Lesson 7)", "ranking": lc_sources},
        ],
        "blocks": blocks,
    }


def main():
    serve(
        title="Lesson 7 · Rebuild RAG with LangChain",
        subtitle="Two pipelines, one corpus, one system prompt - watch where they diverge.",
        hint="Move the chunk size and watch the two arms start citing different files.",
        params=PARAMS,
        examples=EXAMPLES,
        search=search,
    )


if __name__ == "__main__":
    main()
