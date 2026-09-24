// Lesson 9 - Ollama's /api/chat with tools, and nothing else.
//
// Mirrors python/ollama_chat.py over Node's built-in fetch: no SDK, no npm
// package, because the point is to see the JSON.
//
// Request:   {"model", "messages", "tools": [...], "stream": false, "options": {...}}
// Response:  {"message": {"role": "assistant", "content": "...",
//                         "tool_calls": [{"function": {"name": ..., "arguments": {...}}}]}}

import net from "node:net";

import { RuntimeError } from "./cassette.mjs";
import { dumps, formatFixed, isDict, loads, pyRound, repr } from "./pycompat.mjs";

/** The model failed: a crash, a bad request, a missing model. */
export class OllamaError extends RuntimeError {}
/** The server is not there. Not the model's fault. */
export class OllamaUnreachable extends OllamaError {}

// Parse with pycompat.loads so a float argument stays a float, as it does when
// Python's requests parses the same body.
async function readJson(resp) {
  const text = await resp.text();
  try {
    return loads(text);
  } catch {
    return { error: text.slice(0, 200) || `HTTP ${resp.status}` };
  }
}

// Could a TCP connection to the server be opened at all, within `ms`?
function reachable(base, ms = 5_000) {
  const url = new URL(base);
  const port = Number(url.port) || (url.protocol === "https:" ? 443 : 80);
  return new Promise((resolve) => {
    const sock = net.connect({ host: url.hostname, port, timeout: ms });
    const done = (ok) => {
      sock.destroy();
      resolve(ok);
    };
    sock.once("connect", () => done(true)).once("timeout", () => done(false)).once("error", () => done(false));
  });
}

async function post(base, route, body, timeoutMs) {
  try {
    return await fetch(`${base}${route}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // dumps, not JSON.stringify: a PyFloat argument must go back as 3.0, not {"value":3}.
      body: dumps(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (exc) {
    // fetch has one deadline for connect and reply together, where requests has
    // one for each. So when it fires, probe the port: a server that answers is
    // there and the model was slow (a result); one that does not is an outage.
    if (exc.name === "TimeoutError" && (await reachable(base))) {
      throw new OllamaError(`no reply within ${formatFixed(timeoutMs / 1000, 0)}s`);
    }
    throw new OllamaUnreachable(`cannot reach Ollama at ${base}: ${exc.cause?.message ?? exc.message}`);
  }
}

export async function show(url, model) {
  const resp = await post(url.replace(/\/+$/, ""), "/api/show", { model }, 30_000);
  const body = resp.status === 200 ? await readJson(resp) : {};
  return isDict(body) ? body : {};
}

export class OllamaModel {
  constructor(url, model, { think = false, temperature = 0.0, seed = 7, numCtx = 8192, timeoutMs = 600_000 } = {}) {
    this.url = url.replace(/\/+$/, "");
    this.model = model;
    this.think = think;
    // num_ctx: Ollama's default window is 4K on machines with under 24 GB of VRAM.
    // Tool schemas, three passages and a few turns fit in 8K; past the window,
    // Ollama truncates the prompt and the model never sees what was cut.
    this.options = { temperature, seed, num_ctx: numCtx };
    this.timeoutMs = timeoutMs;
    this.caps = null;
  }

  /** What the model's own metadata claims: e.g. ['completion', 'tools', 'thinking']. */
  async capabilities() {
    if (this.caps === null) this.caps = (await show(this.url, this.model)).capabilities ?? [];
    return this.caps;
  }

  async chat(messages, tools) {
    const payload = { model: this.model, messages, stream: false, options: this.options };
    if (tools.length) payload.tools = tools;
    // Sending `think` to a model without the capability is an error, not a no-op.
    if (this.think !== null && (await this.capabilities()).includes("thinking")) payload.think = this.think;
    const started = performance.now();
    const resp = await post(this.url, "/api/chat", payload, this.timeoutMs);
    if (resp.status === 404) {
      throw new OllamaError(`model ${repr(this.model)} not found - run: ollama pull ${this.model}`);
    }
    const parsed = await readJson(resp);
    const body = isDict(parsed) ? parsed : {};
    if (resp.status !== 200 || "error" in body) throw new OllamaError(body.error || `HTTP ${resp.status}`);
    const msg = isDict(body.message) ? body.message : {};
    const keep = { role: "assistant", content: msg.content || "" };
    if (Array.isArray(msg.tool_calls) && msg.tool_calls.length) keep.tool_calls = msg.tool_calls;
    return { message: keep, seconds: pyRound((performance.now() - started) / 1000, 1) };
  }
}
