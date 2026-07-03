"""Lesson 6 - interactive repo-aware assistant (experiment locally).

Ask a question about the sample repo under `data/repo/`. The assistant answers
**only from indexed lines**, always citing `path:start-end`, and says **not
found** when nothing clears the score gate. Move the sliders (retriever top_k,
the minimum score to answer) or flip on **plan mode** to get a plan-before-edit
instead of an answer - the same index/retrieve/answer the one-shot `demo` and the
test use.

Run:  ./run -l 6        (or:  ./run -l 6 web)
"""

import sys
from pathlib import Path

# Reach the shared GUI scaffold under tools/ (this file runs with cwd = the lesson
# dir, so locate the repo root from the file path, not the working directory).
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

from lesson_web import serve  # noqa: E402  (sys.path set up above)

from repo_assistant import (  # noqa: E402
    answer,
    build_index,
    cite,
    plan,
    retrieve,
)

FILES, CHUNKS = build_index()

# Defaults match the demo/test config, so the page opens on the same answers.
PARAMS = [
    {"name": "top_k", "label": "Retriever top_k - passages considered per question",
     "kind": "range", "min": 1, "max": 6, "step": 1, "default": 3},
    {"name": "min_score", "label": "Minimum score to answer - below this the assistant abstains",
     "kind": "range", "min": 1, "max": 4, "step": 1, "default": 2},
    {"name": "plan_mode", "label": "Plan mode - return a plan-before-edit instead of an answer",
     "kind": "toggle", "default": False},
]

EXAMPLES = [
    {"label": "Where is chunking implemented?", "query": "where is chunking implemented"},
    {"label": "Which tests cover the retriever?", "query": "which tests cover the retriever"},
    {"label": "Where to add a provider? (try plan mode)", "query": "where should i add a new embedding provider"},
    {"label": "Off-repo question (abstains)", "query": "how do i configure kubernetes autoscaling"},
]


def _retrieved_table(query, top_k, min_score):
    hits = retrieve(query, CHUNKS, top_k)
    rows = []
    for i, (s, c) in enumerate(hits):
        rows.append([
            {"v": cite(c), "cls": "text"},
            {"v": str(s), "cls": "num" if s >= min_score else "miss"},
            {"v": "top" if i == 0 else "", "cls": "num" if i == 0 else "text"},
            {"v": c["first_line"], "cls": "text"},
        ])
    return {"kind": "table", "title": "Retrieved passages (each a citation)",
            "columns": ["path:lines", "score", "", "first line"], "rows": rows}


def _answer_view(query, top_k, min_score):
    result = answer(query, CHUNKS, top_k, min_score)
    if result["kind"] == "grounded":
        arms = [{"label": "Cited answer", "ranking": [result["line"], "  " + result["citation"]],
                 "highlight": True}]
        stats = {"kind": "stats", "items": [
            {"v": str(result["score"]), "l": "top score"},
            {"v": str(len(result["sources"])), "l": "sources cited"},
            {"v": "GROUNDED", "l": "verdict"},
        ]}
        note_text = ("The answer is the top passage's first line and nothing else - grounded in "
                     "indexed repository lines and cited by path and line range. Drop min_score or "
                     "raise top_k to change what clears the gate.")
    else:
        arms = [{"label": "Cited answer", "ranking": ["NOT FOUND - the assistant abstains"],
                 "highlight": True}]
        stats = {"kind": "stats", "items": [
            {"v": str(result["best"]), "l": "best score"},
            {"v": str(min_score), "l": "min to answer"},
            {"v": "NOT FOUND", "l": "verdict"},
        ]}
        note_text = ("Nothing in the repo scored the minimum, so the assistant says not found "
                     "instead of inventing an answer. Lower min_score to force a (weaker) answer "
                     "and see why the gate matters.")
    return {"arms": arms, "blocks": [stats, _retrieved_table(query, top_k, min_score),
                                     {"kind": "note", "text": note_text}]}


def _plan_view(query, top_k, min_score):
    result = plan(query, FILES, CHUNKS, top_k)
    if result["kind"] != "plan":
        return {"arms": [{"label": "Plan", "ranking": ["NOT FOUND - nothing to plan against"],
                          "highlight": True}],
                "blocks": [{"kind": "note", "text": "No passage matched, so there is nothing to "
                            "ground a plan in. The assistant will not invent a change."}]}
    steps = {"kind": "table", "title": "Plan-before-edit (no files changed)",
             "columns": ["step", "grounded in"], "rows": [
                 [{"v": "1. relevant files", "cls": "text"}, {"v": " . ".join(result["relevant"]), "cls": "text"}],
                 [{"v": "2. current behaviour", "cls": "text"}, {"v": result["behaviour"]["citation"], "cls": "text"}],
                 [{"v": "3. minimal change", "cls": "text"}, {"v": result["change"], "cls": "text"}],
                 [{"v": "4. update tests", "cls": "text"}, {"v": result["tests"], "cls": "text"}],
                 [{"v": "5. update docs", "cls": "text"}, {"v": result["docs"], "cls": "text"}],
             ]}
    arms = [{"label": "Plan", "ranking": [result["behaviour"]["line"], "  " + result["behaviour"]["citation"]],
             "highlight": True}]
    note = {"kind": "note", "text": ("The plan cites the current behaviour and lists which tests and "
            "docs to touch - but it edits nothing. Plan first, approve, then edit.")}
    return {"arms": arms, "blocks": [steps, _retrieved_table(query, top_k, min_score), note]}


def search(query, values):
    query = (query or "").strip()
    top_k = int(values["top_k"])
    min_score = int(values["min_score"])
    if not query:
        return {"arms": [{"label": "Ask the repo", "ranking": ["Type a question, or pick an example."],
                          "highlight": True}],
                "blocks": [{"kind": "note", "text": "The assistant answers only from lines indexed "
                            "under data/repo/, always with a citation, and abstains when nothing "
                            "clears the score gate."}]}
    if values["plan_mode"]:
        return _plan_view(query, top_k, min_score)
    return _answer_view(query, top_k, min_score)


def main():
    serve(
        title="Lesson 6 - repo-aware assistant: answer from the repo, with citations",
        subtitle="Ask about the sample repo. Every answer is grounded in indexed lines and cited; "
                 "off-repo questions are refused. Flip on plan mode for a plan-before-edit.",
        hint="Pick an example or type a question. Move top_k / min_score, or turn on plan mode - "
             "the same index the demo and test use.",
        params=PARAMS,
        examples=EXAMPLES,
        search=search,
    )


if __name__ == "__main__":
    main()
