// Lesson 9 - paths, the corpus, and the retriever, all borrowed.
//
// Mirrors python/lesson_core.py. The retriever is Lesson 1's Node engine
// (node/lesson-1/src), imported by path: its chunker, extractor, BM25 and
// config loader import nothing from npm at module load (extract.js reaches for
// pdf-parse and mammoth lazily, only for .pdf and .docx), so this lesson still
// needs no `npm install`. The corpus is Lesson 7's plus this lesson's one
// poisoned note, exactly as in Python.

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chunkPages } from "../../../node/lesson-1/src/chunk.js";
import { loadConfig } from "../../../node/lesson-1/src/config.js";
import { discoverFiles, extractPages } from "../../../node/lesson-1/src/extract.js";
import { buildRetriever as lesson1Retriever } from "../../../node/lesson-1/src/retriever.js";
import { loads } from "./pycompat.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const LESSON_DIR = path.resolve(HERE, "..");
export const ROOT = path.resolve(LESSON_DIR, "..", "..");
export const DATA_DIR = path.join(LESSON_DIR, "data");
export const CASSETTE_DIR = path.join(DATA_DIR, "cassettes");

export const CORPUS_DIR = path.join(ROOT, "lessons", "07-langchain-rag", "data", "corpus");
export const NOTES_DIR = path.join(DATA_DIR, "notes");

export const CHUNK_SIZE = 700;
export const CHUNK_OVERLAP = 120;
export const TOP_K = 3;

/** The lesson's settings and its task set, from data/tasks.json. */
export function loadTasks() {
  return loads(readFileSync(path.join(DATA_DIR, "tasks.json"), "utf8"));
}

async function loadPages(...dirs) {
  const pages = [];
  for (const d of dirs) {
    for (const file of discoverFiles(d)) pages.push(...(await extractPages(file)));
  }
  return pages;
}

/** BM25 over the given folders (default: the corpus plus the notes). */
export async function buildRetriever(...dirs) {
  if (!dirs.length) dirs = [CORPUS_DIR, NOTES_DIR];
  const chunks = chunkPages(await loadPages(...dirs), CHUNK_SIZE, CHUNK_OVERLAP);
  return lesson1Retriever(chunks, { retriever: "bm25" });
}

/** [url, model] from the course config: OLLAMA_URL and OLLAMA_MODEL. */
export function ollamaSettings() {
  const config = loadConfig();
  return [config.ollamaUrl, config.ollamaModel];
}
