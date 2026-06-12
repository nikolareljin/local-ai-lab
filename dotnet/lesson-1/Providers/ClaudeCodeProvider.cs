// Default provider: shell out to the Claude Code CLI (`claude -p`).
// No API key required — reuses your existing Claude Code login. Mirrors
// localrag/providers/claude_code.py.

using System.Diagnostics;

namespace LocalRag.Providers;

public class ClaudeCodeProvider : ILlmProvider
{
    public string Name => "claude";

    private readonly string _bin;

    public ClaudeCodeProvider(Config config) => _bin = config.ClaudeBin;

    public bool IsAvailable() => Which(_bin) is not null;

    public string Chat(string system, string user)
    {
        if (!IsAvailable())
        {
            throw new InvalidOperationException(
                $"Claude Code CLI '{_bin}' not found on PATH. Install it, or set " +
                "RAG_PROVIDER to ollama|gemini|openai.");
        }

        // Pass the prompt on STDIN (not as an argv) so it behaves identically on
        // Linux, macOS and Windows — no command-line length limits, no shell
        // quoting of a multi-line string.
        var prompt = $"{system}\n\n{user}";
        var resolved = Which(_bin)!;
        var psi = new ProcessStartInfo
        {
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        // A Windows `claude.cmd` / `.bat` is a script, not an executable, so it
        // must be launched through cmd.exe; a real binary is launched directly.
        if (OperatingSystem.IsWindows() &&
            (resolved.EndsWith(".cmd", StringComparison.OrdinalIgnoreCase) ||
             resolved.EndsWith(".bat", StringComparison.OrdinalIgnoreCase)))
        {
            psi.FileName = "cmd.exe";
            psi.ArgumentList.Add("/c");
            psi.ArgumentList.Add(resolved);
        }
        else
        {
            psi.FileName = resolved;
        }
        psi.ArgumentList.Add("-p");

        using var proc = Process.Start(psi)
            ?? throw new InvalidOperationException($"Failed to start '{_bin}'.");
        proc.StandardInput.Write(prompt);
        proc.StandardInput.Close();
        // Read stdout and stderr concurrently: reading one to EOF before the
        // other can deadlock if the CLI fills the other pipe's buffer (e.g. a
        // large auth/permission error stream).
        var stdoutTask = proc.StandardOutput.ReadToEndAsync();
        var stderrTask = proc.StandardError.ReadToEndAsync();
        // Bound the wait so a hung CLI (e.g. an interactive login prompt) can't
        // block the request forever; matches the Node port's 180s.
        const int timeoutMs = 180_000;
        if (!proc.WaitForExit(timeoutMs))
        {
            try { proc.Kill(entireProcessTree: true); } catch { /* already exiting */ }
            throw new InvalidOperationException(
                $"claude did not respond within {timeoutMs / 1000}s — it may be waiting for login. " +
                "Run `claude` once to sign in, or set RAG_PROVIDER to ollama|gemini|openai.");
        }
        var stdout = stdoutTask.GetAwaiter().GetResult();
        var stderr = stderrTask.GetAwaiter().GetResult();
        if (proc.ExitCode != 0)
        {
            throw new InvalidOperationException(
                $"claude exited with {proc.ExitCode}: {stderr.Trim()}");
        }
        return stdout.Trim();
    }

    private static string? Which(string bin)
    {
        // Absolute/relative path with a separator: check directly.
        if (bin.Contains(Path.DirectorySeparatorChar) || bin.Contains('/'))
        {
            return File.Exists(bin) ? bin : null;
        }
        // On Windows the launcher is `claude.cmd` / `claude.exe`, so try each
        // PATHEXT suffix; on POSIX the bare name is the executable.
        var exts = new List<string> { string.Empty };
        if (OperatingSystem.IsWindows())
        {
            var pathext = Environment.GetEnvironmentVariable("PATHEXT")
                          ?? ".COM;.EXE;.BAT;.CMD";
            exts.AddRange(pathext.Split(Path.PathSeparator,
                StringSplitOptions.RemoveEmptyEntries));
        }
        var pathEnv = Environment.GetEnvironmentVariable("PATH") ?? string.Empty;
        foreach (var dir in pathEnv.Split(Path.PathSeparator))
        {
            if (dir.Length == 0)
            {
                continue;
            }
            foreach (var ext in exts)
            {
                var candidate = Path.Combine(dir, bin + ext);
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }
        }
        return null;
    }
}
