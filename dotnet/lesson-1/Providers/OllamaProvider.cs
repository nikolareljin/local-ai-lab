// Local Ollama provider: chat via /api/chat. Mirrors localrag/providers/ollama.py
// (embeddings are out of scope for this C# port).

using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace LocalRag.Providers;

public class OllamaProvider : ILlmProvider
{
    public string Name => "ollama";

    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(180) };

    private readonly string _url;
    private readonly string _model;
    private readonly string _troubleshootingUrl;

    public OllamaProvider(Config config)
    {
        _url = config.OllamaUrl;
        _model = config.OllamaModel;
        _troubleshootingUrl = config.DocsBaseUrl + "troubleshooting.html";
    }

    public bool IsAvailable()
    {
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(2));
            var resp = Http.GetAsync($"{_url}/api/tags", cts.Token).GetAwaiter().GetResult();
            return resp.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    public string Chat(string system, string user)
    {
        var payload = new
        {
            model = _model,
            stream = false,
            messages = new[]
            {
                new { role = "system", content = system },
                new { role = "user", content = user },
            },
        };
        var resp = Http.PostAsJsonAsync($"{_url}/api/chat", payload).GetAwaiter().GetResult();
        if (!resp.IsSuccessStatusCode)
        {
            // Surface what's actually wrong. A 404 here almost always means the
            // model isn't pulled — give the exact fix, not a bare status code.
            var body = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult().Trim();
            var detail = body;
            try { detail = JsonNode.Parse(body)?["error"]?.GetValue<string>() ?? body; }
            catch { /* not JSON — keep the raw body */ }
            var hint = (int)resp.StatusCode == 404
                ? $" Model '{_model}' is not installed — run `ollama pull {_model}`, " +
                  "or set OLLAMA_MODEL to a model you have (`ollama list`)."
                : string.Empty;
            throw new InvalidOperationException(
                $"Ollama request failed ({(int)resp.StatusCode}): {detail}.{hint} " +
                $"See {_troubleshootingUrl}");
        }
        var json = resp.Content.ReadFromJsonAsync<JsonNode>().GetAwaiter().GetResult();
        var content = json?["message"]?["content"]?.GetValue<string>()
            ?? throw new InvalidOperationException("Ollama returned no message content.");
        return content.Trim();
    }
}
