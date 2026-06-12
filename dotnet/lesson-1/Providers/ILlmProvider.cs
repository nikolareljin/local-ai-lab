// Pluggable AI providers behind one small interface.
// Mirrors localrag/providers/__init__.py's factory + LLMProvider protocol.

namespace LocalRag.Providers;

public interface ILlmProvider
{
    string Name { get; }
    bool IsAvailable();
    string Chat(string system, string user);
}

public static class ProviderFactory
{
    public static ILlmProvider GetProvider(string name, Config config)
    {
        name = (name ?? string.Empty).ToLowerInvariant();
        return name switch
        {
            "claude" => new ClaudeCodeProvider(config),
            "ollama" => new OllamaProvider(config),
            "gemini" => throw new InvalidOperationException(
                "Provider 'gemini' is not ported in C# yet — use the Python reference."),
            "openai" => throw new InvalidOperationException(
                "Provider 'openai' is not ported in C# yet — use the Python reference."),
            _ => throw new InvalidOperationException(
                $"Unknown provider '{name}'. Choose one of: claude, ollama, gemini, openai."),
        };
    }
}
