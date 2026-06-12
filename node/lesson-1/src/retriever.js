// Retrieval engine: BM25 (default, zero setup).
//
// Mirrors localrag/retriever.py's Bm25Retriever, with BM25 Okapi implemented by
// hand to match rank_bm25's BM25Okapi defaults (k1=1.5, b=0.75, and the same
// `log((N - n + 0.5) / (n + 0.5))` IDF that can go negative on tiny corpora).
//
// PARITY NOTE: the EmbeddingRetriever is out of scope for this Node port. If
// `config.retriever === "embeddings"`, buildRetriever prints a one-line notice
// and falls back to BM25, like the Python does on embedding failure.

function tokenize(text) {
  return (text.toLowerCase().match(/[a-z0-9]+/g)) || [];
}

class Bm25Retriever {
  constructor(chunks) {
    this.name = "bm25";
    this.chunks = chunks;
    this.k1 = 1.5;
    this.b = 0.75;

    const corpus = chunks.length ? chunks.map((c) => tokenize(c.text)) : [[""]];
    this.corpusSize = corpus.length;
    this.docLengths = corpus.map((doc) => doc.length);
    const totalLen = this.docLengths.reduce((s, l) => s + l, 0);
    this.avgdl = totalLen / this.corpusSize;

    // Per-document term frequencies + document frequency per term.
    this.docFreqs = [];
    const df = new Map();
    for (const doc of corpus) {
      const freqs = new Map();
      for (const term of doc) freqs.set(term, (freqs.get(term) || 0) + 1);
      this.docFreqs.push(freqs);
      for (const term of freqs.keys()) df.set(term, (df.get(term) || 0) + 1);
    }

    // IDF, matching rank_bm25 BM25Okapi: log((N - n + 0.5) / (n + 0.5)).
    this.idf = new Map();
    for (const [term, n] of df.entries()) {
      this.idf.set(term, Math.log((this.corpusSize - n + 0.5) / (n + 0.5)));
    }
  }

  scores(queryTokens) {
    const out = new Array(this.corpusSize).fill(0);
    for (const term of queryTokens) {
      const idf = this.idf.get(term);
      if (idf === undefined) continue;
      for (let i = 0; i < this.corpusSize; i++) {
        const f = this.docFreqs[i].get(term);
        if (!f) continue;
        const denom = f + this.k1 * (1 - this.b + (this.b * this.docLengths[i]) / this.avgdl);
        out[i] += idf * ((f * (this.k1 + 1)) / denom);
      }
    }
    return out;
  }

  search(query, k) {
    if (!this.chunks.length) return [];
    const scores = this.scores(tokenize(query));
    const ranked = scores
      .map((_, i) => i)
      .sort((a, b) => scores[b] - scores[a]);
    // Return the top-k candidates by score and let the grounding prompt judge
    // relevance. (BM25 IDF can be negative on tiny corpora, so an absolute score
    // cutoff would wrongly discard everything.) Only drop the long tail that
    // scores strictly worse than the best, when there is a real signal.
    const top = ranked.slice(0, k);
    const best = scores[top[0]];
    if (best <= 0) {
      return top.map((i) => this.chunks[i]);
    }
    return top.filter((i) => scores[i] > 0).map((i) => this.chunks[i]);
  }
}

export function buildRetriever(chunks, config) {
  // Pick a retriever from config. Embeddings are not ported in Node; fall back
  // to BM25 with a clear message, mirroring the Python "never dead-end" design.
  if (config.retriever === "embeddings") {
    console.log(
      "[localrag] Embeddings not ported in Node. Falling back to BM25 (use the Python reference for embeddings)."
    );
  }
  return new Bm25Retriever(chunks);
}
