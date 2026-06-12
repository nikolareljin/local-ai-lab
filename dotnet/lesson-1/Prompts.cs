// The anti-hallucination core: grounding system prompt + context formatting.
// SYSTEM_PROMPT is verbatim from localrag/prompts.py.

namespace LocalRag;

public static class Prompts
{
    public const string SystemPrompt =
        "You are a careful assistant answering questions over a set of " +
        "the user's own documents. Follow these rules exactly:\n" +
        "\n" +
        "1. Answer from the DOCUMENT CONTEXT below FIRST. For every claim that comes from " +
        "the documents, cite the source like [filename:page].\n" +
        "2. If the answer is not contained in the document context, say so plainly: " +
        "\"This is not covered in your documents.\" You may then add general knowledge, but " +
        "you MUST prefix it with \"(general knowledge — not from your documents)\".\n" +
        "3. Never invent document contents, quotes, or citations. Only cite sources that " +
        "appear in the context.\n" +
        "4. Be concise. Prefer the documents' own wording.\n";

    /// <summary>Format retrieved chunks with a citation header on each block.</summary>
    public static string BuildContext(List<Chunk> chunks)
    {
        var blocks = chunks.Select(c => $"[{c.Source}:{c.PageNumber}]\n{c.Text}");
        return string.Join("\n\n---\n\n", blocks);
    }

    public static string BuildUserPrompt(string question, List<Chunk> chunks)
    {
        var context = chunks.Count > 0 ? BuildContext(chunks) : "(no relevant documents found)";
        return
            "DOCUMENT CONTEXT:\n" +
            $"{context}\n\n" +
            "QUESTION:\n" +
            $"{question}\n\n" +
            "Answer using the rules above, citing [filename:page] for document-based claims.";
    }
}
