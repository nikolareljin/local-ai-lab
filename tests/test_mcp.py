"""Integration test for the Lesson 2 MCP server.

Spawns mcp_server.py over stdio (as a real MCP client would), lists its tools,
and calls search_docs — asserting it returns a cited passage from the sample
document. No network and no LLM; skipped if the MCP SDK isn't installed.
"""

import asyncio
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


async def _run():
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "mcp_server.py")],
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            result = await session.call_tool(
                "search_docs", {"query": "how do I reset the device", "k": 3}
            )
            text = "".join(getattr(c, "text", "") for c in result.content)
            return names, text


def test_mcp_server_exposes_and_runs_search_docs():
    names, text = asyncio.run(asyncio.wait_for(_run(), timeout=60))
    assert "search_docs" in names
    assert "list_documents" in names
    # The reset instructions live in documents/sample_manual.md.
    assert "power button" in text.lower()
    assert "sample_manual.md" in text
