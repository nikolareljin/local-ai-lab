"""Demo client for the Lesson 2 MCP server.

Spawns ``mcp_server.py`` over stdio (exactly as an MCP host like Claude Code
would), lists its tools, and calls them — proving the server works locally
without needing an LLM. Run via:  ``./run -l 2 demo``  or  ``python examples/mcp_demo.py "your question"``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parent.parent
QUERY = sys.argv[1] if len(sys.argv) > 1 else "How do I reset the device?"


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "mcp_server.py")],
        cwd=str(ROOT),
    )
    with open(os.devnull, "w") as devnull:
        async with stdio_client(params, errlog=devnull) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                print("Connected to MCP server. Tools:",
                      ", ".join(t.name for t in tools.tools))

                docs = await session.call_tool("list_documents", {})
                print("\nlist_documents ->")
                print("".join(getattr(c, "text", "") for c in docs.content))

                print(f"\nsearch_docs({QUERY!r}, k=3) ->")
                res = await session.call_tool("search_docs", {"query": QUERY, "k": 3})
                print("".join(getattr(c, "text", "") for c in res.content))


if __name__ == "__main__":
    asyncio.run(main())
