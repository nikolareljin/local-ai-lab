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
        // idf = log((N - df + 0.5) / (df + 0.5)). (Can be negative on tiny corpora.)
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
        foreach (var (term, freq) in df)
        {
            _idf[term] = Math.Log((n - freq + 0.5) / (freq + 0.5));
        }
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
