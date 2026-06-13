// Lesson 3 - hybrid retrieval demo (Node.js, ESM).
//
// BM25 (lexical) + a semantic stand-in, fused with Reciprocal Rank Fusion (RRF).
// Dependency-free and offline. The same compact BM25 and synonym-expanded
// "semantic" score are implemented identically in the Python and .NET ports, so
// all three produce the same rankings.
//
// Run:  node hybrid_demo.mjs
//
// PRODUCTION (see the lesson README, "From demo to production"):
// - replace the semantic stand-in with real sentence embeddings,
// - add a cross-encoder reranker over the fused top-k.

import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const DATA_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "data");

const K1 = 1.5;
const B = 0.75;
const RRF_K = 60;

// Kept identical across the Python, Node and .NET ports.
const SYNONYMS = {
  turn: ["power", "start", "startup", "boot"],
  on: ["up"],
  wont: ["fail", "fails", "cannot", "dead"],
  broken: ["fail", "fails", "dead"],
};

function tokenize(text) {
  return (text.toLowerCase().match(/[a-z0-9_]+/g) ?? []);
}

function loadDocs() {
  return readdirSync(DATA_DIR)
    .filter((f) => f.endsWith(".md"))
    .sort()
    .map((name) => ({ name, tokens: tokenize(readFileSync(join(DATA_DIR, name), "utf8")) }));
}

function count(arr, value) {
  let c = 0;
  for (const x of arr) if (x === value) c++;
  return c;
}

// --- Lexical arm: a compact BM25 (no external library) ----------------------
function bm25Scores(queryTokens, docs) {
  const n = docs.length;
  const avgdl = docs.reduce((s, d) => s + d.tokens.length, 0) / n;
  const df = new Map();
  for (const d of docs) for (const t of new Set(d.tokens)) df.set(t, (df.get(t) ?? 0) + 1);
  return docs.map((d) => {
    const dl = d.tokens.length;
    let score = 0;
    for (const t of queryTokens) {
      if (!df.has(t)) continue;
      const idf = Math.log(1 + (n - df.get(t) + 0.5) / (df.get(t) + 0.5));
      const tf = count(d.tokens, t);
      score += idf * (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * dl / avgdl));
    }
    return score;
  });
}

// --- Semantic stand-in: synonym-expanded overlap (no model needed) ----------
function semanticScores(queryTokens, docs) {
  const q = new Set(queryTokens);
  for (const t of [...q]) for (const s of SYNONYMS[t] ?? []) q.add(s);
  return docs.map((d) => {
    const toks = new Set(d.tokens);
    let overlap = 0;
    for (const t of q) if (toks.has(t)) overlap++;
    return overlap / (q.size || 1);
  });
}

// Deterministic: score desc, then name asc.
function rank(docs, scores) {
  return docs
    .map((d, i) => ({ name: d.name, score: scores[i] }))
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name))
    .map((x) => x.name);
}

function rrf(rankings) {
  const fused = new Map();
  for (const ranking of rankings) {
    ranking.forEach((name, pos) => fused.set(name, (fused.get(name) ?? 0) + 1 / (RRF_K + pos + 1)));
  }
  return [...fused.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([name]) => name);
}

function hybrid(query, docs) {
  const q = tokenize(query);
  const lexical = rank(docs, bm25Scores(q, docs));
  const semantic = rank(docs, semanticScores(q, docs));
  return { lexical, semantic, fused: rrf([lexical, semantic]) };
}

function main() {
  const docs = loadDocs();
  for (const query of ["error E_4096", "my device won't turn on"]) {
    const { lexical, semantic, fused } = hybrid(query, docs);
    console.log(`\nQuery: ${JSON.stringify(query)}`);
    console.log(`  BM25 (lexical):   [${lexical.map((s) => `'${s}'`).join(", ")}]`);
    console.log(`  Semantic (stand): [${semantic.map((s) => `'${s}'`).join(", ")}]`);
    console.log(`  Hybrid (RRF):     [${fused.map((s) => `'${s}'`).join(", ")}]`);
  }
}

main();
