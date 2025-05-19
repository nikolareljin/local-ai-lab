"""Lesson 2 — an MCP server exposing the Lesson 1 retriever as tools.

This wraps the same document search you built in Lesson 1 (`localrag`) as
Model Context Protocol tools, so an MCP client (e.g. Claude Code) can search
your local `documents/` folder natively instead of you pasting text into a
prompt.

Run it over stdio (an MCP client launches it as a subprocess):

    python mcp_server.py

Or register it with Claude Code (see LESSON2.md) and just ask questions in chat.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from localrag.config import load_config
from localrag.engine import get_retriever
from localrag.extract import discover_files

mcp = FastMCP("local-ai-lab-docs")


@mcp.tool()
def search_docs(query: str, k: int = 5) -> str:
    """Search the user's local documents and return the most relevant passages.

    Each passage is prefixed with its source as ``[filename:page]`` so the model
    can cite it. Call this to ground answers in the user's own files instead of
    relying on training data.

    Args:
        query: What to search for, in natural language.
        k: How many passages to return (default 5).
    """
    config = load_config()
    hits = get_retriever(config).search(query, max(1, int(k)))
    if not hits:
        return "No relevant passages found in the local documents."
    return "\n\n".join(
        f"[{h['source']}:{h['page_number']}] {h['text']}" for h in hits
    )


@mcp.tool()
def list_documents() -> str:
    """List the documents currently available to search in the local corpus."""
    config = load_config()
    names = [p.name for p in discover_files(config.docs_dir)]
    return "\n".join(names) if names else "(no documents indexed yet)"


def main() -> None:
    # Default transport is stdio — what Claude Code and most MCP hosts launch.
    mcp.run()


if __name__ == "__main__":
    main()
