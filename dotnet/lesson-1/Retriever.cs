// Retrieval engine: BM25 Okapi by hand (k1=1.5, b=0.75 — rank_bm25 defaults).
// Mirrors localrag/retriever.py's Bm25Retriever and build_retriever. Embeddings
// are out of scope for this C# port (see build_retriever's fallback notice).

using System.Text.RegularExpressions;

namespace LocalRag;

public interface IRetriever
{
    string Name { get; }
    List<Chunk> Search(string query, int k);
}

public partial class Bm25Retriever : IRetriever
{
    private const double K1 = 1.5;
    private const double B = 0.75;

    public string Name => "bm25";

    private readonly List<Chunk> _chunks;
    private readonly List<List<string>> _corpus;
    private readonly double[] _docLengths;
    private readonly double _avgDocLength;
    private readonly Dictionary<string, double> _idf;

    [GeneratedRegex("[a-z0-9]+")]
    private static partial Regex TokenRegex();

    public static List<string> Tokenize(string text) =>
        TokenRegex().Matches(text.ToLowerInvariant()).Select(m => m.Value).ToList();

    public Bm25Retriever(List<Chunk> chunks)
    {
        _chunks = chunks;
        _corpus = chunks.Count > 0
            ? chunks.Select(c => Tokenize(c.Text)).ToList()
            : new List<List<string>> { new() { "" } };

        _docLengths = _corpus.Select(d => (double)d.Count).ToArray();
        _avgDocLength = _docLengths.Length > 0 ? _docLengths.Average() : 0.0;

        // Document frequency per term, then the rank_bm25 Okapi IDF formula:
        // idf = log((N - df + 0.5) / (df + 0.5)), with negative IDFs (a term in
        // more than half the docs) floored to epsilon * average_idf. Without the
        // floor, a common query term scores matching chunks negatively while
        // chunks that lack it stay at 0, so unrelated chunks would rank first.
        var df = new Dictionary<string, int>();
        foreach (var doc in _corpus)
        {
            foreach (var term in doc.Distinct())
            {
                df[term] = df.GetValueOrDefault(term) + 1;
            }
        }
        var n = _corpus.Count;
        _idf = new Dictionary<string, double>(df.Count);
        var negatives = new List<string>();
        var idfSum = 0.0;
        foreach (var (term, freq) in df)
        {
            var idf = Math.Log((n - freq + 0.5) / (freq + 0.5));
            _idf[term] = idf;
            idfSum += idf;
            if (idf < 0) negatives.Add(term);
        }
        const double epsilon = 0.25; // rank_bm25 BM25Okapi default
        var eps = _idf.Count > 0 ? epsilon * (idfSum / _idf.Count) : 0.0;
        foreach (var term in negatives) _idf[term] = eps;
    }

    private double[] GetScores(List<string> query)
    {
        var scores = new double[_corpus.Count];
        for (var i = 0; i < _corpus.Count; i++)
        {
            var doc = _corpus[i];
            var freqs = new Dictionary<string, int>();
            foreach (var term in doc)
            {
                freqs[term] = freqs.GetValueOrDefault(term) + 1;
            }
            var dl = _docLengths[i];
            double score = 0.0;
            foreach (var term in query)
            {
                if (!freqs.TryGetValue(term, out var tf) || !_idf.TryGetValue(term, out var idf))
                {
                    continue;
                }
                var denom = tf + K1 * (1 - B + B * dl / _avgDocLength);
                score += idf * (tf * (K1 + 1)) / denom;
            }
            scores[i] = score;
        }
        return scores;
    }

    public List<Chunk> Search(string query, int k)
    {
        if (_chunks.Count == 0)
        {
            return new List<Chunk>();
        }
        var scores = GetScores(Tokenize(query));
        // Stable descending sort by score (mirrors Python's sorted by key, reverse).
        var ranked = Enumerable.Range(0, _chunks.Count)
            .OrderByDescending(i => scores[i])
            .ToList();

        var top = ranked.Take(k).ToList();
        var best = scores[top[0]];
        if (best <= 0)
        {
            return top.Select(i => _chunks[i]).ToList();
        }
        return top.Where(i => scores[i] > 0).Select(i => _chunks[i]).ToList();
    }

    private static string Truncate(string s, int n) => s.Length <= n ? s : s.Substring(0, n);

    // Expose the raw BM25 numbers for the "How the system sees your data" view.
    // Mirrors localrag/retriever.py Bm25Retriever.peek (same JSON shape). Keys are
    // written in exact snake_case so they serialize verbatim (jsonOpts sets no
    // naming policy).
    public object Peek(string? query, int k)
    {
        var n = _corpus.Count;
        var topTerms = _idf.OrderByDescending(kv => kv.Value).Take(18)
            .Select(kv => new { term = kv.Key, idf = Math.Round(kv.Value, 3) })
            .ToList();

        object? sample = null;
        if (_chunks.Count > 0)
        {
            var c0 = _chunks[0];
            var toks = Tokenize(c0.Text);
            sample = new
            {
                source = c0.Source,
                page_number = c0.PageNumber,
                text_preview = Truncate(c0.Text, 240),
                num_tokens = toks.Count,
                tokens = toks.Take(48).ToList(),
            };
        }

        var outDict = new Dictionary<string, object?>
        {
            ["retriever"] = "bm25",
            ["params"] = new { k1 = K1, b = B },
            ["num_chunks"] = n,
            ["vocabulary"] = _idf.Count,
            ["avg_doc_length"] = Math.Round(_avgDocLength, 2),
            ["top_terms"] = topTerms,
            ["sample_chunk"] = sample,
        };

        query = (query ?? string.Empty).Trim();
        if (query.Length > 0 && _chunks.Count > 0)
        {
            var qTokens = Tokenize(query);
            var uniq = qTokens.Distinct().ToList();
            var scores = GetScores(qTokens);
            var ranked = Enumerable.Range(0, n).OrderByDescending(i => scores[i]).Take(k).ToList();
            var results = ranked.Select(i =>
            {
                var freqs = new Dictionary<string, int>();
                foreach (var t in _corpus[i]) freqs[t] = freqs.GetValueOrDefault(t) + 1;
                return new
                {
                    source = _chunks[i].Source,
                    page_number = _chunks[i].PageNumber,
                    score = Math.Round(scores[i], 4),
                    text_preview = Truncate(_chunks[i].Text, 160),
                    term_freqs = uniq.ToDictionary(t => t, t => freqs.GetValueOrDefault(t)),
                };
            }).ToList();
            outDict["query"] = new
            {
                text = query,
                tokens = qTokens,
                term_idf = uniq.ToDictionary(t => t, t => Math.Round(_idf.GetValueOrDefault(t, 0.0), 3)),
                results,
            };
        }
        return outDict;
    }
}

public static class RetrieverFactory
{
    /// <summary>Pick a retriever from config. Embeddings fall back to BM25 in this port.</summary>
    public static IRetriever BuildRetriever(List<Chunk> chunks, Config config)
    {
        if (config.Retriever == "embeddings")
        {
            Console.WriteLine("[localrag] Embeddings are not ported in C# yet. Falling back to BM25.");
        }
        return new Bm25Retriever(chunks);
    }
}
