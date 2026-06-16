# Lesson 1 · RAG (C# / .NET 8 port)

A faithful, tiny C# port of the Lesson 1 Retrieval-Augmented Generation app. It
indexes the documents in the shared `documents/` corpus, retrieves the most
relevant chunks for a question with BM25, and asks an LLM to answer **grounded
in those documents** with cited sources.

This mirrors the Python reference in [`localrag/`](../../localrag/) module for
module (`Config`, `Extract`, `Chunk`, `Store`, `Retriever`, `Prompts`,
`Providers`, `Engine`, `Program`).

## Run it (from the repo root)

```bash
./run -l 1 --lang csharp                       # launch the web UI (auto-free port)
./run -l 1 --lang csharp ask "What is in these documents?"
./run -l 1 --lang csharp index                 # build/refresh the index
```

The default AI provider is the **Claude Code CLI** (`claude -p`) - no API key,
it reuses your existing Claude Code login. Override with
`RAG_PROVIDER=ollama` (chat via the local Ollama `/api/chat`).

## Validate (offline smoke test)

No network, no API key, no LLM - this restores/builds, then indexes the committed
sample documents and exits `0`:

```bash
./run -l 1 --lang csharp test && echo PASS || echo FAIL
# expected: [localrag] Indexed N file(s) into M chunk(s).   (counts depend on documents/)
#           PASS
```

## Check the RAG behaviour (needs an AI provider)

Download the **fictional** story *The Voyage of Caretta the Magnificent*
([PDF](https://nikolareljin.github.io/local-ai-lab/pdf/The_Magic_Turtle_Astronaut.pdf)) - it's
user-supplied, not committed - and drop it into `documents/` (or upload it in the web UI). Then ask
a grounded question and one the story can't answer:

```bash
# Grounded - must cite [The_Magic_Turtle_Astronaut.pdf:page]
./run -l 1 --lang csharp ask "What was the name of Caretta's ship and where did it travel?"

# Not in the document - stays honest, then labels general knowledge
./run -l 1 --lang csharp ask "Which dog went to space?"
#   → "... not covered in your documents. (general knowledge - not from your documents)
#      ... Laika ... Sputnik 2 in 1957 ..."
```

## What it does

- **Extract** text from `.pdf` (PdfPig), `.docx` (OpenXml), and `.txt/.md/.markdown`.
- **Chunk** pages into overlapping windows (size 1000, overlap 200), breaking on
  sentence/word boundaries.
- **Index** to `<repoRoot>/.localrag/dotnet/index.json`, fingerprinted by
  `(path, mtime, size)` so it only re-indexes when documents change. (Uses a
  separate cache dir from Python so the two never clobber each other.)
- **Retrieve** with a hand-rolled **BM25 Okapi** (`k1=1.5`, `b=0.75`).
- **Answer** via the grounding system prompt, citing `[filename:page]`.

## Parity notes vs. the Python reference

- **BM25 only.** The embeddings (semantic) retriever is not ported; selecting it
  prints a one-line notice and falls back to BM25.
- **Providers:** `claude` (default) and `ollama` are ported. `gemini` and
  `openai` throw a clear "not ported in C# yet - use the Python reference" error.

Part of the [local-ai-lab](https://nikolareljin.github.io/local-ai-lab/) course.
