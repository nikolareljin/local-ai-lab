# Lesson 3 · Hybrid Retrieval & Reranking

**Install (Linux · macOS · Windows):** [guide](../../INSTALL.md)

> **Part of [local-ai-lab](https://nikolareljin.github.io/local-ai-lab/)** — a hands-on course for building local AI.
>
> **Course home:** https://nikolareljin.github.io/local-ai-lab/
> **Source:** https://github.com/nikolareljin/local-ai-lab
> **Author:** [Nik Reljin](https://www.linkedin.com/in/nikolareljin)
>
> **Lessons:** [1 · RAG](../../LESSON1.md) → [2 · MCP](../../LESSON2.md) → **3 · Hybrid retrieval (you are here)** → 4 · RAG safety → 5 · RAG evaluation → 6 · Repo assistant → 7 · LangChain → … → 15 · Docs from changes
>
> **Status: working demo.** Runnable in **Python, Node.js, and C# / .NET** — same algorithm, three
> languages, identical rankings. Runs 100% offline, no embedding model required. See *From demo to
> production* at the end for what to harden for real use.

---

## What you'll learn

[Lesson 1](../../LESSON1.md) put **BM25** and **embeddings** side by side as two ways to retrieve. This
lesson answers the question that always comes next: *which one should I use?* The honest answer is
**both** — and this lesson shows why, and how to combine them.

```
query ─┬─▶ BM25 (exact terms) ──────┐
       └─▶ embeddings (meaning) ─────┤──▶ RRF fuse ──▶ (rerank) ──▶ top chunks ──▶ LLM
                                     ┘
```

By the end you'll understand:

- **BM25** — best for exact terms: IDs, error codes, names, keywords
- **Embeddings** — best for semantic similarity and paraphrasing
- **RRF** (Reciprocal Rank Fusion) — combine multiple ranked lists into one
- **Reranking** — reorder the top chunks before generation for precision
- **Query rewriting** — turn a vague question into a better retrieval query
- **Metadata filtering** — narrow by file type, product, date, page, module, system

> **The one idea:** BM25 and embeddings are not enemies. They solve *different* retrieval problems.
> *"What fixes error E_4096?"* needs exact-term BM25; *"why won't it turn on?"* needs semantic
> matching. Good enterprise RAG runs both and fuses the results.

---

## The demo

A tiny corpus of three support docs lives in [`data/`](./data). We run **two queries** that pull in
opposite directions:

- an **exact-keyword** query — `error E_4096`
- a **semantic / paraphrase** query — `my device won't turn on`

…and print the BM25 ranking, the semantic ranking, and the fused (RRF) ranking for each.

### Run it (offline, no dependencies)

Pick any language — all three give the **same** rankings:

```bash
# Python
cd lessons/03-hybrid-retrieval-reranking/python && python hybrid_demo.py

# Node.js
cd lessons/03-hybrid-retrieval-reranking/node && ./run.sh

# C# / .NET 8
cd lessons/03-hybrid-retrieval-reranking/dotnet && ./run.sh
```

Output:

```
Query: "error E_4096"
  BM25 (lexical):   ['error_codes.md', 'power_issues.md', 'setup.md']
  Semantic (stand): ['error_codes.md', 'power_issues.md', 'setup.md']
  Hybrid (RRF):     ['error_codes.md', 'power_issues.md', 'setup.md']

Query: "my device won't turn on"
  BM25 (lexical):   ['power_issues.md', 'setup.md', 'error_codes.md']
  Semantic (stand): ['power_issues.md', 'error_codes.md', 'setup.md']
  Hybrid (RRF):     ['power_issues.md', 'error_codes.md', 'setup.md']
```

> **Why no embedding model?** To keep the demo offline and dependency-free, the "semantic" arm is a
> small **synonym-expanded overlap** stand-in — enough to behave like embeddings (matching
> *won't turn on* → the *power/startup* doc) so you can watch RRF fuse two different rankings. In
> production you swap in real sentence embeddings; the *fusion* code doesn't change. That swap is the
> first item in *From demo to production*.

---

## Concept 1 · BM25 — lexical retrieval

BM25 ranks documents by **exact term overlap**, weighting rare terms more (IDF) and damping repeated
terms and long documents. The compact implementation in the demo:

```python
idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))      # rare terms count more
tf  = d["tokens"].count(t)
score += idf * (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * dl / avgdl))   # tf, length-normalized
```

- **Wins** the exact query: `E_4096` appears in exactly one document, so its IDF is high and
  `error_codes.md` shoots to the top.
- **Loses** on paraphrase: ask *"won't power on"* and BM25 can't match the synonym *"fails to power
  on"* — there's no shared token.

> **Teaching point:** reach for BM25 when the user knows the exact string — an error code, a product
> SKU, a function name, a person's name. It is fast, needs no model, and is unbeatable at literal
> matching.

## Concept 2 · Embeddings — semantic retrieval

Embeddings map text into a vector space where *meaning* is distance, so paraphrases land near each
other even with no shared words. In the demo a synonym-expanded overlap **stands in** for this:

```python
SYNONYMS = {"turn": ["power", "start", "startup", "boot"], "on": ["up"], ...}
# "my device won't turn on" now overlaps the power/startup document
```

- **Wins** the paraphrase query: `power_issues.md` rises even though *"won't turn on"* never appears
  verbatim.
- **Loses** on exact IDs: a rare code like `E_4096` can get diluted among "semantically similar" text.

> **Teaching point:** reach for embeddings when the user describes a problem in their own words. They
> cost more (you embed every chunk and the query) but they recover the recall BM25 misses.

## Concept 3 · RRF — fusing the two rankings

Each retriever produces a different *ranked list*. **Reciprocal Rank Fusion** combines them without
needing comparable scores — each list contributes `1 / (k + rank)` to a document, then you re-sort:

```python
fused[name] += 1.0 / (RRF_K + position + 1)     # RRF_K = 60
```

Because it works on **ranks, not raw scores**, BM25 and embeddings get an equal vote despite living on
totally different scales. In the demo, the fused ranking gets **both** queries right where each single
retriever gets only one right.

> **Teaching point:** RRF is the cheapest, most robust way to combine retrievers — a few lines, no
> tuning of score scales. It's the default first step of any hybrid system.

## Concept 4 · Reranking, query rewriting & metadata filtering

Three more levers that production systems add on top of fusion:

- **Reranking** — take the fused top-k and reorder them with a stronger model (a cross-encoder that
  scores each `(query, chunk)` pair). Retrieval optimizes *recall*; reranking optimizes *precision* at
  the very top, where the LLM actually reads.
- **Query rewriting** — rewrite a vague question into a better retrieval query *before* searching
  (*"it keeps crashing"* → *"device repeatedly powers off overheating E_4096"*).
- **Metadata filtering** — restrict candidates by structured fields (file type, product, version,
  date, page, module) before or after ranking, to cut noise in large mixed corpora.

> **Teaching point:** reranking is usually the single biggest quality win — and the main added cost
> and latency. Add it once you've proven fusion isn't enough (and measure it — see
> Lesson 5 · RAG evaluation).

---

## When each technique wins

| Technique | Best for | Weak at | Cost | Needs a model? |
|-----------|----------|---------|------|----------------|
| **BM25** | exact terms: IDs, error codes, names | paraphrase, synonyms | very low | no |
| **Embeddings** | semantic similarity, paraphrasing | exact tokens, rare IDs | medium | yes |
| **RRF (fusion)** | combining BM25 + embeddings | nothing — it's combinatorial | negligible | no |
| **Reranking** | precision at the top-k | adds latency; needs top-k first | higher | yes |
| **Query rewriting** | vague / underspecified questions | can over-expand | one LLM call | yes |
| **Metadata filtering** | scoping large mixed corpora | needs good metadata | negligible | no |

On the demo corpus, each single retriever fails one of the two queries; the hybrid handles both —
that's the whole argument for fusion.

---

## Polyglot by design

The retrieval algorithm is language-agnostic, so this lesson ships in **Python, Node.js, and C# /
.NET** — each dependency-free, each reading the same [`data/`](./data), each producing byte-identical
rankings. Compare the three implementations side by side: the *concepts* (BM25, synonym expansion,
RRF) are the same; only the syntax changes.

| Port | Entry point | Run |
|------|-------------|-----|
| [Python](./python) | `python/hybrid_demo.py` | `python hybrid_demo.py` · `pytest` |
| [Node.js](./node) | `node/hybrid_demo.mjs` | `./run.sh` |
| [.NET 8](./dotnet) | `dotnet/Program.cs` | `./run.sh` |

---

## Exercises

- **Real embeddings:** replace the semantic stand-in with a local sentence-embedding model and rerun
  both queries — does fusion still help?
- **Tune RRF:** change `RRF_K` and the per-arm weighting; observe the effect on the fused order.
- **Add a third retriever:** fold in a title/metadata match as a third ranked list — RRF takes any
  number of lists.
- **Break it:** add a document that mentions *E_4096* in passing and watch how BM25 vs hybrid handle
  the near-duplicate.

## From demo to production

- **Real embeddings** for the semantic arm (a local sentence-embedding model, or the repo's optional
  embedding path) — the demo's synonym stand-in is only to stay offline.
- **A cross-encoder reranker** over the fused top-k — usually the biggest single quality win, at some
  latency/compute cost.
- **Query rewriting / expansion** as an LLM step before retrieval for vague queries.
- **A metadata-rich index** so you can filter by product, version, date, and module.
- **Tune `RRF_K`, the top-k, and per-arm weights** per corpus.
- **Measure it** — pair with **Lesson 5 · RAG evaluation** (coming) and prove hybrid actually beats
  single retrievers on your golden set before shipping it.

## Next lesson

**Lesson 4 · RAG safety & prompt injection** — retrieved documents are untrusted input; never follow
instructions found inside them.

---

*Course: [nikolareljin.github.io/local-ai-lab](https://nikolareljin.github.io/local-ai-lab/) · Author: [Nik Reljin](https://www.linkedin.com/in/nikolareljin)*
