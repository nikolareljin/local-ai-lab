// Demo client for the Lesson 2 (Node.js) MCP server.
//
// Spawns `server.js` over stdio (exactly as an MCP host like Claude Code
// would), lists its tools, and calls them — proving the server works locally
// without needing an LLM. Run via:  ./run -l 2 --lang node
// or:  node node/lesson-2/src/demo.js "your question"

import path from "node:path";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SERVER = path.join(__dirname, "server.js");
const QUERY = process.argv[2] || "How do I reset the device?";

function textOf(result) {
  return (result.content || [])
    .map((c) => (c.type === "text" ? c.text : ""))
    .join("");
}

async function main() {
  // The host launches the server as a subprocess and talks JSON-RPC over stdio.
  const transport = new StdioClientTransport({
    command: process.execPath, // the same Node binary running this demo
    args: [SERVER],
  });
  const client = new Client({ name: "local-ai-lab-demo", version: "1.0.0" });
  await client.connect(transport);

  // The handshake in code: connect() does initialize, then list + call.
  const tools = await client.listTools();
  console.log(
    "Connected to MCP server. Tools:",
    tools.tools.map((t) => t.name).join(", ")
  );

  const docs = await client.callTool({ name: "list_documents", arguments: {} });
  console.log("\nlist_documents ->");
  console.log(textOf(docs));

  console.log(`\nsearch_docs(${JSON.stringify(QUERY)}, k=3) ->`);
  const res = await client.callTool({
    name: "search_docs",
    arguments: { query: QUERY, k: 3 },
  });
  console.log(textOf(res));

  await client.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
