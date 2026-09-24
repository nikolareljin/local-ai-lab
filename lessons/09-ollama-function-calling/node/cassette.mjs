// Lesson 9 - recording a real model once, replaying it forever.
//
// Mirrors python/cassette.py. Only the model is replayed; the loop, the schema
// validation, the guards and the tools all run for real. Each recorded turn
// carries a digest of the exact conversation the model was shown, and replay
// refuses when today's conversation hashes differently.
//
// The digest is sha256 over Python's json.dumps(sort_keys=True,
// ensure_ascii=False), first 16 hex digits. pycompat.dumps reproduces those
// bytes, and this port's tools produce byte-identical output to Python's (same
// chunks, same BM25 ranking, same formatting), so the Node replay verifies the
// digests the Python recorder wrote - not merely the turn count.

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import { dumps, loads, num } from "./pycompat.mjs";

export class RuntimeError extends Error {}
export class CassetteDrift extends RuntimeError {}

const SHOWN = ["role", "content", "tool_calls", "tool_name"];

export function digest(messages, tools) {
  const shown = {
    messages: messages.map((m) => Object.fromEntries(SHOWN.map((k) => [k, Object.hasOwn(m, k) ? m[k] : null]))),
    tools,
  };
  const blob = dumps(shown, { sortKeys: true, ensureAscii: false });
  return createHash("sha256").update(blob, "utf8").digest("hex").slice(0, 16);
}

/** Plays one task's recorded turns back, checking each one still applies. */
export class Replay {
  constructor(turns, label = "", { strict = true } = {}) {
    this.turns = [...turns];
    this.label = label;
    this.strict = strict;
    this.used = 0;
    this.diverged = false;
  }

  drift(why) {
    // strict (demo): refuse. Not strict: end the run honestly, because nobody
    // recorded the model's reply to a conversation that did not happen.
    if (this.strict) throw new CassetteDrift(`${this.label}: ${why}`);
    this.diverged = true;
    return { message: { role: "assistant", content: "" }, seconds: 0.0 };
  }

  async chat(messages, tools) {
    if (this.used >= this.turns.length) {
      return this.drift(`the loop asked for turn ${this.used + 1}, only ${this.turns.length} were recorded`);
    }
    const turn = this.turns[this.used];
    if (turn.digest !== digest(messages, tools)) {
      return this.drift(`turn ${this.used + 1} was recorded against a different conversation - re-record with ./run -l 9 record`);
    }
    this.used += 1;
    return { message: turn.message, seconds: num(turn.seconds) };
  }
}

/** A cassette, parsed so that 3 and 3.0 stay different (see pycompat). */
export function load(file) {
  return loads(readFileSync(file, "utf8"));
}
