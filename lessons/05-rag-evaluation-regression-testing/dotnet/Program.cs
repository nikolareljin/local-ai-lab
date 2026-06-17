// Lesson 5 - RAG evaluation & regression testing demo (C# / .NET).
//
// "Seems good" is not a metric. This demo turns the quality of a RAG pipeline
// into numbers you can track: a small golden set of questions (each with the
// document that should be retrieved and the keywords a correct answer must
// contain) scored on three axes - retrieval recall@k, groundedness, and answer
// correctness. A question PASSES only if all three clear their thresholds; the
// gate passes only if every question passes. We run two configs over the same
// golden set: a BASELINE that clears the gate, and a CANDIDATE - a
// reasonable-looking tweak (smaller top_k, an answer padded with an unsupported
// sentence) that silently regresses two of the numbers. The eval catches it.
//
// Dependency-free and offline. The retriever, answerer stand-in and metrics are
// implemented identically in the Python and Node ports, so all three produce the
// same output.
//
// Run:  dotnet run

using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

// Kept identical across the Python, Node and .NET ports.
var stopwords = new HashSet<string>
{
    "a", "an", "the", "to", "of", "do", "i", "in", "on", "is", "are",
    "and", "my", "your", "you", "they", "their", "it", "we",
};

// A hallucinated sentence the CANDIDATE answerer pads onto every answer. None of
// its content terms appear anywhere in the corpus, so groundedness drops.
const string Unsupported = "A complimentary gift card will be mailed separately.";

var dataDir = FindDataDir();
var docs = Directory.GetFiles(dataDir, "*.md")
    .Select(Path.GetFileName)
    .OrderBy(n => n, StringComparer.Ordinal)
    .Select(name => new Doc(name!, File.ReadAllText(Path.Combine(dataDir, name!))))
    .ToList();

var golden = JsonSerializer.Deserialize<GoldenSet>(
    File.ReadAllText(Path.Combine(dataDir, "golden.json")),
    new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;

var baseline = new Config("baseline", 3, false);
var candidate = new Config("candidate", 1, true);

var baseResult = Evaluate(golden, docs, baseline);
var candResult = Evaluate(golden, docs, candidate);
PrintReport(baseResult, baseline);
PrintReport(candResult, candidate);
PrintRegression(baseResult, candResult, golden.Thresholds.Groundedness);

List<string> Tokenize(string text) =>
    Regex.Matches(text.ToLowerInvariant(), "[a-z0-9_]+").Select(m => m.Value).ToList();

HashSet<string> Terms(string text) =>
    Tokenize(text).Where(t => !stopwords.Contains(t)).ToHashSet();

// --- Retrieval: distinct-term overlap, minus stopwords (deterministic) -------
List<Doc> Retrieve(string query, List<Doc> corpus, int topK)
{
    var q = Terms(query);
    return corpus
        .Select(d => (Doc: d, Score: q.Count(d.TokenSet.Contains)))
        .Where(x => x.Score > 0)
        .OrderByDescending(x => x.Score)
        .ThenBy(x => x.Doc.Name, StringComparer.Ordinal)
        .Take(topK)
        .Select(x => x.Doc)
        .ToList();
}

// --- Answerer: a deterministic, offline extractive stand-in ------------------
string FirstBodyLine(Doc doc)
{
    foreach (var raw in doc.Raw.Split('\n'))
    {
        var line = raw.Trim();
        if (line.Length > 0 && !line.StartsWith("#")) return line;
    }
    return "";
}

string Answer(List<Doc> retrieved, bool padUnsupported)
{
    if (retrieved.Count == 0) return "";
    var text = FirstBodyLine(retrieved[0]);
    if (padUnsupported) text = (text + " " + Unsupported).Trim();
    return text;
}

// --- The three metrics -------------------------------------------------------
double RecallAtK(List<string> goldDocs, List<Doc> retrieved)
{
    if (goldDocs.Count == 0) return 1.0;
    var names = retrieved.Select(d => d.Name).ToHashSet();
    var hit = goldDocs.Count(names.Contains);
    return (double)hit / goldDocs.Count;
}

double Groundedness(string answerText, List<Doc> retrieved)
{
    var a = Terms(answerText);
    if (a.Count == 0) return 1.0;
    var context = new HashSet<string>();
    foreach (var d in retrieved) context.UnionWith(Terms(d.Raw));
    return (double)a.Count(context.Contains) / a.Count;
}

double Correctness(string answerText, List<string> keywords)
{
    if (keywords.Count == 0) return 1.0;
    var toks = Tokenize(answerText).ToHashSet();
    var hit = keywords.Count(toks.Contains);
    return (double)hit / keywords.Count;
}

// --- One config over the whole golden set ------------------------------------
EvalResult Evaluate(GoldenSet g, List<Doc> corpus, Config config)
{
    var thr = g.Thresholds;
    if (g.Questions.Count == 0)
        throw new InvalidOperationException("golden set has no questions - add at least one to data/golden.json");
    var rows = g.Questions.Select(q =>
    {
        var retrieved = Retrieve(q.Text, corpus, config.TopK);
        var ans = Answer(retrieved, config.PadUnsupported);
        var recall = RecallAtK(q.GoldDocs, retrieved);
        var grounded = Groundedness(ans, retrieved);
        var correct = Correctness(ans, q.AnswerKeywords);
        var passed = recall >= 1.0 && grounded >= thr.Groundedness && correct >= thr.Correctness;
        return new Row(q.Id, recall, grounded, correct, passed);
    }).ToList();
    var n = rows.Count;
    var agg = new Aggregate(
        rows.Sum(r => r.Recall) / n,
        rows.Sum(r => r.Groundedness) / n,
        rows.Sum(r => r.Correctness) / n,
        rows.Count(r => r.Passed),
        n);
    return new EvalResult(config.Name, rows, agg, agg.PassCount == n);
}

// --- Reporting (byte-identical across the three ports) -----------------------
string Pct(double x) => x.ToString("F2");
string GateWord(bool passed) => passed ? "PASS" : "FAIL";
string Signed(double x) => (x >= 0 ? "+" : "-") + Math.Abs(x).ToString("F2");

void PrintReport(EvalResult result, Config config)
{
    var flags = $"top_k={config.TopK}, padding={(config.PadUnsupported ? "on" : "off")}";
    Console.WriteLine($"\nConfig: {result.ConfigName}  ({flags})");
    Console.WriteLine("  id               recall  grounded  correct  result");
    foreach (var r in result.Rows)
        Console.WriteLine(
            $"  {r.Id,-15}   {Pct(r.Recall)}      {Pct(r.Groundedness)}     {Pct(r.Correctness)}  {GateWord(r.Passed)}");
    var a = result.Aggregate;
    Console.WriteLine(
        $"  Aggregate: recall {Pct(a.MeanRecall)}  grounded {Pct(a.MeanGroundedness)}  correct {Pct(a.MeanCorrectness)}   {a.PassCount}/{a.Total} passed   GATE: {GateWord(result.GatePassed)}");
}

void PrintRegression(EvalResult baseRes, EvalResult candRes, double groundednessThreshold)
{
    var b = baseRes.Aggregate;
    var c = candRes.Aggregate;
    void Line(string label, double bv, double cv, string note = "") =>
        Console.WriteLine($"  {label,-18} {Pct(bv)} -> {Pct(cv)}   ({Signed(cv - bv)}){note}");
    Console.WriteLine("\nRegression vs baseline:");
    Line("mean recall:", b.MeanRecall, c.MeanRecall);
    var below = c.MeanGroundedness < groundednessThreshold
        ? $"   below threshold {Pct(groundednessThreshold)}" : "";
    Line("mean groundedness:", b.MeanGroundedness, c.MeanGroundedness, below);
    Line("mean correctness:", b.MeanCorrectness, c.MeanCorrectness);
    Console.WriteLine($"  {"gate:",-18} {GateWord(baseRes.GatePassed)} -> {GateWord(candRes.GatePassed)}");
}

// Walk up from the executable and the working directory to find the shared data/ folder.
static string FindDataDir()
{
    foreach (var start in new[] { AppContext.BaseDirectory, Directory.GetCurrentDirectory() })
    {
        var dir = new DirectoryInfo(start);
        while (dir != null)
        {
            var candidate = Path.Combine(dir.FullName, "data", "golden.json");
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

record Config(string Name, int TopK, bool PadUnsupported);
record Row(string Id, double Recall, double Groundedness, double Correctness, bool Passed);
record Aggregate(double MeanRecall, double MeanGroundedness, double MeanCorrectness, int PassCount, int Total);
record EvalResult(string ConfigName, List<Row> Rows, Aggregate Aggregate, bool GatePassed);

record GoldenSet(
    [property: JsonPropertyName("thresholds")] Thresholds Thresholds,
    [property: JsonPropertyName("questions")] List<Question> Questions);

record Thresholds(
    [property: JsonPropertyName("groundedness")] double Groundedness,
    [property: JsonPropertyName("correctness")] double Correctness);

record Question(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("question")] string Text,
    [property: JsonPropertyName("gold_docs")] List<string> GoldDocs,
    [property: JsonPropertyName("answer_keywords")] List<string> AnswerKeywords);
