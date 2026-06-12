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

// Resolve a command on PATH WITHOUT invoking a shell, so a CLAUDE_BIN containing
// spaces or shell metacharacters can't break detection or inject a command. On
// Windows we try each PATHEXT suffix (claude.cmd / claude.exe); on POSIX the
// bare name is the executable. Mirrors the C# Which() in this PR.
function onPath(bin) {
  if (bin.includes("/") || bin.includes(path.sep)) {
    return isExecutableFile(bin);
  }
  const exts = isWindows
    ? ["", ...(process.env.PATHEXT || ".COM;.EXE;.BAT;.CMD").split(";").filter(Boolean)]
    : [""];
  for (const dir of (process.env.PATH || "").split(path.delimiter).filter(Boolean)) {
    for (const ext of exts) {
      if (isExecutableFile(path.join(dir, bin + ext))) return true;
    }
  }
  return false;
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
