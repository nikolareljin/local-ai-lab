// Lesson 10 - Jev and System One models vs a local LLM, on two fake call centers.
// Node.js port of `python python/jev.py demo`, byte for byte. Standard library only.
//
//     node node/jev.mjs [demo] [--dataset insurance|media]
//
// It replays the recorded replies in data/cassettes (no model, no network), runs
// the keyword rules live, and prints the same scorecard, traps and threshold table.
// Recording and live runs stay in Python; the SDK example is sdk_example.mjs.

import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  canonical, formatFixed, isDict, ljust, loads, num, PyFloat, fsum, repr, rjust, strip,
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

const DEFAULT_DATASET = "insurance";

// jev-like-qwen3-1.7b-insurance.json: engine, model and dataset.
function cassetteName(backend, model, dataset = DEFAULT_DATASET) {
  const suffix = `-${dataset}`;
  if (backend === "typesafe") return `typesafe-jev${suffix}.json`;
  const prefix = { "llm-json": "llm-json", local: "jev-like" }[backend];
  return `${prefix}-${model.replaceAll(":", "-").replaceAll("/", "-")}${suffix}.json`;
}

const read = (path) => readFileSync(path, "utf8");

// Per dataset: title and the short column name of each question.
const DATASETS = JSON.parse(read(join(DATA, "datasets.json")));

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
  if (!isDict(body)) return ["body: a JSON object"];
  const found = [];
  if (typeof body.model !== "string" || !body.model) found.push("model: required");
  if (!("state" in body)) found.push("state: required");
  const questions = body.questions;
  if (!isDict(questions) || !Object.keys(questions).length) return [...found, "questions: at least one question"];
  const n = Object.keys(questions).length;
  if (n > 64) found.push(`questions: at most 64, got ${n}`);
  for (const [name, q] of Object.entries(questions)) {
    if (!isDict(q)) {
      found.push(`questions.${name}: an object`);
      continue;
    }
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

/** A real number in [0, 1]. Not a bool, not NaN, not 1.5. */
function isProbability(v) {
  if (!(typeof v === "number" || typeof v === "bigint" || v instanceof PyFloat)) return false;
  const x = Number(num(v));
  return Number.isFinite(x) && x >= 0 && x <= 1;
}

/**
 * Turn a System One response into { question: { pick, probs, confidence } }.
 *
 * The three answer types arrive in three shapes. This gives them one: `pick` is always a
 * label from options() ("yes"/"no" for a noul, the level name for a score) and `probs` maps
 * every label to its probability. The policy and the scorecard only ever see this shape, so
 * they cannot tell TypeSafe's Jev from the local adapter or the keyword rules.
 *
 * An answer that is missing or does not match its question is left out and reported in
 * `problems`. With a real System One model that list stays empty.
 */
function readAnswers(questions, response) {
  const answers = {}, problems = [];
  // A reply that is not an object (or has no "answers" object) answers nothing.
  const got = isDict(response) && isDict(response.answers) ? response.answers : {};
  for (const [name, q] of Object.entries(questions)) {
    const a = Object.hasOwn(got, name) ? got[name] : undefined;
    const labels = options(q);
    // The answer must be of the type that was asked: a noul for a noul, and so on.
    if (!isDict(a) || a.type !== q.type) {
      problems.push(`${name}: no ${q.type} answer`);
      continue;
    }
    let pick, probs, confidence;
    if (q.type === "noul") {
      // noul: one number, P(yes). Split it into yes/no so it looks like the other types.
      if (!isProbability(a.noul)) {
        problems.push(`${name}: noul must be a number in [0, 1]`);
        continue;
      }
      const p = Number(num(a.noul));
      probs = { yes: p, no: 1.0 - p };
      pick = p >= 0.5 ? "yes" : "no";
      confidence = Math.max(p, 1 - p);
    } else {
      // choice and score: a probability per option.
      let raw = isDict(a.probabilities) ? a.probabilities : {};
      if (q.type === "score") {
        // A score's keys are level numbers ("0", "1", ...): translate them to level names.
        const mapped = {};
        for (const [k, v] of Object.entries(raw)) {
          if (/^[0-9]+$/.test(k) && Number(k) < labels.length) mapped[labels[Number(k)]] = v;
        }
        raw = mapped;
      }
      // Valid means: exactly the question's options, each a real probability, summing to 1.
      const keys = Object.keys(raw);
      const sameSet = keys.length === new Set(labels).size && keys.every((k) => labels.includes(k));
      const numeric = Object.values(raw).every(isProbability);
      if (!sameSet || !numeric || Math.abs(fsum(Object.values(raw)) - 1.0) > 0.01) {
        problems.push(`${name}: probabilities must cover ${repr(labels)} and sum to 1`);
        continue;
      }
      probs = {};
      for (const label of labels) probs[label] = Number(num(raw[label]));
      if (q.type === "choice") {
        pick = Object.hasOwn(a, "choice") ? a.choice : null; // the server names its pick
      } else {
        pick = labels[0]; // a score has no "choice": take the most likely level
        for (const label of labels) if (probs[label] > probs[pick]) pick = label;
      }
      if (!labels.includes(pick)) {
        problems.push(`${name}: ${repr(pick)} is not an option`);
        continue;
      }
      // No usable confidence in the reply: fall back to the top probability.
      const c = Object.hasOwn(a, "confidence") ? a.confidence : null;
      confidence = isProbability(c) ? Number(num(c)) : Math.max(...Object.values(probs));
    }
    answers[name] = { pick, probs, confidence };
  }
  return [answers, problems];
}

// --------------------------------------------------------------------------- engines.py
// data/rules.json: per dataset and question, an ordered list of [label, [words]].
// The first rule with a word in the transcript wins; the last rule is the default.
const RULES = JSON.parse(read(join(DATA, "rules.json")));

/** A word matches at the start of a word ("app" in "the app", not in "happened"). */
function rulePick(text, rules) {
  const low = text.toLowerCase();
  const starts = (w) => w === "" || new RegExp("(?<![a-z0-9])" + w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).test(low);
  for (const [label, words] of rules) if (words.some(starts)) return label;
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

/** Answer by keyword. A question with no rules gets its first option. */
function keywordsResponse(body, dataset = DEFAULT_DATASET) {
  const rules = RULES[dataset];
  const answers = {};
  for (const [name, q] of Object.entries(body.questions)) {
    const pick = Object.hasOwn(rules, name) ? rulePick(String(body.state), rules[name]) : options(q)[0];
    answers[name] = certain(q, pick);
  }
  return { model: "keywords", answers, usage: {} };
}

/**
 * Read what a chat model wrote when asked for JSON, the way most code does it today.
 *
 * Nothing guarantees the text is JSON, or that a value is one of the options. A field
 * the model got wrong, or left out, is a type error: it is reported and that question
 * stays unanswered. Every valid answer gets probability 1.0 - a written answer carries
 * no probability to put a threshold on.
 */
function parseLlmJson(body, text) {
  const errors = [];
  // Models wrap JSON in prose or code fences: take the outermost {...} and try to parse it.
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
    if (typeof value === "boolean") value = value ? "yes" : "no"; // {"emergency": true} is a fair reading
    // "very bad" for a question whose levels are none..catastrophic is not an answer.
    if (typeof value !== "string" || !options(q).includes(strip(value).toLowerCase())) {
      errors.push(`${name}=${repr(value)}`);
      continue;
    }
    answers[name] = certain(q, strip(value).toLowerCase()); // all the weight on its pick
  }
  return [{ model: "llm-json", answers, usage: {} }, errors];
}

// --------------------------------------------------------------------------- policy.py
// The model answers questions; this code decides. The thresholds are the knobs.
const EMERGENCY = 0.5;  // P(someone needs help right now) to dispatch assistance
const SIU = 0.6;        // P(fraud signals) to send a claim to the Special Investigations Unit
const FAST_TRACK = 0.8; // P(no fraud signals) needed to pay a small claim without a human
const CONFIDENT = 0.6;  // below this confidence in the caller's intent, a person takes the call
const RETAIN = 0.5;     // P(high churn risk) to hand the call to the retention desk
const REFUND = 0.8;     // P(wants money back) to draft a refund for approval

const prob = (answers, name, label, dflt = 0.0) => answers[name]?.probs?.[label] ?? dflt;

/**
 * One action per insurance call, from the answers to the six questions.
 *
 * The model never chooses the action. It says P(fraud signals) = 0.83; this function
 * decides that 0.83 is enough. Moving a threshold changes what the business does without
 * retraining or re-prompting anything. The order of the rules is the priority.
 */
function decide(answers, { siu = SIU, emergency = EMERGENCY, fast_track: fastTrack = FAST_TRACK, confident = CONFIDENT } = {}) {
  const intent = answers.intent;
  // 1. Someone needs help now: that comes first, whatever else the call is about.
  if (prob(answers, "emergency", "yes") >= emergency) return "dispatch emergency help";
  // 2. No usable answer, or the model is unsure what the caller wants: a person, never a guess.
  if (answers.emergency === undefined || intent === undefined || intent.confidence < confident) return "human agent";
  // 3. Complaints and cancellations are conversations, not forms.
  if (["complaint", "cancel_policy"].includes(intent.pick)) return "human agent";
  // 4. Questions about a claim or about cover can be answered without a claim handler.
  if (["claim_status", "coverage_question"].includes(intent.pick)) return "self-service answer";
  // 5. What is left is a new claim. A missing fraud answer counts as suspicious (default 1.0).
  const pFraud = prob(answers, "fraud_signals", "yes", 1.0);
  if (pFraud >= siu) return "special investigations";
  // 6. Pay without a human only when the loss is small, nobody needs to inspect it,
  //    and the claim is clean enough: P(no fraud) >= FAST_TRACK.
  const small = prob(answers, "severity", "none") + prob(answers, "severity", "minor") > 0.5;
  if (small && prob(answers, "needs_adjuster", "yes", 1.0) < 0.5 && 1 - pFraud >= fastTrack) return "fast-track payout";
  // 7. Everything else is looked at by an adjuster.
  return "assign adjuster";
}

/** One action per newspaper call. */
function decideMedia(answers, { retain = RETAIN, refund = REFUND, confident = CONFIDENT } = {}) {
  const topic = answers.topic;
  if (topic === undefined || topic.confidence < confident) return "human agent";
  if (topic.pick === "editorial") return "pass to newsroom";
  if (topic.pick === "advertising") return "pass to ad sales";
  if (topic.pick === "cancel" || prob(answers, "churn_risk", "high", 1.0) >= retain) return "retention desk";
  if (prob(answers, "wants_refund", "yes", 1.0) >= refund) return "refund for approval";
  return "self-service answer";
}

// What the scorecard needs to know about each policy: the threshold the demo sweeps
// (knob, values), the action it controls (watch), and what a wrong or missed one costs.
const POLICIES = {
  insurance: { decide, knob: "siu", values: [0.3, 0.6, 0.9], watch: "special investigations",
    wrong: "honest callers investigated", missed: "suspicious claims not investigated" },
  media: { decide: decideMedia, knob: "retain", values: [0.3, 0.5, 0.9], watch: "retention desk",
    wrong: "happy readers sent to retention", missed: "leaving readers not sent to retention" },
};

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

/**
 * The Brier score of one answer: the squared distance between the probabilities and the truth.
 *
 * 0 is perfect. Certain and wrong costs 2 (1 on the wrong option, 1 on the right one).
 * An unanswered question is scored as "every option equally likely". Accuracy only asks
 * whether the top answer was right; this also asks whether the engine knew how sure to be,
 * which is what a threshold in the policy relies on.
 */
function brier(q, answer, truth) {
  const labels = options(q);
  return fsum(labels.map((label) => {
    const p = answer === undefined ? 1.0 / labels.length : answer.probs[label];
    const d = p - (label === truth ? 1.0 : 0.0); // the truth is 1 on the right label, 0 elsewhere
    return d * d;
  }));
}

function median(xs) {
  const s = [...xs].sort((a, b) => a - b);
  const n = s.length, i = Math.floor(n / 2);
  return n % 2 ? s[i] : (s[i - 1] + s[i]) / 2;
}

/** `knob` overrides the policy's main threshold, for the engine and the labels alike. */
function score(questions, records, runs, pol, knob = null) {
  const kwargs = knob === null ? {} : { [pol.knob]: knob };
  const names = Object.keys(questions);
  const n = records.length;
  const correct = Object.fromEntries(names.map((name) => [name, 0]));
  let typed = 0, brierSum = 0.0, actions = 0, wrong = 0, missed = 0;
  const seconds = [];
  for (const rec of records) {
    const run = runs[rec.id];
    for (const name of names) {
      const a = run.answers[name];
      typed += a !== undefined;
      correct[name] += a !== undefined && a.pick === rec.labels[name];
      brierSum += brier(questions[name], a, rec.labels[name]);
    }
    const got = pol.decide(run.answers, kwargs);
    const want = pol.decide(goldAnswers(questions, rec.labels), kwargs);
    actions += got === want;
    wrong += got === pol.watch && want !== pol.watch;
    missed += want === pol.watch && got !== pol.watch;
    seconds.push(run.seconds);
  }
  return {
    n, correct, typed, asked: n * names.length, brier: brierSum / (n * names.length),
    actions, wrong, missed,
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
    const stored = Object.hasOwn(tape.calls, rec.id) ? tape.calls[rec.id] : null;
    if (stored === null) {
      throw new StaleCassette(`${file}: has no recording of ${rec.id} - re-record it without --limit`);
    }
    const want = digest(buildRequest(rec.text, questions, tape.model));
    if (stored.digest !== want) {
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
  return ljust(label, 32) + cells.map((c) => rjust(c, 7)).join("")
    + rjust(String(Math.floor((s.typed * 100) / s.asked)), 6) + "%" + rjust(formatFixed(s.brier, 3), 7)
    + rjust(String(s.actions), 5) + `/${s.n}` + rjust(String(s.wrong), 6) + rjust(String(s.missed), 7)
    + rjust(formatFixed(s.seconds, 1), 8) + rjust(String(s.calls), 6);
}

function header(questions, dataset) {
  const short = DATASETS[dataset].short;
  const cols = Object.keys(questions).map((q) => rjust(short[q], 7)).join("");
  return ljust("engine", 32) + cols + rjust("typed", 7) + rjust("brier", 7) + rjust("action", 8)
    + rjust("wrong", 6) + rjust("missed", 7) + rjust("s/call", 8) + rjust("calls", 6);
}

function demo(dataset) {
  const [questions, records] = loadDataset(dataset);
  const pol = POLICIES[dataset];
  const meta = DATASETS[dataset];
  const p = (line = "") => process.stdout.write(line + "\n");
  const nq = Object.keys(questions).length;
  p(`Lesson 10 \u00b7 Jev and System One models - ${meta.title}: ${records.length} labelled fake `
    + `calls, ${nq} typed questions`);
  p("Replayed from recorded replies: no model, no network. "
    + "Live: ./run -l 10 live --backend keywords,llm-json,local");
  p();
  p(header(questions, dataset));
  const keywordRuns = {};
  for (const r of records) {
    const response = keywordsResponse(buildRequest(r.text, questions), dataset);
    keywordRuns[r.id] = toRun(questions, { response, seconds: 0.0, calls: 0 });
  }
  const rows = [["keywords", null, keywordRuns]];
  const missing = [];
  for (const [backend, model] of RECORDED_MODELS) {
    const tape = loadCassette(cassetteName(backend, model, dataset), questions, records, dataset);
    if (tape === null) {
      missing.push([backend, model]);
      continue;
    }
    rows.push([backend, tape, Object.fromEntries(records.map((r) => [r.id, toRun(questions, tape.calls[r.id])]))]);
  }
  for (const [backend, tape, runs] of rows) {
    p(fmtRow(labelFor(backend, tape), score(questions, records, runs, pol), questions));
  }
  for (const [backend, model] of missing) {
    let hint = backend === "typesafe" ? "needs TYPESAFE_API_KEY: ./run -l 10 record --backend typesafe"
      : `./run -l 10 record --backend ${backend} --model ${model}`;
    hint += dataset === DEFAULT_DATASET ? "" : ` --dataset ${dataset}`;
    p(`${ljust(labelFor(backend, null, model), 32)}not recorded - ${hint}`);
  }
  p();
  p("Columns: right/total per question; typed = answers that were a valid option;");
  p("brier = probability error, 0 best, 2 = certain and wrong; action = same action as the");
  p(`human labels lead to; wrong = ${pol.wrong}; missed = ${pol.missed};`);
  p("s/call = median seconds; calls = model calls per record.");

  p();
  p("The traps - the action each engine's answers lead to:");
  for (const r of records.filter((rec) => rec.trap)) {
    const want = pol.decide(goldAnswers(questions, r.labels));
    p(`  ${r.id}  ${r.trap}`);
    p(`    ${ljust("labels", 14)} ${want}`);
    for (const [backend, tape, runs] of rows) {
      const got = pol.decide(runs[r.id].answers);
      p(`    ${ljust(shortName(backend, tape), 14)} ${got}${got === want ? "" : "   <- wrong"}`);
    }
  }

  const name = pol.knob.toUpperCase();
  p();
  p(`The threshold is a business decision. '${pol.watch}' as ${name} moves:`);
  p(`  ${ljust("engine", 32)}` + pol.values.map((t) => rjust(`${name} ${formatFixed(t, 1)}`, 20)).join(""));
  for (const [backend, tape, runs] of rows) {
    const cells = pol.values.map((t) => {
      const s = score(questions, records, runs, pol, t);
      return `${s.wrong} wrong ${s.missed} missed`;
    });
    p(`  ${ljust(labelFor(backend, tape), 32)}` + cells.map((c) => rjust(c, 20)).join(""));
  }
  p("  Rules and JSON answers are always 0 or 1, so the knob does nothing for them.");
  return 0;
}

function main(argv) {
  const names = Object.keys(DATASETS);
  const usage = `usage: jev.mjs [demo] [--dataset {${names.join(",")}}]`;
  const args = [...argv];
  if (args[0] === "demo") args.shift();
  let dataset = DEFAULT_DATASET;
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    let v;
    if (a === "--dataset") v = args[++i];
    else if (a.startsWith("--dataset=")) v = a.slice(10);
    else {
      process.stderr.write(`${usage}\njev.mjs: error: unrecognized arguments: ${a}\n`);
      return 2;
    }
    if (!names.includes(v)) {
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

// The other Node files of this lesson reuse the parts that read answers and decide.
export { DEFAULT_DATASET, POLICIES, buildRequest, loadDataset, options, readAnswers };

// Run the demo only when this file is the program, not when it is imported.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = main(process.argv.slice(2));
}
