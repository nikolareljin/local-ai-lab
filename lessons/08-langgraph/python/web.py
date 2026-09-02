"""Lesson 8 - the playground: watch the loop iterate, and watch it stop for you.

The demo prints one fixed run. This page lets you move the settings and watch the
control flow change shape underneath them.

Two controls are worth reaching for first:

  Grade threshold   at 0.0 nothing is ever weak, so the graph never loops - it IS
                    Lesson 7's linear chain. At 1.0 everything loops to the cap
                    and abstains. Everything interesting is in between.
  Rewrite query     turn it OFF and the loop still runs, but re-searches the SAME
                    query every time. A cycle that cannot change its own input is
                    just a slower chain, and this is the fastest way to feel that.

And one that has no equivalent in Lesson 7: **Human review**. Leave it on `pause`
and the run stops mid-graph and shows you what it wants to answer from. Move it to
`approve` and watch the retrieval count NOT go up - the graph resumed, it did not
start again.

Launch it with:  ./run -l 8
"""

import sys
import threading
from collections import OrderedDict
from pathlib import Path

# this file -> python -> 08-langgraph -> lessons -> repo root (parents is 0-indexed)
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import graders  # noqa: E402
import langgraph_agent as agent  # noqa: E402
import loop_agent  # noqa: E402
import rag_core  # noqa: E402
import rewriter  # noqa: E402
from lesson_web import serve  # noqa: E402

SETTINGS = rag_core.load_questions()
MAX_TOP_K = 6

PARAMS = [
    {"name": "top_k", "label": "Top k", "kind": "range",
     "min": 1, "max": MAX_TOP_K, "step": 1, "default": SETTINGS["top_k"]},
    {"name": "threshold", "label": "Grade threshold", "kind": "range",
     "min": 0.0, "max": 1.0, "step": 0.05, "default": SETTINGS["grade_threshold"]},
    {"name": "max_attempts", "label": "Max attempts (your cap)", "kind": "range",
     "min": 1, "max": 4, "step": 1, "default": SETTINGS["max_attempts"]},
    {"name": "rewrite", "label": "Rewrite the query between attempts", "kind": "toggle",
     "default": True},
    # The shared GUI has sliders and toggles but no select, so the three review
    # decisions are three stops on one slider. It carries the whole interrupt
    # story: 0 pauses, 1 approves, 2 refuses.
    {"name": "review_decision", "label": "Human review:  0 pause · 1 approve · 2 veto",
     "kind": "range", "min": 0, "max": 2, "step": 1, "default": 0},
    {"name": "show_state", "label": "Show the checkpoint", "kind": "toggle",
     "default": False},
]

EXAMPLES = [
    {"label": "Passes first try", "query": "What is the factory reset procedure?"},
    {"label": "Vocabulary - watch it loop",
     "query": "The light is orange and it will not connect."},
    {"label": "Acronym - one rewrite fixes it", "query": "What paperwork does an RMA need?"},
    {"label": "Notation - 5GHz vs five gigahertz", "query": "Is 5GHz supported?"},
    {"label": "False alarm - the loop pays for nothing", "query": "Can I mount it sideways?"},
    {"label": "Not in the corpus - watch it give up", "query": "What is the MTBF?"},
]

DECISIONS = {0: "pause", 1: "approve", 2: "veto"}

# The GUI calls /api/search on every keystroke and slider move. Re-indexing the
# corpus each time would be sluggish and would contradict the "build the index
# once" contract the rest of the lesson pins with tests.
_LOCK = threading.Lock()
_RETRIEVER = None
# Live graph threads, keyed by everything that changes what the RUN does. The
# review decision is deliberately NOT in the key: that is what lets moving the
# decision slider resume the SAME paused checkpoint instead of starting a new one.
_THREADS: "OrderedDict[tuple, tuple]" = OrderedDict()
_MAX_THREADS = 32


def _clamp(value, low, high, default):
    """Never trust a number from the browser: /api/search takes arbitrary JSON."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def retriever():
    global _RETRIEVER
    with _LOCK:
        if _RETRIEVER is None:
            _RETRIEVER = rag_core.build_retriever(SETTINGS["chunk_size"],
                                                  SETTINGS["chunk_overlap"])
        return _RETRIEVER


def _graph_thread(key, ga, grader, rw, top_k, max_attempts, question):
    """Get or create the paused graph run for this exact configuration.

    The retriever is resolved BEFORE the lock is taken. `retriever()` takes the
    same lock, and `threading.Lock` is not reentrant, so building it inside here
    would deadlock the request thread - which it did, once.
    """
    index = retriever()
    with _LOCK:
        if key in _THREADS:
            _THREADS.move_to_end(key)
            return _THREADS[key]
        graph = ga.build_graph(
            grader=grader, rewriter=rw, top_k=top_k, max_attempts=max_attempts,
            human_review=True,
            generate=lambda q, d: "(a grounded answer would be generated here)",
            checkpointer=ga.memory_saver())
        thread_id = f"web-{abs(hash(key))}"
        config = {"configurable": {"thread_id": thread_id}}
        first = ga.run(graph, index, question, config=config)
        _THREADS[key] = (graph, config, first)
        while len(_THREADS) > _MAX_THREADS:
            _THREADS.popitem(last=False)
        return _THREADS[key]


def search(query, values):
    if not query:
        return {"arms": [], "blocks": [{"kind": "note", "text": "Ask the sensor something."}]}

    top_k = int(_clamp(values.get("top_k"), 1, MAX_TOP_K, SETTINGS["top_k"]))
    threshold = _clamp(values.get("threshold"), 0.0, 1.0, SETTINGS["grade_threshold"])
    max_attempts = int(_clamp(values.get("max_attempts"), 1, 4, SETTINGS["max_attempts"]))
    do_rewrite = bool(values.get("rewrite", True))
    decision = DECISIONS[int(_clamp(values.get("review_decision"), 0, 2, 0))]
    show_state = bool(values.get("show_state", False))

    grader = graders.CoverageGrader(threshold)
    rw = rewriter.GlossaryRewriter() if do_rewrite else _NoRewriter()

    linear = loop_agent.run_linear(retriever(), query, top_k=top_k)
    loop = loop_agent.run(retriever(), query, grader=grader, rewriter=rw,
                          top_k=top_k, max_attempts=max_attempts)

    blocks = [{
        "kind": "stats",
        "items": [
            {"v": str(loop["attempts"]), "l": "attempts"},
            {"v": str(loop["retrievals"]), "l": "retrieval calls"},
            {"v": f"{loop['grade']['score']:.2f}" if loop["grade"] else "-", "l": "final coverage"},
            {"v": loop["status"], "l": "outcome"},
        ],
    }]

    rows = _attempt_rows(query, grader, rw, top_k, max_attempts)
    blocks.append({
        "kind": "table", "title": "Every attempt",
        "columns": ["#", "query used", "coverage", "verdict", "top source"],
        "rows": rows,
    })

    if loop["attempts"] > 1 and do_rewrite:
        blocks.append(_rewrite_block(query, grader, rw, top_k))
    elif not do_rewrite and loop["status"] == "abstained":
        blocks.append({"kind": "note", "text":
                       "Rewrite is OFF. The grader said this evidence was weak, and with no way "
                       "to change the query there was nothing left to try, so the loop gave up "
                       "after one attempt. A cycle that cannot change its own input is not a "
                       "cycle - it is a chain that runs slower. Turn Rewrite back on and watch "
                       "the same question get answered."})

    blocks.extend(_review_blocks(query, grader, rw, top_k, max_attempts, decision,
                                 threshold, do_rewrite, show_state))

    if threshold <= 0.0:
        blocks.append({"kind": "note", "text":
                       "Threshold is 0, so nothing is ever graded weak and the graph never "
                       "loops. This is Lesson 7's linear chain, reached by moving a slider."})
    if max_attempts == 1:
        blocks.append({"kind": "note", "text":
                       "Max attempts is 1, so there is no second pass. Same destination as "
                       "threshold 0, by a different route: graph and chain are a continuum "
                       "you configure, not two different products."})

    return {
        "arms": [
            {"label": "linear - retrieve once (Lesson 7)", "ranking": linear["sources"]},
            {"label": f"corrective loop - {loop['attempts']} attempt(s)",
             "ranking": loop["sources"] or ["(abstained - nothing grounded it)"],
             "highlight": True},
        ],
        "blocks": blocks,
    }


class _NoRewriter:
    """Deliberately useless: it hands the same query back, so the loop spins in place."""

    name = "none"

    def rewrite(self, question, query, missing):
        return query


def _attempt_rows(question, grader, rw, top_k, max_attempts):
    """Replay the loop one attempt at a time so each cycle becomes a row."""
    rows = []
    query, attempt = question, 1
    while True:
        docs = rag_core.retrieve(retriever(), query, top_k)
        grade = grader.grade(question, query, docs)
        src = rag_core.sources(docs)
        weak = grade["verdict"] == "weak"
        rows.append([
            {"v": str(attempt), "cls": "num"},
            {"v": query[:60], "cls": "text"},
            {"v": f"{grade['score']:.2f}", "cls": "miss" if weak else "num"},
            {"v": grade["verdict"], "cls": "miss" if weak else "text"},
            {"v": src[0] if src else "-", "cls": "text"},
        ])
        if not weak or attempt >= max_attempts:
            break
        new_query = rw.rewrite(question, query, grade["missing"])
        if new_query == query:
            break
        query, attempt = new_query, attempt + 1
    return rows


def _rewrite_block(question, grader, rw, top_k):
    docs = rag_core.retrieve(retriever(), question, top_k)
    grade = grader.grade(question, question, docs)
    rewritten = rw.rewrite(question, question, grade["missing"])
    items = []
    for term in rag_core.content_terms(question):
        gone = term in grade["missing"]
        items.append({"text": term, "note": "not in any chunk" if gone else "found",
                      "muted": gone})
    for term in rag_core.content_terms(rewritten):
        if term not in rag_core.content_terms(question):
            items.append({"text": term, "note": "added from the glossary", "muted": False})
    return {"kind": "tokens", "title": "What the rewriter changed", "items": items}


def _review_blocks(question, grader, rw, top_k, max_attempts, decision,
                   threshold, do_rewrite, show_state):
    ga = agent.import_graph_agent()
    if ga is None:
        return [{"kind": "note", "text":
                 "LangGraph is not installed, so the pause-and-resume half of this page is "
                 "off. Everything above is the while-loop arm, which needs no dependency. "
                 f"To switch it on: {agent.INSTALL_HINT}"}]
    key = (question, top_k, round(threshold, 3), max_attempts, do_rewrite)
    graph, config, paused = _graph_thread(key, ga, grader, rw, top_k, max_attempts, question)
    blocks = []
    if paused["status"] != "paused":
        blocks.append({"kind": "note", "text":
                       f"This run finished without stopping ({paused['status']}) - there was "
                       "nothing to approve."})
    elif decision == "pause":
        payload = paused["__interrupt__"][0].value
        evidence = "".join(f"\n  - {s[:140]}..." for s in payload["evidence"])
        blocks.append({"kind": "note", "text":
                       "PAUSED. The graph stopped before generating and is waiting for a "
                       f"human.\n\nIt wants to answer from {payload['citations']} after "
                       f"{payload['attempts']} attempt(s), having searched "
                       f"{payload['query_used']!r}.{evidence}\n\nMove **Human review** to 1 to "
                       "approve or 2 to veto. It is waiting, not restarting - watch the "
                       "retrieval count when you do."})
    else:
        resumed = ga.run(graph, retriever(), question, config=config, resume=decision)
        blocks.append({"kind": "stats", "items": [
            {"v": str(paused["retrievals"]), "l": "retrievals when paused"},
            {"v": str(resumed["retrievals"]), "l": "retrievals after resume"},
            {"v": resumed["status"], "l": "outcome"},
        ]})
        if resumed["retrievals"] == paused["retrievals"]:
            blocks.append({"kind": "note", "text":
                           "Those two numbers are the same, and that is the whole point of a "
                           "checkpoint: the graph picked up where it stopped instead of "
                           "starting the question again."})
        if decision == "veto":
            blocks.append({"kind": "note", "text":
                           "Vetoed. `generate` never ran, so no answer was ever produced - "
                           "which is a different thing from producing one and hiding it."})
    if show_state:
        snap = graph.get_state(config)
        trace = "".join(f"\n  {ln}" for ln in snap.values.get("trace", []))
        blocks.append({"kind": "tokens", "title": "The checkpoint", "items": [
            {"text": f"thread_id={config['configurable']['thread_id']}",
             "note": "", "muted": False},
            {"text": f"next={snap.next}", "note": "where it is standing", "muted": False},
            {"text": f"retrievals={snap.values.get('retrievals', 0)}", "note": "", "muted": False},
            {"text": f"attempt={snap.values.get('attempt', 1)}", "note": "", "muted": False},
        ]})
        blocks.append({"kind": "note", "text": f"trace:{trace}"})
    return blocks


def main():
    serve(
        title="Lesson 8 · A stateful agent with LangGraph",
        subtitle="Watch a corrective loop iterate - then stop it mid-run and decide yourself.",
        hint="Try 'The light is orange and it will not connect.', then drag Grade threshold "
             "to 0 and watch the graph collapse into Lesson 7's chain.",
        params=PARAMS,
        examples=EXAMPLES,
        search=search,
    )


if __name__ == "__main__":
    main()
