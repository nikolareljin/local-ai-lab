# Changelog

All notable changes to this project are documented here. This project follows
[Conventional Commits](https://www.conventionalcommits.org/) and
[Semantic Versioning](https://semver.org/).

## [0.3.0]

Cross-platform install docs, per-lesson PDFs, an easy lesson runner, and the polyglot foundation.

### Added
- **`INSTALL.md`** — Linux / macOS / Windows dependency setup for Python, Node.js, and C#, with a
  per-lesson dependency table. Clarifies the app runs with Python directly (no Docker).
- **PDFs** — `tools/build_lesson_pdfs.py` (pure-Python) generates `docs/pdf/INSTALL.pdf` and
  `docs/pdf/LESSON1-8.pdf`; linked from each lesson, the README, and the course site.
- **`./run` dispatcher** — `./run -l <N> [--lang python|node|csharp] [action]`; auto-creates the
  venv, auto-picks a free port, and announces the default AI (Claude Code).
- **`examples/mcp_demo.py`** — stdio client used by `./run -l 2`.
- **Install slides** added to the Lesson 1 and Lesson 2 interactive sliders.

### Changed
- **Polyglot (Option B):** Python is the reference; `--lang node|csharp` is wired (points to the
  Python reference where a lesson isn't ported yet).
- Reduced emoji usage across docs and the site for a cleaner look.

## [0.2.0]

**Lesson 2 (MCP) complete & working**, plus the full 8-lesson roadmap.

### Added
- **MCP server** (`mcp_server.py`) — a FastMCP stdio server exposing the Lesson 1 retriever as
  `search_docs` and `list_documents` tools, callable from Claude Code.
- **MCP integration test** (`tests/test_mcp.py`) — spawns the server over stdio, lists tools, and
  calls `search_docs`; skipped if the MCP SDK is absent.
- **Full Lesson 2** — interactive step-slider (`docs/lesson-2-mcp.html`) and written guide
  (`LESSON2.md`) with runnable code.
- **Roadmap lessons 3–8** — written guides `LESSON3.md`–`LESSON8.md` (LangChain, LangGraph,
  Ollama + function calling, Microsoft Semantic Kernel in C#/.NET, AWS Bedrock Agents, Google ADK).

### Changed
- `requirements.txt` adds `mcp`. README/landing curriculum mark Lesson 2 as Available.

## [0.1.0]

First public release of **local-ai-lab** — Lesson 1 (RAG) complete, Lesson 2 (MCP) previewed.

### Added
- **Lesson 1 RAG app** — extract (PDF/DOCX/TXT/MD), overlap chunking, cached JSON index.
- **Retrieval** — `Bm25Retriever` (default, zero setup) and `EmbeddingRetriever` (semantic) behind
  one interface, with automatic BM25 fallback when no embed provider is reachable.
- **Provider abstraction** — Claude Code CLI (default, no API key), Ollama, Gemini, OpenAI,
  swappable via `RAG_PROVIDER`.
- **Anti-hallucination grounding prompt** — cites `[file:page]`, admits when an answer isn't in the
  documents, and labels general knowledge.
- **CLI** — `index`, `ask` (REPL + one-shot), `web`.
- **Drag-and-drop web UI** — Flask app with upload + reindex + grounded answers and source chips.
- **Course site** — GitHub Pages with interactive step-slider lessons (Lesson 1 full, Lesson 2 preview).
- **Lesson guides** — full written lessons `LESSON1.md`–`LESSON4.md`, cross-linked to the live site.
- **Docs** — README, ARCHITECTURE; ingestable `documents/rag_tutorial.md`.
- **CI** — ci-helpers Python workflow; **script-helpers** submodule with `start`/`stop`/`status`/`update`.
- **Tests** — offline smoke tests for extraction, chunking, and BM25 retrieval.
