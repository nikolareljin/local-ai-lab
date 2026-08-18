// Lesson 7 - Rebuild RAG with LangChain, Node.js port.
//
// LangChain ships two official SDKs: Python and JavaScript. This file is the
// second one, and it exists to make a point the Python side cannot: the same
// components, the same LCEL-style composition, a different runtime - and a
// noticeably different dependency bill.
//
// The hand-rolled half is a direct port of Lesson 1's Python (extract -> chunk ->
// BM25 -> cite), so the retrieval half of the output matches the Python run byte
// for byte. The scorecard half does not, and must not: 18 added packages / 9 MB on
// PyPI against 12 added packages / 48 MB on npm is the honest result.
//
// Run:  node langchain_rag.mjs        (from lessons/07-langchain-rag/node)

import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Document } from "@langchain/core/documents";
import { RecursiveCharacterTextSplitter } from "@langchain/textsplitters";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const LESSON_DIR = path.resolve(HERE, "..");
const CORPUS_DIR = path.join(LESSON_DIR, "data", "corpus");
const SETTINGS = JSON.parse(readFileSync(path.join(LESSON_DIR, "data", "questions.json"), "utf8"));

// --------------------------------------------------------------- hand-rolled (Lesson 1)

// localrag/retriever.py:_tokenize
function tokenize(text) {
  return text.toLowerCase().match(/[a-z0-9]+/g) ?? [];
}

// localrag/extract.py - one page per markdown file, sorted for a stable index.
function handLoad() {
  return readdirSync(CORPUS_DIR)
    .filter((name) => name.endsWith(".md"))
    .sort()
    .map((name) => ({
      source: name,
      page_number: 1,
      text: readFileSync(path.join(CORPUS_DIR, name), "utf8").trim(),
    }));
}

// localrag/chunk.py:_split_text - collapse whitespace first, then break on a
// sentence boundary past the halfway mark.
function splitText(text, size, overlap) {
  const normalized = text.split(/\s+/).filter(Boolean).join(" ");
  if (normalized.length <= size) return normalized ? [normalized] : [];

  const chunks = [];
  let start = 0;
  const n = normalized.length;
  while (start < n) {
    let end = Math.min(start + size, n);
    if (end < n) {
      const window = normalized.slice(start, end);
      for (const sep of [". ", "! ", "? ", "\n", " "]) {
        const pos = window.lastIndexOf(sep);
        if (pos > Math.floor(size / 2)) {
          end = start + pos + sep.length;
          break;
        }
      }
    }
    const piece = normalized.slice(start, end).trim();
    if (piece) chunks.push(piece);
    if (end >= n) break;
    start = Math.max(end - overlap, start + 1);
  }
  return chunks;
}

function handSplit(pages, size, overlap) {
  const chunks = [];
  let index = 0;
  for (const page of pages) {
    for (const piece of splitText(page.text, size, overlap)) {
      chunks.push({ source: page.source, page_number: page.page_number, chunk_index: index, text: piece });
      index += 1;
    }
  }
  return chunks;
}

// rank_bm25.BM25Okapi, ported exactly - including the epsilon floor it applies to
// terms that appear in more than half the corpus. Same numbers, same ordering.
class BM25Okapi {
  constructor(corpus, k1 = 1.5, b = 0.75, epsilon = 0.25) {
    this.k1 = k1;
    this.b = b;
    this.corpusSize = corpus.length;
    this.docFreqs = [];
    this.docLen = [];
    this.idf = new Map();

    const nd = new Map();
    let numDoc = 0;
    for (const document of corpus) {
      this.docLen.push(document.length);
      numDoc += document.length;
      const frequencies = new Map();
      for (const word of document) frequencies.set(word, (frequencies.get(word) ?? 0) + 1);
      this.docFreqs.push(frequencies);
      for (const word of frequencies.keys()) nd.set(word, (nd.get(word) ?? 0) + 1);
    }
    this.avgdl = numDoc / this.corpusSize;

    let idfSum = 0;
    const negative = [];
    for (const [word, freq] of nd) {
      const idf = Math.log(this.corpusSize - freq + 0.5) - Math.log(freq + 0.5);
      this.idf.set(word, idf);
      idfSum += idf;
      if (idf < 0) negative.push(word);
    }
    const eps = epsilon * (idfSum / this.idf.size);
    for (const word of negative) this.idf.set(word, eps);
  }

  getScores(query) {
    const scores = new Array(this.corpusSize).fill(0);
    for (const q of query) {
      const idf = this.idf.get(q) ?? 0;
      for (let i = 0; i < this.corpusSize; i += 1) {
        const freq = this.docFreqs[i].get(q) ?? 0;
        const denom = freq + this.k1 * (1 - this.b + (this.b * this.docLen[i]) / this.avgdl);
        scores[i] += (idf * (freq * (this.k1 + 1))) / denom;
      }
    }
    return scores;
  }
}

// One index per corpus, built on first use and reused for every later query -
// the same contract as Lesson 1's Bm25Retriever.__init__ and as the Python arms.
// Keyed on the array itself, so the two corpora here never share an index.
const bm25Indexes = new WeakMap();

function indexFor(items, textOf) {
  let bm25 = bm25Indexes.get(items);
  if (!bm25) {
    bm25 = new BM25Okapi(items.map((it) => tokenize(textOf(it))));
    bm25Indexes.set(items, bm25);
  }
  return bm25;
}

// localrag/retriever.py:Bm25Retriever.search - top-k, dropping the tail that
// scores at or below zero once there is a real signal.
function bm25Search(items, textOf, query, k) {
  if (!items.length || k <= 0) return [];
  const scores = indexFor(items, textOf).getScores(tokenize(query));
  const ranked = items
    .map((_, i) => i)
    .sort((a, b) => scores[b] - scores[a])
    .slice(0, k);
  if (scores[ranked[0]] <= 0) return ranked.map((i) => items[i]);
  return ranked.filter((i) => scores[i] > 0).map((i) => items[i]);
}

// localrag/engine.py:dedup_sources
function citations(pairs) {
  const seen = [];
  for (const [source, page] of pairs) {
    const tag = `${source}:${page}`;
    if (!seen.includes(tag)) seen.push(tag);
  }
  return seen;
}

// --------------------------------------------------------------- LangChain

function lcLoad() {
  return readdirSync(CORPUS_DIR)
    .filter((name) => name.endsWith(".md"))
    .sort()
    .map(
      (name) =>
        new Document({
          pageContent: readFileSync(path.join(CORPUS_DIR, name), "utf8").trim(),
          metadata: { source: name, page: 1 },
        }),
    );
}

async function lcSplit(docs, size, overlap) {
  const splitter = new RecursiveCharacterTextSplitter({ chunkSize: size, chunkOverlap: overlap });
  return splitter.splitDocuments(docs);
}

// --------------------------------------------------------------- report

async function main() {
  const { chunk_size: size, chunk_overlap: overlap, top_k: k, questions } = SETTINGS;

  const handChunks = handSplit(handLoad(), size, overlap);
  const lcChunks = await lcSplit(lcLoad(), size, overlap);
  const docs = new Set(handChunks.map((c) => c.source)).size;

  const out = [];
  out.push(`Rebuild RAG with LangChain  -  ${docs} documents, same corpus, same system prompt`);
  out.push(`chunked at size=${size} overlap=${overlap}, retrieving top ${k}`);
  out.push("");
  out.push(`  hand-rolled  ${String(handChunks.length).padStart(3)} chunks   (chunk.py: collapse whitespace, break on sentences)`);
  out.push(`  langchain    ${String(lcChunks.length).padStart(3)} chunks   (RecursiveCharacterTextSplitter: keep text, split on separators)`);
  out.push("");

  let agreements = 0;
  questions.forEach((question, i) => {
    const handHits = bm25Search(handChunks, (c) => c.text, question, k);
    const handSources = citations(handHits.map((c) => [c.source, c.page_number]));
    const lcHits = bm25Search(lcChunks, (d) => d.pageContent, question, k);
    const lcSources = citations(lcHits.map((d) => [d.metadata.source, d.metadata.page]));

    out.push(`Q${i + 1}  ${question}`);
    out.push(`    hand-rolled   sources: ${handSources.join(" . ")}`);
    out.push(`    langchain     sources: ${lcSources.join(" . ")}`);
    if (handSources.join("|") === lcSources.join("|")) {
      agreements += 1;
      out.push("    GROUNDING AGREES  -  same sources, same order");
    } else {
      const onlyLc = lcSources.filter((s) => !handSources.includes(s));
      const onlyHand = handSources.filter((s) => !lcSources.includes(s));
      const extra = [];
      if (onlyLc.length) extra.push(`langchain also cites ${onlyLc.join(", ")}`);
      if (onlyHand.length) extra.push(`hand-rolled also cites ${onlyHand.join(", ")}`);
      out.push(`    GROUNDING DIFFERS  -  ${extra.join("; ")}`);
    }
    out.push("");
  });
  out.push(`    ${agreements}/${questions.length} questions grounded identically. Different chunk boundaries, mostly the same evidence.`);
  out.push("");
  console.log(out.join("\n"));

  console.log("What it cost, on npm");
  console.log("  @langchain/core + @langchain/textsplitters");
  console.log("  installed packages   12   (from a baseline of none at all)");
  console.log("  install size         ~48 MB");
  console.log("");
  console.log("  The Python run adds 18 packages and ~9 MB for the same pipeline,");
  console.log("  on top of a course baseline that is already 49 packages.");
  console.log("  Same framework, same components, a different bill. Measure the one you ship.");
}

// Surface failures instead of leaving an unhandled rejection: without this a bad
// data/questions.json or a missing corpus file could end the process with a stack
// trace and a zero exit status, which `./run` would read as success.
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
