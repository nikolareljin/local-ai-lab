"""The anti-hallucination core: grounding system prompt + context formatting.

The whole point of the demo is that answers stay honest about their source.
The model is told to answer from the provided documents first and cite them,
to say plainly when something is not in the documents, and to clearly label any
general knowledge it adds so the audience can tell the two apart.
"""

from __future__ import annotations

from typing import List

from .chunk import Chunk

SYSTEM_PROMPT = """You are a careful assistant answering questions over a set of \
the user's own documents. Follow these rules exactly:

1. Answer from the DOCUMENT CONTEXT below FIRST. For every claim that comes from \
the documents, cite the source like [filename:page].
2. If the answer is not contained in the document context, say so plainly: \
"This is not covered in your documents." You may then add general knowledge, but \
you MUST prefix it with "(general knowledge — not from your documents)".
3. Never invent document contents, quotes, or citations. Only cite sources that \
appear in the context.
4. Be concise. Prefer the documents' own wording.
"""


def build_context(chunks: List[Chunk]) -> str:
    """Format retrieved chunks with a citation header on each block."""
    blocks = []
    for c in chunks:
        header = f"[{c['source']}:{c['page_number']}]"
        blocks.append(f"{header}\n{c['text']}")
    return "\n\n---\n\n".join(blocks)


def build_user_prompt(question: str, chunks: List[Chunk]) -> str:
    context = build_context(chunks) if chunks else "(no relevant documents found)"
    return (
        "DOCUMENT CONTEXT:\n"
        f"{context}\n\n"
        "QUESTION:\n"
        f"{question}\n\n"
        "Answer using the rules above, citing [filename:page] for document-based claims."
    )
