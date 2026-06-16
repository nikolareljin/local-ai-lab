# Architecture

`local-ai-lab` Lesson 1 is a small, dependency-light RAG system. This document maps the modules and
the data flow so you can navigate the source quickly.

## Data flow

```
documents/*.{pdf,docx,txt,md}
        │
        ▼  extract.py    file → list[Page]{source, page_number, text}
        ▼  chunk.py      pages → list[Chunk]{source, page_number, chunk_index, text}
        ▼  store.py      build + cache index in .localrag/index.json (fingerprint by mtime+size)
        │
question ┤
        ▼  retriever.py  Bm25Retriever | EmbeddingRetriever → top-k Chunks
        ▼  prompts.py    SYSTEM_PROMPT + build_user_prompt(question, chunks)
        ▼  providers/    get_provider(name).chat(system, user) → answer text
        ▼  engine.py     answer_question() ties retrieval + provider, returns {answer, sources, ...}
        │
        ├─ __main__.py   CLI: index / ask / web
        └─ web.py        Flask UI: /api/upload, /api/ask, /api/status → templates/index.html
```

## Modules

| Module | Responsibility |
|--------|----------------|
| `config.py` | Load configuration from environment / `.env`. No hard-coded paths. |
| `extract.py` | Turn a file into a list of pages. PDF via `pypdf`, DOCX via `python-docx`, TXT/MD as text. |
| `chunk.py` | Split pages into overlapping chunks, breaking on sentence boundaries, keeping source + page. |
| `store.py` | Build/load/cache the index under `.localrag/`. Re-index only when files change. |
| `retriever.py` | `Bm25Retriever` (keyword) and `EmbeddingRetriever` (semantic) behind one `search()` interface; `build_retriever` selects and falls back to BM25. |
| `prompts.py` | The anti-hallucination system prompt and context formatting. |
| `providers/` | `LLMProvider` protocol + `claude_code`, `ollama`, `gemini`, `openai` adapters; `get_provider` factory and `embed_texts`. |
| `engine.py` | Cached retriever + `answer_question()`; shared by the web UI. |
| `__main__.py` | CLI entry: `index`, `ask` (REPL or one-shot), `web`. |
| `web.py` + `templates/index.html` | Flask drag-and-drop UI reusing the same engine. |

## Design choices

- **No vector database, no framework.** The index is a JSON file; embeddings (when used) are an
  `.npz` file. This keeps the code readable and the demo trivial to run - the teaching goal.
- **Provider-agnostic.** One `chat(system, user)` interface, four adapters, switched by
  `RAG_PROVIDER`. The default (`claude`) shells out to the Claude Code CLI, so there's no API key.
- **Retrieval retrieves; the LLM decides.** The retriever returns top-k candidates by score (no
  absolute cutoff - BM25 IDF can go negative on tiny corpora); the grounding prompt judges relevance.
- **Never dead-end.** Embeddings mode falls back to BM25 with a clear message if no embed provider
  is reachable.
- **Auto-refresh.** Files are fingerprinted by `(path, mtime, size)`; dropping a new file into
  `documents/` and asking again rebuilds only what changed.

## Extending it

- **Hybrid retrieval:** merge BM25 and embedding rankings (e.g. reciprocal-rank fusion) in `retriever.py`.
- **Smarter chunking:** split on Markdown headings or PDF layout in `chunk.py`.
- **New provider:** add `providers/<name>.py` implementing `chat()` (+ `embed()` if it can embed)
  and register it in `providers/__init__.py:get_provider`.
- **MCP (Lesson 2):** wrap `engine.get_retriever().search()` in a `search_docs` MCP tool.
