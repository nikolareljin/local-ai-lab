// Shared query engine used by the CLI and web UI.
// Mirrors localrag/engine.py: a cached retriever rebuilt when docs change or the
// retriever type is switched; thread-safe for concurrent web requests.

using System.Text.Json.Serialization;
using LocalRag.Providers;

namespace LocalRag;

// snake_case JSON keys to match the Python web API and the HTML's fetch code.
public record AnswerResult(
    [property: JsonPropertyName("answer")] string Answer,
    [property: JsonPropertyName("sources")] List<string> Sources,
    [property: JsonPropertyName("provider")] string Provider,
    [property: JsonPropertyName("retriever")] string Retriever,
    [property: JsonPropertyName("num_hits")] int NumHits);

public static class Engine
{
    private static readonly object Lock = new();
    private static IRetriever? _retriever;
    private static string? _key;

    /// <summary>Force a rebuild of the on-disk index and invalidate the retriever cache.</summary>
    public static (List<Chunk> Chunks, int FileCount) RefreshIndex(Config config)
    {
        lock (Lock)
        {
            var (chunks, nFiles) = Store.BuildIndex(config);
            _retriever = null;
            _key = null;
            return (chunks, nFiles);
        }
    }

    /// <summary>Return a retriever for the current docs, rebuilding only when needed.</summary>
    public static IRetriever GetRetriever(Config config)
    {
        lock (Lock)
        {
            if (Store.IsStale(config))
            {
                Store.BuildIndex(config);
                _retriever = null;
            }
            if (_retriever is null || _key != config.Retriever)
            {
                var chunks = Store.LoadChunks(config);
                _retriever = RetrieverFactory.BuildRetriever(chunks, config);
                _key = config.Retriever;
            }
            return _retriever;
        }
    }

    public static List<string> DedupSources(List<Chunk> hits)
    {
        var seen = new List<string>();
        foreach (var h in hits)
        {
            var tag = $"{h.Source}:{h.PageNumber}";
            if (!seen.Contains(tag))
            {
                seen.Add(tag);
            }
        }
        return seen;
    }

    /// <summary>Retrieve grounding context, call the provider, and return a result.</summary>
    public static AnswerResult AnswerQuestion(Config config, string question)
    {
        var retriever = GetRetriever(config);
        var hits = retriever.Search(question, config.TopK);
        var provider = ProviderFactory.GetProvider(config.Provider, config);
        var answer = provider.Chat(Prompts.SystemPrompt, Prompts.BuildUserPrompt(question, hits));
        return new AnswerResult(
            Answer: answer.Trim(),
            Sources: DedupSources(hits),
            Provider: config.Provider,
            Retriever: retriever.Name,
            NumHits: hits.Count);
    }
}
