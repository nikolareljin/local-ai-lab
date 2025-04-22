# Lesson 2 · Build an MCP Server

> **Part of [local-ai-lab](https://nikolareljin.github.io/local-ai-lab/)** — a hands-on course for building local AI.
>
> ▶ **Interactive version (slides):** https://nikolareljin.github.io/local-ai-lab/lesson-2-mcp.html
> 🏠 **Course home:** https://nikolareljin.github.io/local-ai-lab/
> 💻 **Source:** https://github.com/nikolareljin/local-ai-lab
>
> **Lessons:** [1 · RAG](./LESSON1.md) → **2 · MCP (you are here)** → [3 · LangChain](./LESSON3.md) → [4 · LangGraph](./LESSON4.md) → [5 · Ollama tools](./LESSON5.md) → [6 · Semantic Kernel](./LESSON6.md) → [7 · Bedrock Agents](./LESSON7.md) → [8 · Google ADK](./LESSON8.md)
>
> 🚧 **Status: coming soon.** This page is the lesson outline and the design we'll build. The full
> step-by-step (with runnable code) lands in a future update — ⭐ the repo to follow along.

---

## What you'll learn

In [Lesson 1](./LESSON1.md) **your app** drove the pipeline and called the LLM. In Lesson 2 the
relationship **flips**: *the LLM* drives, and your retriever becomes a **tool** it reaches for on
demand. Same retrieval engine, new integration surface.

You'll learn:

- **What MCP is** — the Model Context Protocol, an open standard for connecting AI clients to tools
- **Servers, tools, and resources** — the core MCP concepts and the JSON-RPC handshake
- **The stdio transport** — how Claude Code launches and talks to a local server as a subprocess
- **Tool design** — schemas, descriptions, and returning grounded context the model can cite
- **Wiring** — registering your server in Claude Code's MCP configuration
- **Security** — keeping a local tool safe and scoped to your folder

---

## Concept: what is MCP, and why?

The **Model Context Protocol (MCP)** is an open standard that lets an AI client (like Claude Code,
or a desktop assistant) **discover and call external tools** over a simple JSON-RPC connection.
Instead of *you* pasting document text into a prompt, the model calls a `search_docs` tool and
pulls the context itself, exactly when it needs it.

```
   ┌──────────────┐   "list your tools"      ┌───────────────────────────┐
   │ Claude Code  │ ───────────────────────▶ │ local-ai-lab MCP server   │
   │  (MCP host)  │                          │  exposes: search_docs()   │
   │              │ ◀─────────────────────── │                           │
   └──────┬───────┘   tool schemas           └─────────────┬─────────────┘
          │                                                 │ reuses Lesson 1
          │  user: "how do I reset the device?"             ▼
          │  model decides to call search_docs("reset")  documents/ + retriever
          ▼
   grounded answer with citations
```

**Why it matters:** RAG you can call from *any* MCP-aware client, with no bespoke UI. Your documents
become a first-class capability of the assistant itself.

---

## The design we'll build

A tiny **stdio MCP server** that wraps the Lesson 1 retriever and advertises one tool. Notice how
much we reuse — `get_retriever` and the chunk format come straight from Lesson 1. MCP is just a new
doorway onto the same engine.

**`mcp_server.py`** (design sketch)

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

from localrag.config import load_config
from localrag.engine import get_retriever

server = Server("local-ai-lab-docs")


@server.list_tools()
async def list_tools():
    return [{
        "name": "search_docs",
        "description": "Search the user's local documents and return the most "
                       "relevant passages, each tagged [source:page] for citation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for"},
                "k": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    }]


@server.call_tool()
async def call_tool(name, arguments):
    if name != "search_docs":
        raise ValueError(f"Unknown tool: {name}")
    config = load_config()
    hits = get_retriever(config).search(arguments["query"], arguments.get("k", 5))
    text = "\n\n".join(
        f"[{h['source']}:{h['page_number']}] {h['text']}" for h in hits)
    return [{"type": "text", "text": text or "No relevant passages found."}]


# Run over stdio so Claude Code can launch this as a subprocess.
# async def main(): async with stdio_server() as (r, w): await server.run(r, w, ...)
```

## Registering it with Claude Code

You'll add the server to your MCP config so the client launches it on demand:

```jsonc
// ~/.claude/mcp.json (illustrative)
{
  "mcpServers": {
    "local-ai-lab-docs": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "/path/to/local-ai-lab"
    }
  }
}
```

Then, in a normal Claude Code chat, ask a question about your files — and watch the model call
`search_docs` against your own `documents/` folder and answer with citations. RAG, but **native to
the assistant**.

---

## What this builds on

| From Lesson 1 | Reused in Lesson 2 |
|---------------|--------------------|
| `engine.get_retriever()` | the tool's search backend |
| chunk `{source, page_number, text}` | the cited tool output |
| `documents/` corpus | the data the tool searches |
| grounding mindset | the model still cites `[source:page]` |

## Prerequisites

Finish [Lesson 1](./LESSON1.md) first — the MCP server is a thin wrapper over the retriever you
build there.

## Next lesson

[**Lesson 3 · LangChain →**](./LESSON3.md) — rebuild the RAG pipeline with LangChain and compare it,
honestly, against your from-scratch version.

---

*Course: [nikolareljin.github.io/local-ai-lab](https://nikolareljin.github.io/local-ai-lab/) ·
Source: [github.com/nikolareljin/local-ai-lab](https://github.com/nikolareljin/local-ai-lab) ·
Author: [Nik Reljin](https://www.linkedin.com/in/nikolareljin)*
