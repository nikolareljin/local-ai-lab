# local-ai-lab

![local-ai-lab — build local AI, one lesson at a time](docs/assets/hero-banner.png)

[![CI](https://github.com/nikolareljin/local-ai-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/nikolareljin/local-ai-lab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Course site](https://img.shields.io/badge/course-live%20site-5b9dff)](https://nikolareljin.github.io/local-ai-lab/)
[![Runs locally](https://img.shields.io/badge/runs-100%25%20local-3fb950)](./INSTALL.md)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-18%2B-339933?logo=nodedotjs&logoColor=white)
![.NET](https://img.shields.io/badge/.NET-8-512BD4?logo=dotnet&logoColor=white)
[![GitHub stars](https://img.shields.io/github/stars/nikolareljin/local-ai-lab?style=social)](https://github.com/nikolareljin/local-ai-lab/stargazers)

**A hands-on course for building local, private AI from scratch** — RAG, MCP, LangChain, and
LangGraph that run on your own machine. Each lesson builds a small, fully working, *readable*
program, so you finish understanding how the thing actually works — not just how to call an SDK.

**📖 Full documentation:** https://nikolareljin.github.io/local-ai-lab/documentation.html
· **Course site:** https://nikolareljin.github.io/local-ai-lab/
· **Author:** [Nik Reljin](https://www.linkedin.com/in/nikolareljin)

> ### ⭐ Star this repo
> If local-ai-lab is helping you build local AI, **[give it a star](https://github.com/nikolareljin/local-ai-lab)** —
> it helps other developers find the course and motivates new lessons. **[⭐ Star on GitHub →](https://github.com/nikolareljin/local-ai-lab)**

> **No Docker.** Everything runs with the language toolchains directly. The course is **polyglot** —
> **Python** is the reference, with **Node.js** and **C#** ports per lesson
> (`./run -l <N> --lang node|csharp`). **Lessons 1–5 ship in all three.**

---

## Quickstart

Needs **Python 3.10+** (add **Node.js 18+** / **.NET 8 SDK** only for those ports).

```bash
python -m venv venv && source venv/bin/activate    # Windows (PowerShell): .\venv\Scripts\Activate.ps1
pip install -r requirements.txt

./run -l 1                     # launch the RAG web UI (the default AI is Claude Code — no API key)
./run -l 1 ask "How do I reset the device?"   # one-shot grounded answer in the terminal
./run -l 5                     # jump to the latest lesson's interactive playground
```

`./run` creates the virtualenv on first use. On Windows, run `./run` from **Git Bash** or **WSL**, or
call the toolchains directly — see the
**[full documentation](https://nikolareljin.github.io/local-ai-lab/documentation.html)** for install,
run, test, experiment, and how-it-works details (Linux · macOS · Windows). Per-OS setup and optional
providers (Ollama, Gemini, OpenAI) are in **[INSTALL.md](./INSTALL.md)**
([PDF](https://nikolareljin.github.io/local-ai-lab/pdf/INSTALL.pdf)).

---

## Curriculum

Each available lesson is a deep-linkable **interactive slideshow** on the course site and a **written
guide**, and runs **100% locally**. **Lessons 1–5 are live and runnable**; the rest are on the roadmap.

| # | Lesson | What you build | Guide | Live | Status |
|---|--------|----------------|-------|------|--------|
| 1 | **RAG from scratch** | Extract → chunk → retrieve (BM25 + embeddings) → grounded answer with citations | [LESSON1.md](./LESSON1.md) | [open](https://nikolareljin.github.io/local-ai-lab/lesson-1-rag.html) | ✅ Available |
| 2 | **MCP servers** | Expose your document search as a Model Context Protocol tool Claude Code can call natively | [LESSON2.md](./LESSON2.md) | [open](https://nikolareljin.github.io/local-ai-lab/lesson-2-mcp.html) | ✅ Available |
| 3 | **Hybrid retrieval & reranking** | BM25 + a semantic arm fused with Reciprocal Rank Fusion | [README](./lessons/03-hybrid-retrieval-reranking/README.md) | [open](https://nikolareljin.github.io/local-ai-lab/lesson-3-hybrid-retrieval-reranking.html) | ✅ Available |
| 4 | **RAG safety & prompt injection** | Treat retrieved documents as untrusted input — defend against prompt injection and poisoned content | [README](./lessons/04-rag-safety-prompt-injection/README.md) | [open](https://nikolareljin.github.io/local-ai-lab/lesson-4-rag-safety-prompt-injection.html) | ✅ Available |
| 5 | **RAG evaluation & regression testing** | Golden questions, groundedness scoring, and regression tests — turn "seems good" into a tracked number | [README](./lessons/05-rag-evaluation-regression-testing/README.md) | [open](https://nikolareljin.github.io/local-ai-lab/lesson-5-rag-evaluation-regression-testing.html) | ✅ Available |
| 6 | **Repo-aware AI assistant** | Ground an assistant in your codebase so it answers with repo-specific context | — | — | Planned |
| 7 | **LangChain** | Rebuild the RAG pipeline with LangChain and compare the trade-offs | [outline](./roadmap/LESSON7-langchain.md) | — | Planned |
| 8 | **LangGraph** | Turn the pipeline into a stateful agent graph with retries, tool routing, and memory | [outline](./roadmap/LESSON8-langgraph.md) | — | Planned |
| 9 | **Ollama + Function Calling** | Give a local model real tools it can call (function calling) — 100% offline | [outline](./roadmap/LESSON9-ollama.md) | — | Planned |
| 10 | **Microsoft Semantic Kernel** | Rebuild the agent in **C# / .NET** with SK plugins and auto function calling | [outline](./roadmap/LESSON10-semantic-kernel.md) | — | Planned |
| 11 | **AWS Bedrock Agents** | Knowledge bases + action groups on a managed cloud agent, driven from your machine | [outline](./roadmap/LESSON11-bedrock.md) | — | Planned |
| 12 | **Google AI Development Kit** | Build and run a Gemini agent locally with Google's open-source ADK | [outline](./roadmap/LESSON12-google-adk.md) | — | Planned |
| 13 | **AI-assisted testing** | Generate, run, and review tests, and let failures guide the fix | — | — | Planned |
| 14 | **AI code review & issue detection** | Use AI to catch the serious issues in review — real bugs, security, risky changes | — | — | Planned |
| 15 | **Documentation from sprint changes** | Generate release notes and docs straight from a sprint's commits and pull requests | — | — | Planned |

**Browse all lessons live:** https://nikolareljin.github.io/local-ai-lab/ — or grab any lesson as a
printable **PDF** from the [**Lessons & downloads**](#lessons--downloads) table just below.

---

## Lessons & downloads

<!-- BEGIN: lessons-and-downloads (auto-generated by tools/sync-readme-downloads.py — do not edit by hand) -->

_This table is generated by [`tools/sync-readme-downloads.py`](./tools/sync-readme-downloads.py) from the lesson sources on disk — run it after adding a lesson or rebuilding the PDFs._

| # | Lesson | Guide (Markdown) | PDF | Status |
|---|--------|------------------|-----|--------|
| 1 | Build a RAG System From Scratch | [`LESSON1.md`](./LESSON1.md) | [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON1.pdf) | ✅ live |
| 2 | Build an MCP Server | [`LESSON2.md`](./LESSON2.md) | [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON2.pdf) | ✅ live |
| 3 | Hybrid Retrieval & Reranking | [`README.md`](./lessons/03-hybrid-retrieval-reranking/README.md) | [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON3.pdf) | ✅ live |
| 4 | RAG Safety & Prompt Injection | [`README.md`](./lessons/04-rag-safety-prompt-injection/README.md) | [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON4.pdf) | ✅ live |
| 5 | RAG Evaluation & Regression Testing | [`README.md`](./lessons/05-rag-evaluation-regression-testing/README.md) | [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON5.pdf) | ✅ live |
| 7 | Rebuild RAG with LangChain | [`LESSON7-langchain.md`](./roadmap/LESSON7-langchain.md) | [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON7.pdf) | 🚧 roadmap |
| 8 | A Stateful Agent with LangGraph | [`LESSON8-langgraph.md`](./roadmap/LESSON8-langgraph.md) | [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON8.pdf) | 🚧 roadmap |
| 9 | Ollama + Function Calling | [`LESSON9-ollama.md`](./roadmap/LESSON9-ollama.md) | [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON9.pdf) | 🚧 roadmap |
| 10 | Microsoft Semantic Kernel (C# / .NET) | [`LESSON10-semantic-kernel.md`](./roadmap/LESSON10-semantic-kernel.md) | [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON10.pdf) | 🚧 roadmap |
| 11 | AWS Bedrock Agents | [`LESSON11-bedrock.md`](./roadmap/LESSON11-bedrock.md) | [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON11.pdf) | 🚧 roadmap |
| 12 | Google AI Development Kit (ADK) | [`LESSON12-google-adk.md`](./roadmap/LESSON12-google-adk.md) | [PDF](https://nikolareljin.github.io/local-ai-lab/pdf/LESSON12.pdf) | 🚧 roadmap |

**Other PDFs in [`docs/pdf/`](./docs/pdf/):**
- [`CHEATSHEET.pdf`](https://nikolareljin.github.io/local-ai-lab/pdf/CHEATSHEET.pdf) — AI-for-developers cheat-sheet
- [`INSTALL.pdf`](https://nikolareljin.github.io/local-ai-lab/pdf/INSTALL.pdf) — Install guide (Linux · macOS · Windows)
- [`The_Magic_Turtle_Astronaut.pdf`](https://nikolareljin.github.io/local-ai-lab/pdf/The_Magic_Turtle_Astronaut.pdf) — Sample document used in Lesson 1's *try it yourself*

<!-- END: lessons-and-downloads -->

---

## What you'll be able to do

**Who it's for:** developers who can already write code but want to understand how RAG and agents work
*underneath* the frameworks — not just how to call an SDK. No ML background required.

By the end of the **live lessons (1–5)** you can:

- Build a grounded, cited RAG service from scratch — extract, chunk, retrieve (BM25 + embeddings), and
  answer **without hallucinating**.
- Expose your own tools to an AI host over the **Model Context Protocol (MCP)**.
- Make retrieval **better** (hybrid search + reranking), **safe** (prompt-injection defence), and
  **measurable** (an evaluation gate that catches regressions a candidate tweak slips in).

The full path — clusters, prerequisites, and time estimates — is in **[SYLLABUS.md](./SYLLABUS.md)**.

---

## About the author

local-ai-lab is built and maintained by **[Nik Reljin](https://www.linkedin.com/in/nikolareljin)**, who
builds local-first, developer-focused AI tools — and likes nothing more than teaching how they work. A
former college educator, he now helps engineers build with modern AI through team trainings, 1:1
mentoring, talks and workshops, and hands-on courses like this one.

The teaching philosophy runs through every lesson: software should be *understandable*, should *run on
your own hardware*, and should treat AI as a primitive you control — not a remote black box. More on the
approach and related work on the **[About page](https://nikolareljin.github.io/local-ai-lab/about.html)**.

---

## Documentation

- **[SYLLABUS.md](./SYLLABUS.md)** — the full learning path: clusters, prerequisites, and time estimates.

- **[📖 Documentation](https://nikolareljin.github.io/local-ai-lab/documentation.html)** — install, run,
  test, experiment, and how everything works (Linux · macOS · Windows).
- **[INSTALL.md](./INSTALL.md)** ([PDF](https://nikolareljin.github.io/local-ai-lab/pdf/INSTALL.pdf)) —
  per-OS prerequisites and optional providers.
- **[Troubleshooting](https://nikolareljin.github.io/local-ai-lab/troubleshooting.html)** — provider /
  API-key setup and common errors.
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — data flow and module map.

```bash
./run list                 # every lesson and its actions
./run -l <N> demo          # one-shot, print-and-exit run (lessons 3–5; --lang node|csharp for the ports)
./run -l <N> test          # the lesson's offline test (no network, no model)
./run -h                   # full help
```

---

## License

MIT © Nik Reljin — see [LICENSE](./LICENSE). Educational use encouraged; attribution appreciated.

---

## Clone traffic

![Clone traffic](https://raw.githubusercontent.com/nikolareljin/stats/main/charts/local-ai-lab.svg)

_Updated daily. Total and unique cloners over the last 14 days._
