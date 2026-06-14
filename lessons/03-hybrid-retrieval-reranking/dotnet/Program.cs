// Lesson 3 - hybrid retrieval demo (C# / .NET).
//
// BM25 (lexical) + a semantic stand-in, fused with Reciprocal Rank Fusion (RRF).
// Dependency-free and offline. The same compact BM25 and synonym-expanded
// "semantic" score are implemented identically in the Python and Node ports, so
// all three produce the same rankings.
//
// Run:  dotnet run
//
// PRODUCTION (see the lesson README, "From demo to production"):
// - replace the semantic stand-in with real sentence embeddings,
// - add a cross-encoder reranker over the fused top-k.

using System.Text.RegularExpressions;

const double K1 = 1.5;
const double B = 0.75;
const int RrfK = 60;

// Kept identical across the Python, Node and .NET ports.
var synonyms = new Dictionary<string, string[]>
{
    ["turn"] = new[] { "power", "start", "startup", "boot" },
    ["on"] = new[] { "up" },
    ["wont"] = new[] { "fail", "fails", "cannot", "dead" },
    ["broken"] = new[] { "fail", "fails", "dead" },
};

var dataDir = FindDataDir();
var docs = Directory.GetFiles(dataDir, "*.md")
    .Select(Path.GetFileName)
    .OrderBy(n => n, StringComparer.Ordinal)
    .Select(name => new Doc(name!, Tokenize(File.ReadAllText(Path.Combine(dataDir, name!)))))
    .ToList();

foreach (var query in new[] { "error E_4096", "broken gadget" })
{
    var q = Tokenize(query);
    var lexical = Rank(docs, Bm25Scores(q, docs));
    var semantic = Rank(docs, SemanticScores(q, docs));
    var fused = Rrf(new[] { lexical, semantic });

    Console.WriteLine($"\nQuery: \"{query}\"");
    Console.WriteLine($"  BM25 (lexical):   {Fmt(lexical)}");
    Console.WriteLine($"  Semantic (stand): {Fmt(semantic)}");
    Console.WriteLine($"  Hybrid (RRF):     {Fmt(fused)}");
}

static List<string> Tokenize(string text) =>
    Regex.Matches(text.ToLowerInvariant(), "[a-z0-9_]+").Select(m => m.Value).ToList();

// --- Lexical arm: a compact BM25 (no external library) ----------------------
List<double> Bm25Scores(List<string> queryTokens, List<Doc> corpus)
{
    int n = corpus.Count;
    double avgdl = corpus.Average(d => d.Tokens.Count);
    var df = new Dictionary<string, int>();
    foreach (var d in corpus)
        foreach (var t in d.Tokens.Distinct())
            df[t] = df.GetValueOrDefault(t) + 1;

    return corpus.Select(d =>
    {
        int dl = d.Tokens.Count;
        double score = 0;
        foreach (var t in queryTokens)
        {
            if (!df.TryGetValue(t, out int dft)) continue;
            double idf = Math.Log(1 + (n - dft + 0.5) / (dft + 0.5));
            int tf = d.Tokens.Count(x => x == t);
            score += idf * (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * dl / avgdl));
        }
        return score;
    }).ToList();
}

// --- Semantic stand-in: synonym-expanded overlap (no model needed) ----------
List<double> SemanticScores(List<string> queryTokens, List<Doc> corpus)
{
    var q = new HashSet<string>(queryTokens);
    foreach (var t in q.ToList())
        if (synonyms.TryGetValue(t, out var syns))
            foreach (var s in syns) q.Add(s);

    return corpus.Select(d =>
    {
        var toks = new HashSet<string>(d.Tokens);
        int overlap = q.Count(toks.Contains);
        return (double)overlap / Math.Max(q.Count, 1);
    }).ToList();
}

// Drop zero-score (unmatched) docs so an arm that finds nothing contributes
// nothing to RRF. Deterministic: score desc, then name asc.
static List<string> Rank(List<Doc> corpus, List<double> scores) =>
    corpus.Select((d, i) => (d.Name, Score: scores[i]))
        .Where(x => x.Score > 0)
        .OrderByDescending(x => x.Score)
        .ThenBy(x => x.Name, StringComparer.Ordinal)
        .Select(x => x.Name)
        .ToList();

static List<string> Rrf(IEnumerable<List<string>> rankings)
{
    var fused = new Dictionary<string, double>();
    foreach (var ranking in rankings)
        for (int pos = 0; pos < ranking.Count; pos++)
            fused[ranking[pos]] = fused.GetValueOrDefault(ranking[pos]) + 1.0 / (RrfK + pos + 1);

    return fused.OrderByDescending(kv => kv.Value)
        .ThenBy(kv => kv.Key, StringComparer.Ordinal)
        .Select(kv => kv.Key)
        .ToList();
}

static string Fmt(List<string> names) => "[" + string.Join(", ", names.Select(s => $"'{s}'")) + "]";

// Walk up from the executable and the working directory to find the shared data/ folder.
static string FindDataDir()
{
    foreach (var start in new[] { AppContext.BaseDirectory, Directory.GetCurrentDirectory() })
    {
        var dir = new DirectoryInfo(start);
        while (dir != null)
        {
            var candidate = Path.Combine(dir.FullName, "data", "error_codes.md");
            if (File.Exists(candidate)) return Path.Combine(dir.FullName, "data");
            dir = dir.Parent;
        }
    }
    throw new DirectoryNotFoundException("Could not locate the lesson 'data/' directory.");
}

record Doc(string Name, List<string> Tokens);
