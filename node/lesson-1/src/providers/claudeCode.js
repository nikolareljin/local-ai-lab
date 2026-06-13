// Default provider: shell out to the Claude Code CLI (`claude -p`).
//
// No API key required — it reuses your existing Claude Code login. Mirrors
// localrag/providers/claude_code.py.

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const isWindows = process.platform === "win32";

function isExecutableFile(p) {
  try {
    if (!fs.statSync(p).isFile()) return false;
    // On Windows executability is determined by extension (PATHEXT); on POSIX
    // require the execute bit so we don't report a non-executable file as found.
    if (isWindows) return true;
    fs.accessSync(p, fs.constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

// Resolve a command to its full path on PATH WITHOUT invoking a shell, so a
// CLAUDE_BIN containing spaces or shell metacharacters can't break detection or
// inject a command. On Windows we try each PATHEXT suffix (claude.cmd /
// claude.exe); on POSIX the bare name is the executable. Returns null if not
// found. Mirrors the C# Which() in this PR.
function resolveBin(bin) {
  if (bin.includes("/") || bin.includes(path.sep)) {
    return isExecutableFile(bin) ? bin : null;
  }
  const exts = isWindows
    ? ["", ...(process.env.PATHEXT || ".COM;.EXE;.BAT;.CMD").split(";").filter(Boolean)]
    : [""];
  for (const dir of (process.env.PATH || "").split(path.delimiter).filter(Boolean)) {
    for (const ext of exts) {
      const candidate = path.join(dir, bin + ext);
      if (isExecutableFile(candidate)) return candidate;
    }
  }
  return null;
}

export class ClaudeCodeProvider {
  constructor(config) {
    this.name = "claude";
    this.bin = config.claudeBin;
  }

  isAvailable() {
    return resolveBin(this.bin) !== null;
  }

  chat(system, user) {
    const resolved = resolveBin(this.bin);
    if (!resolved) {
      throw new Error(
        `Claude Code CLI '${this.bin}' not found on PATH. Install it, or set ` +
          "RAG_PROVIDER to ollama|gemini|openai."
      );
    }
    // Run the resolved binary directly (never `shell: true`). A Windows
    // claude.cmd / .bat is a script, so launch it via cmd.exe /c; a real binary
    // runs as-is. The prompt goes on STDIN — no argv-length limits and no shell
    // quoting of a multi-line string. Mirrors the .NET ClaudeCodeProvider.
    let file = resolved;
    let args = ["-p"];
    if (isWindows && /\.(cmd|bat)$/i.test(resolved)) {
      file = "cmd.exe";
      args = ["/c", resolved, "-p"];
    }
    try {
      const out = execFileSync(file, args, {
        input: `${system}\n\n${user}`,
        encoding: "utf-8",
        timeout: 180000,
        maxBuffer: 64 * 1024 * 1024,
      });
      return out.trim();
    } catch (err) {
      const stderr = (err.stderr || "").toString().trim();
      throw new Error(`claude exited with ${err.status ?? "error"}: ${stderr}`);
    }
  }
}
