// The anti-hallucination core: grounding system prompt + context formatting.
//
// The model is told to answer from the provided documents first and cite them,
// to say plainly when something is not in the documents, and to clearly label
// any general knowledge it adds. Ported verbatim from localrag/prompts.py.

export const SYSTEM_PROMPT = `You are a careful assistant answering questions over a set of \
the user's own documents. Follow these rules exactly:

1. Answer from the DOCUMENT CONTEXT below FIRST. For every claim that comes from \
the documents, cite the source like [filename:page].
2. If the answer is not contained in the document context, say so plainly: \
"This is not covered in your documents." You may then add general knowledge, but \
you MUST prefix it with "(general knowledge — not from your documents)".
3. Never invent document contents, quotes, or citations. Only cite sources that \
appear in the context.
4. Be concise. Prefer the documents' own wording.
`;

export function buildContext(chunks) {
  // Format retrieved chunks with a citation header on each block.
  const blocks = chunks.map((c) => {
    const header = `[${c.source}:${c.page_number}]`;
    return `${header}\n${c.text}`;
  });
  return blocks.join("\n\n---\n\n");
}

export function buildUserPrompt(question, chunks) {
  const context = chunks.length ? buildContext(chunks) : "(no relevant documents found)";
  return (
    "DOCUMENT CONTEXT:\n" +
    `${context}\n\n` +
    "QUESTION:\n" +
    `${question}\n\n` +
    "Answer using the rules above, citing [filename:page] for document-based claims."
  );
}
