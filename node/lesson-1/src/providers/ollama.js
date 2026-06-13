// Local Ollama provider: chat via /api/chat. Mirrors localrag/providers/ollama.py.
// Uses the Node 18+ built-in fetch. (Embeddings are out of scope in this port.)

export class OllamaProvider {
  constructor(config) {
    this.name = "ollama";
    this.url = config.ollamaUrl;
    this.model = config.ollamaModel;
    this.embedModel = config.ollamaEmbedModel;
    this.troubleshootingUrl = config.docsBaseUrl + "troubleshooting.html";
  }

  async isAvailable() {
    try {
      const resp = await fetch(`${this.url}/api/tags`, {
        signal: AbortSignal.timeout(2000),
      });
      return resp.ok;
    } catch {
      return false;
    }
  }

  async chat(system, user) {
    const resp = await fetch(`${this.url}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: this.model,
        stream: false,
        messages: [
          { role: "system", content: system },
          { role: "user", content: user },
        ],
      }),
      signal: AbortSignal.timeout(180000),
    });
    if (!resp.ok) {
      // Surface what's actually wrong. A 404 here almost always means the model
      // isn't pulled — give the exact fix instead of a bare status code.
      let detail = (await resp.text()).trim();
      try {
        detail = JSON.parse(detail).error || detail;
      } catch {
        /* not JSON — keep the raw body */
      }
      const hint =
        resp.status === 404
          ? ` Model '${this.model}' is not installed — run \`ollama pull ${this.model}\`, ` +
            "or set OLLAMA_MODEL to a model you have (`ollama list`)."
          : "";
      throw new Error(
        `Ollama request failed (${resp.status}): ${detail}.${hint} ` +
          `See ${this.troubleshootingUrl}`
      );
    }
    const data = await resp.json();
    return data.message.content.trim();
  }
}
