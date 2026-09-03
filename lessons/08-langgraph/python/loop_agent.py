"""Lesson 8 - arm B: the corrective loop, written as a plain `while`.

This file exists to stop the lesson cheating. Comparing a LangGraph agent against
a single-shot chain would prove that *looping* helps, which is not the same claim
as *LangGraph* helps - and a reader would be right to answer "so write a while
loop". So here is the while loop.

It calls the same `rag_core.retrieve`, the same grader and the same rewriter that
`graph_agent.py` calls. Same settings, same corpus, same order. If the two ever
disagree on any of the nine questions, one of them has drifted and the whole
scorecard is void - which is what `test_graph_and_loop_are_indistinguishable`
is for.

The loop is sixty-three lines. Read it before you read the graph, and then
decide for yourself what the graph is worth.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import rag_core
from graders import Grader
from rewriter import Rewriter


def run(retriever, question: str, *, grader: Grader, rewriter: Rewriter,
        top_k: int, max_attempts: int,
        generate: Optional[Callable] = None) -> dict:
    """Retrieve, grade, and re-search with a better query until the evidence holds up."""
    query = question
    attempt = 1
    retrievals = grades = rewrites = 0
    trace: List[str] = []
    verdicts: List[str] = []
    docs: List[rag_core.Chunk] = []
    grade = None

    while True:
        docs = rag_core.retrieve(retriever, query, top_k)
        retrievals += 1
        trace.append(f"retrieve  attempt={attempt} query={query!r} -> {rag_core.sources(docs)}")

        grade = grader.grade(question, query, docs)
        grades += 1
        verdicts.append(grade["verdict"])
        trace.append(f"grade     {grade['verdict']} score={grade['score']} - {grade['reason']}")

        if grade["verdict"] == "grounded":
            break
        if attempt >= max_attempts:
            trace.append(f"abstain   {attempt} attempts used, evidence still weak")
            break

        new_query = rewriter.rewrite(question, query, grade["missing"])
        rewrites += 1
        if new_query == query:
            # The rewriter had nothing left to try. Retrying an identical query
            # would retrieve identical chunks and grade identically - a cycle that
            # cannot change its own input is an infinite loop with extra steps.
            # Stopping here reaches the same decision the cap would, one wasted
            # retrieval sooner.
            trace.append("abstain   rewrite changed nothing - no point asking again")
            break
        # A rewriter that quietly fell back to the glossary must not look like one
        # that produced this query itself.
        note = "  [fell back to the glossary]" if getattr(rewriter, "fell_back", False) else ""
        trace.append(
            f"rewrite   {query!r} -> {new_query!r}  (missing {grade['missing']}){note}")
        query = new_query
        attempt += 1

    grounded = grade["verdict"] == "grounded"
    answer = ""
    if grounded and generate is not None:
        answer = generate(question, docs)
    elif not grounded:
        answer = rag_core.ABSTAIN_TEXT

    return {
        "question": question, "query": query, "attempts": attempt,
        "retrievals": retrievals, "grades": grades, "rewrites": rewrites,
        "sources": rag_core.sources(docs) if grounded else [],
        "verdicts": verdicts, "grade": grade, "docs": docs,
        "status": "answered" if grounded else "abstained",
        "answer": answer, "trace": trace,
    }


def run_linear(retriever, question: str, *, top_k: int,
               generate: Optional[Callable] = None) -> dict:
    """Arm A: retrieve once, answer. Lesson 1 and Lesson 7's shape, for comparison.

    No grader, no loop, no second chance - which is exactly the behaviour the
    other two arms are measured against.
    """
    docs = rag_core.retrieve(retriever, question, top_k)
    return {
        "question": question, "query": question, "attempts": 1,
        "retrievals": 1, "grades": 0, "rewrites": 0,
        "sources": rag_core.sources(docs), "verdicts": [], "grade": None, "docs": docs,
        "status": "answered",
        "answer": generate(question, docs) if generate is not None else "",
        "trace": [f"retrieve  query={question!r} -> {rag_core.sources(docs)}"],
    }
