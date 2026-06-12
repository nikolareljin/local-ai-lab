// Build, cache, and load the document index.
// Mirrors localrag/store.py: a JSON file of chunks (plus a (path, mtime, size)
// fingerprint) under the cache dir. BM25 only — no vectors in this C# port.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace LocalRag;

public record FileFingerprint(
    [property: JsonPropertyName("path")] string Path,
    [property: JsonPropertyName("mtime")] long Mtime,
    [property: JsonPropertyName("size")] long Size);

public record IndexFile(
    [property: JsonPropertyName("fingerprint")] List<FileFingerprint> Fingerprint,
    [property: JsonPropertyName("chunks")] List<ChunkRecord> Chunks);

// JSON shape matches Python's chunk dicts (snake_case keys).
public record ChunkRecord(
    [property: JsonPropertyName("source")] string Source,
    [property: JsonPropertyName("page_number")] int PageNumber,
    [property: JsonPropertyName("chunk_index")] int ChunkIndex,
    [property: JsonPropertyName("text")] string Text);

public static class Store
{
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    private static string IndexPath(Config config) => Path.Combine(config.CacheDir, "index.json");

    private static List<FileFingerprint> Fingerprint(List<string> files)
    {
        var fp = new List<FileFingerprint>();
        foreach (var p in files)
        {
            var info = new FileInfo(p);
            var mtime = ((DateTimeOffset)info.LastWriteTimeUtc).ToUnixTimeSeconds();
            fp.Add(new FileFingerprint(p, mtime, info.Length));
        }
        return fp;
    }

    private static bool FingerprintsEqual(List<FileFingerprint> a, List<FileFingerprint> b)
    {
        if (a.Count != b.Count)
        {
            return false;
        }
        for (var i = 0; i < a.Count; i++)
        {
            if (a[i].Path != b[i].Path || a[i].Mtime != b[i].Mtime || a[i].Size != b[i].Size)
            {
                return false;
            }
        }
        return true;
    }

    /// <summary>True if the cache is missing or the docs folder changed since last build.</summary>
    public static bool IsStale(Config config)
    {
        var path = IndexPath(config);
        if (!File.Exists(path))
        {
            return true;
        }
        IndexFile? data;
        try
        {
            data = JsonSerializer.Deserialize<IndexFile>(File.ReadAllText(path), JsonOpts);
        }
        catch
        {
            return true;
        }
        if (data is null)
        {
            return true;
        }
        return !FingerprintsEqual(data.Fingerprint, Fingerprint(Extract.DiscoverFiles(config.DocsDir)));
    }

    /// <summary>Extract + chunk every supported file. Returns (chunks, file_count).</summary>
    public static (List<Chunk> Chunks, int FileCount) BuildIndex(Config config)
    {
        var files = Extract.DiscoverFiles(config.DocsDir);
        var chunks = new List<Chunk>();
        foreach (var path in files)
        {
            chunks.AddRange(Chunking.ChunkPages(Extract.ExtractPages(path)));
        }

        Directory.CreateDirectory(config.CacheDir);
        var records = chunks
            .Select(c => new ChunkRecord(c.Source, c.PageNumber, c.ChunkIndex, c.Text))
            .ToList();
        var index = new IndexFile(Fingerprint(files), records);
        File.WriteAllText(IndexPath(config), JsonSerializer.Serialize(index, JsonOpts));
        return (chunks, files.Count);
    }

    public static List<Chunk> LoadChunks(Config config)
    {
        var data = JsonSerializer.Deserialize<IndexFile>(File.ReadAllText(IndexPath(config)), JsonOpts)
                   ?? throw new InvalidOperationException("Could not read the index file.");
        return data.Chunks
            .Select(c => new Chunk(c.Source, c.PageNumber, c.ChunkIndex, c.Text))
            .ToList();
    }
}
