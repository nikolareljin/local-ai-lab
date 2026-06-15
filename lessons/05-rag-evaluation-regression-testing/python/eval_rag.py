"""Lesson 5 - RAG evaluation & regression testing demo (Python).

"Seems good" is not a metric. This demo turns the quality of a RAG pipeline into
**numbers you can track**: a small **golden set** of questions (each with the
document that *should* be retrieved and the keywords a correct answer must
contain) scored on three axes —

  - retrieval recall@k : was the gold document in the top-k results?
  - groundedness       : is every claim in the answer supported by the context?
  - answer correctness : does the answer contain the expected facts?

A question PASSES only if all three clear their thresholds; the **gate** passes
only if every question passes. We run two configs over the same golden set: a
BASELINE that clears the gate, and a CANDIDATE — a reasonable-looking tweak
(smaller top_k, an answer that pads in an unsupported sentence) that *looks* fine
but silently regresses two of the numbers. The eval catches it.

Dependency-free and offline: the retriever, the answerer stand-in and the metrics
are implemented identically in the Node and .NET ports, so all three produce the
same output.

Run:  python eval_rag.py

PRODUCTION (see the lesson README, "From demo to production"):
- the answerer here is a deterministic extractive stand-in so the lesson is
  reproducible; swap in your real pipeline and keep the golden set + the gate.
"""

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Common words dropped before scoring so retrieval and groundedness key on the
# meaningful terms. Kept identical across the Python, Node and .NET ports.
STOPWORDS = {
    "a", "an", "the", "to", "of", "do", "i", "in", "on", "is", "are",
    "and", "my", "your", "you", "they", "their", "it", "we",
}

# A hallucinated sentence the CANDIDATE answerer pads onto every answer. None of
# its content terms appear anywhere in the corpus, so groundedness drops.
UNSUPPORTED = "A complimentary gift card will be mailed separately."


def tokenize(text):
    return re.findall(r"[a-z0-9_]+", text.lower())


def terms(text):
    """Distinct meaningful (non-stopword) tokens of `text`."""
    return {t for t in tokenize(text) if t not in STOPWORDS}


def load_docs():
    docs = []
    for path in sorted(DATA_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        docs.append({"name": path.name, "raw": raw, "tokens": set(tokenize(raw))})
    return docs


def load_golden():
    with open(DATA_DIR / "golden.json", encoding="utf-8") as fh:
        return json.load(fh)


# --- Retrieval: distinct-term overlap, minus stopwords (deterministic) -------
def retrieve(query, docs, top_k):
    """Top-k docs by how many distinct meaningful query terms they contain.
    Deterministic: score desc, then name asc; zero-overlap docs are dropped."""
    q = terms(query)
    scored = []
    for d in docs:
        score = len(q & d["tokens"])
        if score > 0:
            scored.append((score, d))
    scored.sort(key=lambda s: (-s[0], s[1]["name"]))
    return [d for _, d in scored[:top_k]]


# --- Answerer: a deterministic, offline extractive stand-in ------------------
def first_body_line(doc):
    """The first non-heading, non-blank line of a doc (its one fact)."""
    for line in doc["raw"].splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return ""


def answer(retrieved, pad_unsupported=False):
    """Extractive answer: the fact from the top retrieved doc. With
    `pad_unsupported`, append a sentence that is *not* in any document — a
    stand-in for a model that pads its answer with an unsupported claim."""
    if not retrieved:
        return ""
    text = first_body_line(retrieved[0])
    if pad_unsupported:
        text = (text + " " + UNSUPPORTED).strip()
    return text


# --- The three metrics -------------------------------------------------------
def recall_at_k(gold_docs, retrieved):
    """Fraction of the gold documents that made it into the retrieved set."""
    if not gold_docs:
        return 1.0
    names = {d["name"] for d in retrieved}
    hit = sum(1 for g in gold_docs if g in names)
    return hit / len(gold_docs)


def groundedness(answer_text, retrieved):
    """Fraction of the answer's meaningful terms that appear in the retrieved
    context. An unsupported (hallucinated) claim drags this below 1.0."""
    a = terms(answer_text)
    if not a:
        return 1.0
    context = set()
    for d in retrieved:
        context |= terms(d["raw"])
    return len(a & context) / len(a)


def correctness(answer_text, keywords):
    """Fraction of the expected-answer keywords present in the answer."""
    if not keywords:
        return 1.0
    toks = set(tokenize(answer_text))
    hit = sum(1 for k in keywords if k in toks)
    return hit / len(keywords)


# --- One config over the whole golden set ------------------------------------
def evaluate(golden, docs, config):
    """Score every golden question under `config` and aggregate the result.
    `config` = {"name", "top_k", "pad_unsupported"}."""
    thr = golden["thresholds"]
    rows = []
    for q in golden["questions"]:
        retrieved = retrieve(q["question"], docs, config["top_k"])
        ans = answer(retrieved, config["pad_unsupported"])
        rec = recall_at_k(q["gold_docs"], retrieved)
        gnd = groundedness(ans, retrieved)
        cor = correctness(ans, q["answer_keywords"])
        passed = rec >= 1.0 and gnd >= thr["groundedness"] and cor >= thr["correctness"]
        rows.append({"id": q["id"], "recall": rec, "groundedness": gnd,
                     "correctness": cor, "passed": passed, "answer": ans})
    n = len(rows)
    agg = {
        "mean_recall": sum(r["recall"] for r in rows) / n,
        "mean_groundedness": sum(r["groundedness"] for r in rows) / n,
        "mean_correctness": sum(r["correctness"] for r in rows) / n,
        "pass_count": sum(1 for r in rows if r["passed"]),
        "total": n,
    }
    return {"config_name": config["name"], "rows": rows, "aggregate": agg,
            "gate_passed": agg["pass_count"] == n}


# Two configs that tell the regression story.
BASELINE = {"name": "baseline", "top_k": 3, "pad_unsupported": False}
CANDIDATE = {"name": "candidate", "top_k": 1, "pad_unsupported": True}


# --- Reporting (byte-identical across the three ports) -----------------------
def pct(x):
    return "%.2f" % x


def gate_word(passed):
    return "PASS" if passed else "FAIL"


def print_report(result, config):
    flags = "top_k=%d, padding=%s" % (config["top_k"], "on" if config["pad_unsupported"] else "off")
    print("\nConfig: %s  (%s)" % (result["config_name"], flags))
    print("  id               recall  grounded  correct  result")
    for r in result["rows"]:
        print("  %-15s   %s      %s     %s  %s"
              % (r["id"], pct(r["recall"]), pct(r["groundedness"]),
                 pct(r["correctness"]), gate_word(r["passed"])))
    agg = result["aggregate"]
    print("  Aggregate: recall %s  grounded %s  correct %s   %d/%d passed   GATE: %s"
          % (pct(agg["mean_recall"]), pct(agg["mean_groundedness"]),
             pct(agg["mean_correctness"]), agg["pass_count"], agg["total"],
             gate_word(result["gate_passed"])))


def print_regression(base, cand, groundedness_threshold):
    b, c = base["aggregate"], cand["aggregate"]

    def line(label, bv, cv, note=""):
        print("  %-18s %s -> %s   (%+.2f)%s"
              % (label, pct(bv), pct(cv), cv - bv, note))

    print("\nRegression vs baseline:")
    line("mean recall:", b["mean_recall"], c["mean_recall"])
    below = "   below threshold %s" % pct(groundedness_threshold) \
        if c["mean_groundedness"] < groundedness_threshold else ""
    line("mean groundedness:", b["mean_groundedness"], c["mean_groundedness"], below)
    line("mean correctness:", b["mean_correctness"], c["mean_correctness"])
    print("  %-18s %s -> %s" % ("gate:", gate_word(base["gate_passed"]),
                                gate_word(cand["gate_passed"])))


def main():
    docs = load_docs()
    golden = load_golden()
    base = evaluate(golden, docs, BASELINE)
    cand = evaluate(golden, docs, CANDIDATE)
    print_report(base, BASELINE)
    print_report(cand, CANDIDATE)
    print_regression(base, cand, golden["thresholds"]["groundedness"])


if __name__ == "__main__":
    main()
