// Lesson 9 - Ollama + function calling: the command line, Node.js port.
//
//   node node/function_calling.mjs                 offline: router vs recorded models vs guards
//   node node/function_calling.mjs ask "<question>" [--model M] [--think] [--lenient] [--max-turns N]
//                                                  live: a local model with tools, you confirm side effects
//
// `demo` prints byte-for-byte what `python python/function_calling.py demo`
// prints. It replays the same cassettes through a port of the same loop, the
// same guards and the same tools, and every recorded turn's digest is checked
// against the conversation this runtime builds - so parity is verified on every
// run, not assumed. `trace`, `bench`, `record` and `models` stay in Python.
//
// Live actions need Ollama (OLLAMA_URL, OLLAMA_MODEL in the repo's .env, read by
// Lesson 1's Node config loader). `demo` needs nothing: no model, no network,
// no npm install.

import { readdirSync } from "node:fs";
import path from "node:path";
import { createInterface } from "node:readline/promises";

import * as cassette from "./cassette.mjs";
import { CASSETTE_DIR, CORPUS_DIR, NOTES_DIR, loadTasks, ollamaSettings } from "./lesson_core.mjs";
import { OllamaModel } from "./ollama_chat.mjs";
import {
  cmpCodePoints, formatFixed, len, ljust, pyRegex, repr, rjust, slice, str, truthy,
} from "./pycompat.mjs";
import * as router from "./router.mjs";
import { run } from "./tool_loop.mjs";
import { Toolbox } from "./tools.mjs";

const ABBR = new Map([["search_docs", "S"], ["calculator", "C"], ["list_documents", "L"], ["create_ticket", "T"]]);
const LEGEND = "S search_docs  C calculator  L list_documents  T create_ticket  " +
  "? a tool that does not exist";
// Statuses set by the loop's guards. `declined` is a human saying no, and
// `tool error` is the tool refusing its own input: neither is a guard stop.
const GUARD_STOPS = ["unknown tool", "invalid args", "not requested", "repeat"];
const CITES = pyRegex(String.raw`\[[\w.-]+:\d+\]`);

const print = (line = "") => process.stdout.write(line + "\n");
const count = (xs, pred = Boolean) => xs.filter(pred).length;
const setEq = (a, b) => {
  const x = new Set(a), y = new Set(b);
  return x.size === y.size && [...x].every((v) => y.has(v));
};

// --- shared helpers ---------------------------------------------------------------

/** Every cassette on disk, in file-name order. */
function recordedModels() {
  return readdirSync(CASSETTE_DIR)
    .filter((f) => f.endsWith(".json"))
    .sort(cmpCodePoints)
    .map((f) => cassette.load(path.join(CASSETTE_DIR, f)));
}

/** The demo's stand-in for a human: says yes. It only ever sees calls that have
 *  already passed the schema and the intent check. */
const policyConfirm = async () => true;

// One line reader for the whole run. Its async iterator queues lines, so a
// piped "y\nn\n" answers two prompts in order; terminal: false leaves echo to
// the tty. A closed stdin answers "no".
let lines = null;

async function askHuman(name, args) {
  if (lines === null) lines = createInterface({ input: process.stdin, terminal: false })[Symbol.asyncIterator]();
  process.stdout.write(`\n  The model wants to run ${str(name)}(${str(args)}). Allow? [y/N] `);
  const { value, done } = await lines.next();
  if (done) print();
  return !done && ["y", "yes"].includes(value.trim().toLowerCase());
}

/** Judge one run against the task's `expect`. Only ever called after the run. */
function score(task, result) {
  const proposed = result.calls.map((c) => c.name);
  const answer = result.answer || "";
  return {
    right: setEq(proposed, task.expect),
    proposed,
    first_valid: !result.calls.length || result.calls[0].status !== "invalid args",
    stops: result.calls.filter((c) => GUARD_STOPS.includes(c.status)),
    flagged: count(result.calls, (c) => c.flags.length > 0),
    cites: CITES.test(answer),
    searched: proposed.includes("search_docs"),
    turns: result.turns,
    seconds: result.seconds,
  };
}

function cell(s) {
  if (s === null) return "crashed";
  const tools = [...new Set(s.proposed)].map((n) => ABBR.get(n) ?? "?").join("") || "-";
  return ljust(tools, 4) + (s.right ? "ok" : "XX");
}

/** Run every task through the real loop with this model's recorded replies. */
async function replayAll(tape, tasks, retriever, { maxTurns, lenient = false }) {
  const out = {};
  for (const task of tasks) {
    const rec = tape.tasks[task.id] ?? {};
    if (truthy(rec.error)) {
      out[task.id] = null;
      continue;
    }
    if (!rec.turns) throw new Error(`${tape.model}: no recording for ${task.id}`);
    const model = new cassette.Replay(rec.turns, `${str(tape.model)} ${task.id}`);
    const result = await run(model, task.ask, await Toolbox.create({ retriever }), {
      maxTurns, confirm: policyConfirm, lenient,
    });
    out[task.id] = { ...score(task, result), result };
  }
  return out;
}

function printScorecard(names, runs, tasks, lenient = null) {
  const width = Math.max(12, ...names.map(len));
  print(`  ${ljust("", 24)}` + names.map((n) => rjust(n, width + 2)).join(""));
  const row = (label, fn) => print(`  ${ljust(label, 24)}` + names.map((n) => rjust(fn(runs[n]), width + 2)).join(""));
  const done = (r) => Object.values(r).filter(Boolean);
  const sum = (xs) => xs.reduce((a, b) => a + b, 0);

  const n = tasks.length;
  row("right tools", (r) => `${count(done(r), (s) => s.right)}/${n}`);
  if (lenient && Object.keys(lenient).length) {
    print(`  ${ljust("  ...with --lenient", 24)}` +
      names.map((m) => rjust(`${count(done(lenient[m]), (s) => s.right)}/${n}`, width + 2)).join(""));
  }
  row("first call valid", (r) => `${count(done(r), (s) => s.first_valid)}/${done(r).length}`);
  row("cites when it searched", (r) =>
    `${count(done(r), (s) => s.searched && s.cites)}/${count(done(r), (s) => s.searched)}`);
  row("calls a guard stopped", (r) => String(sum(done(r).map((s) => s.stops.length))));
  row("model round trips", (r) => String(sum(done(r).map((s) => s.turns))));
  row("crashed", (r) => String(count(Object.values(r), (s) => s === null)));
  row("seconds (recorded)", (r) => formatFixed(sum(done(r).map((s) => s.seconds)), 0));
}

// --- demo -------------------------------------------------------------------------

async function cmdDemo() {
  const data = loadTasks();
  const tasks = data.tasks, maxTurns = data.settings.max_turns;
  const base = await Toolbox.create();
  const retriever = base.retriever;
  const docs = new Set(retriever.chunks.map((c) => c.source));

  print("Lesson 9 - Ollama + function calling");
  print("=".repeat(36));
  print(`Corpus : ${docs.size} documents from ${path.basename(path.dirname(path.dirname(CORPUS_DIR)))} + ` +
    `${path.basename(NOTES_DIR)}/, ${retriever.chunks.length} chunks (BM25, Lesson 1)`);
  print("Tools  : " + [...base.tools].map(([n, t]) => n + (t.sideEffect ? "*" : "")).join(", ") +
    "   (* changes something)");
  print("Replies: recorded from real Ollama runs and replayed. The loop, the schemas,");
  print("         the guards and the tools all run for real, right now.");

  print("\n1. The task set - and the tools a correct run proposes");
  for (const t of tasks) {
    const want = t.expect.map((x) => ABBR.get(x)).join("") || "-";
    print(`   ${ljust(t.id, 4)}${ljust(want, 4)}${t.ask}`);
  }
  print(`   ${LEGEND}`);

  print("\n2. Arm A - a keyword router: code picks the tool");
  let right = 0;
  for (const t of tasks) {
    const picked = router.route(t.ask);
    const ok = setEq(picked, t.expect);
    right += ok ? 1 : 0;
    print(`   ${ljust(t.id, 4)}${ljust(picked.map((x) => ABBR.get(x)).join("") || "-", 4)}${ok ? "ok" : "XX"}`);
  }
  print(`   right tools: ${right}/${tasks.length}  -  0 model calls, 0 seconds, and every rule`);
  print("   was written by someone who had already read these ten questions.");

  const tapes = recordedModels();
  const names = tapes.map((tp) => tp.model);
  const runs = {};
  for (const tp of tapes) runs[tp.model] = await replayAll(tp, tasks, retriever, { maxTurns });

  print("\n3. Arm B - the model picks (recorded replies, guards on)");
  for (const tp of tapes) {
    print(`   ${ljust(str(tp.model), 18)} recorded ${str(tp.recorded)} on Ollama ${str(tp.ollama)}, ` +
      `${str(tp.hardware)}`);
  }
  const width = Math.max(12, ...names.map(len));
  print("\n   " + ljust("", 6) + names.map((n) => rjust(n, width + 2)).join(""));
  for (const t of tasks) {
    print("   " + ljust(t.id, 6) + names.map((n) => rjust(cell(runs[n][t.id]), width + 2)).join(""));
  }
  const loose = {};
  for (const tp of tapes) loose[tp.model] = await replayAll(tp, tasks, retriever, { maxTurns, lenient: true });
  print();
  printScorecard(names, runs, tasks, loose);

  print("\n4. Arm C - what the guards stopped or flagged (without them, all of it runs)");
  let stopped = 0;
  for (const n of names) {
    for (const t of tasks) {
      const s = runs[n][t.id];
      for (const c of s ? s.stops : []) {
        stopped += 1;
        let args = str(c.args);
        args = len(args) <= 44 ? args : slice(args, 0, 41) + "...";
        print(`   ${ljust(n, 18)}${ljust(t.id, 5)}${ljust(c.status, 15)}${str(c.name)}(${args})`);
      }
      for (const c of s ? s.result.calls : []) {
        if (c.flags.length) {
          print(`   ${ljust(n, 18)}${ljust(t.id, 5)}${ljust("flagged", 15)}${str(c.name)} output: ` +
            c.flags.join(", "));
        }
      }
    }
  }
  if (!stopped) print("   (none)");

  const coder = tapes.find((tp) => String(tp.model).startsWith("qwen2.5-coder"));
  if (coder) {
    print(`\n5. A model that writes its call as text (${coder.model}, t2)`);
    const t2 = tasks.find((t) => t.id === "t2");
    for (const lenient of [false, true]) {
      const r = (await replayAll(coder, [t2], retriever, { maxTurns, lenient })).t2;
      const res = r ? r.result : null;
      const label = lenient ? "lenient" : "strict ";
      if (res === null) {
        print(`   ${label} crashed`);
        continue;
      }
      const ran = res.calls.map((c) => str(c.name) + (c.recovered ? " (recovered from text)" : "")).join(", ") ||
        "no tool ran";
      const ans = (res.answer || "").replaceAll("\n", " ");
      print(`   ${label} ${ran}`);
      print(`           answer: ${slice(ans, 0, 78) + (len(ans) > 78 ? "..." : "")}`);
    }
  }

  print("\n6. A model that obeys the document (scripted stand-in, not a recording) - t8");
  const box = await Toolbox.create({ retriever });
  const res = await run(new router.ObedientStandIn(), "Summarize support ticket 9001.", box, {
    maxTurns, confirm: policyConfirm,
  });
  for (const c of res.calls) {
    const flags = c.flags.length ? `  flagged: ${c.flags.join(", ")}` : "";
    print(`   turn ${c.turn}  ${ljust(str(c.name), 14)}${c.status}${flags}`);
  }
  print(`   tickets actually opened: ${box.outbox.length}`);
  print("   The order came from a document. The intent guard reads only the user's message,");
  print("   which asked for a summary, so no confirmation was ever requested.");

  print("\nSummary");
  if (!names.length) {
    print(`   router ${right}/${tasks.length}; no recorded models - run ./run -l 9 record --model <name>.`);
    return 0;
  }
  // max() keeps the first of equal scores, so the reduce keeps it too.
  const rightCount = (n) => count(Object.values(runs[n]), (s) => s && s.right);
  const best = names.reduce((a, b) => (rightCount(b) > rightCount(a) ? b : a));
  const got = rightCount(best);
  print(`   router ${right}/${tasks.length}; best recorded model ${best} ${got}/${tasks.length};` +
    ` guards stopped ${stopped} call${stopped !== 1 ? "s" : ""} across` +
    ` ${names.length} models.`);
  return 0;
}

// --- live -------------------------------------------------------------------------

async function cmdAsk(args) {
  const [url, fallback] = ollamaSettings();
  const model = new OllamaModel(url, args.model || fallback, { think: args.think });
  const box = await Toolbox.create();
  let result;
  try {
    result = await run(model, args.question, box, {
      maxTurns: args.maxTurns, confirm: askHuman, lenient: args.lenient,
    });
  } finally {
    await lines?.return();
  }
  for (const c of result.calls) print(`  [${c.status}] ${str(c.name)}(${str(c.args)})`);
  print();
  print(result.answer || `(no answer: ${result.stopped})`);
  return 0;
}

// --- command line -----------------------------------------------------------------

const ACTIONS = ["demo", "trace", "ask", "bench", "record", "models"];
const USAGE = "usage: function_calling.mjs [demo | ask \"<question>\"] [--model M] [--think | --no-think] " +
  "[--lenient] [--max-turns N]";

function parseArgs(argv) {
  const args = { action: "demo", question: "Why does the status ring stay amber?", model: null, think: false,
    lenient: false, maxTurns: 5 };
  const positional = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-h" || a === "--help") {
      print(USAGE);
      process.exit(0);
    } else if (a === "--model") args.model = argv[++i];
    else if (a === "--think") args.think = true;
    else if (a === "--no-think") args.think = false;
    else if (a === "--lenient") args.lenient = true;
    else if (a === "--max-turns") args.maxTurns = Number.parseInt(argv[++i], 10);
    else if (a.startsWith("--")) throw new UsageError(`unrecognized argument: ${a}`);
    else positional.push(a);
  }
  if (positional.length > 2) throw new UsageError(`unrecognized arguments: ${positional.slice(2).join(" ")}`);
  if (positional[0] !== undefined) {
    if (!ACTIONS.includes(positional[0])) {
      throw new UsageError(`argument action: invalid choice: ${repr(positional[0])} (choose from ${ACTIONS.map(repr).join(", ")})`);
    }
    args.action = positional[0];
  }
  if (positional[1] !== undefined) args.question = positional[1];
  if (!Number.isInteger(args.maxTurns) || args.maxTurns < 1) throw new UsageError("--max-turns needs a whole number >= 1");
  if (args.model === undefined) throw new UsageError("--model needs a value");
  return args;
}

class UsageError extends Error {}

async function main(argv) {
  let args;
  try {
    args = parseArgs(argv);
  } catch (exc) {
    if (!(exc instanceof UsageError)) throw exc;
    process.stderr.write(`${USAGE}\nfunction_calling.mjs: error: ${exc.message}\n`);
    return 2;
  }
  if (args.action !== "demo" && args.action !== "ask") {
    process.stderr.write(`'${args.action}' is in the Python reference only: ./run -l 9 ${args.action}\n`);
    return 2;
  }
  try {
    return args.action === "demo" ? await cmdDemo() : await cmdAsk(args);
  } catch (exc) {
    if (exc instanceof cassette.CassetteDrift) {
      process.stderr.write(`cassette out of date: ${exc.message}\n`);
      return 2;
    }
    if (exc instanceof cassette.RuntimeError) {
      process.stderr.write(`error: ${exc.message}\n`);
      return 1;
    }
    throw exc;
  }
}

process.exitCode = await main(process.argv.slice(2));
