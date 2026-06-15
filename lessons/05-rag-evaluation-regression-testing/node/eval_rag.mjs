// Lesson 5 - RAG evaluation & regression testing demo (Node.js, ESM).
//
// "Seems good" is not a metric. This demo turns the quality of a RAG pipeline
// into numbers you can track: a small golden set of questions (each with the
// document that should be retrieved and the keywords a correct answer must
// contain) scored on three axes — retrieval recall@k, groundedness, and answer
// correctness. A question PASSES only if all three clear their thresholds; the
// gate passes only if every question passes. We run two configs over the same
// golden set: a BASELINE that clears the gate, and a CANDIDATE — a
// reasonable-looking tweak (smaller top_k, an answer padded with an unsupported
// sentence) that silently regresses two of the numbers. The eval catches it.
//
// Dependency-free and offline. The retriever, answerer stand-in and metrics are
// implemented identically in the Python and .NET ports, so all three produce the
// same output.
//
// Run:  node eval_rag.mjs

import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const DATA_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "data");

// Kept identical across the Python, Node and .NET ports.
const STOPWORDS = new Set([
  "a", "an", "the", "to", "of", "do", "i", "in", "on", "is", "are",
  "and", "my", "your", "you", "they", "their", "it", "we",
]);

// A hallucinated sentence the CANDIDATE answerer pads onto every answer. None of
// its content terms appear anywhere in the corpus, so groundedness drops.
const UNSUPPORTED = "A complimentary gift card will be mailed separately.";

// Ordinal (code-unit) comparator — locale-independent, so the tie-break order
// matches Python and .NET (StringComparer.Ordinal).
const cmpOrdinal = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

function tokenize(text) {
  return text.toLowerCase().match(/[a-z0-9_]+/g) ?? [];
}

function terms(text) {
  return new Set(tokenize(text).filter((t) => !STOPWORDS.has(t)));
}

function loadDocs() {
  return readdirSync(DATA_DIR)
    .filter((f) => f.endsWith(".md"))
    .sort()
    .map((name) => {
      const raw = readFileSync(join(DATA_DIR, name), "utf8");
      return { name, raw, tokens: new Set(tokenize(raw)) };
    });
}

function loadGolden() {
  return JSON.parse(readFileSync(join(DATA_DIR, "golden.json"), "utf8"));
}

// --- Retrieval: distinct-term overlap, minus stopwords (deterministic) -------
function retrieve(query, docs, topK) {
  const q = terms(query);
  const scored = [];
  for (const d of docs) {
    let score = 0;
    for (const t of q) if (d.tokens.has(t)) score++;
    if (score > 0) scored.push({ score, d });
  }
  scored.sort((a, b) => b.score - a.score || cmpOrdinal(a.d.name, b.d.name));
  return scored.slice(0, topK).map((s) => s.d);
}

// --- Answerer: a deterministic, offline extractive stand-in ------------------
function firstBodyLine(doc) {
  for (const raw of doc.raw.split("\n")) {
    const line = raw.trim();
    if (line && !line.startsWith("#")) return line;
  }
  return "";
}

function answer(retrieved, padUnsupported = false) {
  if (retrieved.length === 0) return "";
  let text = firstBodyLine(retrieved[0]);
  if (padUnsupported) text = (text + " " + UNSUPPORTED).trim();
  return text;
}

// --- The three metrics -------------------------------------------------------
function recallAtK(goldDocs, retrieved) {
  if (goldDocs.length === 0) return 1.0;
  const names = new Set(retrieved.map((d) => d.name));
  const hit = goldDocs.filter((g) => names.has(g)).length;
  return hit / goldDocs.length;
}

function intersectCount(a, b) {
  let n = 0;
  for (const t of a) if (b.has(t)) n++;
  return n;
}

function groundedness(answerText, retrieved) {
  const a = terms(answerText);
  if (a.size === 0) return 1.0;
  const context = new Set();
  for (const d of retrieved) for (const t of terms(d.raw)) context.add(t);
  return intersectCount(a, context) / a.size;
}

function correctness(answerText, keywords) {
  if (keywords.length === 0) return 1.0;
  const toks = new Set(tokenize(answerText));
  const hit = keywords.filter((k) => toks.has(k)).length;
  return hit / keywords.length;
}

// --- One config over the whole golden set ------------------------------------
function evaluate(golden, docs, config) {
  const thr = golden.thresholds;
  if (golden.questions.length === 0) {
    throw new Error("golden set has no questions — add at least one to data/golden.json");
  }
  const rows = golden.questions.map((q) => {
    const retrieved = retrieve(q.question, docs, config.top_k);
    const ans = answer(retrieved, config.pad_unsupported);
    const recall = recallAtK(q.gold_docs, retrieved);
    const grounded = groundedness(ans, retrieved);
    const correct = correctness(ans, q.answer_keywords);
    const passed = recall >= 1.0 && grounded >= thr.groundedness && correct >= thr.correctness;
    return { id: q.id, recall, groundedness: grounded, correctness: correct, passed };
  });
  const n = rows.length;
  const sum = (f) => rows.reduce((s, r) => s + f(r), 0);
  const aggregate = {
    mean_recall: sum((r) => r.recall) / n,
    mean_groundedness: sum((r) => r.groundedness) / n,
    mean_correctness: sum((r) => r.correctness) / n,
    pass_count: rows.filter((r) => r.passed).length,
    total: n,
  };
  return { config_name: config.name, rows, aggregate, gate_passed: aggregate.pass_count === n };
}

const BASELINE = { name: "baseline", top_k: 3, pad_unsupported: false };
const CANDIDATE = { name: "candidate", top_k: 1, pad_unsupported: true };

// --- Reporting (byte-identical across the three ports) -----------------------
const pct = (x) => x.toFixed(2);
const gateWord = (passed) => (passed ? "PASS" : "FAIL");
const signed = (x) => (x >= 0 ? "+" : "-") + Math.abs(x).toFixed(2);

function printReport(result, config) {
  const flags = `top_k=${config.top_k}, padding=${config.pad_unsupported ? "on" : "off"}`;
  console.log(`\nConfig: ${result.config_name}  (${flags})`);
  console.log("  id               recall  grounded  correct  result");
  for (const r of result.rows) {
    console.log(
      `  ${r.id.padEnd(15)}   ${pct(r.recall)}      ${pct(r.groundedness)}     ${pct(r.correctness)}  ${gateWord(r.passed)}`,
    );
  }
  const a = result.aggregate;
  console.log(
    `  Aggregate: recall ${pct(a.mean_recall)}  grounded ${pct(a.mean_groundedness)}  correct ${pct(a.mean_correctness)}   ${a.pass_count}/${a.total} passed   GATE: ${gateWord(result.gate_passed)}`,
  );
}

function printRegression(base, cand, groundednessThreshold) {
  const b = base.aggregate;
  const c = cand.aggregate;
  const line = (label, bv, cv, note = "") =>
    console.log(`  ${label.padEnd(18)} ${pct(bv)} -> ${pct(cv)}   (${signed(cv - bv)})${note}`);
  console.log("\nRegression vs baseline:");
  line("mean recall:", b.mean_recall, c.mean_recall);
  const below = c.mean_groundedness < groundednessThreshold
    ? `   below threshold ${pct(groundednessThreshold)}` : "";
  line("mean groundedness:", b.mean_groundedness, c.mean_groundedness, below);
  line("mean correctness:", b.mean_correctness, c.mean_correctness);
  console.log(`  ${"gate:".padEnd(18)} ${gateWord(base.gate_passed)} -> ${gateWord(cand.gate_passed)}`);
}

function main() {
  const docs = loadDocs();
  const golden = loadGolden();
  const base = evaluate(golden, docs, BASELINE);
  const cand = evaluate(golden, docs, CANDIDATE);
  printReport(base, BASELINE);
  printReport(cand, CANDIDATE);
  printRegression(base, cand, golden.thresholds.groundedness);
}

main();
