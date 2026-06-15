"""Lesson 5 - interactive RAG-evaluation GUI (experiment locally).

Leave the box empty to see the **whole golden set** scored as one card — mean
recall, groundedness and correctness, and whether the **gate** passes. Pick a
golden question to drill into its three numbers, the expected keywords it did or
did not hit, and what each retrieved document contributed. Then move the sliders
(top_k, the groundedness and correctness gates) or flip on **unsupported
padding** and watch a number cross its threshold — the same `evaluate` the
one-shot `demo` and the test use.

Run:  ./run -l 5        (or:  ./run -l 5 web)
"""

import copy
import re
import sys
from pathlib import Path

# Reach the shared GUI scaffold under tools/ (this file runs with cwd = the lesson
# dir, so locate the repo root from the file path, not the working directory).
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

from lesson_web import serve  # noqa: E402  (sys.path set up above)

from eval_rag import (  # noqa: E402
    UNSUPPORTED,
    answer,
    correctness,
    evaluate,
    groundedness,
    load_docs,
    load_golden,
    recall_at_k,
    retrieve,
    terms,
)

DOCS = load_docs()
GOLDEN = load_golden()

# Defaults match the BASELINE config the demo and test pin, so the page opens on
# the all-green scorecard. Move them to watch a number cross its gate.
PARAMS = [
    {"name": "top_k", "label": "Retriever top_k — documents fed to the answerer",
     "kind": "range", "min": 1, "max": 5, "step": 1, "default": 3},
    {"name": "groundedness_threshold", "label": "Groundedness gate — answer terms found in context",
     "kind": "range", "min": 0.0, "max": 1.0, "step": 0.05, "default": 0.75},
    {"name": "correctness_threshold", "label": "Correctness gate — expected keywords present",
     "kind": "range", "min": 0.0, "max": 1.0, "step": 0.05, "default": 0.5},
    {"name": "pad_unsupported", "label": "Pad the answer with an unsupported sentence (a candidate regression)",
     "kind": "toggle", "default": False},
]

EXAMPLES = [
    {"label": "Whole golden set (the scorecard)", "query": ""},
    {"label": "Refund window (gold ranks 1st)", "query": "how long do refunds take to arrive"},
    {"label": "Reset password (gold ranks 2nd)", "query": "how do i reset my password"},
    {"label": "Warranty length", "query": "how long is the warranty"},
]


def _tok(text):
    return re.findall(r"[a-z0-9_]+", (text or "").lower())


def _config(values):
    return {"name": "live", "top_k": int(values["top_k"]),
            "pad_unsupported": bool(values["pad_unsupported"])}


def _golden_with_thresholds(values):
    """A copy of the golden set whose gate uses the slider thresholds live."""
    g = copy.deepcopy(GOLDEN)
    g["thresholds"]["groundedness"] = values["groundedness_threshold"]
    g["thresholds"]["correctness"] = values["correctness_threshold"]
    return g


def _verdict(passed):
    return "PASS" if passed else "FAIL"


def _scorecard(values):
    """Empty query: score the entire golden set as one card."""
    result = evaluate(_golden_with_thresholds(values), DOCS, _config(values))
    agg = result["aggregate"]
    gt, ct = values["groundedness_threshold"], values["correctness_threshold"]

    ranking = ["%s — %s" % (r["id"], _verdict(r["passed"])) for r in result["rows"]]
    arms = [{"label": "Golden-set scorecard", "ranking": ranking, "highlight": True}]

    stats = {"kind": "stats", "items": [
        {"v": "%.2f" % agg["mean_recall"], "l": "mean recall@k"},
        {"v": "%.2f" % agg["mean_groundedness"], "l": "mean groundedness"},
        {"v": "%.2f" % agg["mean_correctness"], "l": "mean correctness"},
        {"v": "%d / %d" % (agg["pass_count"], agg["total"]), "l": "questions passed"},
        {"v": _verdict(result["gate_passed"]), "l": "gate"},
    ]}

    rows = []
    for r in result["rows"]:
        rows.append([
            {"v": r["id"], "cls": "text"},
            {"v": "%.2f" % r["recall"], "cls": "miss" if r["recall"] < 1.0 else "num"},
            {"v": "%.2f" % r["groundedness"], "cls": "miss" if r["groundedness"] < gt else "num"},
            {"v": "%.2f" % r["correctness"], "cls": "miss" if r["correctness"] < ct else "num"},
            {"v": _verdict(r["passed"]), "cls": "text"},
        ])
    table = {"kind": "table", "title": "Per-question scorecard",
             "columns": ["question", "recall", "grounded", "correct", "result"], "rows": rows}

    note = {"kind": "note", "text":
            "The gate passes only when every question passes. Drop top_k to 1 and the question whose "
            "gold document ranks second loses its recall; turn on unsupported padding and groundedness "
            "falls below its gate everywhere — each is a tracked number you would catch in CI."}
    return {"arms": arms, "blocks": [stats, table, note]}


def _drilldown(query, values):
    """A specific question: show its three numbers and what drove them."""
    cfg = _config(values)
    gt, ct = values["groundedness_threshold"], values["correctness_threshold"]
    gold = next((q for q in GOLDEN["questions"] if q["question"].lower() == query.lower()), None)

    retrieved = retrieve(query, DOCS, cfg["top_k"])
    ans = answer(retrieved, cfg["pad_unsupported"])
    gnd = groundedness(ans, retrieved)
    cor = correctness(ans, gold["answer_keywords"]) if gold else None
    rec = recall_at_k(gold["gold_docs"], retrieved) if gold else None
    passed = bool(gold and rec >= 1.0 and gnd >= gt and cor >= ct)

    arms = [{"label": "Extractive answer", "ranking": [ans or "(no document retrieved)"], "highlight": True}]

    items = [{"v": "%.2f" % rec if rec is not None else "n/a", "l": "recall@k"},
             {"v": "%.2f" % gnd, "l": "groundedness"},
             {"v": "%.2f" % cor if cor is not None else "n/a", "l": "correctness"},
             {"v": _verdict(passed) if gold else "n/a", "l": "result"}]
    blocks = [{"kind": "stats", "items": items}]

    if gold:
        ans_tokens = set(_tok(ans))
        kw_items = [{"text": k, "note": "found" if k in ans_tokens else "missing",
                     "muted": k not in ans_tokens} for k in gold["answer_keywords"]]
        blocks.append({"kind": "tokens", "title": "Expected keywords", "items": kw_items})

    if cfg["pad_unsupported"]:
        ctx = set()
        for d in retrieved:
            ctx |= terms(d["raw"])
        pad_items = [{"text": t, "note": "not in context", "muted": True}
                     for t in sorted(terms(UNSUPPORTED) - ctx)]
        if pad_items:
            blocks.append({"kind": "tokens",
                           "title": "Unsupported terms padded into the answer", "items": pad_items})

    ans_terms = terms(ans)
    rows = []
    for d in retrieved:
        is_gold = bool(gold and d["name"] in gold["gold_docs"])
        contributes = bool(ans_terms & terms(d["raw"]))
        rows.append([
            {"v": d["name"], "cls": "text"},
            {"v": ("yes" if is_gold else "no") if gold else "n/a",
             "cls": ("num" if is_gold else "miss") if gold else "text"},
            {"v": "yes" if contributes else "no", "cls": "num" if contributes else "miss"},
        ])
    blocks.append({"kind": "table", "title": "Retrieved documents",
                   "columns": ["document", "relevant (gold)?", "supports the answer?"], "rows": rows})

    if not gold:
        msg = ("This query is not in the golden set, so there is no labelled gold document to score "
               "recall or correctness against — only groundedness, which needs no labels.")
    elif passed:
        msg = ("All three numbers clear their gates, so this question passes. Shrink top_k or turn on "
               "padding to watch a number drop below its line.")
    elif rec < 1.0:
        msg = ("The gold document was not in the top-%d results, so recall is 0 — the answer is drawn "
               "from a higher-ranked distractor. Raise top_k to bring the gold document back."
               % cfg["top_k"])
    else:
        msg = ("The answer carries terms that appear in no retrieved document, so groundedness falls "
               "below its gate — a fluent answer that still smuggles in an unsupported claim.")
    blocks.append({"kind": "note", "text": msg})
    return {"arms": arms, "blocks": blocks}


def search(query, values):
    query = (query or "").strip()
    if not query:
        return _scorecard(values)
    return _drilldown(query, values)


def main():
    serve(
        title="Lesson 5 · RAG evaluation — turn “seems good” into a tracked number",
        subtitle="Score a golden set on recall@k, groundedness and correctness. Move the sliders or "
                 "pad the answer with an unsupported sentence and watch the gate flip.",
        hint="Leave the box empty for the whole-golden-set scorecard, or pick a question to drill in. "
             "Same evaluate() the demo and test use.",
        params=PARAMS,
        examples=EXAMPLES,
        search=search,
    )


if __name__ == "__main__":
    main()
