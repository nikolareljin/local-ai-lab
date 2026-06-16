# Production notes - what this demo deliberately keeps simple

`local-ai-lab` is a **teaching project**. It favors small, readable code so you can see exactly how
each piece works — a retriever, a chunker, a provider adapter, an evaluation gate — without a
framework hiding the moving parts. That clarity comes with deliberate trade-offs: the code skips
hardening that a real deployment would need, and a few "gaps" are themselves the lesson.

This page is the honest list of what you'd add for production, and why it's intentionally absent here.

## Security

- **Prompt injection is *not* defended against by default — on purpose.** Retrieved document text is
  fed straight into the prompt, so a malicious document can try to hijack the answer. That failure
  mode is exactly what **[Lesson 4 — RAG safety & prompt injection](./lessons/04-rag-safety-prompt-injection/)**
  teaches you to see and mitigate. In production you'd apply the defenses from that lesson
  (input/output framing, allow-lists, instruction/data separation, output validation).
- **The web UI is single-user and unauthenticated.** `localrag web` defaults to binding `127.0.0.1`, but can be exposed with `--host`; it has no
  auth, CSRF protection, rate limiting, or per-user isolation. For anything multi-user or
  network-exposed you'd add authentication, request limits, and upload scanning.
- **Secrets** are read from the environment / `.env`. Keep real keys out of indexed documents and out
  of version control (use a secrets manager in production).

## Testing

- The demo keeps a **handful of offline smoke tests** so the suite stays readable and fast. A
  production codebase would add **comprehensive unit tests for every provider** (mocked
  HTTP/`subprocess`), **Flask endpoint tests** (`/api/ask`, `/api/upload`, `/api/status`,
  `/api/peek`), **engine cache/concurrency tests**, and a **coverage gate** in CI. These are
  intentionally left out to keep the example code uncluttered and easy to follow.

## Performance

- **Embeddings are computed serially** for Ollama and Gemini (one HTTP request per chunk); the OpenAI
  adapter already batches. For real corpora you'd switch Ollama from the per-item `/api/embeddings`
  call to the batch `/api/embed` endpoint and Gemini to `:batchEmbedContents`, plus add concurrency,
  caching, and retries with backoff.

## Observability

- The code uses plain `print()` for the few diagnostic messages (e.g. the BM25 fallback). A
  production service would use the **`logging`** module with structured levels, and emit metrics for
  retrieval latency, provider errors, and cache hit/miss.

## Robustness & code quality

- **Type coverage** is partial — the package carries type hints; the lesson and tooling scripts are
  intentionally untyped.
- Network calls use fixed timeouts but **no retries/backoff**; add those for flaky providers.
- A little formatting logic (the `[source:page]` citation block) is **duplicated across modules**; a
  production codebase would extract one shared helper. Here it's kept inline so each file reads on its
  own.

---

**The point:** every item above is a deliberate choice to keep the teaching code small and legible.
When you take these ideas into production, treat this list as your hardening checklist.
