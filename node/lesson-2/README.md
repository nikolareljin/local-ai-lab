# Lesson 2 (Node.js) — an MCP server

A faithful Node.js (ESM, Node 18+) port of [Lesson 2](../../LESSON2.md) of
**local-ai-lab**. It exposes the Lesson 1 document search as **Model Context
Protocol** tools (`search_docs`, `list_documents`) over **stdio**, so an MCP
host like Claude Code can search your local `documents/` folder natively.

It reuses the Node Lesson 1 engine module-for-module — `loadConfig`,
`getRetriever`, and `discoverFiles` are imported straight from
[`node/lesson-1`](../lesson-1). MCP is a new doorway onto the same retriever.

Built on the official [`@modelcontextprotocol/sdk`](https://www.npmjs.com/package/@modelcontextprotocol/sdk).

## Run

From the repo root (preferred — the `run` dispatcher routes `--lang node` here):

```bash
./run -l 2 --lang node                 # demo the server end-to-end (no LLM needed)
./run -l 2 --lang node serve           # run the server over stdio (a host connects to it)
./run -l 2 --lang node register        # register it with Claude Code
./run -l 2 --lang node test            # offline smoke test (drives it via the demo client)
```

Or directly:

```bash
bash node/lesson-2/run.sh demo                       # or: serve | register | test
cd node/lesson-2 && npm install && node src/demo.js  # spawn server, list tools, call them
```

## What's inside

| File | What it does |
|------|--------------|
| `src/server.js` | the MCP server: `McpServer` + `StdioServerTransport`, two tools |
| `src/demo.js` | an stdio **client** that spawns the server, lists tools, and calls them |
| `run.sh` | `demo` / `serve` / `register` / `test` actions |

## Test it (offline smoke test)

No network, no API key, no LLM — the demo client spawns the server, does the MCP
handshake, lists the tools, and calls `search_docs` against the committed sample
corpus:

```bash
./run -l 2 --lang node test
# Connected to MCP server. Tools: search_docs, list_documents
# list_documents -> sample_manual.md ...
# search_docs("How do I reset the device?", k=3) -> [sample_manual.md:1] ... power button ...
```

## Register with Claude Code

```bash
claude mcp add local-ai-lab-docs-node -- node node/lesson-2/src/server.js
claude mcp list                         # confirm it's registered
```

Prefer **absolute paths** if you run Claude Code from elsewhere. The Node server
registers under a distinct name (`local-ai-lab-docs-node`) so it can live
alongside the Python server.

## Parity notes vs. the Python reference

- **Tools:** `search_docs` and `list_documents`, identical shape and citation
  format (`[filename:page]`) to [`mcp_server.py`](../../mcp_server.py).
- **Engine:** reuses the Node Lesson 1 retriever, so the same parity notes apply
  — **BM25 only** (no embeddings), `claude`/`ollama` providers, and PDFs as a
  single page. See [`node/lesson-1/README.md`](../lesson-1/README.md).
- **Cache:** shares the Node index under `<repoRoot>/.localrag/node/`, so it
  never clobbers the Python index.

## Course

Part of [local-ai-lab](https://nikolareljin.github.io/local-ai-lab/) — a
hands-on course for building local AI.
