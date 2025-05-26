# local-ai-lab

**A hands-on course for building local, private AI from scratch** — RAG, MCP, LangChain, and
LangGraph that run on your own machine. Each lesson builds a small, fully working, *readable*
program, so you finish understanding how the thing actually works — not just how to call an SDK.

🔗 **Course site (interactive lessons):** https://nikolareljin.github.io/local-ai-lab/
👤 **Author:** [Nik Reljin](https://www.linkedin.com/in/nikolareljin)

---

## Curriculum

Every lesson comes in two forms: a **written guide** (`LESSONx.md`, full text + code) and an
**interactive slider** on the course site (each step explains *what* and *why*, gives the exact
command to type, and shows the code — steps are deep-linkable).

| # | Lesson | What you build | Read (Markdown) | Live (interactive) | Status |
|---|--------|----------------|-----------------|--------------------|--------|
| 1 | **RAG from scratch** | A drag-and-drop document Q&A app: extract → chunk → retrieve (BM25 + embeddings) → grounded answer with citations | [LESSON1.md](./LESSON1.md) | [▶ open](https://nikolareljin.github.io/local-ai-lab/lesson-1-rag.html) | ✅ Available |
| 2 | **MCP servers** | Expose your document search as a Model Context Protocol tool Claude Code can call (`mcp_server.py`) | [LESSON2.md](./LESSON2.md) | [▶ open](https://nikolareljin.github.io/local-ai-lab/lesson-2-mcp.html) | ✅ Available |
| 3 | **LangChain** | Rebuild the RAG pipeline with LangChain and compare trade-offs | [LESSON3.md](./LESSON3.md) | _on site soon_ | 🚧 Planned |
| 4 | **LangGraph** | Turn the pipeline into a stateful, self-correcting agent graph | [LESSON4.md](./LESSON4.md) | _on site soon_ | 🚧 Planned |
| 5 | **Ollama + Function Calling** | Give a local model real tools (function calling), 100% offline | [LESSON5.md](./LESSON5.md) | _on site soon_ | 🚧 Planned |
| 6 | **Microsoft Semantic Kernel** | Rebuild the agent in **C# / .NET** with SK plugins (runs locally) | [LESSON6.md](./LESSON6.md) | _on site soon_ | 🚧 Planned |
| 7 | **AWS Bedrock Agents** | Knowledge bases + action groups on a managed cloud agent, driven locally | [LESSON7.md](./LESSON7.md) | _on site soon_ | 🚧 Planned |
| 8 | **Google AI Development Kit** | Build & run a Gemini agent locally with Google's ADK | [LESSON8.md](./LESSON8.md) | _on site soon_ | 🚧 Planned |

Every lesson's end goal: a **fully published slideshow lesson** with step-by-step instructions, and
**all code runs locally**.

🔗 **Browse all lessons live:** https://nikolareljin.github.io/local-ai-lab/

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

Full walkthrough: [LESSON2.md](./LESSON2.md) · [interactive lesson](https://nikolareljin.github.io/local-ai-lab/lesson-2-mcp.html).

---

## Repository layout

```
local-ai-lab/
├── docs/                  # GitHub Pages course site (interactive sliders)
│   ├── index.html         #   landing + curriculum
│   ├── lesson-1-rag.html  #   Lesson 1 (RAG) — full interactive lesson
│   ├── lesson-2-mcp.html  #   Lesson 2 (MCP) — full interactive lesson
│   └── assets/            #   styles + slider.js
├── documents/             # the RAG corpus — drop your files here
├── localrag/              # Lesson 1 source code (the working app)
│   ├── extract.py chunk.py store.py retriever.py prompts.py engine.py
│   ├── providers/         #   claude_code · ollama · gemini · openai
│   ├── web.py             #   Flask drag-and-drop UI
│   └── templates/         #   index.html (web UI)
├── mcp_server.py          # Lesson 2 — MCP server (search_docs, list_documents)
├── examples/mcp_demo.py   # Lesson 2 — stdio client demo (used by ./run -l 2)
├── run                    # ./run -l <N> — run any lesson locally
├── scripts/               # script-helpers submodule + start/stop/status helpers
├── tests/                 # offline smoke tests (incl. MCP integration test)
├── LESSON1.md … LESSON8.md   # full written lessons (linked to the live site)
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
./run -l 2                                   # demo the MCP server end-to-end (no LLM needed)
./run -l 2 register                          # register the MCP server with Claude Code
./run -l 2 serve                             # run the MCP server over stdio
./run -l 2 test                              # run Lesson 2 tests
./run -h                                     # full help
```

Lessons **3–8** are written guides for now: `./run -l 3` points you to `LESSON3.md`.

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
