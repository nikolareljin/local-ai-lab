// Pluggable AI providers behind one small interface.
//
// Every provider exposes the same `chat(system, user)` method; the factory picks
// an implementation by name so the rest of the app never branches on provider.
// Mirrors localrag/providers/__init__.py's get_provider.
//
// PARITY NOTE: only `claude` and `ollama` are ported in Node. `gemini`/`openai`
// throw a clear "not ported in Node yet" error pointing at the Python reference.

import { ClaudeCodeProvider } from "./claudeCode.js";
import { OllamaProvider } from "./ollama.js";

export function getProvider(name, config) {
  name = (name || "").toLowerCase();
  if (name === "claude") return new ClaudeCodeProvider(config);
  if (name === "ollama") return new OllamaProvider(config);
  if (name === "gemini" || name === "openai") {
    throw new Error(
      `Provider '${name}' is not ported in Node yet — use the Python reference ` +
        "(python -m localrag --provider " + name + " ...) or set RAG_PROVIDER=claude|ollama."
    );
  }
  throw new Error(`Unknown provider '${name}'. Choose one of: claude, ollama.`);
}
