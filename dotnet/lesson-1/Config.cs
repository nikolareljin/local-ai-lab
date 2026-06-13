// Configuration loaded from environment / repo-root .env. No hard-coded paths.
// Mirrors localrag/config.py field-for-field.

namespace LocalRag;

public record Config(
    string Provider,
    string Retriever,
    string EmbedProvider,
    string DocsDir,
    string CacheDir,
    int TopK,
    // Social / course links surfaced in the web UI
    string LinkedinUrl,
    string GithubUrl,
    string TutorialUrl,
    // Base URL of the docs site (trailing slash). Override (e.g.
    // http://localhost:8000/) to point Troubleshooting links at a LOCAL copy.
    string DocsBaseUrl,
    // Provider settings
    string ClaudeBin,
    string OllamaUrl,
    string OllamaModel,
    string OllamaEmbedModel,
    string GeminiApiKey,
    string GeminiModel,
    string GeminiEmbedModel,
    string OpenaiApiKey,
    string OpenaiBaseUrl,
    string OpenaiModel,
    string OpenaiEmbedModel)
{
    /// <summary>
    /// Walk up from the running binary to find the repo root: the first parent
    /// directory that contains both a "documents" folder and a "run" file.
    /// </summary>
    public static string FindRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var hasDocs = Directory.Exists(Path.Combine(dir.FullName, "documents"));
            var hasRun = File.Exists(Path.Combine(dir.FullName, "run"));
            if (hasDocs && hasRun)
            {
                return dir.FullName;
            }
            dir = dir.Parent;
        }
        // Fallback: the project sits at <repoRoot>/dotnet/lesson-1, so from the
        // build output (bin/Release/net8.0) the repo root is four levels up.
        var guess = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
        return guess;
    }

    /// <summary>Tiny hand-rolled .env line parser. Does not override real env vars.</summary>
    private static void LoadDotEnv(string root)
    {
        var path = Path.Combine(root, ".env");
        if (!File.Exists(path))
        {
            return;
        }
        foreach (var raw in File.ReadAllLines(path))
        {
            var line = raw.Trim();
            if (line.Length == 0 || line.StartsWith('#'))
            {
                continue;
            }
            if (line.StartsWith("export "))
            {
                line = line["export ".Length..].TrimStart();
            }
            var eq = line.IndexOf('=');
            if (eq <= 0)
            {
                continue;
            }
            var key = line[..eq].Trim();
            var value = line[(eq + 1)..].Trim();
            if (value.Length >= 2 &&
                ((value[0] == '"' && value[^1] == '"') || (value[0] == '\'' && value[^1] == '\'')))
            {
                value = value[1..^1];
            }
            if (Environment.GetEnvironmentVariable(key) is null)
            {
                Environment.SetEnvironmentVariable(key, value);
            }
        }
    }

    private static string Env(string name, string fallback) =>
        Environment.GetEnvironmentVariable(name) is { Length: > 0 } v ? v : fallback;

    public static Config Load()
    {
        var root = FindRepoRoot();
        LoadDotEnv(root);

        var docsDir = Env("RAG_DOCS_DIR", "documents");
        if (!Path.IsPathRooted(docsDir))
        {
            docsDir = Path.Combine(root, docsDir);
        }

        // IMPORTANT: dotnet uses its own cache subdir so it never clobbers Python's.
        var cacheDir = Path.Combine(root, ".localrag", "dotnet");

        return new Config(
            Provider: Env("RAG_PROVIDER", "claude").ToLowerInvariant(),
            Retriever: Env("RAG_RETRIEVER", "bm25").ToLowerInvariant(),
            EmbedProvider: Env("RAG_EMBED_PROVIDER", "ollama").ToLowerInvariant(),
            DocsDir: docsDir,
            CacheDir: cacheDir,
            TopK: int.TryParse(Env("RAG_TOP_K", "5"), out var k) && k > 0 ? k : 5,
            LinkedinUrl: Env("LINKEDIN_URL", "https://www.linkedin.com/in/nikolareljin"),
            GithubUrl: Env("GITHUB_URL", "https://github.com/nikolareljin/local-ai-lab"),
            TutorialUrl: Env("TUTORIAL_URL", "https://nikolareljin.github.io/local-ai-lab/"),
            DocsBaseUrl: Env("DOCS_BASE_URL", "https://nikolareljin.github.io/local-ai-lab/").TrimEnd('/') + "/",
            ClaudeBin: Env("CLAUDE_BIN", "claude"),
            OllamaUrl: Env("OLLAMA_URL", "http://localhost:11434").TrimEnd('/'),
            OllamaModel: Env("OLLAMA_MODEL", "llama3.1:8b"),
            OllamaEmbedModel: Env("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            GeminiApiKey: Env("GEMINI_API_KEY", ""),
            GeminiModel: Env("GEMINI_MODEL", "gemini-2.5-flash"),
            GeminiEmbedModel: Env("GEMINI_EMBED_MODEL", "text-embedding-004"),
            OpenaiApiKey: Env("OPENAI_API_KEY", ""),
            OpenaiBaseUrl: Env("OPENAI_BASE_URL", "https://api.openai.com/v1").TrimEnd('/'),
            OpenaiModel: Env("OPENAI_MODEL", "gpt-4o-mini"),
            OpenaiEmbedModel: Env("OPENAI_EMBED_MODEL", "text-embedding-3-small"));
    }
}
