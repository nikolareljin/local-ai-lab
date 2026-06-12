# Lesson 1 (Node.js) — Tiny local RAG

A faithful Node.js (ESM, Node 18+) port of [Lesson 1](../../LESSON1.md) of
**local-ai-lab**. Drop documents into `documents/`, ask questions, and get
answers grounded in your files with cited `[filename:page]` sources.

It mirrors the Python reference in `localrag/` one module at a time: `config`,
`extract`, `chunk`, `store`, `retriever`, `prompts`, `providers`, `engine`,
`cli`, and `web`.

## Run

From the repo root (preferred — the `run` dispatcher routes `--lang node` here):

```bash
./run -l 1 --lang node                       # launch the RAG web UI (auto-picks a free port)
./run -l 1 --lang node ask "What is in these documents?"
./run -l 1 --lang node index                 # build/refresh the index
```

Or directly:

```bash
bash node/lesson-1/run.sh web                # or: ask "your question" | index | repl | test
cd node/lesson-1 && npm install && node src/cli.js ask "your question"
```

The default AI provider is the **Claude Code CLI** (`claude -p`) — no API key,
it reuses your existing Claude Code login. Override with
`RAG_PROVIDER=ollama`, or any of the `RAG_*` / provider env vars (see the
repo-root `.env.example`); this port also reads `<repoRoot>/.env`.

## Validate (offline smoke test)

No network, no API key, no LLM — this just builds the index over the committed
sample documents and exits `0`:

```bash
./run -l 1 --lang node test && echo PASS || echo FAIL
# expected: [localrag] Indexed N file(s) into M chunk(s).   (counts depend on documents/)
#           PASS
```

## Check the RAG behaviour (needs an AI provider)

The shared corpus includes a **fictional** story, *The Voyage of Caretta the Magnificent*
(`documents/The_Magic_Turtle_Astronaut.pdf`). Ask a grounded question and one the story can't
answer:

```bash
# Grounded — must cite [The_Magic_Turtle_Astronaut.pdf:page]
./run -l 1 --lang node ask "What was the name of Caretta's ship and where did it travel?"

# Not in the document — stays honest, then labels general knowledge
./run -l 1 --lang node ask "Which dog went to space?"
#   → "... not covered in your documents. (general knowledge — not from your documents)
#      ... Laika ... Sputnik 2 in 1957 ..."
```

## Parity notes vs. the Python reference

- **Retriever:** BM25 only (Okapi, k1=1.5, b=0.75, by hand). The semantic
  `embeddings` retriever is not ported — requesting it falls back to BM25 with
  a notice (use the Python reference for embeddings).
- **Providers:** `claude` and `ollama` are ported. `gemini`/`openai` throw a
  clear "not ported in Node yet — use the Python reference" error.
- **PDF:** `pdf-parse` returns whole-document text, so PDFs are emitted as a
  single page (`page_number 1`) rather than one page per physical PDF page.
- **Cache:** the Node index lives under `<repoRoot>/.localrag/node/` so it never
  clobbers the Python index in `<repoRoot>/.localrag/`.

## Course

Part of [local-ai-lab](https://nikolareljin.github.io/local-ai-lab/) — a
hands-on course for building local AI.
