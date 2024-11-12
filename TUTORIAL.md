# Lesson 1 · Build a RAG system from scratch (written walkthrough)

> 💡 This is the markdown companion to the **interactive lesson** at
> <https://nikolareljin.github.io/local-ai-lab/lesson-1-rag.html>, where each step is a slide with
> copy-paste commands. Same content, two formats.

By the end you'll understand every stage of Retrieval-Augmented Generation:
**extract → chunk → index → retrieve → ground → answer** — in a few hundred lines of readable
Python, no heavyweight frameworks.

## Prerequisites

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

The simplest AI to answer questions is the **Claude Code CLI** — if you can run `claude`, you're
ready, no API key. Ollama / Gemini / OpenAI are wired in at Step 6.

---

## Step 1 · Extract text (`localrag/extract.py`)

RAG starts by turning files into plain text. We dispatch on extension and normalize everything to a
list of **pages**, each carrying its text, page number, and source filename (needed for citations).
PDFs are read page-by-page with `pypdf`; DOCX with `python-docx`; TXT/MD as raw text.

**Why pages?** A citation like `manual.pdf:4` points the reader to the exact spot. Extraction is the
unglamorous 80% of real RAG — garbage text in, garbage answers out.

## Step 2 · Chunk with overlap (`localrag/chunk.py`)

A whole document is too big to feed the model and too coarse to retrieve precisely. We split into
~1000-character chunks with ~200 characters of **overlap**, breaking on sentence boundaries. Overlap
ensures a sentence split across a boundary still appears intact in at least one chunk. Each chunk
keeps `{source, page_number, chunk_index, text}`.

**Chunk size is a dial.** Too large → imprecise retrieval; too small → lost context. 800–1200 chars
with 10–20% overlap is a sane default.

## Step 3 · Index and cache (`localrag/store.py`)

Extract + chunk every file in `documents/`, then cache to `.localrag/index.json`. Files are
fingerprinted by `(path, mtime, size)`, so the index is rebuilt only when something changes — this is
the "drop a file and ask again" loop. The index is just JSON: no database, no vector server.

## Step 4 · Retrieve with BM25 (`localrag/retriever.py`)

BM25 is a classic keyword-ranking algorithm. It needs no model and no embedding service, so it works
with *any* provider, including Claude Code (which can't embed).

> ⚠️ **A real bug worth knowing.** BM25's IDF goes *negative* when a word appears in every chunk —
> common on a tiny corpus. An early version filtered with `score > 0` and returned **nothing**. The
> fix: return top-k by rank and let the grounding prompt judge relevance. *Retrieval retrieves; the
> LLM decides.*

## Step 5 · The grounding prompt (`localrag/prompts.py`)

The heart of RAG. We hand the model the retrieved chunks as **context** and instruct it to:

1. Answer **from the context first**, citing each claim as `[filename:page]`.
2. Say plainly **"This is not covered in your documents."** when the answer isn't there.
3. **Label any general knowledge** it adds as `(general knowledge — not from your documents)`.
4. Never invent document contents or citations.

**RAG quality = retrieval quality + prompt quality.** You need both.

## Step 6 · Provider abstraction (`localrag/providers/`)

One tiny interface — `chat(system, user) -> str` — with four implementations: `claude_code`,
`ollama`, `gemini`, `openai`. Switching providers is a one-line env-var change (`RAG_PROVIDER`). The
default shells out to the Claude Code CLI, so there's no API key. *This is the pattern every LLM
framework is built around.*

## Step 7 · Wire it together (`localrag/__main__.py`)

Ensure the index is fresh → retrieve top-k → build the grounded prompt → call the provider → print
the answer and its `Sources:`.

```bash
python -m localrag index
python -m localrag ask "How do I reset the device?"
# → ...press and hold the power button for 10 seconds... [sample_manual.md:1]
#   Sources: sample_manual.md:1
```

That's a complete RAG system. Everything else is upgrades.

## Step 8 · Semantic embeddings (`localrag/retriever.py`)

BM25 matches **words**; embeddings match **meaning**. We embed each chunk into a vector and rank by
cosine similarity to the question, catching paraphrases BM25 misses ("power-cycle" ≈ "restart").
Embeddings need `RAG_EMBED_PROVIDER=ollama|gemini|openai`; if none is reachable the selector **falls
back to BM25** with a message. Production often runs **both** (hybrid retrieval).

## Step 9 · Drag-and-drop web UI (`localrag/web.py`)

A tiny Flask app reuses the *exact same* engine. Three endpoints: serve the page, accept dropped
files (save + reindex), answer questions. The front end is one HTML file with vanilla JS.

```bash
python -m localrag web      # http://127.0.0.1:5000
```

## Step 10 · See anti-hallucination work

```bash
python -m localrag ask "How long is the warranty?"
# → 24 months from purchase date [warranty.txt:1]

python -m localrag ask "What is the capital of France?"
# → This is not covered in your documents.
#   (general knowledge — not from your documents) The capital of France is Paris.
```

```bash
pytest -q      # 4 passed — offline test of extract + chunk + BM25
```

---

## Recap

You built extraction, chunking, indexing, BM25 **and** embedding retrieval, a grounding prompt, a
four-provider abstraction, and a web UI — no LangChain, no vector DB, no cloud. That understanding is
the point: frameworks become easy once you know what they automate.

**Next:** [Lesson 2 · MCP servers](https://nikolareljin.github.io/local-ai-lab/lesson-2-mcp.html).
