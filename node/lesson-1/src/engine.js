// Shared query engine used by the web UI and the CLI.
//
// Keeps a cached retriever so repeated questions don't re-read and re-rank from
// scratch, rebuilding when the docs folder changes or the retriever type is
// switched. JS is single-threaded, but async I/O lets concurrent web requests
// interleave at `await` points, so index build/load is serialized through a
// promise-chain mutex (the analogue of engine.py's threading.Lock).

import { SYSTEM_PROMPT, buildUserPrompt } from "./prompts.js";
import { getProvider } from "./providers/index.js";
import { buildRetriever } from "./retriever.js";
import { buildIndex, isStale, loadChunks } from "./store.js";

const cache = { retriever: null, key: null };

// Run async sections one at a time: each waits for the previous to settle, and
// the chain itself never rejects so one failure can't wedge later callers.
let lock = Promise.resolve();
function withLock(fn) {
  const result = lock.then(fn, fn);
  lock = result.then(
    () => {},
    () => {}
  );
  return result;
}

export async function refreshIndex(config) {
  // Force a rebuild of the on-disk index and invalidate the retriever cache.
  return withLock(async () => {
    const { chunks, fileCount } = await buildIndex(config);
    cache.retriever = null;
    cache.key = null;
    return { chunks, fileCount };
  });
}

export async function getRetriever(config) {
  // Return a retriever for the current docs, rebuilding only when needed.
  return withLock(async () => {
    if (isStale(config)) {
      await buildIndex(config);
      cache.retriever = null;
    }
    if (cache.retriever === null || cache.key !== config.retriever) {
      const chunks = loadChunks(config);
      cache.retriever = buildRetriever(chunks, config);
      cache.key = config.retriever;
    }
    return cache.retriever;
  });
}

export function dedupSources(hits) {
  const seen = [];
  for (const h of hits) {
    const tag = `${h.source}:${h.page_number}`;
    if (!seen.includes(tag)) seen.push(tag);
  }
  return seen;
}

export async function answerQuestion(config, question) {
  // Retrieve grounding context, call the provider, and return a result object.
  const retriever = await getRetriever(config);
  const hits = retriever.search(question, config.topK);
  const provider = getProvider(config.provider, config);
  const answer = await provider.chat(SYSTEM_PROMPT, buildUserPrompt(question, hits));
  return {
    answer: answer.trim(),
    sources: dedupSources(hits),
    provider: config.provider,
    retriever: retriever.name || config.retriever,
    num_hits: hits.length,
  };
}
