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
import threading
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import handrolled_pipeline as handrolled  # noqa: E402
import langchain_rag  # noqa: E402
from lesson_web import serve  # noqa: E402

LESSON_DIR = Path(__file__).resolve().parent.parent
SETTINGS = json.loads((LESSON_DIR / "data" / "questions.json").read_text(encoding="utf-8"))

# The largest top_k the slider offers. Retrievers are cached at this width and the
# results sliced per request, so a request never mutates shared state.
MAX_TOP_K = 6

# Defaults match data/questions.json, so the page opens on exactly the result the
# demo prints and the test pins.
PARAMS = [
    {"name": "chunk_size", "label": "Chunk size", "kind": "range",
     "min": 200, "max": 2000, "step": 100, "default": SETTINGS["chunk_size"]},
    {"name": "chunk_overlap", "label": "Chunk overlap", "kind": "range",
     "min": 0, "max": 400, "step": 20, "default": SETTINGS["chunk_overlap"]},
    {"name": "top_k", "label": "Top k", "kind": "range",
     "min": 1, "max": MAX_TOP_K, "step": 1, "default": SETTINGS["top_k"]},
    {"name": "show_prompt", "label": "Show the rendered prompt", "kind": "toggle",
     "default": False},
]

EXAMPLES = [{"label": q, "query": q} for q in SETTINGS["questions"]]


# The shared GUI calls /api/search on every keystroke and slider move, so loading
# and splitting the corpus inside search() would re-index on each one - sluggish,
# and a contradiction of the "build the index once" contract the rest of the
# lesson pins with tests.
#
# The cache key is exactly what changes the *contents* of an index: chunk_size,
# chunk_overlap, and whether the LangChain arm is available at all. top_k is
# deliberately NOT part of it - it only decides how many of the ranked results
# come back, so moving that slider re-ranks without re-indexing.
# Bounded, because the sliders can produce hundreds of (size, overlap) pairs and
# each entry holds a full chunk list plus a BM25 index. A handful is plenty: you
# move a slider, compare, move it back.
_ARM_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
_ARM_CACHE_MAX = 8
# Without this lock, two concurrent requests can both miss the same key and both
# pay for the load, split and index - the exact spike the cache exists to prevent,
# and most likely when the GUI fires several /api/search calls as you type.
_ARM_LOCK = threading.Lock()


def _clamp(name, value, fallback):
    """Hold a client-supplied param inside the range the UI actually offers.

    /api/search takes arbitrary JSON, not just whatever the sliders sent, so an
    unclamped chunk_size would let a caller demand a very expensive split and mint
    a fresh cache entry for it. Clamping keeps the work bounded and the key space
    finite at the same time.
    """
    spec = next((p for p in PARAMS if p["name"] == name), None)
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    if spec and spec.get("kind") == "range":
        return max(int(spec["min"]), min(int(spec["max"]), number))
    return number


def _arms_for(size, overlap, lc):
    """Chunks and built retrievers for these settings, computed once per setting."""
    key = (size, overlap, lc is not None)
    with _ARM_LOCK:
        cached = _ARM_CACHE.get(key)
        if cached is not None:
            _ARM_CACHE.move_to_end(key)
            return cached
        hand_chunks = handrolled.split(handrolled.load(), size, overlap)
        entry = {
            "hand_chunks": hand_chunks,
            "hand_retriever": handrolled.build_retriever(hand_chunks),
            "lc_chunks": None,
            "lc_retriever": None,
        }
        if lc is not None:
            lc_chunks = lc.split(lc.load(), size, overlap)
            entry["lc_chunks"] = lc_chunks
            entry["lc_retriever"] = lc.bm25_retriever(lc_chunks, MAX_TOP_K)
        _ARM_CACHE[key] = entry
        while len(_ARM_CACHE) > _ARM_CACHE_MAX:
            _ARM_CACHE.popitem(last=False)  # drop the least recently used
        return entry


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

    size = _clamp("chunk_size", values.get("chunk_size"), SETTINGS["chunk_size"])
    overlap = _clamp("chunk_overlap", values.get("chunk_overlap"), SETTINGS["chunk_overlap"])
    k = _clamp("top_k", values.get("top_k"), SETTINGS["top_k"])
    if overlap >= size:
        overlap = max(0, size // 4)

    lc = _import_langchain()
    arms = _arms_for(size, overlap, lc)
    hand_chunks = arms["hand_chunks"]
    hand_hits = handrolled.retrieve(arms["hand_retriever"], query, k)
    hand_sources = handrolled.sources(hand_hits)

    if lc is None:
        return {
            "arms": [{"label": "hand-rolled (Lesson 1)", "ranking": hand_sources}],
            "blocks": [{"kind": "note",
                        "text": "LangChain is not installed, so only the hand-rolled arm ran. "
                                f"Install it with: {langchain_rag.INSTALL_HINT}"}],
        }

    lc_chunks = arms["lc_chunks"]
    # The cached retriever is shared, and Flask may serve requests on several
    # threads, so slice its widest result rather than mutating its `k`. Ranking is
    # score-descending, so the first k of a top-MAX_TOP_K list is the top k.
    lc_hits = arms["lc_retriever"].invoke(query)[:k]
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
