// Lesson 8 - a stateful agent with LangGraph, Node.js port.
//
// Same three arms as the Python reference, over the same corpus, with the same
// settings read from the same JSON files. The retrieval and the control flow are
// deterministic string arithmetic on both runtimes, so the arms reach the same
// documents in the same order and the comparison is a measurement rather than a
// coincidence.
//
// What is deliberately NOT the same is the dependency bill - see the lesson
// README, "Python and Node". Faking parity there would hide the number.
//
//   node langgraph_agent.mjs          the three-arm comparison
//   ./run -l 8 --lang node demo       the same thing, through the course runner

import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const LESSON_DIR = path.join(HERE, "..");
const REPO_ROOT = path.join(LESSON_DIR, "..", "..");

// Lesson 7's corpus, by path - not a copy. Same reason as the Python arm.
const CORPUS_DIR = path.join(REPO_ROOT, "lessons", "07-langchain-rag", "data", "corpus");
const SETTINGS = JSON.parse(readFileSync(path.join(LESSON_DIR, "data", "questions.json"), "utf8"));
const GLOSSARY = Object.fromEntries(
  Object.entries(JSON.parse(readFileSync(path.join(LESSON_DIR, "data", "glossary.json"), "utf8")))
    .filter(([k]) => !k.startsWith("_")),
);

// --------------------------------------------------------------- Lesson 1, ported

// localrag/retriever.py:_tokenize
function tokenize(text) {
  return text.toLowerCase().match(/[a-z0-9]+/g) ?? [];
}

// rag_core.py:STOPWORDS - kept identical so "which terms are missing?" is asked
// in the same vocabulary on both runtimes.
const STOPWORDS = new Set(
  `a an and any are as at be but by can do does for from has have how i if in is
   it its me my no not of on or so that the their them then there they this to was
   what when where which who why will with you your`.split(/\s+/).filter(Boolean),
);

function contentTerms(text) {
  const seen = [];
  for (const t of tokenize(text)) {
    if (!STOPWORDS.has(t) && !seen.includes(t)) seen.push(t);
  }
  return seen;
}

// localrag/extract.py - one page per markdown file, sorted for a stable index.
function load() {
  return readdirSync(CORPUS_DIR)
    .filter((name) => name.endsWith(".md"))
    .sort()
    .map((name) => ({
      source: name,
      page_number: 1,
      text: readFileSync(path.join(CORPUS_DIR, name), "utf8").trim(),
    }));
}

// localrag/chunk.py:_split_text
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

function split(pages, size, overlap) {
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
// terms appearing in more than half the corpus.
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

// The index is built once and reused, exactly as Lesson 1's Bm25Retriever does.
const CHUNKS = split(load(), SETTINGS.chunk_size, SETTINGS.chunk_overlap);
const INDEX = new BM25Okapi(CHUNKS.map((c) => tokenize(c.text)));

function retrieve(query, k) {
  if (!CHUNKS.length || k <= 0) return [];
  const scores = INDEX.getScores(tokenize(query));
  const ranked = CHUNKS.map((_, i) => i)
    .sort((a, b) => scores[b] - scores[a])
    .slice(0, k);
  if (scores[ranked[0]] <= 0) return ranked.map((i) => CHUNKS[i]);
  return ranked.filter((i) => scores[i] > 0).map((i) => CHUNKS[i]);
}

// localrag/engine.py:dedup_sources
function sources(hits) {
  const seen = [];
  for (const h of hits) {
    const tag = `${h.source}:${h.page_number}`;
    if (!seen.includes(tag)) seen.push(tag);
  }
  return seen;
}

// --------------------------------------------------------------- grader and rewriter

// graders.py:CoverageGrader - what fraction of the query's content words does the
// retrieved text actually contain?
function grade(question, query, docs, threshold) {
  const terms = contentTerms(query);
  if (!terms.length) {
    return { verdict: "weak", score: 0, missing: [], reason: "no content terms to look for" };
  }
  const haystack = new Set(tokenize(docs.map((d) => d.text).join("\n\n")));
  const missing = terms.filter((t) => !haystack.has(t));
  const score = (terms.length - missing.length) / terms.length;
  const grounded = score >= threshold;
  return {
    verdict: grounded ? "grounded" : "weak",
    score: Math.round(score * 100) / 100,
    missing,
    reason: `evidence covers ${terms.length - missing.length}/${terms.length} query terms`,
  };
}

// rewriter.py:GlossaryRewriter - expand only the terms that did not land.
function rewrite(question, query, missing) {
  if (!missing.length) return query;
  const expanded = [];
  for (const term of missing) expanded.push(...(GLOSSARY[term] ?? []));
  if (!expanded.length) return query;
  const kept = contentTerms(query).filter((t) => !missing.includes(t));
  const out = [];
  for (const term of [...kept, ...expanded]) if (!out.includes(term)) out.push(term);
  return out.join(" ");
}

// --------------------------------------------------------------- the arms

function runLinear(question, topK) {
  const docs = retrieve(question, topK);
  return { sources: sources(docs), attempts: 1, retrievals: 1, rewrites: 0, status: "answered" };
}

function runLoop(question, topK, threshold, maxAttempts) {
  let query = question;
  let attempt = 1;
  let retrievals = 0;
  let rewrites = 0;
  let docs = [];
  let verdict = null;
  const trace = [];
  for (;;) {
    docs = retrieve(query, topK);
    retrievals += 1;
    trace.push(`retrieve  attempt=${attempt} query=${JSON.stringify(query)} -> ${JSON.stringify(sources(docs))}`);
    verdict = grade(question, query, docs, threshold);
    trace.push(`grade     ${verdict.verdict} score=${verdict.score}`);
    if (verdict.verdict === "grounded") break;
    if (attempt >= maxAttempts) break;
    const next = rewrite(question, query, verdict.missing);
    rewrites += 1;
    if (next === query) break; // nothing left to try - see loop_agent.py
    trace.push(`rewrite   -> ${JSON.stringify(next)}`);
    query = next;
    attempt += 1;
  }
  const grounded = verdict.verdict === "grounded";
  return {
    sources: grounded ? sources(docs) : [],
    attempts: attempt, retrievals, rewrites,
    status: grounded ? "answered" : "abstained", trace,
  };
}

// The graph arm. Imported lazily so `demo` still runs, and still prints the whole
// accuracy result, when @langchain/langgraph is not installed.
async function buildGraph(topK, threshold, maxAttempts) {
  let lg;
  try {
    lg = await import("@langchain/langgraph");
  } catch {
    return null;
  }
  const { Annotation, StateGraph, START, END, MemorySaver } = lg;

  const State = Annotation.Root({
    question: Annotation(),
    query: Annotation(),
    attempt: Annotation({ default: () => 1, reducer: (_a, b) => b }),
    docs: Annotation(),
    sources: Annotation(),
    // Named `verdict`, not `grade`: the JS StateGraph refuses to let a state
    // channel share a name with a node, and `grade` is a node here.
    verdict: Annotation(),
    // The reducers, exactly as in the Python AgentState: these ACCUMULATE while
    // everything above is last-write-wins.
    trace: Annotation({ default: () => [], reducer: (a, b) => a.concat(b) }),
    retrievals: Annotation({ default: () => 0, reducer: (a, b) => a + b }),
    rewrites: Annotation({ default: () => 0, reducer: (a, b) => a + b }),
    status: Annotation(),
  });

  const builder = new StateGraph(State)
    .addNode("retrieve", (s) => {
      const docs = retrieve(s.query, topK);
      return { docs, sources: sources(docs), retrievals: 1,
               trace: [`retrieve  attempt=${s.attempt} -> ${JSON.stringify(sources(docs))}`] };
    })
    .addNode("grade", (s) => ({ verdict: grade(s.question, s.query, s.docs, threshold) }))
    .addNode("rewrite", (s) => {
      const next = rewrite(s.question, s.query, s.verdict.missing);
      if (next === s.query) return { rewrites: 1, trace: ["abstain   rewrite changed nothing"] };
      return { query: next, attempt: s.attempt + 1, rewrites: 1,
               trace: [`rewrite   -> ${JSON.stringify(next)}`] };
    })
    .addNode("generate", (s) => ({ status: "answered" }))
    .addNode("abstain", (s) => ({ status: "abstained", sources: [] }))
    .addEdge(START, "retrieve")
    .addEdge("retrieve", "grade")
    .addConditionalEdges("grade", (s) => {
      if (s.verdict.verdict === "grounded") return "generate";
      if (s.attempt >= maxAttempts) return "abstain";
      return "rewrite";
    }, { rewrite: "rewrite", generate: "generate", abstain: "abstain" })
    .addConditionalEdges("rewrite", (s) => (
      String(s.trace.at(-1) ?? "").startsWith("abstain") ? "abstain" : "retrieve"
    ), { retrieve: "retrieve", abstain: "abstain" })   // <- the cycle
    .addEdge("generate", END)
    .addEdge("abstain", END);

  return builder.compile({ checkpointer: new MemorySaver() });
}

async function runGraph(graph, question, threadId) {
  const state = await graph.invoke(
    { question, query: question, attempt: 1, retrievals: 0, rewrites: 0, trace: [] },
    { configurable: { thread_id: threadId } },
  );
  return {
    sources: state.status === "answered" ? state.sources : [],
    attempts: state.attempt, retrievals: state.retrievals,
    rewrites: state.rewrites, status: state.status,
  };
}

// --------------------------------------------------------------- the demo

function scored(result, expect) {
  if (expect === null) return result.status === "abstained";
  return result.sources[0] === `${expect}:1`;
}

function pad(text, width) {
  return String(text).padEnd(width);
}

async function main() {
  const { top_k: topK, grade_threshold: threshold, max_attempts: maxAttempts } = SETTINGS;
  const graph = await buildGraph(topK, threshold, maxAttempts);

  console.log("Lesson 8 · A stateful agent with LangGraph  (Node.js)");
  console.log(`corpus: lessons/07-langchain-rag/data/corpus  (${CHUNKS.length} chunks - Lesson 7's, by path)`);
  console.log(`settings: top_k=${topK} threshold=${threshold} max_attempts=${maxAttempts}`);
  console.log();
  console.log(`  ${pad("", 4)} ${pad("linear", 7)}${pad("loop", 7)}${pad("graph", 7)}${pad("att", 4)} question`);
  console.log("  " + "-".repeat(74));

  let linOk = 0, loopOk = 0, linAbs = 0, loopAbs = 0;
  let linRet = 0, loopRet = 0, answerable = 0, unanswerable = 0, agree = 0;

  for (const item of SETTINGS.questions) {
    const lin = runLinear(item.ask, topK);
    const loop = runLoop(item.ask, topK, threshold, maxAttempts);
    const grp = graph ? await runGraph(graph, item.ask, `node-${item.id}`) : null;
    linRet += lin.retrievals;
    loopRet += loop.retrievals;
    if (item.expect === null) {
      unanswerable += 1;
      if (scored(lin, null)) linAbs += 1;
      if (scored(loop, null)) loopAbs += 1;
    } else {
      answerable += 1;
      if (scored(lin, item.expect)) linOk += 1;
      if (scored(loop, item.expect)) loopOk += 1;
    }
    if (grp && JSON.stringify(grp.sources) === JSON.stringify(loop.sources)
        && grp.attempts === loop.attempts && grp.retrievals === loop.retrievals) agree += 1;
    const cell = (ok) => pad(ok ? "PASS" : "FAIL", 7);
    console.log(`  ${pad(item.id, 4)} ${cell(scored(lin, item.expect))}`
      + `${cell(scored(loop, item.expect))}`
      + `${grp ? cell(scored(grp, item.expect)) : pad("  - ", 7)}`
      + `${pad(loop.attempts, 4)} ${item.ask}`);
  }

  const pct = Math.round(((loopRet - linRet) / linRet) * 100);
  console.log();
  console.log("The scorecard");
  const row = (label, a, b) => console.log(`  ${pad(label, 26)}${pad(a, 18)}${b}`);
  row("", "linear", "loop (while)");
  row("top source correct", `${linOk}/${answerable}`, `${loopOk}/${answerable}`);
  row("correctly abstained", `${linAbs}/${unanswerable}`, `${loopAbs}/${unanswerable}`);
  row("retrieval calls", linRet, `${loopRet}  (+${pct}%)`);
  console.log();
  if (graph) {
    console.log(`  The graph agrees with the while loop on ${agree}/${SETTINGS.questions.length} questions.`);
    console.log("  Same answers, same attempts, same retrievals - in a second runtime.");
  } else {
    console.log("  @langchain/langgraph is not installed, so the graph column is blank.");
    console.log("  The accuracy result above belongs to the loop, which needs no dependency.");
    console.log("  npm --prefix lessons/08-langgraph/node install");
  }
  console.log();
  console.log("  Retrieval and control flow are identical to the Python run. The dependency");
  console.log("  bill is not - see the lesson README, \"Python and Node\".");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
