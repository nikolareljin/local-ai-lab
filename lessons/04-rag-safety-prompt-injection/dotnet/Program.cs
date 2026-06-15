// Lesson 4 - RAG safety & prompt injection demo (C# / .NET).
//
// Retrieved documents are untrusted input. A poisoned document can carry an
// instruction a naive pipeline will obey. The same query runs through two
// pipelines over a tiny corpus that contains poisoned support tickets:
//
//   - Undefended: retrieved text is pasted in as-is, so the model obeys the
//     injected instruction and emits the attacker's scripted payload.
//   - Defended: quarantine (drop instruction-like docs), isolate (treat
//     retrieved text as data), and an output filter (block leaked secrets).
//
// Dependency-free and offline. The detection patterns and the model stand-in are
// implemented identically in the Python and Node ports, so all three produce the
// same output.
//
// Run:  dotnet run

using System.Text.RegularExpressions;

const int TopK = 3;

// Kept identical across the Python, Node and .NET ports.
var stopwords = new HashSet<string>
{
    "a", "an", "the", "to", "of", "do", "i", "in", "on", "is", "are",
    "and", "my", "your", "you", "they", "their", "it", "we",
};

// Ordered (label, pattern) rules that flag a chunk as "trying to give instructions".
var injectionPatterns = new (string Label, Regex Pattern)[]
{
    ("instruction override", new Regex(@"ignore\s+(all\s+|the\s+)?(previous\s+|above\s+)?(instructions|documents)")),
    ("disregard context", new Regex(@"disregard")),
    ("role injection", new Regex(@"system\s*:")),
    ("forced reply", new Regex(@"reply only with")),
    ("data exfiltration", new Regex(@"https?://exfil|api key|session token|fake-api-key")),
};

var exfilPattern = new Regex(@"https?://exfil|api key|session token|fake-api-key");
var payloadPattern = new Regex("reply only with:\\s*\"([^\"]+)\"", RegexOptions.IgnoreCase);

const string NoAnswer = "I could not find a trustworthy answer in the documents.";
const string OutputBlocked = "[blocked by output filter: the answer tried to leak a secret]";

var dataDir = FindDataDir();
var docs = Directory.GetFiles(dataDir, "*.md")
    .Select(Path.GetFileName)
    .OrderBy(n => n, StringComparer.Ordinal)
    .Select(name => new Doc(name!, File.ReadAllText(Path.Combine(dataDir, name!))))
    .ToList();

foreach (var query in new[] { "how long do refunds take to arrive", "i cannot log in to my account" })
{
    var undefended = Assess(query, docs, quarantine: false, isolate: false, outputFilter: false);
    var defended = Assess(query, docs, quarantine: true, isolate: true, outputFilter: true);
    Console.WriteLine($"\nQuery: \"{query}\"");
    Console.WriteLine($"  Retrieved:  {Fmt(undefended.Retrieved)}");
    Console.WriteLine($"  Undefended: {undefended.Text}");
    Console.WriteLine($"  Defended:   {defended.Text}");
}

List<string> Tokenize(string text) =>
    Regex.Matches(text.ToLowerInvariant(), "[a-z0-9_]+").Select(m => m.Value).ToList();

// --- Retrieval: distinct-term overlap, minus stopwords (deterministic) -------
List<Doc> Retrieve(string query, List<Doc> corpus, int topK)
{
    var q = Tokenize(query).Where(t => !stopwords.Contains(t)).ToHashSet();
    return corpus
        .Select(d => (Doc: d, Score: q.Count(d.TokenSet.Contains)))
        .Where(x => x.Score > 0)
        .OrderByDescending(x => x.Score)
        .ThenBy(x => x.Doc.Name, StringComparer.Ordinal)
        .Take(topK)
        .Select(x => x.Doc)
        .ToList();
}

// --- Detection: does this chunk try to issue instructions? -------------------
List<string> MatchedPatterns(string text)
{
    var low = text.ToLowerInvariant();
    return injectionPatterns.Where(p => p.Pattern.IsMatch(low)).Select(p => p.Label).ToList();
}

string ExtractPayload(string text)
{
    var m = payloadPattern.Match(text);
    return m.Success ? m.Groups[1].Value : "[the model followed an injected instruction]";
}

bool ContainsExfil(string text) => exfilPattern.IsMatch(text.ToLowerInvariant());

string LegitAnswer(List<Doc> corpus, Dictionary<string, List<string>> flagged)
{
    foreach (var d in corpus)
    {
        if (flagged[d.Name].Count > 0) continue;
        foreach (var raw in d.Raw.Split('\n'))
        {
            var line = raw.Trim();
            if (line.Length > 0 && !line.StartsWith("#")) return line;
        }
    }
    return NoAnswer;
}

// --- The two pipelines, parameterised by which defences are on ---------------
Result Assess(string query, List<Doc> corpus, bool quarantine, bool isolate, bool outputFilter)
{
    var retrieved = Retrieve(query, corpus, TopK);
    var flagged = retrieved.ToDictionary(d => d.Name, d => MatchedPatterns(d.Raw));

    List<Doc> effective = quarantine
        ? retrieved.Where(d => flagged[d.Name].Count == 0).ToList()
        : new List<Doc>(retrieved);

    string? obeyed = null;
    if (!isolate)
        foreach (var d in effective)
            if (flagged[d.Name].Count > 0)
            {
                obeyed = ExtractPayload(d.Raw);
                break;
            }

    var text = obeyed ?? LegitAnswer(effective, flagged);

    if (outputFilter && ContainsExfil(text))
        text = OutputBlocked;

    return new Result(text, retrieved.Select(d => d.Name).ToList());
}

static string Fmt(List<string> names) => "[" + string.Join(", ", names.Select(n => $"'{n}'")) + "]";

// Walk up from the executable and the working directory to find the shared data/ folder.
static string FindDataDir()
{
    foreach (var start in new[] { AppContext.BaseDirectory, Directory.GetCurrentDirectory() })
    {
        var dir = new DirectoryInfo(start);
        while (dir != null)
        {
            var candidate = Path.Combine(dir.FullName, "data", "refund_policy.md");
            if (File.Exists(candidate)) return Path.Combine(dir.FullName, "data");
            dir = dir.Parent;
        }
    }
    throw new DirectoryNotFoundException("Could not locate the lesson 'data/' directory.");
}

record Doc(string Name, string Raw)
{
    public HashSet<string> TokenSet { get; } =
        Regex.Matches(Raw.ToLowerInvariant(), "[a-z0-9_]+").Select(m => m.Value).ToHashSet();
}

record Result(string Text, List<string> Retrieved);
