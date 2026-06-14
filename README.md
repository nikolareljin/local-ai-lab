# local-ai-lab

![local-ai-lab — build local AI, one lesson at a time](docs/assets/hero-banner.png)

[![CI](https://github.com/nikolareljin/local-ai-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/nikolareljin/local-ai-lab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Course site](https://img.shields.io/badge/course-live%20site-5b9dff)](https://nikolareljin.github.io/local-ai-lab/)
[![Runs locally](https://img.shields.io/badge/runs-100%25%20local-3fb950)](./INSTALL.md)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-18%2B-339933?logo=nodedotjs&logoColor=white)
![.NET](https://img.shields.io/badge/.NET-8-512BD4?logo=dotnet&logoColor=white)

**A hands-on course for building local, private AI from scratch** — RAG, MCP, LangChain, and
LangGraph that run on your own machine. Each lesson builds a small, fully working, *readable*
program, so you finish understanding how the thing actually works — not just how to call an SDK.

**Course site (interactive lessons):** https://nikolareljin.github.io/local-ai-lab/
**Author:** [Nik Reljin](https://www.linkedin.com/in/nikolareljin)
**Related projects:** [About page](https://nikolareljin.github.io/local-ai-lab/about.html) — selected local-first, developer-focused, AI-native tools.

> **How it runs:** with the language toolchains **directly — there is no Docker.** Install once,
> then `./run -l <N>`. Full cross-platform setup (Linux · macOS · Windows) and per-lesson
> dependencies are in **[INSTALL.md](./INSTALL.md)** ([PDF](https://nikolareljin.github.io/local-ai-lab/pdf/INSTALL.pdf)).
> The course is **polyglot** — **Python** is the reference, with **Node.js** and **C#** ports per
> lesson via `./run -l <N> --lang node|csharp` (**Lessons 1, 2 and 3** ship in all three today). Every lesson is also a **PDF** in
> [`docs/pdf/`](./docs/pdf/).

---

## Curriculum

Each available lesson is published as an **interactive slider** on the course site (every step explains
*what* and *why*, gives the command to type, and shows the code — steps are deep-linkable) and as a
**written guide**. **Lessons 1–3 are live and runnable today**; the rest are on the roadmap below.

| # | Lesson | What you build | Guide | Live | Status |
|---|--------|----------------|-------|------|--------|
| 1 | **RAG from scratch** | Extract → chunk → retrieve (BM25 + embeddings) → grounded answer with citations | [LESSON1.md](./LESSON1.md) | [open](https://nikolareljin.github.io/local-ai-lab/lesson-1-rag.html) | Available |
| 2 | **MCP servers** | Expose your document search as a Model Context Protocol tool Claude Code can call natively | [LESSON2.md](./LESSON2.md) | [open](https://nikolareljin.github.io/local-ai-lab/lesson-2-mcp.html) | Available |
| 3 | **Hybrid retrieval & reranking** | BM25 + a semantic arm fused with Reciprocal Rank Fusion — offline, in Python, Node.js and C# | [README](./lessons/03-hybrid-retrieval-reranking/README.md) | [open](https://nikolareljin.github.io/local-ai-lab/lesson-3-hybrid-retrieval-reranking.html) | Available |
| 4 | **RAG safety & prompt injection** | Treat retrieved documents as untrusted input — defend against prompt injection and poisoned content | — | — | Planned |
| 5 | **RAG evaluation & regression testing** | Golden questions, groundedness scoring, and regression tests — turn "seems good" into a tracked number | — | — | Planned |
| 6 | **Repo-aware AI assistant** | Ground an assistant in your codebase so it answers with repo-specific context | — | — | Planned |
| 7 | **LangChain** | Rebuild the RAG pipeline with LangChain and compare the trade-offs | — | — | Planned |
| 8 | **LangGraph** | Turn the pipeline into a stateful agent graph with retries, tool routing, and memory | — | — | Planned |
| 9 | **Ollama + Function Calling** | Give a local model real tools it can call (function calling) — 100% offline | — | — | Planned |
| 10 | **Microsoft Semantic Kernel** | Rebuild the agent in **C# / .NET** with SK plugins and auto function calling | — | — | Planned |
| 11 | **AWS Bedrock Agents** | Knowledge bases + action groups on a managed cloud agent, driven from your machine | — | — | Planned |
| 12 | **Google AI Development Kit** | Build and run a Gemini agent locally with Google's open-source ADK | — | — | Planned |
| 13 | **AI-assisted testing** | Generate, run, and review tests, and let failures guide the fix | — | — | Planned |
| 14 | **AI code review & issue detection** | Use AI to catch the serious issues in review — real bugs, security, risky changes | — | — | Planned |
| 15 | **Documentation from sprint changes** | Generate release notes and docs straight from a sprint's commits and pull requests | — | — | Planned |

Every lesson's end goal: a **fully published slideshow lesson** with step-by-step instructions, and
**all code runs locally**.

**Browse all lessons live:** https://nikolareljin.github.io/local-ai-lab/
**Every lesson as a printable PDF** (with cross-platform install instructions): [`docs/pdf/`](./docs/pdf/) — e.g. [LESSON1.pdf](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON1.pdf), [INSTALL.pdf](https://nikolareljin.github.io/local-ai-lab/pdf/INSTALL.pdf).

---

## Lesson 1: the working RAG app

This repository ships the complete, runnable code for Lesson 1. Drop PDF / DOCX / TXT / MD files
into `documents/`, ask questions, and get answers grounded in your files with cited sources. It
runs against the **Claude Code CLI** (default, no API key), **Ollama** (fully local), **Gemini**,
or **OpenAI** — swappable with one environment variable.

### 60-second quickstart

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Drop your PDFs/DOCX/TXT/MD into documents/  (samples are already there)
cp ~/my-manual.pdf documents/

# Ask, in your terminal (default provider = Claude Code CLI, uses your login)
python -m localrag ask "How do I reset the device?"

# ...or launch the drag-and-drop web UI
python -m localrag web        # http://127.0.0.1:5000
```

### Commands

```bash
python -m localrag index [--reindex]      # build/refresh the index from documents/
python -m localrag ask "question"         # one-shot grounded answer
python -m localrag ask                     # interactive REPL
python -m localrag web [--port 5000]       # drag-and-drop web UI
pytest -q                                  # offline tests (extract + chunk + BM25)
```

### Switching providers and retrieval

Copy `.env.example` to `.env` to set keys/models. Override per run with env vars or flags.

| Provider | `RAG_PROVIDER` | Needs | Embeddings? |
|----------|----------------|-------|-------------|
| Claude Code CLI (default) | `claude` | `claude` on PATH (your login) | no |
| Ollama (local) | `ollama` | Ollama running + a pulled model | yes |
| Gemini | `gemini` | `GEMINI_API_KEY` | yes |
| OpenAI / compatible | `openai` | `OPENAI_API_KEY` | yes |

```bash
RAG_PROVIDER=ollama python -m localrag ask "How do I connect to Wi-Fi?"
RAG_RETRIEVER=embeddings RAG_EMBED_PROVIDER=ollama python -m localrag ask "reset steps?"
```

- **`RAG_RETRIEVER=bm25`** (default) — pure-Python keyword ranking, zero setup, works with every
  provider including Claude Code.
- **`RAG_RETRIEVER=embeddings`** — semantic vector search; needs an embedding provider. Falls back
  to BM25 with a clear message if none is reachable, so the demo never dead-ends.

### How grounding prevents hallucination

The system prompt (`localrag/prompts.py`) forces the model to answer **from the retrieved document
context first**, cite each claim as `[file:page]`, say plainly when something **isn't** in the
documents, and clearly **label any general knowledge** it adds. Every answer ends with a `Sources:`
line. See it live in [Lesson 1, Step 10](https://nikolareljin.github.io/local-ai-lab/lesson-1-rag.html#step-12).

---

## Lesson 2: the MCP server

`mcp_server.py` exposes the same retriever as **Model Context Protocol** tools (`search_docs`,
`list_documents`), so Claude Code can query your `documents/` folder natively — no copy-paste.

```bash
pip install -r requirements.txt          # includes the `mcp` SDK
pytest -q tests/test_mcp.py              # spawns the server over stdio and calls a tool

# register with Claude Code (run from the repo dir), then just ask in chat:
claude mcp add local-ai-lab-docs -- python mcp_server.py
```

**Polyglot:** the same server is also built on the official **Node.js**
([`node/lesson-2`](./node/lesson-2)) and **C# / .NET** ([`dotnet/lesson-2`](./dotnet/lesson-2))
MCP SDKs — try `./run -l 2 demo --lang node` or `./run -l 2 demo --lang csharp`.

Full walkthrough: [LESSON2.md](./LESSON2.md) · [interactive lesson](https://nikolareljin.github.io/local-ai-lab/lesson-2-mcp.html).

---

## Lesson 3: hybrid retrieval & reranking

Lesson 3 combines **BM25** keyword search with a **semantic** arm and fuses them with **Reciprocal
Rank Fusion (RRF)** — offline and dependency-free, with byte-identical results in **Python, Node.js
and C#**. It's the first **config-driven** lesson: it lives under
[`lessons/03-hybrid-retrieval-reranking/`](./lessons/03-hybrid-retrieval-reranking/) and is run,
previewed, and published through one engine (`tools/lesson.py`).

```bash
./run -l 3                 # interactive experiment GUI: tune BM25 k1/b, RRF k, synonyms — live
./run -l 3 demo            # one-shot: print the BM25 / semantic / fused rankings and exit
./run -l 3 demo --lang node|csharp   # the same algorithm, byte-identical, in the other ports
./run -l 3 test            # offline test pinning the lesson's claims
```

Full walkthrough: [README](./lessons/03-hybrid-retrieval-reranking/README.md) · [interactive lesson](https://nikolareljin.github.io/local-ai-lab/lesson-3-hybrid-retrieval-reranking.html).

---

## Repository layout

```
local-ai-lab/
├── docs/                  # GitHub Pages course site (interactive sliders)
│   ├── index.html         #   landing + curriculum
│   ├── lesson-1-rag.html  #   Lesson 1 (RAG) — full interactive lesson
│   ├── lesson-2-mcp.html  #   Lesson 2 (MCP) — full interactive lesson
│   ├── lesson-3-hybrid-retrieval-reranking.html  # Lesson 3 (generated from lessons/03-*)
│   └── assets/            #   styles + slider.js
├── documents/             # the RAG corpus — drop your files here
├── localrag/              # Lesson 1 source code (the working app)
│   ├── extract.py chunk.py store.py retriever.py prompts.py engine.py
│   ├── providers/         #   claude_code · ollama · gemini · openai
│   ├── web.py             #   Flask drag-and-drop UI
│   └── templates/         #   index.html (web UI)
├── mcp_server.py          # Lesson 2 — MCP server (search_docs, list_documents)
├── examples/
│   ├── mcp_demo.py        # Lesson 2 — stdio client demo (used by ./run -l 2 demo)
│   └── mcp_web.py         # Lesson 2 — interactive tool GUI (./run -l 2)
├── lessons/               # config-driven lessons (3+): one lesson.json per lesson
│   └── 03-hybrid-retrieval-reranking/   # Lesson 3 (Python · Node · C#)
├── tools/                 # lesson engine (lesson.py) + shared experiment-GUI scaffold (lesson_web.py)
├── node/                  # Node.js ports — lesson-1/ (RAG) · lesson-2/ (MCP server)
├── dotnet/                # C# / .NET ports — lesson-1/ (RAG) · lesson-2/ (MCP server)
├── run                    # ./run -l <N> [--lang python|node|csharp] — run any lesson locally
├── scripts/               # script-helpers submodule + start/stop/status helpers
├── tests/                 # offline smoke tests (incl. MCP integration test)
├── LESSON1.md, LESSON2.md, …   # written lesson guides (Lesson 3+ guides live in lessons/NN-*/README.md)
├── ARCHITECTURE.md  CHANGELOG.md  AGENTS.md
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the data flow and module map.

---

## Run a lesson — `./run`

One command runs any lesson locally. It sets up the virtualenv on first use and, by default,
uses the **Claude Code CLI** as the AI — no API key, it just uses your existing Claude Code login.

```bash
./run -l 1                                   # launch the RAG web UI (auto-picks a free port)
./run -l 1 ask "How do I reset the device?"  # one-shot question in the terminal
./run -l 1 repl                              # interactive Q&A loop
./run -l 1 test                              # run Lesson 1 tests
./run -l 2                                   # launch the MCP tool GUI (auto-picks a free port)
./run -l 2 demo                              # call the MCP tools over stdio in the terminal (no LLM needed)
./run -l 2 register                          # register the MCP server with Claude Code
./run -l 2 serve                             # run the MCP server over stdio
./run -l 2 test                              # run Lesson 2 tests
./run -l 1 --lang node                       # Node.js impl (Lessons 1-3 ported; else points to Python)
./run -l 2 demo --lang csharp                # C# MCP server, demoed end-to-end
./run -h                                     # full help
```

Lesson **3** is interactive too — `./run -l 3` opens its experiment GUI (or `./run -l 3 demo` for the
one-shot terminal run). Lessons **4–8** are written guides for now.

First-time setup and per-lesson dependencies for **Linux, macOS, and Windows** (Python, Node.js,
C#) are in **[INSTALL.md](./INSTALL.md)** ([PDF](https://nikolareljin.github.io/local-ai-lab/pdf/INSTALL.pdf)).

**The AI is Claude Code by default.** `./run` announces the provider and checks that `claude` is on
your PATH. To use a different one, set `RAG_PROVIDER`:

```bash
RAG_PROVIDER=ollama ./run -l 1 ask "..."     # or gemini / openai (set the key in .env)
```

### Other helpers

```bash
./update          # install/update the script-helpers submodule
./start           # background the Lesson 1 web app (./status, ./stop to manage)
```

---

## License

MIT © Nik Reljin — see [LICENSE](./LICENSE). Educational use encouraged; attribution appreciated.

---

## Clone traffic

![Clone traffic](https://raw.githubusercontent.com/nikolareljin/stats/main/charts/local-ai-lab.svg)

_Updated daily. Total and unique cloners over the last 14 days._
