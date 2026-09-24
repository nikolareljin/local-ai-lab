// Lesson 9 - the tools, and the JSON that describes them to a model.
//
// Mirrors python/tools.py. A tool is a name, a JSON schema for its arguments,
// and a function; the model only ever sees the first two, so the descriptions
// below are prompt text. They are also hashed into every cassette digest, so
// they must stay character-for-character identical to the Python ones.

import { calculate } from "./calculator.mjs";
import { TOP_K, buildRetriever } from "./lesson_core.mjs";
import { cmpCodePoints } from "./pycompat.mjs";

export class Tool {
  constructor(name, description, parameters, fn, { sideEffect = false, intent = "" } = {}) {
    // A tuple of words here used to be the format; a regex string is now.
    // Fail at definition time rather than at the first side effect.
    if (typeof intent !== "string") throw new TypeError(`${name}: intent must be a regex string`);
    Object.assign(this, { name, description, parameters, fn, sideEffect, intent });
  }

  /** The exact shape Ollama's /api/chat expects in its `tools` array. */
  spec() {
    return {
      type: "function",
      function: { name: this.name, description: this.description, parameters: this.parameters },
    };
  }
}

/** What the loop needs from any set of tools. */
export class ToolSet {
  constructor() {
    this.tools = new Map();
  }

  add(...tools) {
    for (const tool of tools) this.tools.set(tool.name, tool);
  }

  specs(only = null) {
    return [...this.tools].filter(([n]) => only === null || only.includes(n)).map(([, t]) => t.spec());
  }

  get(name) {
    return this.tools.get(name) ?? null;
  }
}

/** The core lesson's four tools, bound to one retriever and one outbox. */
export class Toolbox extends ToolSet {
  /** Async because building the retriever reads the corpus. */
  static async create({ retriever = null } = {}) {
    return new Toolbox(retriever ?? (await buildRetriever()));
  }

  constructor(retriever) {
    super();
    this.retriever = retriever;
    this.outbox = [];
    this.add(
      new Tool(
        "search_docs",
        "Search the user's local documents about the Aurora X1 sensor and return " +
          "the most relevant passages. Each passage starts with its source as " +
          "[file:page]; cite it. Use this for any question about the device, its " +
          "setup, networking, battery, warranty, API or support tickets.",
        {
          type: "object",
          properties: {
            query: { type: "string", description: "What to search for." },
            k: { type: "integer", minimum: 1, maximum: 8, description: "How many passages (default 3)." },
          },
          required: ["query"],
        },
        (a) => this.searchDocs(a.query, a.k),
      ),
      new Tool(
        "list_documents",
        "List the file names of the user's local documents.",
        { type: "object", properties: {} },
        () => this.listDocuments(),
      ),
      new Tool(
        "calculator",
        "Evaluate an arithmetic expression such as '2340 * 0.175' or '(14 * 30) / 7'. " +
          "Use it for every calculation instead of doing arithmetic yourself.",
        {
          type: "object",
          properties: { expression: { type: "string" } },
          required: ["expression"],
        },
        (a) => calculate(a.expression),
      ),
      new Tool(
        "create_ticket",
        "Open a support ticket. Only call this when the user explicitly asks " +
          "for a ticket to be opened.",
        {
          type: "object",
          properties: {
            title: { type: "string", maxLength: 120 },
            severity: { type: "string", enum: ["low", "normal", "high"] },
          },
          required: ["title", "severity"],
        },
        (a) => this.createTicket(a.title, a.severity),
        {
          sideEffect: true,
          // A verb and the object, not the bare noun: "Summarize support
          // ticket 9001" mentions a ticket and asks for nothing to be opened.
          intent: String.raw`\b(open|create|file|raise|log)\b[^.?!]{0,40}\bticket\b`,
        },
      ),
    );
  }

  // The tools themselves ----------------------------------------------------

  searchDocs(query, k = TOP_K) {
    // k has passed the schema (an integer, 1-8) by the time it gets here.
    const hits = this.retriever.search(query, Math.max(1, Number(k ?? TOP_K)));
    if (!hits.length) return "No relevant passages found in the local documents.";
    return hits.map((h) => `[${h.source}:${h.page_number}] ${h.text}`).join("\n\n");
  }

  listDocuments() {
    const names = [...new Set(this.retriever.chunks.map((c) => c.source))].sort(cmpCodePoints);
    return names.join("\n") || "(no documents indexed)";
  }

  createTicket(title, severity) {
    const ticket = { id: `T-${1001 + this.outbox.length}`, title, severity };
    this.outbox.push(ticket);
    return `Ticket ${ticket.id} opened: ${title} (${severity}).`;
  }
}
