"""Lesson 8 - a stateful agent with LangGraph, and what the graph is actually worth.

Three arms over Lesson 7's corpus, with the same settings and the same citation
contract, arguing about one thing only: control flow.

  linear   retrieve once, answer.                     Lesson 1 and Lesson 7's shape.
  loop     retrieve, grade, rewrite, retry.           63 lines of `while`.
  graph    the same loop as a LangGraph StateGraph.   Plus checkpoints and interrupts.

Run:
  ./run -l 8                     the playground (default)
  ./run -l 8 demo                the three-arm comparison and the scorecard
  ./run -l 8 trace "question"    one question, every attempt, verbose
  ./run -l 8 chat "q1" "q2"      two turns on one thread - the memory
  ./run -l 8 review "question"   pause and decide, interactively
  ./run -l 8 spread "question"   run the LLM grader N times and watch it disagree
  ./run -l 8 ask "question"      a real, grounded answer through the graph
  ./run -l 8 demo --llm-grade    the grader you should actually use

PRODUCTION (see the lesson README, "From demo to production"):
  pin langgraph exactly; give the checkpointer real storage AND a retention
  policy, because a checkpoint is a copy of your users' questions and your
  documents' text; make thread_id a real identity; cap attempts and set
  recursion_limit; log every Grade with its reason so the LLM grader's spread
  becomes a metric instead of a mystery.
"""

from __future__ import annotations

import ast
import io
import sys
import tokenize
from pathlib import Path
from typing import List, Optional

import graders
import loop_agent
import rag_core
import rewriter

LESSON_DIR = Path(__file__).resolve().parent.parent
ROOT = rag_core.ROOT

INSTALL_HINT = "pip install -r lessons/08-langgraph/requirements.txt"
SQLITE_HINT = "pip install langgraph-checkpoint-sqlite"

# Only these mean "LangGraph is not installed". A NameError in our own code must
# propagate, not send the reader off to reinstall something they already have.
LANGGRAPH_PACKAGES = ("langgraph", "langgraph.graph", "langgraph.types",
                      "langgraph.checkpoint.memory")

# Dependency numbers, measured with `pip download` against this repo's own
# requirements. `--measure` re-derives them on your machine; if these drift, the
# file is wrong and the command is right.
DEPS = {
    # Arms A and B are the course baseline: localrag and nothing else.
    "linear": {"direct": 0, "packages": 48, "size_mb": 34},
    "loop": {"direct": 0, "packages": 48, "size_mb": 34},
    "graph": {"direct": 1, "packages": 71, "size_mb": 43},
}
# Lesson 7's bill, for the sentence about what LangGraph costs on top of it.
DEPS_LESSON7 = {"packages": 67, "size_mb": 42}
# The same measurement with BOTH Lesson 7's requirements and langgraph installed.
DEPS_L7_PLUS_GRAPH = {"packages": 72, "size_mb": 43}

# What each arm actually needs on disk. The linear arm needs no grader and no
# rewriter, so counting them against it would flatter the loop.
ARM_FILES = {
    "linear": ["python/rag_core.py"],
    "loop": ["python/rag_core.py", "python/graders.py", "python/rewriter.py",
             "python/loop_agent.py"],
    "graph": ["python/rag_core.py", "python/graders.py", "python/rewriter.py",
              "python/loop_agent.py", "python/graph_agent.py"],
}


# --------------------------------------------------------------------------- measuring
def code_lines(path: Path) -> int:
    """Lines that are actually code: no blanks, no comments, no docstrings.

    Every arm is counted the same way, so a file full of teaching commentary is
    not unfairly penalised against a terse one.
    """
    source = path.read_text(encoding="utf-8")
    doc_lines = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    doc_lines.update(range(body[0].lineno, body[0].end_lineno + 1))
    counted = set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                        tokenize.DEDENT, tokenize.ENDMARKER, tokenize.ENCODING):
            continue
        if tok.start[0] not in doc_lines:
            counted.add(tok.start[0])
    return len(counted)


def total_lines(rel_paths: List[str]) -> int:
    """Code lines across several lesson-relative files, read off disk at run time."""
    return sum(code_lines(LESSON_DIR / p) for p in rel_paths)


def import_graph_agent():
    """Import arm C, or return None when LangGraph simply is not installed."""
    try:
        import graph_agent
        return graph_agent
    except ModuleNotFoundError as exc:
        missing = (exc.name or "")
        if any(missing == p or p.startswith(missing + ".") for p in LANGGRAPH_PACKAGES):
            return None
        raise


# --------------------------------------------------------------------------- wiring
class Settings:
    """Everything the three arms are handed, so they are handed the same thing."""

    def __init__(self, args) -> None:
        q = rag_core.load_questions()
        self.questions = q["questions"]
        self.chunk_size = q["chunk_size"]
        self.chunk_overlap = q["chunk_overlap"]
        self.top_k = args.get("top_k") or q["top_k"]
        self.threshold = args.get("threshold") or q["grade_threshold"]
        self.max_attempts = args.get("max_attempts") or q["max_attempts"]
        self.llm_grade = args.get("llm_grade", False)
        self.llm_rewrite = args.get("llm_rewrite", False)
        self.provider = args.get("provider")

    def chat(self):
        """A `(system, user) -> str` callable for whichever provider is configured."""
        config = rag_core.lesson_config(self.provider)
        provider = rag_core.get_provider(config.provider, config)
        return lambda system, user: provider.chat(system, user)

    def grader(self):
        if not self.llm_grade:
            return graders.make_grader("coverage", self.threshold)
        label = f"llm:{self.provider or rag_core.lesson_config().provider}"
        return graders.make_grader("llm", self.threshold, chat=self.chat(), label=label)

    def rewriter(self):
        if not self.llm_rewrite:
            return rewriter.make_rewriter("glossary")
        label = f"llm:{self.provider or rag_core.lesson_config().provider}"
        return rewriter.make_rewriter("llm", chat=self.chat(), label=label)

    def retriever(self):
        return rag_core.build_retriever(self.chunk_size, self.chunk_overlap)


def scored(result: dict, expect: Optional[str]) -> bool:
    """The pass rule: the top citation is the expected file, or the arm abstained.

    Strict and single-source, and derived from retrieval alone - never from
    generated prose, which could not be diffed by a test.
    """
    if expect is None:
        return result["status"] == "abstained"
    return result["sources"][:1] == [f"{expect}:1"]


# --------------------------------------------------------------------------- demo
def cmd_demo(settings: Settings) -> int:
    ga = import_graph_agent()
    retriever = settings.retriever()
    grader, rw = settings.grader(), settings.rewriter()

    print("Lesson 8 · A stateful agent with LangGraph")
    print(f"corpus: {rag_core.CORPUS_DIR.relative_to(ROOT)}  "
          f"({len(list(rag_core.CORPUS_DIR.glob('*.md')))} documents - Lesson 7's, by path)")
    print(f"settings: top_k={settings.top_k} threshold={settings.threshold} "
          f"max_attempts={settings.max_attempts} grader={grader.name} rewriter={rw.name}")
    print()

    graph = None
    if ga is not None:
        graph = ga.build_graph(grader=grader, rewriter=rw, top_k=settings.top_k,
                               max_attempts=settings.max_attempts,
                               checkpointer=ga.memory_saver())

    print("Nine questions. Three arms. The same corpus and the same settings.")
    print()
    header = f"  {'':4} {'linear':<7} {'loop':<7} {'graph':<7} {'att':<4} {'question'}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    rows = []
    for i, item in enumerate(settings.questions):
        expect = item["expect"]
        lin = loop_agent.run_linear(retriever, item["ask"], top_k=settings.top_k)
        lop = loop_agent.run(retriever, item["ask"], grader=grader, rewriter=rw,
                             top_k=settings.top_k, max_attempts=settings.max_attempts)
        grp = None
        if graph is not None:
            grp = ga.run(graph, retriever, item["ask"],
                         config={"configurable": {"thread_id": f"demo-{item['id']}"}})
        mark = lambda ok: "PASS" if ok else "FAIL"  # noqa: E731
        gcell = mark(scored(grp, expect)) if grp else "  - "
        print(f"  {item['id']:4} {mark(scored(lin, expect)):<7} {mark(scored(lop, expect)):<7} "
              f"{gcell:<7} {lop['attempts']:<4} {item['ask']}")
        rows.append((item, lin, lop, grp))

    print()
    print("  why each question is here")
    for item, _, _, _ in rows:
        print(f"    {item['id']}  {item['why']}")

    _print_scorecard(settings, rows, graph is not None)
    if graph is not None:
        # Print the FULL topology, review node included, so it matches the diagram
        # in the README. The comparison above ran without review so it would not
        # stop nine times to ask permission.
        _print_topology(ga, ga.build_graph(
            grader=grader, rewriter=rw, top_k=settings.top_k,
            max_attempts=settings.max_attempts, human_review=True,
            checkpointer=ga.memory_saver()))
        _print_human_in_the_loop(ga, settings, retriever, grader, rw)
        _print_memory(ga, settings, retriever, grader, rw)
    else:
        print()
        print("The graph arm")
        print("  LangGraph is not installed, so the third column is blank. Everything")
        print("  above still ran: the accuracy result belongs to the LOOP, and the loop")
        print("  needs no dependency at all - which is itself the lesson's main finding.")
        print(f"  To see the rest:  {INSTALL_HINT}")

    _print_bill(graph is not None)
    print()
    print("grader: coverage (deterministic). Run with --llm-grade for the grader you")
    print("should actually use; it will not print the same thing twice, and that is the point.")
    return 0


def _print_scorecard(settings: Settings, rows, has_graph: bool) -> None:
    answerable = [r for r in rows if r[0]["expect"] is not None]
    unanswerable = [r for r in rows if r[0]["expect"] is None]

    def tally(idx):
        ok = sum(1 for r in answerable if scored(r[idx], r[0]["expect"]))
        ab = sum(1 for r in unanswerable if scored(r[idx], r[0]["expect"]))
        ret = sum(r[idx]["retrievals"] for r in rows)
        gra = sum(r[idx]["grades"] for r in rows)
        rew = sum(r[idx]["rewrites"] for r in rows)
        return ok, ab, ret, gra, rew

    lin = tally(1)
    lop = tally(2)
    grp = tally(3) if has_graph else None
    n, m = len(answerable), len(unanswerable)

    def col(v):
        return f"{v:>18}"

    print()
    print("The scorecard")
    print(f"  {'':26}{col('linear (L7)')}{col('loop (while)')}{col('graph (LangGraph)')}")
    print(f"  {'top source correct':26}{col(f'{lin[0]}/{n}')}{col(f'{lop[0]}/{n}')}"
          f"{col(f'{grp[0]}/{n}' if grp else '-')}")
    print(f"  {'correctly abstained':26}{col(f'{lin[1]}/{m}')}{col(f'{lop[1]}/{m}')}"
          f"{col(f'{grp[1]}/{m}' if grp else '-')}")
    print("  " + "-" * 80)
    pct = round((lop[2] - lin[2]) / lin[2] * 100)
    print(f"  {'retrieval calls':26}{col(lin[2])}{col(f'{lop[2]}  (+{pct}%)')}"
          f"{col(f'{grp[2]}' if grp else '-')}")
    print(f"  {'grade calls':26}{col(lin[3])}{col(lop[3])}{col(grp[3] if grp else '-')}")
    print(f"  {'rewrite calls':26}{col(lin[4])}{col(lop[4])}{col(grp[4] if grp else '-')}")
    print("  " + "-" * 80)
    print(f"  {'state survives a process':26}{col('-')}{col('-')}"
          f"{col('checkpointer' if grp else '-')}")
    print(f"  {'pause / resume mid-run':26}{col('-')}{col('-')}"
          f"{col('interrupt()' if grp else '-')}")
    print(f"  {'topology you can query':26}{col('-')}{col('-')}"
          f"{col('get_graph()' if grp else '-')}")

    fixed = [r[0]["id"] for r in answerable
             if scored(r[2], r[0]["expect"]) and not scored(r[1], r[0]["expect"])]
    wasted = [r[0]["id"] for r in answerable
              if scored(r[1], r[0]["expect"]) and r[2]["attempts"] > 1]
    print()
    print(f"  The loop fixed {len(fixed)} questions the chain got wrong ({', '.join(fixed)}), and")
    print(f"  refused the {len(unanswerable)} it could not answer at all "
          f"- for {pct}% more retrieval calls.")
    if wasted:
        print(f"  {', '.join(wasted)} was already right on the first try and looped anyway: "
              f"a retrieval that bought nothing.")
    if grp:
        same = grp[:5] == lop[:5]
        print()
        print(f"  The while loop and the graph agree on all {len(rows)} questions: "
              f"{'exactly' if same else 'NOT - one of them has drifted'}.")
        print("  LangGraph did not make the agent smarter. It made it resumable,")
        print("  pausable and inspectable - the three rows above that only it can fill.")


def _print_topology(ga, graph) -> None:
    nodes, edges = ga.topology(graph)
    print()
    print("The topology, as data")
    print(f"  nodes  {[n for n in nodes if not n.startswith('__')]}")
    print("  edges")
    for src, dst in edges:
        back = "   <- the cycle" if (src, dst) == ("rewrite", "retrieve") else ""
        print(f"    {src:10} -> {dst}{back}")
    print()
    print("  A while loop cannot answer the question 'what are your edges?' at runtime.")
    print("  Its control flow is `if` and `while`; this one is a value you can print.")


def _print_human_in_the_loop(ga, settings, retriever, grader, rw) -> None:
    question = "How do I wipe the device and start over?"
    graph = ga.build_graph(grader=grader, rewriter=rw, top_k=settings.top_k,
                           max_attempts=settings.max_attempts, human_review=True,
                           generate=lambda q, d: "(a grounded answer would be generated here)",
                           checkpointer=ga.memory_saver())
    print()
    print("Human in the loop")
    print(f"  question: {question!r}")
    print("  This question matters: the manual says a factory reset destroys the logging")
    print("  buffer permanently, and the warranty page says a claim without that export")
    print("  cannot be assessed. Answering helpfully and immediately costs the reader")
    print("  their evidence. So the graph stops and asks.")
    print()
    cfg = {"configurable": {"thread_id": "demo-hitl"}}
    paused = ga.run(graph, retriever, question, config=cfg)
    snap = graph.get_state(cfg)
    payload = paused["__interrupt__"][0].value
    print("  invoke #1 ->  the graph STOPPED. It did not answer.")
    print(f"                status              {paused['status']}")
    print(f"                get_state().next    {snap.next}")
    print(f"                answer in state?    {bool(snap.values.get('answer'))}")
    print(f"                review packet       citations={payload['citations']}")
    print(f"                                    attempts={payload['attempts']}  "
          f"ask={payload['ask']!r}")
    print(f"                retrievals so far   {paused['retrievals']}")
    approved = ga.run(graph, retriever, question, config=cfg, resume="approve")
    print()
    print("  invoke #2 ->  Command(resume='approve') on the same thread_id")
    print(f"                retrievals now      {approved['retrievals']}"
          f"      <- unchanged. It resumed; it did not restart.")
    print(f"                status              {approved['status']}")
    vcfg = {"configurable": {"thread_id": "demo-hitl-veto"}}
    ga.run(graph, retriever, question, config=vcfg)
    vetoed = ga.run(graph, retriever, question, config=vcfg, resume="veto")
    print()
    print("  invoke #2' -> Command(resume='veto') on a fresh thread")
    print(f"                status              {vetoed['status']} - "
          f"generate never ran")
    ecfg = {"configurable": {"thread_id": "demo-hitl-edit"}}
    ga.run(graph, retriever, question, config=ecfg)
    edited = ga.run(graph, retriever, question, config=ecfg,
                    resume="edit:warranty claim form serial number")
    print()
    print("  invoke #2'' -> Command(resume='edit:...') - the reviewer hands back a query")
    print(f"                retrievals now      {edited['retrievals']}"
          f"      <- it re-entered the cycle at retrieve")
    print("                a second way into the loop, which is why review is a node")


def _print_memory(ga, settings, retriever, grader, rw) -> None:
    graph = ga.build_graph(grader=grader, rewriter=rw, top_k=settings.top_k,
                           max_attempts=settings.max_attempts,
                           checkpointer=ga.memory_saver())
    print()
    print("Memory - two turns on one thread")
    turns = ["What is the factory reset procedure?",
             "Which endpoint exports the logging buffer?"]
    cfg = {"configurable": {"thread_id": "aurora"}}
    for q in turns:
        res = ga.run(graph, retriever, q, config=cfg)
        print(f"  thread 'aurora'  turn {len(res['turns'])}  {q}")
        print(f"                   cited {res['sources']}")
    fresh = ga.run(graph, retriever, turns[0],
                   config={"configurable": {"thread_id": "somebody-else"}})
    print(f"  thread 'somebody-else'  turn {len(fresh['turns'])}  "
          f"<- a different thread_id remembers nothing")
    print(f"  checkpoints written on 'aurora': {len(list(graph.get_state_history(cfg)))}")
    print()
    print("  MemorySaver keeps this in the process. For state that outlives the process:")
    print(f"    {SQLITE_HINT}")
    print("    ./run -l 8 chat --sqlite /tmp/aurora.db --thread aurora \"...\"")
    print("  It is a separate package on purpose - see the bill below.")


def _print_bill(has_graph: bool) -> None:
    lin_l = total_lines(ARM_FILES["linear"])
    loop_l = total_lines(ARM_FILES["loop"])
    graph_l = total_lines(ARM_FILES["graph"]) if has_graph else 0

    def col(v):
        return f"{v:>18}"

    print()
    print("What it cost")
    print(f"  {'':26}{col('linear')}{col('loop (while)')}{col('graph (LangGraph)')}")
    print(f"  {'code you maintain':26}{col(f'{lin_l} lines')}{col(f'{loop_l} lines')}"
          f"{col(f'{graph_l} lines' if has_graph else '-')}")
    print(f"  {'requirements lines':26}{col(DEPS['linear']['direct'])}"
          f"{col(DEPS['loop']['direct'])}{col(DEPS['graph']['direct'])}")
    print(f"  {'packages installed':26}{col(DEPS['linear']['packages'])}"
          f"{col(DEPS['loop']['packages'])}{col(DEPS['graph']['packages'])}")
    sizes = [DEPS[a]["size_mb"] for a in ("linear", "loop", "graph")]
    print(f"  {'install size':26}" + "".join(col(f"~{n} MB") for n in sizes))
    print()
    loop_only = code_lines(LESSON_DIR / "python/loop_agent.py")
    graph_only = code_lines(LESSON_DIR / "python/graph_agent.py")
    added = loop_l - lin_l
    print(f"  The corrective loop cost {added} lines and ZERO packages, and it delivered")
    print("  the entire accuracy gain in the scorecard above. Most of those lines are the")
    print("  grader and the rewriter, which the graph needs too. The loop ITSELF is")
    print(f"  {loop_only} lines of `while`.")
    alone = DEPS["graph"]["packages"] - DEPS["linear"]["packages"]
    print()
    print(f"  Swapping those {loop_only} lines for LangGraph cost {graph_only} lines of graph")
    print(f"  wiring and {alone} packages - for answers that are identical on all nine")
    print("  questions. What it bought is the three rows the loop could not fill:")
    print("  checkpoints, interrupts, and a topology you can query.")
    on_top = DEPS_L7_PLUS_GRAPH["packages"] - DEPS_LESSON7["packages"]
    print(f"  If you already did Lesson 7 it is only {on_top} more packages "
          f"({DEPS_LESSON7['packages']} -> {DEPS_L7_PLUS_GRAPH['packages']}),")
    print("  because LangGraph depends on langchain-core and you are already paying for it.")
    print("  Which of those two numbers applies to you is the whole question.")



# --------------------------------------------------------------------------- trace
def cmd_trace(settings: Settings, question: str, recursion_limit: Optional[int]) -> int:
    """One question, every attempt, with the reasoning printed as it happens."""
    ga = import_graph_agent()
    retriever = settings.retriever()
    grader, rw = settings.grader(), settings.rewriter()
    print(f"question: {question!r}")
    print(f"grader:   {grader.name}    rewriter: {rw.name}    "
          f"top_k={settings.top_k} threshold={settings.threshold} "
          f"max_attempts={settings.max_attempts}")
    print()
    if ga is None or recursion_limit is None:
        result = loop_agent.run(retriever, question, grader=grader, rewriter=rw,
                                top_k=settings.top_k, max_attempts=settings.max_attempts)
        for line in result["trace"]:
            print("  " + line)
        print()
        print(f"  status={result['status']}  attempts={result['attempts']}  "
              f"retrievals={result['retrievals']}  sources={result['sources']}")
        if ga is None:
            print()
            print(f"  (LangGraph is not installed; this ran the while-loop arm. {INSTALL_HINT})")
        return 0

    # With an explicit --recursion-limit, run the GRAPH so the framework's own cap
    # can fire. This is the one place the two arms deliberately differ, because
    # only the graph has a recursion limit to hit.
    from langgraph.errors import GraphRecursionError
    graph = ga.build_graph(grader=grader, rewriter=rw, top_k=settings.top_k,
                           max_attempts=settings.max_attempts,
                           checkpointer=ga.memory_saver())
    cfg = {"configurable": {"thread_id": "trace"}, "recursion_limit": recursion_limit}
    try:
        result = ga.run(graph, retriever, question, config=cfg)
    except GraphRecursionError:
        print(f"  GraphRecursionError after {recursion_limit} steps - the framework's")
        print("  floor, not your ceiling.")
        print(f"  Your max_attempts={settings.max_attempts} would have abstained cleanly.")
        print("  An agent without a domain cap is an infinite loop with an invoice.")
        print()
        print("  Two caps, and they are not the same thing:")
        print("    max_attempts     yours, domain logic. Hitting it produces a good")
        print("                     answer: 'not in your documents'.")
        print("    recursion_limit  LangGraph's, structural. Hitting it raises. It is")
        print("                     there to stop a graph whose ROUTING is wrong, not")
        print("                     one whose SEARCH is failing.")
        return 0
    for line in result["trace"]:
        print("  " + line)
    print()
    print(f"  status={result['status']}  attempts={result['attempts']}  "
          f"retrievals={result['retrievals']}  sources={result['sources']}")
    return 0


# --------------------------------------------------------------------------- chat
def cmd_chat(settings: Settings, questions: List[str], thread: str,
             sqlite_path: Optional[str]) -> int:
    """Several turns on one thread, so the checkpoint has something to remember."""
    ga = import_graph_agent()
    if ga is None:
        print("Memory needs LangGraph - it is the checkpointer that remembers.")
        print(f"  {INSTALL_HINT}")
        return 0
    checkpointer, closer = _checkpointer(ga, sqlite_path)
    try:
        retriever = settings.retriever()
        graph = ga.build_graph(grader=settings.grader(), rewriter=settings.rewriter(),
                               top_k=settings.top_k, max_attempts=settings.max_attempts,
                               checkpointer=checkpointer)
        cfg = {"configurable": {"thread_id": thread}}
        for q in questions:
            res = ga.run(graph, retriever, q, config=cfg)
            print(f"turn {len(res['turns'])} on thread {thread!r}: {q}")
            print(f"  status={res['status']}  cited {res['sources']}")
        state = graph.get_state(cfg)
        print()
        print(f"thread {thread!r} now holds {len(state.values.get('turns', []))} turns.")
        if sqlite_path:
            print(f"They are on disk at {sqlite_path}. Run this command again and the")
            print("count keeps going up - the state outlived the process.")
        else:
            print("They are in memory. Run this command again and the count starts at 1:")
            print("MemorySaver does not outlive the process. Add --sqlite PATH if it should.")
    finally:
        closer()
    return 0


def _checkpointer(ga, sqlite_path: Optional[str]):
    """MemorySaver by default; SqliteSaver only when asked for, and only if present."""
    if not sqlite_path:
        return ga.memory_saver(), lambda: None
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ModuleNotFoundError:
        print(f"--sqlite needs a separate package:  {SQLITE_HINT}")
        print("Falling back to MemorySaver, which does not survive this process.")
        return ga.memory_saver(), lambda: None
    ctx = SqliteSaver.from_conn_string(sqlite_path)
    saver = ctx.__enter__()
    return saver, lambda: ctx.__exit__(None, None, None)


# --------------------------------------------------------------------------- review
def cmd_review(settings: Settings, question: str) -> int:
    """The interrupt, on real stdin. No model needed - the grader is deterministic."""
    ga = import_graph_agent()
    if ga is None:
        print(f"Pausing mid-run needs LangGraph.  {INSTALL_HINT}")
        return 0
    retriever = settings.retriever()
    graph = ga.build_graph(grader=settings.grader(), rewriter=settings.rewriter(),
                           top_k=settings.top_k, max_attempts=settings.max_attempts,
                           human_review=True,
                           generate=lambda q, d: "(a grounded answer would be generated here)",
                           checkpointer=ga.memory_saver())
    cfg = {"configurable": {"thread_id": "review"}}
    result = ga.run(graph, retriever, question, config=cfg)
    while result["status"] == "paused":
        payload = result["__interrupt__"][0].value
        print()
        print("The graph has stopped and is waiting for you.")
        print(f"  question   {payload['question']}")
        print(f"  query used {payload['query_used']!r} after {payload['attempts']} attempt(s)")
        print(f"  citations  {payload['citations']}")
        for snippet in payload["evidence"]:
            print(f"    - {snippet[:120]}...")
        print(f"  retrievals so far: {result['retrievals']}")
        try:
            decision = input("\napprove / veto / edit:<new query> > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n(no decision given - leaving the run paused, which is a valid state)")
            return 0
        result = ga.run(graph, retriever, question, config=cfg, resume=decision or "approve")
        print(f"  -> status={result['status']}  retrievals={result['retrievals']}")
    print()
    print(f"final: {result['status']}  cited {result['sources']}")
    return 0


# --------------------------------------------------------------------------- spread
def cmd_spread(settings: Settings, question: str, runs: int) -> int:
    """Run the LLM grader N times on identical evidence and print the disagreement.

    This is the lesson's argument for --llm-grade made honestly: the better grader
    is the one that will not print the same thing twice, and pretending otherwise
    would be the sort of thing this course exists to argue against.
    """
    retriever = settings.retriever()
    docs = rag_core.retrieve(retriever, question, settings.top_k)
    coverage = graders.CoverageGrader(settings.threshold)
    print(f"question: {question!r}")
    print(f"evidence: {rag_core.sources(docs)}   (identical for every run below)")
    print()
    label = f"llm:{settings.provider or rag_core.lesson_config().provider}"
    try:
        llm = graders.make_grader("llm", settings.threshold, chat=settings.chat(), label=label)
    except Exception as exc:
        print(f"Could not reach a provider ({type(exc).__name__}).")
        print("This command needs a model - it is the one thing in this lesson that does.")
        return 1
    verdicts, reasons = [], {}
    for i in range(runs):
        grade = llm.grade(question, question, docs)
        verdicts.append(grade["verdict"])
        reasons[grade["reason"]] = reasons.get(grade["reason"], 0) + 1
        print(f"  run {i + 1}: {grade['verdict']:<9} {grade['reason'][:70]}")
    print()
    print(f"The LLM grader, run {runs} times on the same question and the same chunks")
    for v in ("grounded", "weak"):
        n = verdicts.count(v)
        bar = "#" * n + "." * (runs - n)
        print(f"  {v.upper():<9} {bar}  {n}/{runs}")
    print()
    print("  distinct reasons given")
    for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"    {n}x  {reason[:74]}")
    det = coverage.grade(question, question, docs)
    print()
    print(f"  the deterministic grader, run {runs} times:  {det['verdict'].upper()} "
          f"{runs}/{runs}   (coverage {det['score']}, missing {det['missing']})")
    print()
    if len(set(verdicts)) > 1:
        print("  Both graders are defensible here. Only one of them can be committed to a")
        print("  file and diffed by a test - which is the ONLY reason it is the default.")
    else:
        print("  It agreed with itself this time. Run it again, or raise --runs: the")
        print("  point is not that it always disagrees, it is that you cannot rely on it not to.")
    print("  Use --llm-grade for your own documents. It is the better grader.")
    return 0


# --------------------------------------------------------------------------- ask
def cmd_ask(settings: Settings, question: str) -> int:
    """A real, grounded answer, produced through whichever arm is available."""
    ga = import_graph_agent()
    config = rag_core.lesson_config(settings.provider)
    retriever = settings.retriever()

    def generate(q, docs):
        return rag_core.answer(config, q, docs)

    grader, rw = settings.grader(), settings.rewriter()
    if ga is None:
        result = loop_agent.run(retriever, question, grader=grader, rewriter=rw,
                                top_k=settings.top_k, max_attempts=settings.max_attempts,
                                generate=generate)
    else:
        graph = ga.build_graph(grader=grader, rewriter=rw, top_k=settings.top_k,
                               max_attempts=settings.max_attempts, generate=generate,
                               checkpointer=ga.memory_saver())
        result = ga.run(graph, retriever, question)
    for line in result["trace"]:
        print("  " + line)
    print()
    print(result["answer"])
    if result["sources"]:
        print()
        print("Sources: " + ", ".join(result["sources"]))
    return 0


# --------------------------------------------------------------------------- measure
def cmd_measure(settings: Settings) -> int:
    """Re-derive the dependency numbers on this machine, rather than trusting the file."""
    from importlib.metadata import PackageNotFoundError, distribution, requires
    print("Measured here, now:")
    ga = import_graph_agent()
    print(f"  langgraph installed:      {'yes' if ga else 'no'}")
    if ga is None:
        print(f"  {INSTALL_HINT}")
        return 0

    seen, queue = set(), ["langgraph"]
    while queue:
        name = queue.pop().lower().replace("_", "-")
        if name in seen:
            continue
        try:
            distribution(name)
        except PackageNotFoundError:
            continue
        seen.add(name)
        for req in (requires(name) or []):
            if "extra ==" in req:
                continue
            dep = req.split(";")[0].split("[")[0].strip()
            dep = dep.split("<")[0].split(">")[0].split("=")[0].split("!")[0].split("~")[0]
            if dep.strip():
                queue.append(dep.strip())
    print(f"  langgraph's dependency closure: {len(seen)} distributions")
    print(f"    {', '.join(sorted(seen))}")
    print()
    print("  Note langsmith in that list. LangChain's hosted tracing client installs")
    print("  as a transitive dependency whether you asked for it or not. It is inert")
    print("  until you set LANGSMITH_TRACING - see the README, Concept 7.")
    try:
        from langsmith.utils import tracing_is_enabled
        print(f"  tracing_is_enabled() right now: {tracing_is_enabled()}")
    except Exception:
        pass
    print()
    print("  code you maintain, counted off disk:")
    for arm in ("linear", "loop", "graph"):
        print(f"    {arm:8} {total_lines(ARM_FILES[arm]):>4} lines")
    print()
    print("  If these disagree with the numbers the demo prints, the file is stale")
    print("  and this command is right.")
    return 0


def cmd_graph(settings: Settings) -> int:
    """Print the topology. The whole point is that this is possible at all."""
    ga = import_graph_agent()
    if ga is None:
        print(f"Needs LangGraph.  {INSTALL_HINT}")
        return 0
    graph = ga.build_graph(grader=settings.grader(), rewriter=settings.rewriter(),
                           top_k=settings.top_k, max_attempts=settings.max_attempts,
                           human_review=True, checkpointer=ga.memory_saver())
    _print_topology(ga, graph)
    return 0


# --------------------------------------------------------------------------- CLI
ACTIONS = ("demo", "trace", "chat", "review", "spread", "ask", "measure", "graph")
PROVIDERS = ("claude", "ollama", "gemini", "openai")

USAGE = """\
usage: langgraph_agent.py [action] [question ...] [flags]

actions
  demo                  the three-arm comparison and the scorecard (default)
  trace "question"      one question, every attempt
  chat "q1" ["q2" ...]  several turns on one thread - the memory
  review "question"     pause mid-run and decide, interactively
  spread "question"     run the LLM grader N times and watch it disagree
  ask "question"        a real, grounded answer through the graph
  measure               re-derive the dependency numbers here
  graph                 print the topology as data

flags
  --llm-grade           grade with a model (recommended for real documents)
  --llm-rewrite         rewrite the query with a model
  --llm                 both of the above
  --provider NAME       claude | ollama | gemini | openai
  --top-k N             chunks retrieved per attempt
  --threshold F         the grade pass mark, 0.0-1.0
  --max-attempts N      your cap: how many times the loop may re-search
  --recursion-limit N   LangGraph's cap; set it low to watch it fire
  --thread NAME         checkpoint thread id
  --sqlite PATH         checkpoint to disk instead of memory
  --runs N              how many times `spread` calls the grader
"""


def _die(message: str) -> None:
    """Exit 2 on a bad flag value rather than silently falling back to a default.

    A typo in `--provider ollma` that quietly runs Claude instead would make every
    number printed afterwards a lie about which provider produced it.
    """
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(2)


def _int(flag: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        _die(f"{flag} needs a whole number, got {raw!r}")


def parse(argv: List[str]) -> tuple:
    """Hand-rolled, like Lesson 7's - and, like Lesson 7's, strict about values."""
    opts = {"llm_grade": False, "llm_rewrite": False, "provider": None,
            "top_k": None, "threshold": None, "max_attempts": None,
            "recursion_limit": None, "thread": "lesson8", "sqlite": None, "runs": 5}
    action = None
    positional: List[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            print(USAGE)
            raise SystemExit(0)
        elif arg == "--llm-grade":
            opts["llm_grade"] = True
        elif arg == "--llm-rewrite":
            opts["llm_rewrite"] = True
        elif arg == "--llm":
            opts["llm_grade"] = opts["llm_rewrite"] = True
        elif arg in ("--provider", "--top-k", "--threshold", "--max-attempts",
                     "--recursion-limit", "--thread", "--sqlite", "--runs"):
            if i + 1 >= len(argv):
                _die(f"{arg} needs a value")
            value = argv[i + 1]
            i += 1
            if arg == "--provider":
                if value not in PROVIDERS:
                    _die(f"unknown provider {value!r}. Use: {' | '.join(PROVIDERS)}")
                opts["provider"] = value
            elif arg == "--top-k":
                opts["top_k"] = _int(arg, value)
            elif arg == "--threshold":
                try:
                    opts["threshold"] = float(value)
                except ValueError:
                    _die(f"--threshold needs a number between 0 and 1, got {value!r}")
                if not 0.0 <= opts["threshold"] <= 1.0:
                    _die(f"--threshold must be between 0 and 1, got {value}")
            elif arg == "--max-attempts":
                opts["max_attempts"] = _int(arg, value)
            elif arg == "--recursion-limit":
                opts["recursion_limit"] = _int(arg, value)
            elif arg == "--runs":
                opts["runs"] = _int(arg, value)
            elif arg == "--thread":
                opts["thread"] = value
            elif arg == "--sqlite":
                opts["sqlite"] = value
        elif arg.startswith("-"):
            _die(f"unknown flag {arg!r}. Try --help.")
        elif action is None and arg in ACTIONS:
            action = arg
        else:
            positional.append(arg)
        i += 1
    return action or "demo", positional, opts


def main(argv: Optional[List[str]] = None) -> int:
    action, positional, opts = parse(list(sys.argv[1:] if argv is None else argv))
    settings = Settings(opts)

    if action == "demo":
        return cmd_demo(settings)
    if action == "measure":
        return cmd_measure(settings)
    if action == "graph":
        return cmd_graph(settings)
    if action == "chat":
        if not positional:
            positional = ["What is the factory reset procedure?",
                          "Which endpoint exports the logging buffer?"]
        return cmd_chat(settings, positional, opts["thread"], opts["sqlite"])

    question = " ".join(positional).strip()
    if not question:
        _die(f'{action} needs a question, e.g. {action} "Why is the light orange?"')
    if action == "trace":
        return cmd_trace(settings, question, opts["recursion_limit"])
    if action == "review":
        return cmd_review(settings, question)
    if action == "spread":
        return cmd_spread(settings, question, opts["runs"])
    if action == "ask":
        return cmd_ask(settings, question)
    _die(f"unknown action {action!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
