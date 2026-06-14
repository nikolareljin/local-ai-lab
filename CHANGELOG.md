# Changelog

All notable changes to this project are documented here. This project follows
[Conventional Commits](https://www.conventionalcommits.org/) and
[Semantic Versioning](https://semver.org/).

## [0.5.0]

**Config-driven lessons + Lesson 3 (Hybrid retrieval & reranking).** Lessons from 3 onward are
described by a single `lesson.json` and run, preview, and publish through one engine.

### Added
- **Lesson 3 — Hybrid retrieval & reranking** (`lessons/03-hybrid-retrieval-reranking/`): an offline,
  dependency-free demo of BM25 + a semantic stand-in fused with RRF, in **Python, Node.js and C# / .NET**
  with byte-identical output, an optional Flask web UI, an offline test, and a 5-chapter fictive-story
  corpus to search.
- **Lesson engine** (`tools/lesson.py`): `list`, `run` (per action + `--lang`), `show` (terminal
  walkthrough), `preview` (local step-slideshow server), and `build` (publishable `docs/` page).
  Driven by a per-lesson `lesson.json` of typed elements — command / code / config / text / note /
  media — that **reference real files** (code is never pasted into the config).
- **Step-by-step preview/publish that matches Lessons 1-2**: a shared template references the published
  `docs/assets/style.css` + `slider.js`; adds server-side **syntax highlighting**
  (`docs/assets/highlight.css`), **one or several notes per code snippet**, a **language selector** that
  groups the per-language steps, and a **Lessons dropdown** in the top nav across the site.
- Authoring / reorder tooling: `tools/new-lesson.sh`, `tools/sync-curriculum.sh`,
  `tools/renumber-lessons.sh`, and `lessons/_template/`.

### Changed
- `./run` is registry-driven for lessons 3+ (`./run -l 3 [demo|web|test|show|preview|build] [--lang …]`);
  Lessons 1-2 keep their bespoke dispatch (unchanged).
- The site top-nav is now a **Lessons dropdown** (all pages); switching a lesson's language restarts it
  at step 1 so paging never changes the chosen language.
- Lesson page footers link to the **About** page instead of the LinkedIn / "Source on GitHub" links
  (Lessons 1 and 2, and the Lesson 3 template), matching where those links now live.
- Lesson 3's step prose makes explicit that the code **and** the data already ship in the repo — it's a
  read-along walkthrough, with nothing to copy or create and a single command (`./run -l 3`) to run.

### Fixed
- Single-language renders (`build`/`preview`/`show --html --lang …`) now pin the rendered language in the
  page head and skip the saved-language restore (there is no selector to recover from), so a different
  `localStorage` choice can no longer hide every code block.
- `pytest` is declared in `requirements.txt` and the `ensure_venv` check, so `./run -l N test` works on a
  fresh clone/venv.
- Lesson 3's Python test is self-contained (adds its own directory to `sys.path`), so pytest finds
  `hybrid_demo` regardless of the working directory.
- `tools/new-lesson.sh` resolves the interpreter as `python3 || python`, matching the rest of the repo.
- The `lang` value is escaped before it is interpolated into a `lang-*` CSS class, so a stray or
  malicious `lesson.json` `lang` can't break the attribute or inject markup.
- `--lang` is constrained to `python|node|csharp` at parse time across `run`/`show`/`preview`/`build`,
  so an unknown value fails fast instead of rendering empty/hidden content.
- `tools/sync-curriculum.sh` fails with a clear message when no Python interpreter is found.
- The homepage curriculum cards now reflect the **reordered (Option A) curriculum** — all 15 lessons in
  their new positions (Lessons 1-3 Available; 4-15 Planned), so the cards match the nav dropdown and the
  generated `CURRICULUM.md`. The function-calling model note in Troubleshooting is renumbered to Lesson 9.
- The preview server URL-decodes the request path before normalizing it, so percent-encoded traversal
  (e.g. `%2e%2e/`) can no longer slip past the `..` guard.
- `show --html` (standalone file) now emits absolute `file://…/docs/` nav and brand links, so they stay
  usable when the page is written to an arbitrary location.
- `tools/new-lesson.sh` opens `lesson.json` with a `with` block (no leaked file descriptor).
- The BM25 arm in all three demos (Python / Node / C#) guards an **empty corpus** instead of dividing by
  zero (`ZeroDivisionError` / `Infinity` / `Average` throw).
- The Node demo uses an **ordinal** tie-break comparator instead of locale-dependent `localeCompare`, so
  its ranking stays byte-identical with Python and .NET across locales.
- `read_ref()` keeps file reads **inside the lesson directory**, so a `lesson.json` can't reference and
  embed files outside it (`../../…`).
- `./run list` and the `python3 || python` lookups in `new-lesson.sh` / `sync-curriculum.sh` no longer
  abort under `set -euo pipefail` when the registry list or interpreter lookup fails.
- The Lesson 3 `web.py` docstring shows the correct command (`./run -l 3 web`, not `./run -l 3`).
- `read_ref()` parses the `lines` excerpt spec tolerantly — a single line (`"42"`), surrounding
  whitespace, or an invalid spec returns a clear `[invalid lines spec: …]` placeholder instead of
  crashing the whole `show`/`preview`/`build` render.
- Generated lesson pages carry a `GENERATED FILE — do not edit by hand` banner (from the template), so
  it's clear they come from `./run -l N build` and manual edits will be overwritten.
- `tools/new-lesson.sh` and `tools/sync-curriculum.sh` validate that the resolved interpreter is actually
  Python 3 (some systems alias `python` to Python 2), emitting the intended error instead of a traceback.
- The language CSS-class token is normalized to `[a-z0-9_-]` (not just HTML-escaped), so a `lang` value
  with spaces/punctuation can't split into extra classes or break the `[data-lang] .lang-*` selectors.
- `./run list` prints an explicit fallback line when the lesson registry can't be loaded, instead of
  silently dropping Lessons 3+.
- Added `tests/test_lesson_engine.py` — unit tests for `read_ref()` path confinement, tolerant `lines`
  excerpt parsing, and the CSS-safe language token.
- **Site favicon** — the published site had none (tabs showed nothing). Added a brand-matching icon
  (`docs/assets/favicon.svg` + PNG/apple-touch + a multi-size `docs/favicon.ico`) and linked it from every
  page and the lesson template.
- `registry()` fails fast when two lesson directories share the same number, instead of silently
  overwriting one (which made lesson resolution nondeterministic).
- `cmd_run()` returns a non-zero code when a lesson isn't `working`, so scripts/CI don't read a skipped
  lesson as success.
- Media elements (`image`/`video`/`media`) are confined to the lesson directory like `read_ref()`, so a
  stray `file: "../.."` can't embed files from outside it in standalone `show --html` output.
- The "generated file — do not edit" banner is injected into built pages by the engine rather than living
  in `tools/templates/lesson-preview.html`, so the template itself is no longer mislabeled as generated.
- `tools/renumber-lessons.sh swap` uses a PID-scoped temp directory, so a leftover from an interrupted
  run can't collide and corrupt the swap.
- `lessons/README.md` now correctly states that renumbering changes a lesson's published filename
  (`lesson-<number>-<slug>.html`) and requires rebuilding the affected pages — the dir rename isn't enough.

## [0.4.0]

**Lesson 2 (MCP) goes polyglot** — the MCP server now ships in Node.js and C# alongside Python.

### Added
- **Node.js MCP server** (`node/lesson-2/`) — `search_docs` and `list_documents` over stdio on the
  official `@modelcontextprotocol/sdk` (`McpServer`), reusing the Node Lesson 1 engine. Includes an
  stdio-client demo (`src/demo.js`) and `run.sh` (`demo`/`serve`/`register`/`test`).
- **C# / .NET MCP server** (`dotnet/lesson-2/`) — the same two tools on the official
  `ModelContextProtocol` SDK (`[McpServerTool]`), reusing the C# Lesson 1 retriever. Includes an
  `McpClient` demo and `run.sh`.
- **Language selector** on the Lesson 2 interactive slides (`docs/lesson-2-mcp.html`) — Python /
  Node.js / C#, mirroring Lesson 1; every code step has all three implementations.

### Changed
- `./run -l 2 --lang node|csharp` now runs the real ports (previously pointed to the Python
  reference). README, `LESSON2.md`, and `run` help updated to reflect Lessons 1-2 in all three
  languages. Each server registers under a distinct name so all three can coexist in Claude Code.

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
