# Lesson 2 · MCP server (C# / .NET 8 port)

A faithful C# port of [Lesson 2](../../LESSON2.md) of **local-ai-lab**. It
exposes the Lesson 1 document search as **Model Context Protocol** tools
(`search_docs`, `list_documents`) over **stdio**, so an MCP host like Claude
Code can search your local `documents/` folder natively.

It reuses the C# Lesson 1 engine module-for-module - `Config`, `Extract`,
`Chunk`, `Store`, and `Retriever` are compiled straight from
[`dotnet/lesson-1`](../lesson-1) (no `Providers`/`Prompts`, so the server has no
LLM dependency). MCP is a new doorway onto the same retriever.

Built on the official [`ModelContextProtocol`](https://www.nuget.org/packages/ModelContextProtocol) C# SDK.

## Run it (from the repo root)

```bash
./run -l 2 --lang csharp                 # demo the server end-to-end (no LLM needed)
./run -l 2 --lang csharp serve           # run the server over stdio (a host connects to it)
./run -l 2 --lang csharp register        # register it with Claude Code
./run -l 2 --lang csharp test            # offline smoke test (drives it via the demo client)
```

Or directly:

```bash
bash dotnet/lesson-2/run.sh demo                      # or: serve | register | test
cd dotnet/lesson-2 && dotnet run -c Release -- demo   # spawn server, list tools, call them
```

## What's inside

| Piece | What it does |
|-------|--------------|
| `Program.cs` (`serve`) | the MCP server: `AddMcpServer().WithStdioServerTransport().WithToolsFromAssembly()` |
| `DocTools` | the two `[McpServerTool]` methods (`search_docs`, `list_documents`) |
| `Program.cs` (`demo`) | an stdio **client** (`McpClient`) that spawns the server and calls its tools |

Logs are routed to **stderr** (`LogToStandardErrorThreshold = Trace`) so they
never corrupt the JSON-RPC stream on stdout - the one rule every stdio server
must follow.

## Test it (offline smoke test)

No network, no API key, no LLM - the demo client spawns the server (`dotnet
LocalRagMcp.dll serve`), does the MCP handshake, lists the tools, and calls
`search_docs` against the committed sample corpus:

```bash
./run -l 2 --lang csharp test
# Connected to MCP server. Tools: search_docs, list_documents
# list_documents -> sample_manual.md ...
# search_docs("How do I reset the device?", k=3) -> [sample_manual.md:1] ... power button ...
```

## Register with Claude Code

```bash
claude mcp add local-ai-lab-docs-dotnet -- dotnet dotnet/lesson-2/bin/Release/net8.0/LocalRagMcp.dll serve
claude mcp list                          # confirm it's registered
```

Prefer **absolute paths** if you run Claude Code from elsewhere. The C# server
registers under a distinct name (`local-ai-lab-docs-dotnet`) so it can live
alongside the Python and Node servers.

## Parity notes vs. the Python reference

- **Tools:** `search_docs` and `list_documents`, identical shape and citation
  format (`[filename:page]`) to [`mcp_server.py`](../../mcp_server.py).
- **Engine:** reuses the C# Lesson 1 retriever, so the same parity notes apply
  - **BM25 only** (no embeddings). See [`dotnet/lesson-1/README.md`](../lesson-1/README.md).
- **Cache:** shares the .NET index under `<repoRoot>/.localrag/dotnet/`, so it
  never clobbers the Python index.

Part of the [local-ai-lab](https://nikolareljin.github.io/local-ai-lab/) course.
