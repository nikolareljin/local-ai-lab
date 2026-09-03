"""Lesson 8 - the two graders, and the interface they share.

A corrective loop needs one judgement: *are these hits good enough to answer
from?* Everything else in the graph follows from that answer, so this file is
where the lesson's most interesting trade-off lives.

  CoverageGrader  deterministic, offline, free. The DEFAULT - and only because
                  `./run -l 8 demo` is byte-diffed by the test, so it has to
                  print the same thing every time.
  LlmGrader       asks a model. Non-deterministic, costs a call per grade, and
                  is the one you should actually use on your own documents.

Neither grader is ever shown the expected answer. `expect` lives in
data/questions.json and is used only to score the run afterwards; if a grader
could see it, the whole measurement would be theatre. `test_langgraph_agent.py`
asserts that on the signature, so it cannot quietly change.
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional, Protocol, TypedDict

import rag_core


class Grade(TypedDict):
    verdict: str      # "grounded" | "weak"
    score: float      # 0.0 - 1.0
    missing: List[str]  # terms the evidence did not cover -> this feeds the rewriter
    reason: str       # one line, readable
    grader: str       # which grader spoke, and whether it fell back


class Grader(Protocol):
    name: str

    def grade(self, question: str, query: str, docs: List[rag_core.Chunk]) -> Grade:
        ...


class CoverageGrader:
    """Term coverage: what fraction of the query's content words does the evidence contain?

    This is a real information-retrieval signal, not a stand-in for one. It
    detects the exact failure this lesson is about - a reader asking in words the
    documents never use - because those words cannot appear in any retrieved
    chunk, whatever the retriever ranks first.

    It also explains itself. `missing` is the list of terms that did not land,
    which is precisely what the rewriter needs, so the two nodes are coupled
    through data rather than through a shared hard-coded table.
    """

    name = "coverage"

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold

    def grade(self, question: str, query: str, docs: List[rag_core.Chunk]) -> Grade:
        terms = rag_core.content_terms(query)
        if not terms:
            # A query with no content words cannot be judged this way. Say so
            # rather than dividing by zero or silently passing.
            return Grade(verdict="weak", score=0.0, missing=[],
                         reason="no content terms to look for", grader=self.name)
        haystack = set(rag_core.tokens(rag_core.evidence_text(docs)))
        missing = [t for t in terms if t not in haystack]
        score = (len(terms) - len(missing)) / len(terms)
        grounded = score >= self.threshold
        return Grade(
            verdict="grounded" if grounded else "weak",
            score=round(score, 2),
            missing=missing,
            reason=(f"evidence covers {len(terms) - len(missing)}/{len(terms)} query terms"
                    + ("" if grounded else f"; missing {missing}")),
            grader=self.name,
        )


GRADE_SYSTEM = (
    "You judge whether retrieved documentation is enough to answer a question. "
    "You are strict: if the evidence does not actually address the question, say WEAK."
)

GRADE_BRIEF = """\
Reply with exactly one word on the first line: GROUNDED or WEAK.
On the second line, at most fifteen words saying why.
If WEAK, on the third line list the query terms the evidence is missing, comma separated.

Question: {question}
Search query used: {query}

Retrieved evidence:
{evidence}
"""


class LlmGrader:
    """Ask a model the same question, in the same shape.

    This is the grader you want in production, and it is not the default here for
    exactly one reason: it does not print the same thing twice, and this lesson's
    demo is committed to a file and diffed by a test.

    It never fails closed. A provider error or an unparsable reply falls back to
    coverage and *says so* in `grader`, so a fallback shows up in the trace rather
    than quietly changing what the loop decides.
    """

    def __init__(self, chat: Callable[[str, str], str], fallback: CoverageGrader,
                 label: str = "llm") -> None:
        self.chat = chat
        self.fallback = fallback
        self.name = label

    def grade(self, question: str, query: str, docs: List[rag_core.Chunk]) -> Grade:
        prompt = GRADE_BRIEF.format(question=question, query=query,
                                    evidence=rag_core.evidence_text(docs) or "(nothing retrieved)")
        try:
            reply = self.chat(GRADE_SYSTEM, prompt)
        except Exception as exc:  # provider down, no CLI, no key, timeout
            return self._fell_back(question, query, docs, f"provider error: {type(exc).__name__}")
        parsed = _parse_verdict(reply)
        if parsed is None:
            return self._fell_back(question, query, docs, "could not parse a verdict")
        verdict, reason, missing = parsed
        return Grade(
            verdict=verdict,
            # The model gives no number, so no number is invented. 1.0/0.0 records
            # only what it actually said.
            score=1.0 if verdict == "grounded" else 0.0,
            missing=missing,
            reason=reason or f"model said {verdict.upper()}",
            grader=self.name,
        )

    def _fell_back(self, question: str, query: str, docs: List[rag_core.Chunk],
                   why: str) -> Grade:
        grade = self.fallback.grade(question, query, docs)
        grade["grader"] = f"{self.name}(fell back)"
        grade["reason"] = f"{why}; fell back to coverage - {grade['reason']}"
        return grade


def _parse_verdict(reply: str) -> Optional[tuple]:
    """Read GROUNDED/WEAK out of a model reply, leniently but without guessing.

    Lenient about shape - models add preamble, markdown, and punctuation. Strict
    about substance: if neither word appears, this returns None and the caller
    falls back rather than picking a verdict on the reader's behalf.
    """
    lines = [ln.strip() for ln in (reply or "").splitlines() if ln.strip()]
    upper = " ".join(lines).upper()
    # Whole words only. "GROUNDED" is a substring of "UNGROUNDED", and a model that
    # answers UNGROUNDED means the exact opposite of what a substring test would
    # record - silently, with no fallback, which is the one outcome this class
    # promises never to produce.
    found = [(m.start(), m.group()) for m in re.finditer(r"\b(GROUNDED|WEAK)\b", upper)]
    if not found:
        return None
    # Believe the first verdict word, which is the one the brief asks for on line 1.
    verdict = "grounded" if found[0][1] == "GROUNDED" else "weak"
    reason = lines[1] if len(lines) > 1 else ""
    missing: List[str] = []
    if verdict == "weak" and len(lines) > 2:
        missing = [t.strip().lower() for t in lines[2].split(",") if t.strip()]
    return verdict, reason, missing


def make_grader(kind: str, threshold: float, chat: Optional[Callable[[str, str], str]] = None,
                label: str = "llm") -> Grader:
    """The only place a grader is constructed."""
    coverage = CoverageGrader(threshold)
    if kind == "coverage":
        return coverage
    if kind == "llm":
        if chat is None:
            raise ValueError("the llm grader needs a chat callable")
        return LlmGrader(chat, coverage, label=label)
    raise ValueError(f"unknown grader: {kind!r}")
