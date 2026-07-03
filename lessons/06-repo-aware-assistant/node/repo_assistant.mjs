// Lesson 6 - Repo-aware AI assistant demo (Node.js, ESM).
//
// A repo-aware assistant answers questions about one codebase - and only from
// what is in it. This demo builds a tiny, offline version: it INDEXes the repo
// into line-numbered passages (each carrying its path + line range, i.e. its
// citation), ANSWERs a question only from the retrieved passages (always cited,
// or "not found" when nothing clears a minimum score), and for a change request
// produces a PLAN-before-edit that changes no files.
//
// Dependency-free and offline. The index/retrieve/answer algorithm is identical
// to the Python and .NET ports, so all three print byte-identical output.
//
// Run:  node repo_assistant.mjs

import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const LESSON_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
const REPO_DIR = join(LESSON_DIR, "data", "repo");
const QUESTIONS = join(LESSON_DIR, "data", "questions.json");

// Point the assistant at your OWN repo with:  REPO_PATH=/path/to/repo
// (unset, it indexes the sample repo under data/repo). Vendored/build dirs and
// non-text files are skipped - noise the sample doesn't contain, so the demo is
// unchanged, but which keeps a real repo's index to source and docs.
const IGNORE_DIRS = new Set([
  ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
  "bin", "obj", "target", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".idea",
]);
const TEXT_EXT = new Set([
  ".md", ".txt", ".rst", ".py", ".sh", ".js", ".mjs", ".ts", ".tsx", ".jsx",
  ".cs", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".rs", ".go",
  ".java", ".kt", ".rb", ".php", ".html", ".css", ".c", ".h", ".cpp", ".hpp",
  ".sql", ".xml",
]);

function isIndexable(relPath) {
  const parts = relPath.split("/");
  for (let i = 0; i < parts.length - 1; i++) {
    if (IGNORE_DIRS.has(parts[i]) || parts[i].startsWith(".")) return false;
  }
  const name = parts[parts.length - 1];
  const dot = name.lastIndexOf(".");
  return TEXT_EXT.has(dot >= 0 ? name.slice(dot).toLowerCase() : "");
}

// Kept identical across the Python, Node and .NET ports.
const STOPWORDS = new Set([
  "a", "an", "the", "to", "of", "do", "i", "in", "on", "is", "are",
  "and", "my", "your", "you", "they", "their", "it", "we",
]);

// Ordinal (code-unit) comparator so tie-break order matches Python (str <) and
// .NET (StringComparer.Ordinal).
const cmpOrdinal = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

function tokenize(text) {
  return text.toLowerCase().match(/[a-z0-9_]+/g) ?? [];
}

function terms(text) {
  return new Set(tokenize(text).filter((t) => !STOPWORDS.has(t)));
}

// Match Python str.splitlines(): split on line breaks and drop the empty tail a
// trailing newline would otherwise produce.
function splitLines(raw) {
  const parts = raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  if (parts.length && parts[parts.length - 1] === "" && /\n$/.test(raw)) parts.pop();
  return parts;
}

// --- Index: split every repo file into line-numbered passages ----------------
function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) continue;  // don't follow symlinks: avoids cycles / escaping the repo root
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (IGNORE_DIRS.has(entry.name) || entry.name.startsWith(".")) continue;  // don't descend noise
      out.push(...walk(full));
    } else if (entry.isFile()) out.push(full);
  }
  return out;
}

function relTo(base, full) {
  return full.slice(base.length + 1).split(/[/\\]/).join("/");
}

function makeChunk(relPath, lines, first, last) {
  const body = lines.slice(first, last + 1);
  const text = body.join("\n");
  return { path: relPath, start: first + 1, end: last + 1, firstLine: body[0].trim(), tokens: terms(text) };
}

function chunkFile(relPath, raw) {
  const chunks = [];
  const lines = splitLines(raw);
  let start = null;
  for (let i = 0; i < lines.length; i++) {
    const blank = lines[i].trim() === "";
    if (!blank && start === null) start = i;
    else if (blank && start !== null) { chunks.push(makeChunk(relPath, lines, start, i - 1)); start = null; }
  }
  if (start !== null) chunks.push(makeChunk(relPath, lines, start, lines.length - 1));
  return chunks;
}

function buildIndex(repoDir) {
  const files = walk(repoDir).map((f) => relTo(repoDir, f)).filter(isIndexable).sort(cmpOrdinal);
  const chunks = [];
  for (const relPath of files) {
    chunks.push(...chunkFile(relPath, readFileSync(join(repoDir, relPath), "utf8")));
  }
  return { files, chunks };
}

const cite = (c) => `${c.path}:${c.start}-${c.end}`;

function intersectCount(a, b) {
  let n = 0;
  for (const t of a) if (b.has(t)) n++;
  return n;
}

// --- Retrieve: keyword overlap, deterministic order --------------------------
function retrieve(query, chunks, topK) {
  const q = terms(query);
  const scored = [];
  for (const c of chunks) {
    const s = intersectCount(q, c.tokens);
    if (s > 0) scored.push({ s, c });
  }
  scored.sort((x, y) => y.s - x.s || cmpOrdinal(x.c.path, y.c.path) || x.c.start - y.c.start);
  return scored.slice(0, topK);
}

// --- Answer: only from retrieved passages, always cited, else "not found" ----
function answer(query, chunks, topK, minScore) {
  const hits = retrieve(query, chunks, topK);
  if (hits.length === 0 || hits[0].s < minScore) {
    return { kind: "not_found", best: hits.length ? hits[0].s : 0 };
  }
  const { s, c } = hits[0];
  return { kind: "grounded", score: s, citation: cite(c), line: c.firstLine, sources: hits.map((h) => cite(h.c)) };
}

// --- Plan-before-edit --------------------------------------------------------
function firstUnder(paths, prefix) {
  for (const p of paths) if (p.startsWith(prefix)) return p;
  return null;
}

function plan(query, files, chunks, topK) {
  const hits = retrieve(query, chunks, topK);
  if (hits.length === 0) return { kind: "not_found", best: 0 };
  const top = hits[0].c;
  return {
    kind: "plan",
    relevant: hits.map((h) => cite(h.c)),
    behaviour: { citation: cite(top), line: top.firstLine },
    change: `add the new code alongside ${top.path}, matching the pattern already there`,
    tests: firstUnder(files, "tests/") ?? "add a test under tests/",
    docs: files.includes("README.md") ? "README.md" : "update the project docs",
  };
}

function respond(q, files, chunks, topK, minScore) {
  if (q.kind === "plan") return plan(q.question, files, chunks, topK);
  return answer(q.question, chunks, topK, minScore);
}

// --- Reporting (byte-identical across the three ports) -----------------------
function printResponse(n, q, result, minScore) {
  const tag = q.kind === "plan" ? "   [plan-before-edit]" : "";
  console.log(`\nQ${n}  ${q.question}${tag}`);
  if (result.kind === "grounded") {
    console.log("    GROUNDED  -  answered only from indexed repository lines");
    console.log(`    ${result.citation}`);
    console.log(`      ${result.line}`);
    console.log(`    sources: ${result.sources.join(" . ")}`);
  } else if (result.kind === "plan") {
    console.log("    PLAN  -  no files changed, approve before editing");
    console.log(`    1. relevant files    ${result.relevant.join(" . ")}`);
    console.log(`    2. current behaviour  ${result.behaviour.citation}  ->  ${result.behaviour.line}`);
    console.log(`    3. minimal change     ${result.change}`);
    console.log(`    4. update tests       ${result.tests}`);
    console.log(`    5. update docs        ${result.docs}`);
  } else {
    console.log(`    NOT FOUND  -  best match scored ${result.best} (< min ${minScore}), so the assistant abstains`);
    console.log("      no citation, no invented answer");
  }
}

function main() {
  const cfg = JSON.parse(readFileSync(QUESTIONS, "utf8"));
  const envRepo = process.env.REPO_PATH;
  const repoDir = envRepo ? resolve(envRepo) : REPO_DIR;
  const label = envRepo ? repoDir : "data/repo";

  let files, chunks;
  try {
    ({ files, chunks } = buildIndex(repoDir));
  } catch (err) {
    console.error(`error: cannot index repository at ${repoDir}: ${err.message}`);
    process.exit(1);
  }

  const argv = process.argv.slice(2);
  let questions;
  if (argv[0] === "ask" || argv[0] === "plan") {
    const question = argv.slice(1).join(" ").trim();
    if (!question) { console.log('usage: repo_assistant.mjs [ask|plan] "your question"'); return; }
    questions = [{ id: argv[0], kind: argv[0] === "plan" ? "plan" : "locate", question }];
  } else {
    questions = cfg.questions;
  }

  console.log(`Repo-aware assistant  -  indexed ${files.length} files, ${chunks.length} passages under ${label}`);
  questions.forEach((q, i) => printResponse(i + 1, q, respond(q, files, chunks, cfg.top_k, cfg.min_score), cfg.min_score));
}

main();
