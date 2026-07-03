# Extending Lesson 6 to your own repositories

The demo indexes a bundled sample repo so the output is reproducible. The whole
point, though, is to point the **same code** at a **real repository** and get
cited answers, honest *not-found*s, and plan-before-edit on your own codebase.

Three ways to do that, smallest first.

---

## 0 · Point it at a real repo (no new code)

Every port honours the **`REPO_PATH`** environment variable. Unset, it indexes
`data/repo`; set, it indexes your repository instead (skipping `.git`,
`node_modules`, build output, and non-text files):

```bash
# from the repo root of local-ai-lab
REPO_PATH=/path/to/your/repo \
  python lessons/06-repo-aware-assistant/python/repo_assistant.py ask "where is auth handled?"

REPO_PATH=/path/to/your/repo \
  python lessons/06-repo-aware-assistant/python/repo_assistant.py plan "where should I add a cache?"
```

`ask` returns a cited answer (or *not found*); `plan` returns a plan-before-edit.
The Node and C# ports take the same subcommands and `REPO_PATH`:

```bash
REPO_PATH=/path/to/repo node   lessons/06-repo-aware-assistant/node/repo_assistant.mjs ask "…"
REPO_PATH=/path/to/repo dotnet run --project lessons/06-repo-aware-assistant/dotnet -c Release -- ask "…"
```

> Note: don't pass `--nologo` to `dotnet run` when you also pass `-- ask "…"`; it
> swallows the application arguments. `-c Release -- ask "…"` is enough.

---

## 1 · A standalone `repo-ask` app

[`extend/repo-ask`](./extend/repo-ask) is a tiny wrapper that indexes the current
directory (or `REPO_PATH`) and asks one question. It depends only on the Python
port and the standard library, so you can copy three files anywhere and run:

```bash
cp lessons/06-repo-aware-assistant/extend/repo-ask   ~/bin/repo-ask
cp lessons/06-repo-aware-assistant/python/repo_assistant.py  ~/bin/../python/   # keep ../python/repo_assistant.py next to it
# then, inside ANY repo:
cd ~/work/my-service
repo-ask "where is the HTTP server started?"
repo-ask plan "where should I add request logging?"
```

To make it truly self-contained, keep the layout `bin/repo-ask` +
`python/repo_assistant.py` + `data/questions.json` (the launcher resolves the port
relative to itself). That's a working internal CLI a whole team can share.

---

## 2 · A repo-search MCP tool (a Claude Code skill)

Lesson 2 built an MCP server; this lesson gives it something worth serving.
Expose `ask`/`plan` as MCP tools and any MCP host (Claude Code, an IDE) can search
your repo with citations - and, because the assistant abstains, it won't invent
answers about code that isn't there.

```python
# repo_mcp.py - a repo-search MCP tool built on the Lesson 6 assistant.
# Run your host against this over stdio (see Lesson 2's mcp_server.py for wiring).
import os
from mcp.server.fastmcp import FastMCP           # pip install "mcp[cli]"
from repo_assistant import build_index, answer, plan   # the Lesson 6 port

REPO = os.environ.get("REPO_PATH", ".")
FILES, CHUNKS = build_index(REPO)
mcp = FastMCP("repo-search")

@mcp.tool()
def repo_ask(question: str, top_k: int = 3, min_score: int = 2) -> dict:
    """Answer a question about the repo, with citations, or say not_found."""
    return answer(question, CHUNKS, top_k, min_score)

@mcp.tool()
def repo_plan(question: str, top_k: int = 3) -> dict:
    """Return a plan-before-edit (relevant files, behaviour, change, tests, docs). Edits nothing."""
    return plan(question, FILES, CHUNKS, top_k)

if __name__ == "__main__":
    mcp.run()
```

Register it the way Lesson 2 registers its server (`claude mcp add …`), point
`REPO_PATH` at the repo you're working in, and your assistant can now cite
`path:line` from *that* repo. The `min_score` gate is what keeps it honest - a tool
that can return `not_found` is one a host can trust.

---

## 3 · Import the pieces into your own code

The port is a small, dependency-free library. Reuse the parts you want and swap
the rest:

```python
from repo_assistant import build_index, retrieve, answer, plan, cite

files, chunks = build_index("/path/to/repo")   # index once
hits = retrieve("where is chunking done", chunks, top_k=5)
for score, ch in hits:
    print(score, cite(ch), "->", ch["first_line"])
```

**What to swap for production** (see the lesson's *From demo to production*):

- **Retrieval:** replace the keyword `retrieve()` with BM25, embeddings, or the
  Lesson 3 hybrid. Everything downstream only needs passages that carry a `path`
  and a line range.
- **Answer/plan:** replace the extractive stand-ins with a model, but **keep the
  contract** - require every claim to cite a `path:line` from the retrieved set,
  and keep the `min_score`/`not_found` gate so the model must abstain too.
- **Index signal:** index symbols, imports, git blame and PR history, not just
  blank-line passages.
- **Evaluate it:** fold your questions into Lesson 5's golden set so a drop in
  citation accuracy - or a lost *not-found* - fails a check instead of shipping.

The teaching demo and the production tool share the same three rules: **answer
only from indexed lines, always cite, and refuse rather than invent.**
