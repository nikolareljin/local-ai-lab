// Lesson 10 - Jev and System One models vs a local LLM, on fake support tickets.
// Node.js port of `python python/jev.py demo`, byte for byte. Standard library only.
//
//     node node/jev.mjs [demo] [--dataset tickets|reviews|incidents]
//
// It replays the recorded replies in data/cassettes (no model, no network), runs
// the keyword rules live, and prints the same scorecard, traps and threshold table.
// Recording and live runs stay in Python; the SDK example is sdk_example.mjs.

import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  canonical, formatFixed, isDict, ljust, loads, num, PyFloat, pySum, pySumFloats, repr, rjust, strip,
} from "./pycompat.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
// LESSON10_DATA_DIR is a port-only test hook (Python has none): point it at an edited copy of data/.
const DATA = process.env.LESSON10_DATA_DIR ? resolve(process.env.LESSON10_DATA_DIR) : join(HERE, "..", "data");
const CASSETTES = join(DATA, "cassettes");

// What the demo replays, in the order the scorecard prints them.
const RECORDED_MODELS = [
  ["llm-json", "qwen3:1.7b"],
  ["local", "qwen3:1.7b"],
  ["local", "qwen3.5:4b"],
  ["typesafe", "jev-latest"],
];

// "jev-like 4b": the engine and the model's size tag, for narrow columns.
function shortName(backend, tape) {
  if (!tape) return backend;
  const prefix = { "llm-json": "llm-json", local: "jev-like", typesafe: "typesafe" }[backend];
  return `${prefix} ${tape.model.split(":").at(-1)}`;
}

function cassetteName(backend, model) {
  if (backend === "typesafe") return "typesafe-jev.json";
  const prefix = { "llm-json": "llm-json", local: "jev-like" }[backend];
  return `${prefix}-${model.replaceAll(":", "-").replaceAll("/", "-")}.json`;
}

const PAGE = 0.7, REFUND = 0.8, CONFIDENT = 0.6; // policy.py

const read = (path) => readFileSync(path, "utf8");

function loadDataset(name) {
  const questions = JSON.parse(read(join(DATA, "questions.json")))[name];
  const records = read(join(DATA, `${name}.jsonl`)).split(/\r\n|\r|\n/)
    .filter((line) => strip(line)).map((line) => JSON.parse(line));
  return [questions, records];
}

// --------------------------------------------------------------------------- systemone.py
function options(q) {
  if (q.type === "noul") return ["yes", "no"];
  if (q.type === "choice") return Object.keys(q.criteria);
  if (q.type === "score") return [...q.criteria];
  throw new Error(`unknown question type ${repr(q.type)}`);
}

function requestProblems(body) {
  const found = [];
  if (typeof body.model !== "string" || !body.model) found.push("model: required");
  if (!("state" in body)) found.push("state: required");
  const questions = body.questions;
  if (!isDict(questions) || !Object.keys(questions).length) return [...found, "questions: at least one question"];
  const n = Object.keys(questions).length;
  if (n > 64) found.push(`questions: at most 64, got ${n}`);
  for (const [name, q] of Object.entries(questions)) {
    if (!["noul", "choice", "score"].includes(q.type)) {
      found.push(`questions.${name}.type: noul, choice or score`);
      continue;
    }
    if (!q.instructions) found.push(`questions.${name}.instructions: required`);
    const c = q.criteria;
    if (q.type === "choice" && !(isDict(c) && Object.keys(c).length >= 2 && Object.keys(c).length <= 255)) {
      found.push(`questions.${name}.criteria: 2-255 options`);
    }
    if (q.type === "score" && !(Array.isArray(c) && c.length >= 2 && c.length <= 10)) {
      found.push(`questions.${name}.criteria: 2-10 levels`);
    }
  }
  return found;
}

function buildRequest(state, questions, model = "jev-latest") {
  const body = { model, state, questions };
  const problems = requestProblems(body);
  if (problems.length) throw new Error(problems.join("; "));
  return body;
}

const digest = (body) =>
  createHash("sha256").update(canonical({ state: body.state, questions: body.questions }), "utf8")
    .digest("hex").slice(0, 16);

// bool is an int in Python
const isNumber = (v) => typeof v === "number" || typeof v === "boolean" || typeof v === "bigint" || v instanceof PyFloat;

function readAnswers(questions, response) {
  const answers = {}, problems = [];
  const got = isDict(response.answers) && Object.keys(response.answers).length ? response.answers : {};
  for (const [name, q] of Object.entries(questions)) {
    const a = Object.hasOwn(got, name) ? got[name] : undefined;
    const labels = options(q);
    if (!isDict(a) || a.type !== q.type) {
      problems.push(`${name}: no ${q.type} answer`);
      continue;
    }
    let pick, probs, confidence;
    if (q.type === "noul") {
      const p = isNumber(a.noul) ? Number(num(a.noul)) : NaN;
      if (!isNumber(a.noul) || !(p >= 0 && p <= 1)) {
        problems.push(`${name}: noul must be a number in [0, 1]`);
        continue;
      }
      probs = { yes: p, no: 1.0 - p };
      pick = p >= 0.5 ? "yes" : "no";
      confidence = Math.max(p, 1 - p);
    } else {
      let raw = isDict(a.probabilities) ? a.probabilities : {};
      if (q.type === "score") {
        const mapped = {};
        for (const [k, v] of Object.entries(raw)) {
          if (/^[0-9]+$/.test(k) && Number(k) < labels.length) mapped[labels[Number(k)]] = v;
        }
        raw = mapped;
      }
      const keys = Object.keys(raw);
      const sameSet = keys.length === new Set(labels).size && keys.every((k) => labels.includes(k));
      const numeric = Object.values(raw).every((v) => isNumber(v) && typeof v !== "boolean");
      if (!sameSet || !numeric || Math.abs(pySum(Object.values(raw)) - 1.0) > 0.01) {
        problems.push(`${name}: probabilities must cover ${repr(labels)} and sum to 1`);
        continue;
      }
      probs = {};
      for (const label of labels) probs[label] = Number(num(raw[label]));
      if (q.type === "choice") {
        pick = Object.hasOwn(a, "choice") ? a.choice : null;
      } else {
        pick = labels[0];
        for (const label of labels) if (probs[label] > probs[pick]) pick = label;
      }
      if (!labels.includes(pick)) {
        problems.push(`${name}: ${repr(pick)} is not an option`);
        continue;
      }
      const c = Object.hasOwn(a, "confidence") ? a.confidence : null;
      confidence = isNumber(c) && typeof c !== "boolean" ? Number(num(c)) : Math.max(...Object.values(probs));
    }
    answers[name] = { pick, probs, confidence };
  }
  return [answers, problems];
}

// --------------------------------------------------------------------------- engines.py
// First matching rule wins, per question. Lower-case substring match.
const RULES = {
  queue: [
    ["trust_safety", ["security", "hacked", "phishing", "breach", "leak", "abuse", "fraud"]],
    ["billing", ["charge", "invoice", "refund", "payment", "billing", "card"]],
    ["account", ["log in", "login", "2fa", "password", "account", "admin", "permission"]],
    ["sales", ["price", "pricing", "discount", "quote", "licence", "license", "upgrade"]],
    ["technical", [""]],
  ],
  urgency: [
    ["critical", ["emergency", "outage", "all customers", "data loss"]],
    ["high", ["urgent", "asap", "down", "immediately", "now!"]],
    ["low", ["question", "how do i", "not urgent", "when you can"]],
    ["medium", [""]],
  ],
  refund_request: [["yes", ["refund", "money back", "chargeback"]], ["no", [""]]],
  needs_human: [["yes", ["lawyer", "legal", "gdpr", "security", "emergency", "outage"]], ["no", [""]]],
};

function rulePick(text, rules) {
  const low = text.toLowerCase();
  for (const [label, words] of rules) if (words.some((w) => low.includes(w))) return label;
  return rules[rules.length - 1][0];
}

function certain(q, pick) {
  const labels = options(q);
  if (q.type === "noul") return { type: "noul", noul: pick === "yes" ? 1.0 : 0.0 };
  const probs = labels.map((label) => (label === pick ? 1.0 : 0.0));
  if (q.type === "choice") {
    return { type: "choice", choice: pick, confidence: 1.0,
      probabilities: Object.fromEntries(labels.map((l, i) => [l, probs[i]])) };
  }
  return { type: "score", score: labels.indexOf(pick), confidence: 1.0,
    legend: Object.fromEntries(labels.map((l, i) => [String(i), l])),
    probabilities: Object.fromEntries(probs.map((p, i) => [String(i), p])) };
}

function keywordsResponse(body) {
  const answers = {};
  for (const [name, q] of Object.entries(body.questions)) {
    const pick = Object.hasOwn(RULES, name) ? rulePick(body.state, RULES[name]) : options(q)[0];
    answers[name] = certain(q, pick);
  }
  return { model: "keywords", answers, usage: {} };
}

function parseLlmJson(body, text) {
  const errors = [];
  const match = /\{.*\}/s.exec(text);
  let written = null;
  try {
    written = match ? loads(match[0], { floats: true }) : null;
  } catch {
    written = null;
  }
  if (!isDict(written)) return [{ model: "llm-json", answers: {}, usage: {} }, ["not a JSON object"]];
  const answers = {};
  for (const [name, q] of Object.entries(body.questions)) {
    let value = Object.hasOwn(written, name) ? written[name] : null;
    if (typeof value === "boolean") value = value ? "yes" : "no"; // {"refund_request": true} is a fair reading
    if (typeof value !== "string" || !options(q).includes(strip(value).toLowerCase())) {
      errors.push(`${name}=${repr(value)}`);
      continue;
    }
    answers[name] = certain(q, strip(value).toLowerCase());
  }
  return [{ model: "llm-json", answers, usage: {} }, errors];
}

// --------------------------------------------------------------------------- policy.py
function decide(answers, page = PAGE, refund = REFUND, confident = CONFIDENT) {
  const queue = answers.queue;
  if (queue === undefined) return "human triage";
  const get = (name, label, dflt) => answers[name]?.probs?.[label] ?? dflt;
  const pUrgent = get("urgency", "high", 0.0) + get("urgency", "critical", 0.0);
  const pRefund = get("refund_request", "yes", 0.0);
  const pHuman = get("needs_human", "yes", 1.0);
  if ((queue.probs.trust_safety ?? 0.0) >= 0.5) return "escalate: trust & safety";
  if (pUrgent >= page && queue.pick === "technical") return "page on-call";
  if (pRefund >= refund && queue.pick === "billing") return "draft refund for approval";
  if (pHuman >= 0.5 || queue.confidence < confident) return "human triage";
  return "auto-route";
}

// --------------------------------------------------------------------------- scorecard.py
function goldAnswers(questions, labels) {
  const out = {};
  for (const [name, q] of Object.entries(questions)) {
    const probs = {};
    for (const label of options(q)) probs[label] = label === labels[name] ? 1.0 : 0.0;
    out[name] = { pick: labels[name], probs, confidence: 1.0 };
  }
  return out;
}

function brier(q, answer, truth) {
  const labels = options(q);
  return pySumFloats(labels.map((label) => {
    const p = answer === undefined ? 1.0 / labels.length : answer.probs[label];
    const d = p - (label === truth ? 1.0 : 0.0);
    return d * d;
  }));
}

function median(xs) {
  const s = [...xs].sort((a, b) => a - b);
  const n = s.length, i = Math.floor(n / 2);
  return n % 2 ? s[i] : (s[i - 1] + s[i]) / 2;
}

function score(questions, records, runs, page = PAGE) {
  const names = Object.keys(questions);
  const n = records.length;
  const correct = Object.fromEntries(names.map((name) => [name, 0]));
  let typed = 0, brierSum = 0.0, actions = 0, wrongPages = 0, missedPages = 0;
  const seconds = [];
  for (const rec of records) {
    const run = runs[rec.id];
    for (const name of names) {
      const a = run.answers[name];
      typed += a !== undefined;
      correct[name] += a !== undefined && a.pick === rec.labels[name];
      brierSum += brier(questions[name], a, rec.labels[name]);
    }
    if ("queue" in questions) {
      const got = decide(run.answers, page);
      const want = decide(goldAnswers(questions, rec.labels), page);
      actions += got === want;
      wrongPages += got === "page on-call" && want !== "page on-call";
      missedPages += want === "page on-call" && got !== "page on-call";
    }
    seconds.push(run.seconds);
  }
  return {
    n, correct, typed, asked: n * names.length, brier: brierSum / (n * names.length),
    actions, wrong_pages: wrongPages, missed_pages: missedPages,
    seconds: seconds.length ? median(seconds) : 0.0, calls: n ? runs[records[0].id].calls : 0,
  };
}

// --------------------------------------------------------------------------- jev.py
function toRun(questions, stored) {
  let response, problems;
  if (Object.hasOwn(stored, "text")) {
    [response, problems] = parseLlmJson({ questions }, stored.text);
  } else {
    [response, problems] = [stored.response, []];
  }
  const [answers, more] = readAnswers(questions, response);
  return { answers, seconds: num(stored.seconds), calls: num(stored.calls), problems: [...problems, ...more] };
}

class StaleCassette extends Error {}

function loadCassette(file, questions, records, dataset) {
  const path = join(CASSETTES, file);
  if (!existsSync(path) || !statSync(path).isFile()) return null;
  const tape = loads(read(path), { floats: true });
  if (tape.dataset !== dataset) return null;
  // prompt_version is not checked here; Python's test suite enforces it.
  for (const rec of records) {
    const stored = Object.hasOwn(tape.calls, rec.id) ? tape.calls[rec.id] : undefined;
    const want = digest(buildRequest(rec.text, questions, tape.model));
    if (stored === undefined || stored === null || stored.digest !== want) {
      throw new StaleCassette(`${file}: ${rec.id} was recorded for a different question `
        + "or text - re-record it");
    }
  }
  return tape;
}

function labelFor(backend, tape, model = "") {
  if (backend === "keywords") return "keywords (rules)";
  const name = tape ? tape.model : model;
  return {
    "llm-json": `LLM writes JSON (${name})`,
    local: `Jev-like adapter (${name.startsWith("local-") ? name.slice(6) : name})`,
    typesafe: `TypeSafe Jev (${name})`,
  }[backend];
}

function fmtRow(label, s, questions) {
  const cells = Object.keys(questions).map((q) => `${rjust(String(s.correct[q]), 2)}/${s.n}`);
  return ljust(label, 34) + cells.map((c) => rjust(c, 8)).join("")
    + rjust(String(Math.floor((s.typed * 100) / s.asked)), 6) + "%" + rjust(formatFixed(s.brier, 3), 7)
    + rjust(String(s.actions), 5) + `/${s.n}` + rjust(String(s.wrong_pages), 6) + rjust(String(s.missed_pages), 7)
    + rjust(formatFixed(s.seconds, 1), 8) + rjust(String(s.calls), 6);
}

function header(questions) {
  const short = { queue: "queue", urgency: "urgency", refund_request: "refund", needs_human: "human" };
  const cols = Object.keys(questions).map((q) => rjust(short[q] ?? [...q].slice(0, 7).join(""), 8)).join("");
  return ljust("engine", 34) + cols + rjust("typed", 7) + rjust("brier", 7) + rjust("action", 8)
    + rjust("wrong", 6) + rjust("missed", 7) + rjust("s/item", 8) + rjust("calls", 6);
}

function demo(dataset) {
  const [questions, records] = loadDataset(dataset);
  const p = (line = "") => process.stdout.write(line + "\n");
  const nq = Object.keys(questions).length;
  p(`Lesson 10 · Jev and System One models - ${records.length} labelled fake ${dataset}, `
    + `${nq} typed questions`);
  p("Replayed from recorded replies: no model, no network. Live: ./run -l 10 live --backend local");
  p();
  p(header(questions));
  const keywordRuns = {};
  for (const r of records) {
    const response = keywordsResponse(buildRequest(r.text, questions));
    keywordRuns[r.id] = toRun(questions, { response, seconds: 0.0, calls: 0 });
  }
  const rows = [["keywords", null, keywordRuns]];
  const missing = [];
  for (const [backend, model] of RECORDED_MODELS) {
    const tape = loadCassette(cassetteName(backend, model), questions, records, dataset);
    if (tape === null) {
      missing.push([backend, model]);
      continue;
    }
    rows.push([backend, tape, Object.fromEntries(records.map((r) => [r.id, toRun(questions, tape.calls[r.id])]))]);
  }
  for (const [backend, tape, runs] of rows) p(fmtRow(labelFor(backend, tape), score(questions, records, runs), questions));
  for (const [backend, model] of missing) {
    const hint = backend === "typesafe" ? "needs TYPESAFE_API_KEY: ./run -l 10 record --backend typesafe"
      : `./run -l 10 record --backend ${backend} --model ${model}`;
    p(`${ljust(labelFor(backend, null, model), 34)}not recorded - ${hint}`);
  }
  p();
  p("accuracy = right/total per question; typed = answers that were a valid option;");
  p("brier = probability error, 0 best, 2 = certain and wrong; action = policy matches the");
  p("labels' action; wrong/missed = pages to on-call; s/item = median seconds; calls = model calls.");

  if ("queue" in questions) {
    p();
    p("Where they disagree - the traps (label -> each engine's queue / urgency):");
    for (const r of records.filter((rec) => rec.trap).slice(0, 8)) {
      p(`  ${r.id}  ${r.trap}`);
      p(`    ${ljust("labels", 14)} ${ljust(r.labels.queue, 13)} ${r.labels.urgency}`);
      for (const [backend, tape, runs] of rows) {
        const a = runs[r.id].answers;
        const q = a.queue?.pick ?? "-";
        const u = a.urgency?.pick ?? "-";
        const conf = a.queue?.confidence;
        const note = conf !== undefined && conf !== null && backend !== "keywords" ? `  (${formatFixed(conf, 2)})` : "";
        p(`    ${ljust(shortName(backend, tape), 14)} ${ljust(q, 13)} ${u}${note}`);
      }
    }
    p();
    p("The threshold is a business decision. Pages to on-call as PAGE moves:");
    const ts = [0.5, 0.7, 0.9];
    p(`  ${ljust("engine", 34)}` + ts.map((t) => rjust("PAGE " + formatFixed(t, 1), 20)).join(""));
    for (const [backend, tape, runs] of rows) {
      const cells = ts.map((t) => {
        const s = score(questions, records, runs, t);
        return `${s.wrong_pages} wrong ${s.missed_pages} missed`;
      });
      p(`  ${ljust(labelFor(backend, tape), 34)}` + cells.map((c) => rjust(c, 20)).join(""));
    }
    p("  Rules and JSON answers are always 0 or 1, so the knob does nothing for them.");
  }
  return 0;
}

function main(argv) {
  const usage = "usage: jev.mjs [demo] [--dataset {tickets,reviews,incidents}]";
  const args = [...argv];
  if (args[0] === "demo") args.shift();
  let dataset = "tickets";
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    let v;
    if (a === "--dataset") v = args[++i];
    else if (a.startsWith("--dataset=")) v = a.slice(10);
    else {
      process.stderr.write(`${usage}\njev.mjs: error: unrecognized arguments: ${a}\n`);
      return 2;
    }
    if (!["tickets", "reviews", "incidents"].includes(v)) {
      process.stderr.write(`${usage}\njev.mjs: error: argument --dataset: invalid choice: ${repr(v ?? "")}\n`);
      return 2;
    }
    dataset = v;
  }
  try {
    return demo(dataset);
  } catch (err) {
    if (err instanceof StaleCassette) {
      process.stderr.write(`StaleCassette: ${err.message}\n`);
      return 1;
    }
    throw err;
  }
}

process.exitCode = main(process.argv.slice(2));
