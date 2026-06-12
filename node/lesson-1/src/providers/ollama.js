// Local Ollama provider: chat via /api/chat. Mirrors localrag/providers/ollama.py.
// Uses the Node 18+ built-in fetch. (Embeddings are out of scope in this port.)

export class OllamaProvider {
  constructor(config) {
    this.name = "ollama";
    this.url = config.ollamaUrl;
    this.model = config.ollamaModel;
    this.embedModel = config.ollamaEmbedModel;
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
      throw new Error(`ollama /api/chat returned ${resp.status}: ${await resp.text()}`);
    }
    const data = await resp.json();
    return data.message.content.trim();
  }
}
