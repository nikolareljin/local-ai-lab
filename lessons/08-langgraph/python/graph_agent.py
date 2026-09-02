"""Lesson 8 - arm C: the same corrective loop, as a LangGraph StateGraph.

Read `loop_agent.py` first. This file does the same work, calls the same
functions, and reaches the same answer on every one of the nine questions. That
is the point: on accuracy, LangGraph buys nothing the `while` loop did not
already buy.

What it buys instead is three things the `while` loop structurally cannot do:

  1. state that survives the process        - a checkpointer and a thread_id
  2. a run you can pause and resume mid-way - interrupt() and Command(resume=)
  3. a topology you can enumerate           - get_graph().nodes / .edges

The third one is easy to underrate. In `loop_agent.py` the control flow is
`if` and `while`, which you can read but cannot query. Here it is data, and the
demo prints it.
"""

from __future__ import annotations

import operator
from typing import Annotated, Callable, List, Optional, TypedDict

import rag_core
from graders import Grade, Grader
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from rewriter import Rewriter


class AgentState(TypedDict, total=False):
    """Everything that flows between nodes.

    Note the two kinds of field, deliberately side by side:

      `trace`, `turns`, and the three counters are Annotated with operator.add,
      so a node returning {"retrievals": 1} ADDS ONE to the running total.

      everything else is last-write-wins, so a node returning {"query": "..."}
      REPLACES the query.

    That difference is what a reducer is, and it is easier to see in one struct
    than in any amount of prose.
    """

    question: str          # the human's words. Never mutated.
    query: str             # the CURRENT search query. `rewrite` replaces this.
    attempt: int
    docs: List[rag_core.Chunk]
    sources: List[str]
    grade: Grade

    trace: Annotated[List[str], operator.add]
    turns: Annotated[List[dict], operator.add]
    retrievals: Annotated[int, operator.add]
    grades: Annotated[int, operator.add]
    rewrites: Annotated[int, operator.add]

    decision: str          # "approve" | "veto" | "edit:<new query>"
    answer: str
    status: str            # "answered" | "abstained" | "vetoed"


def build_graph(*, grader: Grader, rewriter: Rewriter, top_k: int, max_attempts: int,
                generate: Optional[Callable] = None, human_review: bool = False,
                checkpointer=None):
    """Wire the nodes and edges, and compile.

    `human_review` is a build-time flag rather than a runtime one because it
    changes the topology: with it off there is no `review` node to pause at, and
    the demo's bulk comparison must not stop nine times to ask permission.
    """

    def retrieve_node(state: AgentState) -> dict:
        docs = rag_core.retrieve(retrieve_node.retriever, state["query"], top_k)
        return {
            "docs": docs,
            "sources": rag_core.sources(docs),
            "retrievals": 1,
            "trace": [f"retrieve  attempt={state['attempt']} query={state['query']!r} "
                      f"-> {rag_core.sources(docs)}"],
        }

    def grade_node(state: AgentState) -> dict:
        grade = grader.grade(state["question"], state["query"], state["docs"])
        return {
            "grade": grade,
            "grades": 1,
            "trace": [f"grade     {grade['verdict']} score={grade['score']} - {grade['reason']}"],
        }

    def rewrite_node(state: AgentState) -> dict:
        old = state["query"]
        new = rewriter.rewrite(state["question"], old, state["grade"]["missing"])
        if new == old:
            # Same reasoning as loop_agent: a cycle that cannot change its own
            # input has nothing left to try. Route straight to abstain rather
            # than spending another identical retrieval on it.
            return {"rewrites": 1,
                    "trace": ["abstain   rewrite changed nothing - no point asking again"]}
        return {
            "query": new, "attempt": state["attempt"] + 1, "rewrites": 1,
            "trace": [f"rewrite   {old!r} -> {new!r}  (missing {state['grade']['missing']})"],
        }

    def review_node(state: AgentState) -> dict:
        """Stop, and hand a human everything they need to judge the answer.

        The payload IS the review packet. That is why this uses the dynamic
        `interrupt()` rather than `interrupt_before=["generate"]`: the static form
        pauses without telling the reviewer anything, and a human approving a
        grounded answer needs to see the evidence it is grounded in.
        """
        decision = interrupt({
            "question": state["question"],
            "query_used": state["query"],
            "attempts": state["attempt"],
            "citations": state["sources"],
            "evidence": [d["text"][:200] for d in state["docs"]],
            "ask": "approve | veto | edit:<new query>",
        })
        out = {"decision": decision, "trace": [f"review    human said {decision!r}"]}
        if isinstance(decision, str) and decision.startswith("edit:"):
            # The reviewer did not just approve or refuse - they handed back a
            # better query. That re-enters the cycle at `retrieve`, which is a
            # second way into the loop and the reason `review` earns a node
            # rather than being a flag on `generate`.
            edited = decision[len("edit:"):].strip()
            if edited:
                out["query"] = edited
                out["attempt"] = state["attempt"] + 1
                out["trace"] = [f"review    human rewrote the query -> {edited!r}"]
        return out

    def generate_node(state: AgentState) -> dict:
        answer = generate(state["question"], state["docs"]) if generate else ""
        return {
            "answer": answer, "status": "answered",
            "turns": [{"question": state["question"], "query": state["query"],
                       "sources": state["sources"], "status": "answered"}],
            "trace": [f"generate  grounded on {state['sources']}"],
        }

    def abstain_node(state: AgentState) -> dict:
        return {
            "answer": rag_core.ABSTAIN_TEXT, "status": "abstained", "sources": [],
            "turns": [{"question": state["question"], "query": state["query"],
                       "sources": [], "status": "abstained"}],
            "trace": ["abstain   nothing in the corpus supports an answer"],
        }

    def veto_node(state: AgentState) -> dict:
        return {
            "answer": "A reviewer vetoed this answer before it was generated.",
            "status": "vetoed",
            "turns": [{"question": state["question"], "query": state["query"],
                       "sources": state["sources"], "status": "vetoed"}],
            "trace": ["veto      reviewer stopped the run before generate"],
        }

    def route_after_grade(state: AgentState) -> str:
        if state["grade"]["verdict"] == "grounded":
            return "review" if human_review else "generate"
        if state["attempt"] >= max_attempts:
            # The cap is a decision, not a crash. It produces a good answer -
            # "not in your documents" - rather than an exception.
            return "abstain"
        return "rewrite"

    def route_after_review(state: AgentState) -> str:
        decision = (state.get("decision") or "approve")
        if decision == "veto":
            return "veto"
        if decision.startswith("edit:"):
            return "retrieve"
        return "generate"

    builder = StateGraph(AgentState)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("grade", grade_node)
    builder.add_node("rewrite", rewrite_node)
    builder.add_node("generate", generate_node)
    builder.add_node("abstain", abstain_node)
    if human_review:
        builder.add_node("review", review_node)
        builder.add_node("veto", veto_node)

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "grade")
    targets = {"rewrite": "rewrite", "generate": "generate", "abstain": "abstain"}
    if human_review:
        targets["review"] = "review"
    builder.add_conditional_edges("grade", route_after_grade, targets)
    builder.add_conditional_edges("rewrite", _rewrite_router,
                                  {"retrieve": "retrieve", "abstain": "abstain"})
    if human_review:
        builder.add_conditional_edges("review", route_after_review,
                                      {"generate": "generate", "retrieve": "retrieve",
                                       "veto": "veto"})
        builder.add_edge("veto", END)
    builder.add_edge("generate", END)
    builder.add_edge("abstain", END)

    graph = builder.compile(checkpointer=checkpointer)
    graph._retrieve_node = retrieve_node  # so run() can attach the retriever
    return graph


def _rewrite_router(state: AgentState) -> str:
    """After a rewrite: go round again, or give up.

    `rewrite_node` signals "nothing left to try" by leaving the query unchanged,
    which is the one case where the back-edge must NOT be taken.
    """
    last = state["trace"][-1] if state.get("trace") else ""
    return "abstain" if last.startswith("abstain") else "retrieve"


def run(graph, retriever, question: str, *, config: Optional[dict] = None,
        resume: Optional[str] = None) -> dict:
    """Invoke the graph for one question and normalise the result.

    The return shape is identical to `loop_agent.run`'s, on purpose: the keystone
    test compares the two dicts field for field.
    """
    graph._retrieve_node.retriever = retriever
    cfg = config or {"configurable": {"thread_id": "lesson8"}}
    if resume is not None:
        state = graph.invoke(Command(resume=resume), cfg)
    else:
        state = graph.invoke(
            {"question": question, "query": question, "attempt": 1,
             "retrievals": 0, "grades": 0, "rewrites": 0, "trace": [], "turns": []},
            cfg,
        )
    return _normalise(state)


def _normalise(state: dict) -> dict:
    grade = state.get("grade")
    verdicts = [ln.split()[1] for ln in state.get("trace", []) if ln.startswith("grade ")]
    return {
        "question": state.get("question", ""), "query": state.get("query", ""),
        "attempts": state.get("attempt", 1),
        "retrievals": state.get("retrievals", 0), "grades": state.get("grades", 0),
        "rewrites": state.get("rewrites", 0),
        "sources": state.get("sources", []) if state.get("status") == "answered" else [],
        "verdicts": verdicts, "grade": grade, "docs": state.get("docs", []),
        "status": state.get("status", "paused"), "answer": state.get("answer", ""),
        "trace": state.get("trace", []), "turns": state.get("turns", []),
        "__interrupt__": state.get("__interrupt__"),
    }


def topology(graph) -> tuple:
    """The nodes and edges, as data. This is the thing a `while` loop cannot answer."""
    g = graph.get_graph()
    nodes = sorted(n for n in g.nodes)
    edges = sorted((e.source, e.target) for e in g.edges)
    return nodes, edges


def memory_saver():
    """The default checkpointer: in-process, and leaves nothing on disk.

    `SqliteSaver` lives in a separate package (`langgraph-checkpoint-sqlite`).
    Making it the default would inflate the exact dependency bill this lesson is
    measuring, and would write a database into your working tree every time you
    ran the demo. It is worth reaching for - see `--sqlite` - but not by default.
    """
    return MemorySaver()
