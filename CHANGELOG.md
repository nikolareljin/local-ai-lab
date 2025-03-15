# Changelog

All notable changes to this project are documented here. This project follows
[Conventional Commits](https://www.conventionalcommits.org/) and
[Semantic Versioning](https://semver.org/).

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
