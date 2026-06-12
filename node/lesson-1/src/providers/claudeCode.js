// Default provider: shell out to the Claude Code CLI (`claude -p`).
//
// No API key required — it reuses your existing Claude Code login. Mirrors
// localrag/providers/claude_code.py.

import { execFileSync, execSync } from "node:child_process";

const isWindows = process.platform === "win32";

function onPath(bin) {
  // Guard the native lookup: `command -v` works on POSIX; `where` searches
  // PATHEXT on Windows so it finds `claude.cmd` / `claude.exe`.
  const probe = isWindows ? `where ${bin}` : `command -v ${bin}`;
  try {
    execSync(probe, { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

export class ClaudeCodeProvider {
  constructor(config) {
    this.name = "claude";
    this.bin = config.claudeBin;
  }

  isAvailable() {
    return onPath(this.bin);
  }

  chat(system, user) {
    if (!this.isAvailable()) {
      throw new Error(
        `Claude Code CLI '${this.bin}' not found on PATH. Install it, or set ` +
          "RAG_PROVIDER to ollama|gemini|openai."
      );
    }
    const prompt = `${system}\n\n${user}`;
    try {
      // Pass the prompt on STDIN (not as an argv) so it works identically on
      // Linux, macOS and Windows: no argv-length limits and no shell quoting of
      // a multi-line string. `shell: true` on Windows lets `claude.cmd` resolve.
      const out = execFileSync(this.bin, ["-p"], {
        input: prompt,
        encoding: "utf-8",
        timeout: 180000,
        maxBuffer: 64 * 1024 * 1024,
        shell: isWindows,
      });
      return out.trim();
    } catch (err) {
      const stderr = (err.stderr || "").toString().trim();
      throw new Error(`claude exited with ${err.status ?? "error"}: ${stderr}`);
    }
  }
}
