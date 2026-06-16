# Syllabus - local-ai-lab

A hands-on course for building local, private AI **from scratch**. The bet behind it: if you build
each piece by hand once - a retriever, a chunker, a provider adapter, an evaluation gate - then every
framework that wraps those pieces stops looking like magic. You can read it, judge it, and decide when
it's worth the dependency.

The live lessons run **100% locally** (no Docker) and ship in **Python, Node.js, and
C# / .NET** with byte-identical output, so you can follow in the language you work in. A few
roadmap framework tours (Lessons 11-12, AWS Bedrock and Google ADK) reach out to cloud services.

- **Course site:** https://nikolareljin.github.io/local-ai-lab/
- **Curriculum table (status at a glance):** [README](./README.md#curriculum)
- **Setup (Linux · macOS · Windows):** [INSTALL.md](./INSTALL.md)

---

## Who this is for

Developers who can already write code and want to understand how RAG and agents work *underneath*
the frameworks - not just how to call an SDK. You don't need an ML background; you do need to be
comfortable running commands and reading code in at least one of Python, Node.js, or C#.

## How the course is structured

Lessons are grouped into four clusters that build on each other:

| Cluster | Lessons | You go from... |
|---------|---------|--------------|
| **1 · Foundation** | 1-2 | nothing → a working, cited RAG app you expose as a tool |
| **2 · RAG depth** | 3-6 | "it works" → it's *better*, *safe*, and *measurable* |
| **3 · Framework tour** | 7-12 | hand-rolled → the same app rebuilt on the major frameworks, compared honestly |
| **4 · Applied dev workflows** | 13-15 | building AI → using AI in your everyday engineering loop |

**Lessons 1-5 are live and runnable today.** Lessons 6-15 are on the roadmap; the framework-tour
outlines (7-12) already exist under [`roadmap/`](./roadmap/).

## Course prerequisites

- **Python 3.10+** (required for every lesson and for `./run`).
- **Node.js 18+** and/or **.NET 8 SDK** - only if you want to follow the Node / C# ports.
- A text editor and a terminal. The default AI provider is **Claude Code** (no API key); Ollama,
  Gemini, and OpenAI are optional alternatives - see [INSTALL.md](./INSTALL.md).

---

## The path

Each lesson below lists what you build, the concrete skills you walk away with, what it assumes, and
a rough time budget (reading + hands-on). Run any live lesson with `./run -l <N>`.

### Cluster 1 · Foundation

#### Lesson 1 - RAG from scratch · ✅ live · Python · Node · .NET · ≈ 60-90 min
**Build:** a full retrieval-augmented-generation pipeline - extract → chunk → retrieve (BM25 +
embeddings) → grounded answer with `[source:page]` citations - plus a small web UI.
**You'll be able to:** load and chunk documents; implement keyword (BM25) and embedding retrieval;
ground a model so it cites sources and refuses to answer off-corpus; reason about why each step exists.
**Assumes:** Python basics. No prior AI experience.

#### Lesson 2 - MCP servers · ✅ live · Python · Node · .NET · ≈ 30-45 min
**Build:** a Model Context Protocol server that exposes your Lesson 1 document search as a tool an AI
host (e.g. Claude Code) can call natively.
**You'll be able to:** define MCP tools with schemas; serve them over stdio; register and call them
from a host; understand the protocol handshake.
**Assumes:** Lesson 1.

### Cluster 2 · RAG depth

#### Lesson 3 - Hybrid retrieval & reranking · ✅ live · Python · Node · .NET · ≈ 30-45 min
**Build:** a retriever that fuses BM25 with a semantic arm using Reciprocal Rank Fusion, then reranks
the merged list - with a live playground to tune the knobs.
**You'll be able to:** combine lexical and semantic signals; apply RRF; explain the per-document score
breakdown and when hybrid beats either arm alone.
**Assumes:** Lesson 1.

#### Lesson 4 - RAG safety & prompt injection · ✅ live · Python · Node · .NET · ≈ 30-45 min
**Build:** an undefended vs. a defended pipeline over a corpus containing a poisoned document, with
three layered defences - quarantine, isolation, and an output filter.
**You'll be able to:** treat retrieved text as untrusted input; recognise injection patterns; defend a
pipeline in depth and show the answer flip between hijacked and safe.
**Assumes:** Lesson 1 (Lesson 3 helpful).

#### Lesson 5 - RAG evaluation & regression testing · ✅ live · Python · Node · .NET · ≈ 30-45 min
**Build:** an evaluation harness that scores a pipeline against a golden set on recall@k, groundedness,
and answer correctness, with a pass/fail gate that catches a regression a candidate tweak slips in.
**You'll be able to:** turn "seems good" into a tracked number; build a golden set; gate quality in CI;
spot regressions an eyeball check would miss.
**Assumes:** Lesson 1 (Lessons 3-4 helpful).

#### Lesson 6 - Repo-aware AI assistant · 🚧 planned · RAG depth
**Build (planned):** ground an assistant in your own codebase so it answers with repo-specific context.
**Assumes:** Lesson 1.

### Cluster 3 · Framework tour

> Each rebuilds the *same* document agent on a major framework and compares the trade-offs against your
> from-scratch version. Outlines exist under [`roadmap/`](./roadmap/); full lessons are on the roadmap.

#### Lesson 7 - LangChain · 🚧 planned · Python · [outline](./roadmap/LESSON7-langchain.md)
Rebuild the RAG pipeline with LangChain and see exactly which hand-rolled piece each component replaces.

#### Lesson 8 - LangGraph · 🚧 planned · Python · [outline](./roadmap/LESSON8-langgraph.md)
Turn the linear pipeline into a stateful agent graph with retries, tool routing, and memory.

#### Lesson 9 - Ollama + function calling · 🚧 planned · Python · [outline](./roadmap/LESSON9-ollama.md)
Give a local model real tools it can call - 100% offline.

#### Lesson 10 - Microsoft Semantic Kernel · 🚧 planned · C# / .NET · [outline](./roadmap/LESSON10-semantic-kernel.md)
Rebuild the agent in C# with SK plugins and automatic function calling.

#### Lesson 11 - AWS Bedrock Agents · 🚧 planned · cloud (driven locally) · [outline](./roadmap/LESSON11-bedrock.md)
Map your primitives onto a managed cloud agent: knowledge bases + action groups.

#### Lesson 12 - Google AI Development Kit (ADK) · 🚧 planned · Python · [outline](./roadmap/LESSON12-google-adk.md)
Build and run a Gemini agent locally with Google's open-source ADK.

### Cluster 4 · Applied dev workflows

#### Lesson 13 - AI-assisted testing · 🚧 planned · Python · Node · .NET
Generate, run, and review tests, and let failures guide the fix.

#### Lesson 14 - AI code review & issue detection · 🚧 planned · language-agnostic
Use AI to catch the serious issues in review - real bugs, security, risky changes.

#### Lesson 15 - Documentation from sprint changes · 🚧 planned · language-agnostic
Generate release notes and docs straight from a sprint's commits and pull requests.

---

## Prerequisites matrix

Read down the **Requires** column to see what to finish first.

| Lesson | Requires | Recommended first |
|--------|----------|-------------------|
| 1 · RAG from scratch | - | - |
| 2 · MCP servers | 1 | - |
| 3 · Hybrid retrieval | 1 | - |
| 4 · RAG safety | 1 | 3 |
| 5 · RAG evaluation | 1 | 3, 4 |
| 6 · Repo-aware assistant | 1 | 3 |
| 7 · LangChain | 1 | - |
| 8 · LangGraph | 1 | 2, 7 |
| 9 · Ollama + function calling | 1 | 2 |
| 10 · Semantic Kernel | 1 | 9 |
| 11 · Bedrock Agents | 1 | 8, 9 |
| 12 · Google ADK | 1 | 9 |
| 13-15 · Applied workflows | 1 | - |

**Lesson 1 is the spine of the whole course** - its retriever and provider abstraction are reused,
in one form or another, by every lesson after it.

## Suggested pace

- **Weekend intro:** Lessons 1-2 (the foundation - you finish with a cited RAG app exposed as a tool).
- **One focused week:** Lessons 1-5 (the full live curriculum - better, safe, and measurable RAG).
- **Self-paced after that:** pick framework-tour lessons (7-12) as they ship, in any order after
  Lesson 1.

Every live lesson is runnable offline and has an `./run -l <N> test` you can use to confirm your
environment before you start.
