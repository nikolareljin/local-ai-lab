"""Lesson 8 - the two rewriters, and an honest note about the first one.

When the grader says the evidence is weak, something has to change before the
next attempt, or the loop just re-runs the same failing search. What changes is
the *query*.

  GlossaryRewriter  a lookup table. Deterministic, offline, and the DEFAULT.
  LlmRewriter       asks a model to rephrase in the documents' vocabulary.

The lookup table is a fixture, not a design. It exists so this lesson's output is
identical on every machine and every run, which is what lets `expected-output.txt`
be diffed by a test. It cannot generalise: it fixes "orange" because someone
wrote "orange" into data/glossary.json, and it will not fix the phrasing you have
not thought of yet. That is the whole argument for `--llm-rewrite`, and the
README says so rather than leaving you to find out.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Protocol

import rag_core


class Rewriter(Protocol):
    name: str

    def rewrite(self, question: str, query: str, missing: List[str]) -> str:
        ...


class GlossaryRewriter:
    """Expand the terms the evidence did not cover into the words the docs use.

    Only `missing` terms are expanded. Rewriting on a grade with nothing missing
    is a no-op, which keeps the rewriter honest: it reacts to the grader's finding
    instead of reaching for the table whenever it is called.
    """

    name = "glossary"

    def __init__(self, glossary: Optional[Dict[str, List[str]]] = None) -> None:
        self.glossary = glossary if glossary is not None else rag_core.load_glossary()

    def rewrite(self, question: str, query: str, missing: List[str]) -> str:
        if not missing:
            return query
        expanded: List[str] = []
        for term in missing:
            expanded.extend(self.glossary.get(term, []))
        if not expanded:
            # Nothing in the table matches. Returning the query unchanged is the
            # honest move: the loop will grade it weak again and, at the cap,
            # abstain - which is the correct outcome for a question the corpus
            # does not answer. Inventing a rewrite here would turn "we have no
            # document about this" into "we tried harder", which is worse.
            return query
        # Keep the terms that DID land, drop the ones that did not, add the
        # documents' words. Dropping the misses is the point: "orange" is not in
        # any chunk, so leaving it in only dilutes the BM25 score of the rest.
        kept = [t for t in rag_core.content_terms(query) if t not in missing]
        out: List[str] = []
        for term in kept + expanded:
            if term not in out:
                out.append(term)
        return " ".join(out)


REWRITE_SYSTEM = (
    "You rewrite a failed documentation search query using the vocabulary the "
    "documentation itself is likely to use. Reply with the query only."
)

REWRITE_BRIEF = """\
The question was: {question}
The search query "{query}" returned nothing useful.
These terms appear nowhere in the retrieved text: {missing}

Write one better search query, using words a technical manual would use.
Reply with the query and nothing else.
"""


class LlmRewriter:
    """Ask a model to rephrase into the documents' vocabulary.

    This is the arm that generalises, because it does not need to have been told
    in advance that "orange" means "amber". On any failure it falls back to the
    glossary and stamps the name, so a fallback is visible in the trace.
    """

    def __init__(self, chat: Callable[[str, str], str], fallback: GlossaryRewriter,
                 label: str = "llm") -> None:
        self.chat = chat
        self.fallback = fallback
        self.name = label

    def rewrite(self, question: str, query: str, missing: List[str]) -> str:
        try:
            reply = self.chat(
                REWRITE_SYSTEM,
                REWRITE_BRIEF.format(question=question, query=query,
                                     missing=", ".join(missing) or "(none)"),
            )
        except Exception:
            return self.fallback.rewrite(question, query, missing)
        candidate = _first_line(reply)
        if not candidate or not rag_core.content_terms(candidate):
            return self.fallback.rewrite(question, query, missing)
        return candidate


def _first_line(reply: str) -> str:
    """The first non-empty line, stripped of the quotes and bullets models add."""
    for line in (reply or "").splitlines():
        line = line.strip().strip("`").strip()
        line = line.lstrip("-*0123456789. ").strip()
        if line.lower().startswith("query:"):
            line = line.split(":", 1)[1].strip()
        line = line.strip('"').strip("'").strip()
        if line:
            return line
    return ""


def make_rewriter(kind: str, chat: Optional[Callable[[str, str], str]] = None,
                  glossary: Optional[Dict[str, List[str]]] = None,
                  label: str = "llm") -> Rewriter:
    """The only place a rewriter is constructed."""
    base = GlossaryRewriter(glossary)
    if kind == "glossary":
        return base
    if kind == "llm":
        if chat is None:
            raise ValueError("the llm rewriter needs a chat callable")
        return LlmRewriter(chat, base, label=label)
    raise ValueError(f"unknown rewriter: {kind!r}")
