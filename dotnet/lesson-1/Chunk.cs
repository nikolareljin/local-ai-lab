// Split extracted pages into overlapping chunks.
// Ports localrag/chunk.py: _split_text and chunk_pages exactly.

namespace LocalRag;

public record Chunk(string Source, int PageNumber, int ChunkIndex, string Text);

public static class Chunking
{
    public static List<string> SplitText(string text, int size, int overlap)
    {
        // Normalize whitespace: split on any whitespace runs, join with single spaces.
        text = string.Join(" ", text.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
        if (text.Length <= size)
        {
            return text.Length > 0 ? new List<string> { text } : new List<string>();
        }

        var chunks = new List<string>();
        var start = 0;
        var n = text.Length;
        while (start < n)
        {
            var end = Math.Min(start + size, n);
            if (end < n)
            {
                // Prefer to break on a sentence boundary, then a space, near the limit.
                var window = text.Substring(start, end - start);
                foreach (var sep in new[] { ". ", "! ", "? ", "\n", " " })
                {
                    var pos = window.LastIndexOf(sep, StringComparison.Ordinal);
                    if (pos > size / 2)
                    {
                        end = start + pos + sep.Length;
                        break;
                    }
                }
            }
            var chunk = text.Substring(start, end - start).Trim();
            if (chunk.Length > 0)
            {
                chunks.Add(chunk);
            }
            if (end >= n)
            {
                break;
            }
            start = Math.Max(end - overlap, start + 1);
        }
        return chunks;
    }

    public static List<Chunk> ChunkPages(List<Page> pages, int size = 1000, int overlap = 200)
    {
        var chunks = new List<Chunk>();
        var index = 0;
        foreach (var page in pages)
        {
            foreach (var piece in SplitText(page.Text, size, overlap))
            {
                chunks.Add(new Chunk(page.Source, page.PageNumber, index, piece));
                index++;
            }
        }
        return chunks;
    }
}
