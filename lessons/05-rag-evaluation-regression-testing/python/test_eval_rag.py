"""Offline test for the Lesson 5 RAG-evaluation demo (Python).

Encodes the lesson's claims:
- the baseline config clears the gate (every golden question passes),
- the candidate config fails it,
- the candidate regresses two *specific tracked numbers* — mean recall and mean
  groundedness — below where the baseline sits,
- groundedness flags an answer padded with an unsupported sentence,
- recall@k drops for the question whose gold doc ranks 2nd when k shrinks 3 -> 1,
- correctness counts the expected keywords, and the aggregate is the mean.

Run:  python -m pytest test_eval_rag.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_rag import (
    BASELINE,
    CANDIDATE,
    answer,
    correctness,
    evaluate,
    groundedness,
    load_docs,
    load_golden,
    retrieve,
)


def _setup():
    return load_golden(), load_docs()


def test_baseline_clears_the_gate():
    golden, docs = _setup()
    base = evaluate(golden, docs, BASELINE)
    assert base["gate_passed"] is True
    assert all(r["passed"] for r in base["rows"])
    assert base["aggregate"]["mean_recall"] == 1.0
    assert base["aggregate"]["mean_groundedness"] == 1.0
    assert base["aggregate"]["pass_count"] == base["aggregate"]["total"]


def test_candidate_fails_the_gate():
    golden, docs = _setup()
    cand = evaluate(golden, docs, CANDIDATE)
    assert cand["gate_passed"] is False
    assert cand["aggregate"]["pass_count"] == 0


def test_candidate_regresses_recall_and_groundedness():
    golden, docs = _setup()
    base = evaluate(golden, docs, BASELINE)["aggregate"]
    cand = evaluate(golden, docs, CANDIDATE)["aggregate"]
    thr = golden["thresholds"]
    # The two tracked numbers that moved.
    assert cand["mean_recall"] < base["mean_recall"]
    assert cand["mean_groundedness"] < thr["groundedness"] <= base["mean_groundedness"]
    # Correctness did NOT move — a fluent answer can still hit the keywords while
    # being ungrounded; that is exactly why groundedness earns its place.
    assert cand["mean_correctness"] == base["mean_correctness"] == 1.0


def test_groundedness_flags_an_unsupported_sentence():
    golden, docs = _setup()
    retrieved = retrieve("how long do refunds take to arrive", docs, top_k=3)
    grounded = answer(retrieved, pad_unsupported=False)
    padded = answer(retrieved, pad_unsupported=True)
    assert groundedness(grounded, retrieved) == 1.0
    assert groundedness(padded, retrieved) < 1.0
    # The padded terms are absent from the retrieved context.
    context = " ".join(d["raw"].lower() for d in retrieved)
    assert "complimentary" not in context and "separately" not in context


def test_recall_drops_when_k_shrinks():
    golden, docs = _setup()
    q = "how do i reset my password"  # gold doc ranks 2nd, behind a distractor
    names_k3 = {d["name"] for d in retrieve(q, docs, top_k=3)}
    names_k1 = {d["name"] for d in retrieve(q, docs, top_k=1)}
    assert "password_reset.md" in names_k3
    assert "password_reset.md" not in names_k1
    # ...and the per-question recall reflects it across the two configs.
    base_row = next(r for r in evaluate(golden, docs, BASELINE)["rows"] if r["id"] == "reset-password")
    cand_row = next(r for r in evaluate(golden, docs, CANDIDATE)["rows"] if r["id"] == "reset-password")
    assert base_row["recall"] == 1.0 and cand_row["recall"] == 0.0


def test_correctness_counts_expected_keywords():
    assert correctness("reset your password from the sign-in page", ["reset", "password", "sign"]) == 1.0
    assert correctness("reset your password", ["reset", "password", "sign", "link"]) == 0.5
    assert correctness("nothing relevant here", ["reset", "password"]) == 0.0


def test_aggregate_is_mean_over_questions():
    golden, docs = _setup()
    result = evaluate(golden, docs, CANDIDATE)
    rows = result["rows"]
    agg = result["aggregate"]
    assert agg["mean_recall"] == sum(r["recall"] for r in rows) / len(rows)
    assert agg["mean_groundedness"] == sum(r["groundedness"] for r in rows) / len(rows)
    assert agg["mean_correctness"] == sum(r["correctness"] for r in rows) / len(rows)
