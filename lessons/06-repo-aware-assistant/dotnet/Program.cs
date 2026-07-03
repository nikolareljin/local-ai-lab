// Lesson 6 - Repo-aware AI assistant demo (C# / .NET).
//
// A repo-aware assistant answers questions about one codebase - and only from
// what is in it. This demo builds a tiny, offline version: it INDEXes the repo
// into line-numbered passages (each carrying its path + line range, i.e. its
// citation), ANSWERs a question only from the retrieved passages (always cited,
// or "not found" when nothing clears a minimum score), and for a change request
// produces a PLAN-before-edit that changes no files.
//
// Dependency-free and offline. The index/retrieve/answer algorithm is identical
// to the Python and Node ports, so all three print byte-identical output.
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

// Point the assistant at your OWN repo with:  REPO_PATH=/path/to/repo
// (unset, it indexes the sample repo under data/repo). Vendored/build dirs and
// non-text files are skipped, so a real repo's index stays source and docs.
var ignoreDirs = new HashSet<string>
{
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    "bin", "obj", "target", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".idea",
};
var textExt = new HashSet<string>
{
    ".md", ".txt", ".rst", ".py", ".sh", ".js", ".mjs", ".ts", ".tsx", ".jsx",
    ".cs", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".rs", ".go",
    ".java", ".kt", ".rb", ".php", ".html", ".css", ".c", ".h", ".cpp", ".hpp",
    ".sql", ".xml",
};

var lessonDir = FindLessonDir();
var envRepo = Environment.GetEnvironmentVariable("REPO_PATH");
var repoDir = string.IsNullOrEmpty(envRepo) ? Path.Combine(lessonDir, "data", "repo") : Path.GetFullPath(envRepo);
var label = string.IsNullOrEmpty(envRepo) ? "data/repo" : repoDir;

var cfg = JsonSerializer.Deserialize<Config>(
    File.ReadAllText(Path.Combine(lessonDir, "data", "questions.json")),
    new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;

var (files, chunks) = BuildIndex(repoDir);

List<Question> questions;
if (args.Length > 0 && (args[0] == "ask" || args[0] == "plan"))
{
    var question = string.Join(" ", args.Skip(1)).Trim();
    if (question.Length == 0) { Console.WriteLine("usage: repo-assistant-demo [ask|plan] \"your question\""); return; }
    questions = new List<Question> { new(args[0], args[0] == "plan" ? "plan" : "locate", question) };
}
else
{
    questions = cfg.Questions;
}

Console.WriteLine($"Repo-aware assistant  -  indexed {files.Count} files, {chunks.Count} passages under {label}");
for (var i = 0; i < questions.Count; i++)
    PrintResponse(i + 1, questions[i], Respond(questions[i], files, chunks, cfg.TopK, cfg.MinScore), cfg.MinScore);

bool IsIndexable(string rel)
{
    var parts = rel.Split('/');
    for (var i = 0; i < parts.Length - 1; i++)
        if (ignoreDirs.Contains(parts[i]) || parts[i].StartsWith('.')) return false;
    return textExt.Contains(Path.GetExtension(parts[^1]).ToLowerInvariant());
}

List<string> Tokenize(string text) =>
    Regex.Matches(text.ToLowerInvariant(), "[a-z0-9_]+").Select(m => m.Value).ToList();

HashSet<string> Terms(string text) =>
    Tokenize(text).Where(t => !stopwords.Contains(t)).ToHashSet();

// Match Python str.splitlines(): split on line breaks, dropping the empty tail a
// trailing newline would otherwise produce.
List<string> SplitLines(string raw)
{
    var norm = raw.Replace("\r\n", "\n").Replace("\r", "\n");
    var parts = norm.Split('\n').ToList();
    if (parts.Count > 0 && parts[^1].Length == 0 && norm.EndsWith('\n')) parts.RemoveAt(parts.Count - 1);
    return parts;
}

// --- Index: split every repo file into line-numbered passages ----------------
(List<string>, List<Chunk>) BuildIndex(string dir)
{
    var acc = new List<string>();
    WalkDir(dir, dir, acc);   // prunes ignored/dot dirs during the walk
    var files = acc.Where(IsIndexable).OrderBy(p => p, StringComparer.Ordinal).ToList();
    var chunks = new List<Chunk>();
    foreach (var rel in files)
        chunks.AddRange(ChunkFile(rel, File.ReadAllText(Path.Combine(dir, rel)), Terms));
    return (files, chunks);
}

void WalkDir(string root, string current, List<string> acc)
{
    foreach (var sub in Directory.GetDirectories(current))
    {
        var name = Path.GetFileName(sub);
        if (ignoreDirs.Contains(name) || name.StartsWith('.')) continue;
        WalkDir(root, sub, acc);
    }
    foreach (var f in Directory.GetFiles(current))
        acc.Add(Path.GetRelativePath(root, f).Replace('\\', '/'));
}

List<Chunk> ChunkFile(string rel, string raw, Func<string, HashSet<string>> terms)
{
    var chunks = new List<Chunk>();
    var lines = SplitLines(raw);
    int? start = null;
    for (var i = 0; i < lines.Count; i++)
    {
        var blank = lines[i].Trim().Length == 0;
        if (!blank && start is null) start = i;
        else if (blank && start is not null) { chunks.Add(MakeChunk(rel, lines, start.Value, i - 1, terms)); start = null; }
    }
    if (start is not null) chunks.Add(MakeChunk(rel, lines, start.Value, lines.Count - 1, terms));
    return chunks;
}

static Chunk MakeChunk(string rel, List<string> lines, int first, int last, Func<string, HashSet<string>> terms)
{
    var body = lines.GetRange(first, last - first + 1);
    return new Chunk(rel, first + 1, last + 1, body[0].Trim(), terms(string.Join("\n", body)));
}

string Cite(Chunk c) => $"{c.Path}:{c.Start}-{c.End}";

// --- Retrieve: keyword overlap, deterministic order --------------------------
List<(int Score, Chunk Chunk)> Retrieve(string query, List<Chunk> chunks, int topK)
{
    var q = Terms(query);
    return chunks
        .Select(c => (Score: q.Count(c.Tokens.Contains), Chunk: c))
        .Where(x => x.Score > 0)
        .OrderByDescending(x => x.Score)
        .ThenBy(x => x.Chunk.Path, StringComparer.Ordinal)
        .ThenBy(x => x.Chunk.Start)
        .Take(topK)
        .ToList();
}

// --- Answer: only from retrieved passages, always cited, else "not found" ----
Response Answer(string query, List<Chunk> chunks, int topK, int minScore)
{
    var hits = Retrieve(query, chunks, topK);
    if (hits.Count == 0 || hits[0].Score < minScore)
        return new Response { Kind = "not_found", Best = hits.Count > 0 ? hits[0].Score : 0 };
    var (score, top) = hits[0];
    return new Response
    {
        Kind = "grounded",
        Score = score,
        Citation = Cite(top),
        Line = top.FirstLine,
        Sources = hits.Select(h => Cite(h.Chunk)).ToList(),
    };
}

// --- Plan-before-edit --------------------------------------------------------
Response Plan(string query, List<string> files, List<Chunk> chunks, int topK)
{
    var hits = Retrieve(query, chunks, topK);
    if (hits.Count == 0) return new Response { Kind = "not_found", Best = 0 };
    var top = hits[0].Chunk;
    var testsPath = files.FirstOrDefault(p => p.StartsWith("tests/"));
    return new Response
    {
        Kind = "plan",
        Relevant = hits.Select(h => Cite(h.Chunk)).ToList(),
        Citation = Cite(top),
        Line = top.FirstLine,
        Change = $"add the new code alongside {top.Path}, matching the pattern already there",
        Tests = testsPath ?? "add a test under tests/",
        Docs = files.Contains("README.md") ? "README.md" : "update the project docs",
    };
}

Response Respond(Question q, List<string> files, List<Chunk> chunks, int topK, int minScore) =>
    q.Kind == "plan" ? Plan(q.Text, files, chunks, topK) : Answer(q.Text, chunks, topK, minScore);

// --- Reporting (byte-identical across the three ports) -----------------------
void PrintResponse(int n, Question q, Response r, int minScore)
{
    var tag = q.Kind == "plan" ? "   [plan-before-edit]" : "";
    Console.WriteLine($"\nQ{n}  {q.Text}{tag}");
    if (r.Kind == "grounded")
    {
        Console.WriteLine("    GROUNDED  -  answered only from indexed repository lines");
        Console.WriteLine($"    {r.Citation}");
        Console.WriteLine($"      {r.Line}");
        Console.WriteLine($"    sources: {string.Join(" . ", r.Sources!)}");
    }
    else if (r.Kind == "plan")
    {
        Console.WriteLine("    PLAN  -  no files changed, approve before editing");
        Console.WriteLine($"    1. relevant files    {string.Join(" . ", r.Relevant!)}");
        Console.WriteLine($"    2. current behaviour  {r.Citation}  ->  {r.Line}");
        Console.WriteLine($"    3. minimal change     {r.Change}");
        Console.WriteLine($"    4. update tests       {r.Tests}");
        Console.WriteLine($"    5. update docs        {r.Docs}");
    }
    else
    {
        Console.WriteLine($"    NOT FOUND  -  best match scored {r.Best} (< min {minScore}), so the assistant abstains");
        Console.WriteLine("      no citation, no invented answer");
    }
}

// Walk up from the executable and the working directory to find the lesson dir
// (the one whose data/questions.json exists).
static string FindLessonDir()
{
    foreach (var start in new[] { AppContext.BaseDirectory, Directory.GetCurrentDirectory() })
    {
        var dir = new DirectoryInfo(start);
        while (dir != null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "data", "questions.json"))) return dir.FullName;
            dir = dir.Parent;
        }
    }
    throw new DirectoryNotFoundException("Could not locate the lesson 'data/' directory.");
}

record Chunk(string Path, int Start, int End, string FirstLine, HashSet<string> Tokens);

class Response
{
    public string Kind = "";
    public int Score;
    public int Best;
    public string? Citation;
    public string? Line;
    public string? Change;
    public string? Tests;
    public string? Docs;
    public List<string>? Sources;
    public List<string>? Relevant;
}

record Config(
    [property: JsonPropertyName("top_k")] int TopK,
    [property: JsonPropertyName("min_score")] int MinScore,
    [property: JsonPropertyName("questions")] List<Question> Questions);

record Question(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("question")] string Text);
