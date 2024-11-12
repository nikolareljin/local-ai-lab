# Lesson 1: Building a RAG System From Scratch

This document is the written companion to Lesson 1 of local-ai-lab. It is also
deliberately placed in the `documents/` folder so the RAG app can answer
questions about RAG *from its own tutorial* — a small but fun demonstration that
the system is grounding answers in real ingested text.

## What RAG is

Retrieval-Augmented Generation (RAG) is a technique for making a language model
answer questions using a specific set of documents instead of relying only on
what it memorized during training. The model is given relevant passages from your
documents as context, and is instructed to answer from that context and cite it.
This dramatically reduces hallucination, because the model is grounded in real,
retrievable text rather than guessing.

## The RAG pipeline

A RAG system has six stages:

1. Extraction — convert files (PDF, DOCX, TXT, Markdown) into plain text. Each
   page keeps its source filename and page number so answers can cite them.
2. Chunking — split the text into overlapping windows of roughly 1000 characters
   with about 200 characters of overlap. Overlap ensures a sentence split across
   a boundary still appears intact in at least one chunk. Chunk size is a tuning
   dial: too large makes retrieval imprecise, too small loses context.
3. Indexing — extract and chunk every document once, then cache the result.
   Files are fingerprinted by path, modification time, and size, so the index is
   only rebuilt when something changes. Dropping a new file in the folder and
   asking again picks it up automatically.
4. Retrieval — given a question, find the most relevant chunks. Two techniques
   are common: BM25 and embeddings.
5. Grounding — build a prompt that gives the model the retrieved chunks as
   context and instructs it to answer from them, cite sources, and clearly label
   any general knowledge it adds.
6. Generation — send the grounded prompt to a language model provider and return
   the answer with its sources.

## BM25 versus embeddings retrieval

BM25 is a classic keyword ranking algorithm, an improved form of TF-IDF. It
matches the actual words in the question against the words in each chunk. BM25
needs no model and no embedding service, so it works with any provider and runs
instantly. Its weakness is that it cannot match paraphrases: a question asking how
to "power-cycle" a device will not match a document that says "restart", because
they share no keywords.

Embeddings retrieval solves that by converting each chunk and the question into a
numeric vector that captures meaning, then ranking chunks by cosine similarity to
the question. This matches concepts and paraphrases, not just exact words. The
cost is that embeddings require an embedding model (from Ollama, Gemini, or
OpenAI) and a place to store the vectors. Production systems often use both BM25
and embeddings together, called hybrid retrieval, and merge the two rankings.

A subtle but important detail: BM25's inverse document frequency term becomes
negative when a word appears in every chunk, which happens often on a tiny
corpus. A naive implementation that discards results with a non-positive score
will return nothing. The fix is to rank by score and return the top results,
letting the grounding prompt decide relevance, rather than applying an absolute
score cutoff.

## The grounding prompt and anti-hallucination

The grounding prompt is the heart of RAG. It instructs the model to answer from
the provided document context first and to cite each claim with its source and
page. If the answer is not in the documents, the model must say so plainly and
must clearly label any general knowledge it adds, for example by prefixing it with
"general knowledge — not from your documents". The model is told never to invent
document contents, quotes, or citations. This clean separation between cited facts
and clearly labeled general knowledge is what makes a RAG system trustworthy.

The quality of a RAG answer depends on both retrieval quality and prompt quality.
A strict prompt with poor retrieval will answer "not in your documents" to
everything, while a sloppy prompt with perfect retrieval will still hallucinate.
Both must be good.

## The provider abstraction

To keep the pipeline independent of any single AI vendor, RAG systems define a
small provider interface with a single chat method that takes a system prompt and
a user prompt and returns text. Each provider — Claude Code, Ollama, Gemini,
OpenAI — implements that interface. Switching providers then becomes a one-line
configuration change. The default in local-ai-lab is the Claude Code CLI, which
requires no API key because it reuses your existing login. This provider pattern
is exactly what larger frameworks like LangChain are built around.

## Why build it from scratch

Most tutorials teach you to glue frameworks together. Building RAG from scratch —
writing the chunker, the retriever, the grounding prompt, and the provider
abstraction yourself — means you understand what every framework is automating.
Once you know the primitives, tools like LangChain, LlamaIndex, and LangGraph stop
looking like magic.
