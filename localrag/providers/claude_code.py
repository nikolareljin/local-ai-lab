"""Default provider: shell out to the Claude Code CLI (`claude -p`).

No API key required — it reuses your existing Claude Code login. Cannot embed,
so embeddings mode must use ollama/gemini/openai instead.
"""

from __future__ import annotations

import shutil
import subprocess

from ..config import Config


class ClaudeCodeProvider:
    name = "claude"

    def __init__(self, config: Config) -> None:
        self.bin = config.claude_bin

    def is_available(self) -> bool:
        return shutil.which(self.bin) is not None

    def chat(self, system: str, user: str) -> str:
        if not self.is_available():
            raise RuntimeError(
                f"Claude Code CLI '{self.bin}' not found on PATH. Install it, or set "
                "RAG_PROVIDER to ollama|gemini|openai."
            )
        # Pass the system prompt via --append-system-prompt and the question on stdin.
        prompt = f"{system}\n\n{user}"
        result = subprocess.run(
            [self.bin, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"claude exited with {result.returncode}: {result.stderr.strip()}"
            )
        return result.stdout.strip()
