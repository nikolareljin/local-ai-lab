// Retrieval engine: BM25 (default, zero setup).
//
// Mirrors localrag/retriever.py's Bm25Retriever, with BM25 Okapi implemented by
// hand to match rank_bm25's BM25Okapi defaults (k1=1.5, b=0.75, the same
// `log((N - n + 0.5) / (n + 0.5))` IDF, and the same epsilon flooring of negative
// IDFs so a term in > half the chunks never outranks the chunks that contain it).
//
// PARITY NOTE: the EmbeddingRetriever is out of scope for this Node port. If
// `config.retriever === "embeddings"`, buildRetriever prints a one-line notice
// and falls back to BM25, like the Python does on embedding failure.

function tokenize(text) {
  return (text.toLowerCase().match(/[a-z0-9]+/g)) || [];
}

const round = (x, d) => {
  const f = 10 ** d;
  return Math.round(x * f) / f;
};

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

    // IDF, matching rank_bm25 BM25Okapi: log((N - n + 0.5) / (n + 0.5)), then
    // floor any negative IDF (a term in more than half the docs) to
    // epsilon * average_idf. Without this floor, a common query term scores
    // matching chunks negatively while chunks that lack it stay at 0, so the
    // unrelated chunks would rank first.
    this.idf = new Map();
    let idfSum = 0;
    const negatives = [];
    for (const [term, n] of df.entries()) {
      const idf = Math.log((this.corpusSize - n + 0.5) / (n + 0.5));
      this.idf.set(term, idf);
      idfSum += idf;
      if (idf < 0) negatives.push(term);
    }
    const epsilon = 0.25; // rank_bm25 BM25Okapi default
    const eps = this.idf.size ? epsilon * (idfSum / this.idf.size) : 0;
    for (const term of negatives) this.idf.set(term, eps);
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
    // Empty corpus or non-positive k (k <= 0 would make top empty -> top[0] undefined).
    if (!this.chunks.length || k <= 0) return [];
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

  // Expose the raw BM25 numbers for the "How the system sees your data" view.
  // Mirrors localrag/retriever.py Bm25Retriever.peek (same JSON shape).
  peek(query, k) {
    const n = this.chunks.length;
    const topTerms = [...this.idf.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 18)
      .map(([term, idf]) => ({ term, idf: round(idf, 3) }));

    let sample = null;
    if (n) {
      const c0 = this.chunks[0];
      const toks = tokenize(c0.text);
      sample = {
        source: c0.source,
        page_number: c0.page_number,
        text_preview: c0.text.slice(0, 240),
        num_tokens: toks.length,
        tokens: toks.slice(0, 48),
      };
    }

    // With no real chunks the placeholder corpus would inflate the stats, so
    // report zeros/empties to stay consistent with num_chunks === 0.
    const out = {
      retriever: "bm25",
      params: { k1: this.k1, b: this.b },
      num_chunks: n,
      vocabulary: n ? this.idf.size : 0,
      avg_doc_length: n ? round(this.avgdl, 2) : 0,
      top_terms: n ? topTerms : [],
      sample_chunk: sample,
    };

    query = (query || "").trim();
    if (query && n) {
      const qTokens = tokenize(query);
      const scores = this.scores(qTokens);
      const ranked = scores.map((_, i) => i).sort((a, b) => scores[b] - scores[a]).slice(0, k);
      const uniq = [...new Set(qTokens)];
      out.query = {
        text: query,
        tokens: qTokens,
        term_idf: Object.fromEntries(uniq.map((t) => [t, round(this.idf.get(t) ?? 0, 3)])),
        results: ranked.map((i) => ({
          source: this.chunks[i].source,
          page_number: this.chunks[i].page_number,
          score: round(scores[i], 4),
          text_preview: this.chunks[i].text.slice(0, 160),
          term_freqs: Object.fromEntries(uniq.map((t) => [t, this.docFreqs[i].get(t) || 0])),
        })),
      };
    }
    return out;
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
