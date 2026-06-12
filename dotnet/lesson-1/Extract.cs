// Extract plain text from supported document types.
// Mirrors localrag/extract.py: a "page" per PDF page; the whole document is one
// page for DOCX/TXT/MD.

using System.Text;
using DocumentFormat.OpenXml.Packaging;
using UglyToad.PdfPig;
using Wordprocessing = DocumentFormat.OpenXml.Wordprocessing;

namespace LocalRag;

public record Page(string Source, int PageNumber, string Text);

public static class Extract
{
    public static readonly HashSet<string> SupportedExts = new(StringComparer.OrdinalIgnoreCase)
    {
        ".pdf", ".docx", ".txt", ".md", ".markdown"
    };

    private static string ReadTextFile(string path)
    {
        var bytes = File.ReadAllBytes(path);
        try
        {
            var utf8 = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);
            return utf8.GetString(bytes);
        }
        catch (DecoderFallbackException)
        {
            // latin-1: every byte maps 1:1 to a code point.
            return Encoding.Latin1.GetString(bytes);
        }
    }

    private static List<Page> ExtractPdf(string path)
    {
        var pages = new List<Page>();
        var name = Path.GetFileName(path);
        using var doc = PdfDocument.Open(path);
        var i = 0;
        foreach (var page in doc.GetPages())
        {
            i++;
            var text = (page.Text ?? string.Empty).Trim();
            if (text.Length > 0)
            {
                pages.Add(new Page(name, i, text));
            }
        }
        return pages;
    }

    private static List<Page> ExtractDocx(string path)
    {
        using var doc = WordprocessingDocument.Open(path, false);
        var body = doc.MainDocumentPart?.Document?.Body;
        // python-docx's doc.paragraphs yields only the body's direct <w:p>
        // children (not paragraphs nested in tables), so match that.
        var paragraphs = body?.Elements<Wordprocessing.Paragraph>() ?? Enumerable.Empty<Wordprocessing.Paragraph>();
        var lines = paragraphs
            .Select(p => p.InnerText)
            .Where(t => t.Trim().Length > 0);
        var text = string.Join("\n", lines);
        if (text.Trim().Length == 0)
        {
            return new List<Page>();
        }
        return new List<Page> { new(Path.GetFileName(path), 1, text) };
    }

    /// <summary>Extract text from a single file. Unsupported types return an empty list.</summary>
    public static List<Page> ExtractPages(string path)
    {
        var ext = Path.GetExtension(path).ToLowerInvariant();
        if (ext == ".pdf")
        {
            return ExtractPdf(path);
        }
        if (ext == ".docx")
        {
            return ExtractDocx(path);
        }
        if (ext is ".txt" or ".md" or ".markdown")
        {
            var text = ReadTextFile(path).Trim();
            return text.Length > 0
                ? new List<Page> { new(Path.GetFileName(path), 1, text) }
                : new List<Page>();
        }
        return new List<Page>();
    }

    /// <summary>Find all supported files under the docs directory (recursively), sorted.</summary>
    public static List<string> DiscoverFiles(string docsDir)
    {
        if (!Directory.Exists(docsDir))
        {
            return new List<string>();
        }
        return Directory
            .EnumerateFiles(docsDir, "*", SearchOption.AllDirectories)
            .Where(p => SupportedExts.Contains(Path.GetExtension(p)))
            .OrderBy(p => p, StringComparer.Ordinal)
            .ToList();
    }
}
