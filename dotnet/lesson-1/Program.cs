// Command-line + web entry point. Mirrors localrag/__main__.py and localrag/web.py.
//   index [--reindex]
//   ask [question...] [--reindex]   (REPL if no question)
//   web [--host H] [--port P]

using System.Text.Json;
using LocalRag;
using LocalRag.Providers;

var (command, rest) = (args.Length > 0 ? args[0] : "", args.Skip(1).ToArray());

// --- Parse shared overrides (--provider/--retriever/--k) and flags out of rest. ---
string? providerOverride = null, retrieverOverride = null;
int? kOverride = null;
string host = "127.0.0.1";
int port = 5000;
bool reindex = false;
var positional = new List<string>();

for (var i = 0; i < rest.Length; i++)
{
    var a = rest[i];
    string? Next() => i + 1 < rest.Length ? rest[++i] : null;
    switch (a)
    {
        case "--provider": providerOverride = Next()?.ToLowerInvariant(); break;
        case "--retriever": retrieverOverride = Next()?.ToLowerInvariant(); break;
        case "--k": if (int.TryParse(Next(), out var kv)) kOverride = kv; break;
        case "--host": host = Next() ?? host; break;
        case "--port": if (int.TryParse(Next(), out var pv)) port = pv; break;
        case "--reindex": reindex = true; break;
        default: positional.Add(a); break;
    }
}

var config = Config.Load() with { };
if (providerOverride is { Length: > 0 }) config = config with { Provider = providerOverride };
if (retrieverOverride is { Length: > 0 }) config = config with { Retriever = retrieverOverride };
if (kOverride is { } kk && kk > 0) config = config with { TopK = kk };

List<Chunk> EnsureIndex(bool force)
{
    if (force || Store.IsStale(config))
    {
        var (chunks, nFiles) = Store.BuildIndex(config);
        Console.WriteLine($"[localrag] Indexed {nFiles} file(s) into {chunks.Count} chunk(s).");
        return chunks;
    }
    return Store.LoadChunks(config);
}

void PrintAnswer(string question, IRetriever retriever)
{
    var hits = retriever.Search(question, config.TopK);
    var provider = ProviderFactory.GetProvider(config.Provider, config);
    var answer = provider.Chat(Prompts.SystemPrompt, Prompts.BuildUserPrompt(question, hits));

    Console.WriteLine("\n" + answer.Trim() + "\n");
    if (hits.Count > 0)
    {
        Console.WriteLine("Sources: " + string.Join(", ", Engine.DedupSources(hits)));
    }
    else
    {
        Console.WriteLine("Sources: (none — nothing relevant found in your documents)");
    }
}

switch (command)
{
    case "index":
        EnsureIndex(reindex);
        return 0;

    case "ask":
    {
        var chunks = EnsureIndex(reindex);
        var retriever = RetrieverFactory.BuildRetriever(chunks, config);
        Console.WriteLine($"[localrag] provider={config.Provider} retriever={retriever.Name}");

        if (positional.Count > 0)
        {
            PrintAnswer(string.Join(" ", positional), retriever);
            return 0;
        }

        Console.WriteLine("Ask a question about your documents (Ctrl-D or 'exit' to quit).");
        while (true)
        {
            Console.Write("\n> ");
            var line = Console.ReadLine();
            if (line is null) { Console.WriteLine(); break; }
            var question = line.Trim();
            if (question.Length == 0) continue;
            if (question.ToLowerInvariant() is "exit" or "quit") break;
            try { PrintAnswer(question, retriever); }
            catch (Exception ex) { Console.WriteLine($"[localrag] Error: {ex.Message}"); }
        }
        return 0;
    }

    case "":
    case "web":
        RunWeb(config, host, port);
        return 0;

    default:
        Console.Error.WriteLine($"Unknown command '{command}'. Use: index | ask | web.");
        return 2;
}

// --- Web UI (Minimal API), mirroring localrag/web.py endpoints. ---
static void RunWeb(Config baseConfig, string host, int port)
{
    Directory.CreateDirectory(baseConfig.DocsDir);

    var builder = WebApplication.CreateBuilder();
    builder.WebHost.UseUrls($"http://{host}:{port}");
    builder.WebHost.ConfigureKestrel(o =>
    {
        // Match the 64 MB upload cap; Kestrel's default request-body limit
        // (~28.6 MB) would otherwise reject larger uploads before the form reader.
        o.Limits.MaxRequestBodySize = 64L * 1024 * 1024;
    });
    builder.Services.Configure<Microsoft.AspNetCore.Http.Features.FormOptions>(o =>
    {
        o.MultipartBodyLengthLimit = 64L * 1024 * 1024; // 64 MB upload cap
    });
    var app = builder.Build();

    var htmlPath = Path.Combine(AppContext.BaseDirectory, "wwwroot", "index.html");
    var jsonOpts = new JsonSerializerOptions
    {
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    List<string> ListFiles(Config cfg) =>
        Extract.DiscoverFiles(cfg.DocsDir).Select(Path.GetFileName).Select(n => n!).ToList();

    app.MapGet("/", () => Results.Content(File.ReadAllText(htmlPath), "text/html"));

    app.MapGet("/api/status", () => Results.Json(new
    {
        provider = baseConfig.Provider,
        retriever = baseConfig.Retriever,
        docs_dir = baseConfig.DocsDir,
        files = ListFiles(baseConfig),
        supported = Extract.SupportedExts.OrderBy(e => e, StringComparer.Ordinal).ToList(),
        links = new
        {
            linkedin = baseConfig.LinkedinUrl,
            github = baseConfig.GithubUrl,
            tutorial = baseConfig.TutorialUrl,
            troubleshooting = baseConfig.DocsBaseUrl + "troubleshooting.html",
        },
    }, jsonOpts));

    app.MapPost("/api/upload", async (HttpRequest request) =>
    {
        var saved = new List<string>();
        var skipped = new List<string>();
        if (request.HasFormContentType)
        {
            var form = await request.ReadFormAsync();
            foreach (var f in form.Files.GetFiles("files"))
            {
                if (string.IsNullOrEmpty(f.FileName)) continue;
                var name = SecureFilename(f.FileName);
                if (!Extract.SupportedExts.Contains(Path.GetExtension(name)))
                {
                    skipped.Add(f.FileName);
                    continue;
                }
                var dest = Path.Combine(baseConfig.DocsDir, name);
                await using var fs = File.Create(dest);
                await f.CopyToAsync(fs);
                saved.Add(name);
            }
        }
        var (chunks, nFiles) = Engine.RefreshIndex(baseConfig);
        return Results.Json(new
        {
            saved,
            skipped,
            files = ListFiles(baseConfig),
            indexed_files = nFiles,
            chunks = chunks.Count,
        }, jsonOpts);
    });

    app.MapPost("/api/ask", async (HttpRequest request) =>
    {
        Dictionary<string, JsonElement> data;
        try
        {
            data = await JsonSerializer.DeserializeAsync<Dictionary<string, JsonElement>>(request.Body)
                   ?? new();
        }
        catch (JsonException)
        {
            // Empty or malformed JSON -> behave like Flask's get_json(silent=True).
            data = new();
        }
        var question = data.TryGetValue("question", out var q) && q.ValueKind == JsonValueKind.String
            ? (q.GetString() ?? "").Trim() : "";
        if (question.Length == 0)
        {
            return Results.Json(new { error = "Please enter a question." }, jsonOpts, statusCode: 400);
        }

        var cfg = baseConfig;
        if (data.TryGetValue("provider", out var pe) && pe.ValueKind == JsonValueKind.String && pe.GetString() is { Length: > 0 } pv)
            cfg = cfg with { Provider = pv.ToLowerInvariant() };
        if (data.TryGetValue("retriever", out var re) && re.ValueKind == JsonValueKind.String && re.GetString() is { Length: > 0 } rv)
            cfg = cfg with { Retriever = rv.ToLowerInvariant() };

        try
        {
            var result = Engine.AnswerQuestion(cfg, question);
            return Results.Json(result, jsonOpts);
        }
        catch (Exception ex)
        {
            return Results.Json(new { error = ex.Message }, jsonOpts, statusCode: 500);
        }
    });

    // The raw numbers behind the index — "How the system sees your data".
    app.MapGet("/api/peek", (string? q) =>
    {
        try
        {
            var retriever = Engine.GetRetriever(baseConfig);
            if (retriever is not Bm25Retriever bm)
            {
                return Results.Json(
                    new { error = $"The '{retriever.Name}' retriever has no peek view yet — switch to BM25." },
                    jsonOpts, statusCode: 400);
            }
            return Results.Json(bm.Peek(q, baseConfig.TopK), jsonOpts);
        }
        catch (Exception ex)
        {
            return Results.Json(new { error = ex.Message }, jsonOpts, statusCode: 500);
        }
    });

    Console.WriteLine($"[localrag] Web UI on http://{host}:{port}  (Ctrl-C to stop)");
    app.Run();
}

// Minimal werkzeug.secure_filename equivalent: keep the basename, allow
// [A-Za-z0-9._-], collapse the rest to underscores.
static string SecureFilename(string filename)
{
    var name = Path.GetFileName(filename.Replace('\\', '/'));
    var chars = name.Select(c => char.IsAsciiLetterOrDigit(c) || c is '.' or '_' or '-' ? c : '_').ToArray();
    var cleaned = new string(chars).Trim('.', '_', '-');
    return cleaned.Length > 0 ? cleaned : "file";
}
