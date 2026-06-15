// Lesson 4 - RAG safety & prompt injection demo (Node.js, ESM).
//
// Retrieved documents are untrusted input. A poisoned document can carry an
// instruction a naive pipeline will obey. The same query runs through two
// pipelines over a tiny corpus that contains poisoned support tickets:
//
//   - Undefended: retrieved text is pasted in as-is, so the model obeys the
//     injected instruction and emits the attacker's scripted payload.
//   - Defended: quarantine (drop instruction-like docs), isolate (treat
//     retrieved text as data), and an output filter (block leaked secrets).
//
// Dependency-free and offline. The detection patterns and the model stand-in are
// implemented identically in the Python and .NET ports, so all three produce the
// same output.
//
// Run:  node safe_rag_demo.mjs

import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const DATA_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "data");

const TOP_K = 3;

// Kept identical across the Python, Node and .NET ports.
const STOPWORDS = new Set([
  "a", "an", "the", "to", "of", "do", "i", "in", "on", "is", "are",
  "and", "my", "your", "you", "they", "their", "it", "we",
]);

// Ordered (label, pattern) rules that flag a chunk as "trying to give instructions".
const INJECTION_PATTERNS = [
  ["instruction override", /ignore\s+(all\s+|the\s+)?(previous\s+|above\s+)?(instructions|documents)/],
  ["disregard context", /disregard/],
  ["role injection", /system\s*:/],
  ["forced reply", /reply only with/],
  ["data exfiltration", /https?:\/\/exfil|api key|session token|sk-leaked/],
];

const EXFIL_PATTERN = /https?:\/\/exfil|api key|session token|sk-leaked/;

const NO_ANSWER = "I could not find a trustworthy answer in the documents.";
const OUTPUT_BLOCKED = "[blocked by output filter: the answer tried to leak a secret]";

// Ordinal (code-unit) comparator — locale-independent, so the tie-break order
// matches Python and .NET (StringComparer.Ordinal).
const cmpOrdinal = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

function tokenize(text) {
  return text.toLowerCase().match(/[a-z0-9_]+/g) ?? [];
}

function loadDocs() {
  return readdirSync(DATA_DIR)
    .filter((f) => f.endsWith(".md"))
    .sort()
    .map((name) => {
      const raw = readFileSync(join(DATA_DIR, name), "utf8");
      return { name, raw, tokens: tokenize(raw) };
    });
}

// --- Retrieval: distinct-term overlap, minus stopwords (deterministic) -------
function retrieve(query, docs, topK = TOP_K) {
  const q = new Set(tokenize(query).filter((t) => !STOPWORDS.has(t)));
  const scored = [];
  for (const d of docs) {
    const toks = new Set(d.tokens);
    let score = 0;
    for (const t of q) if (toks.has(t)) score++;
    if (score > 0) scored.push({ score, d });
  }
  scored.sort((a, b) => b.score - a.score || cmpOrdinal(a.d.name, b.d.name));
  return scored.slice(0, topK).map((s) => s.d);
}

// --- Detection: does this chunk try to issue instructions? -------------------
function matchedPatterns(text) {
  const low = text.toLowerCase();
  return INJECTION_PATTERNS.filter(([, pat]) => pat.test(low)).map(([label]) => label);
}

function extractPayload(text) {
  const m = text.match(/reply only with:\s*"([^"]+)"/i);
  return m ? m[1] : "[the model followed an injected instruction]";
}

function containsExfil(text) {
  return EXFIL_PATTERN.test(text.toLowerCase());
}

function legitAnswer(docs, flagged) {
  for (const d of docs) {
    if (flagged.get(d.name).length > 0) continue;
    for (const raw of d.raw.split("\n")) {
      const line = raw.trim();
      if (line && !line.startsWith("#")) return line;
    }
  }
  return NO_ANSWER;
}

// --- The two pipelines, parameterised by which defences are on ---------------
function assess(query, docs, { quarantine = true, isolate = true, outputFilter = true } = {}) {
  const retrieved = retrieve(query, docs);
  const flagged = new Map(retrieved.map((d) => [d.name, matchedPatterns(d.raw)]));

  let effective;
  let quarantined;
  if (quarantine) {
    effective = retrieved.filter((d) => flagged.get(d.name).length === 0);
    quarantined = retrieved.filter((d) => flagged.get(d.name).length > 0).map((d) => d.name);
  } else {
    effective = [...retrieved];
    quarantined = [];
  }

  let obeyed = null;
  if (!isolate) {
    for (const d of effective) {
      if (flagged.get(d.name).length > 0) {
        obeyed = extractPayload(d.raw);
        break;
      }
    }
  }

  let text;
  let followed;
  if (obeyed !== null) {
    text = obeyed;
    followed = true;
  } else {
    text = legitAnswer(effective, flagged);
    followed = false;
  }

  let blocked = false;
  if (outputFilter && containsExfil(text)) {
    text = OUTPUT_BLOCKED;
    blocked = true;
  }

  return {
    text,
    retrieved: retrieved.map((d) => d.name),
    poisoned: retrieved.filter((d) => flagged.get(d.name).length > 0).map((d) => d.name),
    quarantined,
    followedInjection: followed,
    blocked,
    flagged,
  };
}

function fmt(names) {
  return "[" + names.map((n) => `'${n}'`).join(", ") + "]";
}

function main() {
  const docs = loadDocs();
  for (const query of ["how long do refunds take to arrive", "i cannot log in to my account"]) {
    const undefended = assess(query, docs, { quarantine: false, isolate: false, outputFilter: false });
    const defended = assess(query, docs, { quarantine: true, isolate: true, outputFilter: true });
    console.log(`\nQuery: "${query}"`);
    console.log(`  Retrieved:  ${fmt(undefended.retrieved)}`);
    console.log(`  Undefended: ${undefended.text}`);
    console.log(`  Defended:   ${defended.text}`);
  }
}

main();
