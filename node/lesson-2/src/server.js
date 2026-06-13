// Lesson 2 (Node.js) — an MCP server exposing the Lesson 1 retriever as tools.
//
// A faithful port of the Python reference (`mcp_server.py`). It wraps the same
// document search you built in the Node Lesson 1 port (`node/lesson-1`) as
// Model Context Protocol tools, so an MCP host (e.g. Claude Code) can search
// your local `documents/` folder natively instead of you pasting text.
//
// Run it over stdio (an MCP host launches it as a subprocess):
//
//     node node/lesson-2/src/server.js
//
// or, from the repo root:  ./run -l 2 --lang node serve

import path from "node:path";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

// Reuse the Lesson 1 engine, module-for-module — MCP is a new doorway onto the
// same retriever. Each imported module resolves its own deps from
// node/lesson-1/node_modules, so this port only needs the MCP SDK itself.
import { loadConfig } from "../../lesson-1/src/config.js";
import { getRetriever } from "../../lesson-1/src/engine.js";
import { discoverFiles } from "../../lesson-1/src/extract.js";

const server = new McpServer({ name: "local-ai-lab-docs", version: "1.0.0" });

// --- Tool: search_docs -----------------------------------------------------
// The star of the show. The description is a *prompt*: the model reads it to
// decide WHEN to reach for the tool, so it explicitly says "to ground answers
// in the user's own files instead of relying on training data."
server.registerTool(
  "search_docs",
  {
    title: "Search local documents",
    description:
      "Search the user's local documents and return the most relevant passages. " +
      "Each passage is prefixed with its source as [filename:page] so the model " +
      "can cite it. Call this to ground answers in the user's own files instead " +
      "of relying on training data.",
    inputSchema: {
      query: z.string().describe("What to search for, in natural language."),
      k: z
        .number()
        .int()
        .optional()
        .describe("How many passages to return (default 5)."),
    },
  },
  async ({ query, k }) => {
    const config = loadConfig();
    const retriever = await getRetriever(config);
    const hits = retriever.search(query, Math.max(1, Number.parseInt(k ?? 5, 10) || 5));
    const text = hits.length
      ? hits.map((h) => `[${h.source}:${h.page_number}] ${h.text}`).join("\n\n")
      : "No relevant passages found in the local documents.";
    return { content: [{ type: "text", text }] };
  }
);

// --- Tool: list_documents --------------------------------------------------
// Servers usually expose more than one tool. This lets the model see what's in
// the corpus before searching. Keep each tool small and single-purpose.
server.registerTool(
  "list_documents",
  {
    title: "List local documents",
    description: "List the documents currently available to search in the local corpus.",
    inputSchema: {},
  },
  async () => {
    const config = loadConfig();
    const names = discoverFiles(config.docsDir).map((p) => path.basename(p));
    const text = names.length ? names.join("\n") : "(no documents indexed yet)";
    return { content: [{ type: "text", text }] };
  }
);

async function main() {
  // Default transport is stdio — what Claude Code and most MCP hosts launch.
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  // Log to stderr so it never corrupts the JSON-RPC stream on stdout.
  console.error("MCP server failed:", err);
  process.exit(1);
});
