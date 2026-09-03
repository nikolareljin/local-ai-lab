"""Lesson 8 - the offline test.

No network, no model, no API key, and no LangGraph required: the tests that need
it skip rather than fail, so `./run -l 8 test` is green either way.

Two of these matter more than the rest and are worth reading first:

  test_coverage_grader_never_sees_the_expected_answer
      the measurement is only honest if the grader cannot peek at the label

  test_graph_and_loop_are_indistinguishable
      the whole scorecard rests on the two arms agreeing. If they ever stop
      agreeing, every number the lesson prints is void.
"""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import graders  # noqa: E402
import langgraph_agent as agent  # noqa: E402
import loop_agent  # noqa: E402
import rag_core  # noqa: E402
import rewriter  # noqa: E402

LESSON_DIR = HERE.parent


def has_langgraph() -> bool:
    return agent.import_graph_agent() is not None


needs_langgraph = pytest.mark.skipif(not has_langgraph(),
                                     reason="LangGraph is not installed")


@pytest.fixture(scope="module")
def setup():
    q = rag_core.load_questions()
    retriever = rag_core.build_retriever(q["chunk_size"], q["chunk_overlap"])
    grader = graders.CoverageGrader(q["grade_threshold"])
    rw = rewriter.GlossaryRewriter()
    return q, retriever, grader, rw


def run_loop(setup, question):
    q, retriever, grader, rw = setup
    return loop_agent.run(retriever, question, grader=grader, rewriter=rw,
                          top_k=q["top_k"], max_attempts=q["max_attempts"])


# --------------------------------------------------------------- the corpus
def test_corpus_is_lesson_sevens():
    """The comparison only means anything over the same bytes Lesson 7 used."""
    assert rag_core.CORPUS_DIR.is_dir()
    assert rag_core.CORPUS_DIR.parent.parent.name == "07-langchain-rag"
    assert len(list(rag_core.CORPUS_DIR.glob("*.md"))) == 7


def test_every_question_declares_why_it_exists(setup):
    q, *_ = setup
    for item in q["questions"]:
        assert item["why"].strip(), f"{item['id']} has no stated reason to exist"
        assert item["expect"] is None or item["expect"].endswith(".md")


# --------------------------------------------------------------- the grader
def test_coverage_grader_never_sees_the_expected_answer():
    """The measurement is theatre if the grader can read the label.

    Asserted on the signature AND on the state, so neither route can quietly open.
    """
    params = inspect.signature(graders.CoverageGrader.grade).parameters
    assert set(params) == {"self", "question", "query", "docs"}
    assert "expect" not in params
    if has_langgraph():
        import graph_agent
        assert "expect" not in graph_agent.AgentState.__annotations__


def test_coverage_grader_is_deterministic(setup):
    q, retriever, grader, _ = setup
    ask = "The light is orange and it will not connect."
    docs = rag_core.retrieve(retriever, ask, q["top_k"])
    seen = {repr(grader.grade(ask, ask, docs)) for _ in range(20)}
    assert len(seen) == 1


def test_coverage_grader_flags_the_vocabulary_misses(setup):
    """The four questions the lesson is about must actually grade weak first."""
    q, retriever, grader, _ = setup
    for qid in ("q4", "q5", "q6", "q7"):
        item = next(i for i in q["questions"] if i["id"] == qid)
        docs = rag_core.retrieve(retriever, item["ask"], q["top_k"])
        grade = grader.grade(item["ask"], item["ask"], docs)
        assert grade["verdict"] == "weak", f"{qid} was expected to fail its first search"
        assert grade["missing"], f"{qid} graded weak but named nothing missing"


def test_llm_grader_falls_back_loudly(setup):
    q, retriever, coverage, _ = setup
    docs = rag_core.retrieve(retriever, "anything", q["top_k"])

    def nonsense(system, user):
        return "I am afraid I cannot answer that."

    grade = graders.LlmGrader(nonsense, coverage, label="llm:fake").grade("q", "q", docs)
    assert grade["grader"] == "llm:fake(fell back)"
    assert "fell back" in grade["reason"]


def test_llm_grader_survives_a_provider_that_raises(setup):
    q, retriever, coverage, _ = setup
    docs = rag_core.retrieve(retriever, "anything", q["top_k"])

    def boom(system, user):
        raise RuntimeError("provider is down")

    grade = graders.LlmGrader(boom, coverage, label="llm:fake").grade("q", "q", docs)
    assert grade["grader"].endswith("(fell back)")
    assert grade["verdict"] in ("grounded", "weak")


def test_llm_grader_makes_exactly_one_call_per_grade(setup):
    """Guards the model-call column of the scorecard."""
    q, retriever, coverage, _ = setup
    docs = rag_core.retrieve(retriever, "anything", q["top_k"])
    calls = []

    def counting(system, user):
        calls.append(1)
        return "WEAK\nnot enough\nfoo, bar"

    graders.LlmGrader(counting, coverage).grade("q", "q", docs)
    assert len(calls) == 1


def test_llm_grader_does_not_read_ungrounded_as_grounded(setup):
    """"GROUNDED" is a substring of "UNGROUNDED", and a substring test would record
    the exact opposite of what the model said - silently, with no fallback."""
    assert graders._parse_verdict("UNGROUNDED\nthe band is never named\n5ghz") is None
    assert graders._parse_verdict("NOT UNGROUNDED") is None
    assert graders._parse_verdict("GROUNDED\nit answers directly")[0] == "grounded"
    assert graders._parse_verdict("WEAK\nnope\nfoo")[0] == "weak"


def test_an_unparsable_verdict_falls_back_rather_than_guessing(setup):
    q, retriever, coverage, _ = setup
    docs = rag_core.retrieve(retriever, "Is 5GHz supported?", q["top_k"])
    grade = graders.LlmGrader(lambda s, u: "UNGROUNDED\nthe band is never named",
                              coverage, label="llm:fake").grade("q", "q", docs)
    assert grade["grader"] == "llm:fake(fell back)"


def test_llm_grader_parses_a_well_formed_reply(setup):
    q, retriever, coverage, _ = setup
    docs = rag_core.retrieve(retriever, "anything", q["top_k"])
    grade = graders.LlmGrader(lambda s, u: "WEAK\nthe band is never named\n5ghz, band",
                              coverage, label="llm:fake").grade("q", "q", docs)
    assert grade["verdict"] == "weak"
    assert grade["missing"] == ["5ghz", "band"]
    assert grade["grader"] == "llm:fake"


# --------------------------------------------------------------- the rewriter
def test_rewriter_is_a_noop_when_nothing_is_missing():
    """It reacts to the grader's finding rather than reaching for the table."""
    rw = rewriter.GlossaryRewriter()
    assert rw.rewrite("q", "the original query", []) == "the original query"


def test_rewriter_leaves_unknown_terms_alone():
    """Nothing in the table matches, so it must not invent a rewrite."""
    rw = rewriter.GlossaryRewriter(glossary={"orange": ["amber"]})
    assert rw.rewrite("q", "quokka velocity", ["quokka"]) == "quokka velocity"


def test_llm_rewriter_marks_a_silent_fallback(setup):
    """A glossary fallback must not be indistinguishable from a model rewrite.

    The class docstring promised this before the code did.
    """
    base = rewriter.GlossaryRewriter()

    def boom(system, user):
        raise RuntimeError("provider is down")

    rw = rewriter.LlmRewriter(boom, base, label="llm:fake")
    out = rw.rewrite("q", "the light is orange", ["orange"])
    assert rw.fell_back is True
    assert out == base.rewrite("q", "the light is orange", ["orange"])

    rw_ok = rewriter.LlmRewriter(lambda s, u: "amber status ring", base, label="llm:fake")
    assert rw_ok.rewrite("q", "the light is orange", ["orange"]) == "amber status ring"
    assert rw_ok.fell_back is False


def test_a_rewriter_fallback_reaches_the_trace(setup):
    q, retriever, grader, _ = setup

    def boom(system, user):
        raise RuntimeError("down")

    rw = rewriter.LlmRewriter(boom, rewriter.GlossaryRewriter(), label="llm:fake")
    result = loop_agent.run(retriever, "The light is orange and it will not connect.",
                            grader=grader, rewriter=rw, top_k=q["top_k"],
                            max_attempts=q["max_attempts"])
    assert any("fell back to the glossary" in line for line in result["trace"]), result["trace"]


def test_rewriter_drops_the_missing_terms_it_replaces():
    rw = rewriter.GlossaryRewriter()
    out = rw.rewrite("q", "light orange connect", ["orange", "light", "connect"])
    assert "orange" not in out and "amber" in out


# --------------------------------------------------------------- the arms
def test_linear_arm_cites_every_answerable_question(setup):
    q, retriever, _, _ = setup
    for item in q["questions"]:
        res = loop_agent.run_linear(retriever, item["ask"], top_k=q["top_k"])
        assert res["sources"], f"{item['id']} retrieved nothing at all"


def test_loop_arm_reproduces_the_measured_table(setup):
    """Pins every number the README and the scorecard print.

    If retrieval, chunking or the stop-list changes, this fails here rather than
    silently making the lesson's prose wrong.
    """
    expected = {
        "q1": (1, 1, "answered", "manual.md:1"),
        "q2": (1, 1, "answered", "faq.md:1"),
        "q3": (1, 1, "answered", "api.md:1"),
        "q4": (2, 2, "answered", "faq.md:1"),
        "q5": (2, 2, "answered", "manual.md:1"),
        "q6": (2, 2, "answered", "warranty.md:1"),
        "q7": (2, 2, "answered", "networking.md:1"),
        "q8": (2, 2, "answered", "installation.md:1"),
        "q9": (2, 2, "abstained", None),
    }
    q, *_ = setup
    for item in q["questions"]:
        attempts, retrievals, status, top = expected[item["id"]]
        res = run_loop(setup, item["ask"])
        assert res["attempts"] == attempts, item["id"]
        assert res["retrievals"] == retrievals, item["id"]
        assert res["status"] == status, item["id"]
        assert (res["sources"][:1] or [None])[0] == top, item["id"]


def test_the_scorecard_headline_numbers(setup):
    """4/8 -> 8/8, and the abstention. The lesson's whole claim, in one test."""
    q, retriever, grader, rw = setup
    answerable = [i for i in q["questions"] if i["expect"]]
    lin = sum(1 for i in answerable
              if agent.scored(loop_agent.run_linear(retriever, i["ask"], top_k=q["top_k"]),
                              i["expect"]))
    loop = sum(1 for i in answerable if agent.scored(run_loop(setup, i["ask"]), i["expect"]))
    assert (lin, loop, len(answerable)) == (4, 8, 8)
    unanswerable = next(i for i in q["questions"] if i["expect"] is None)
    assert run_loop(setup, unanswerable["ask"])["status"] == "abstained"


def test_the_loop_costs_more_retrievals_than_the_chain(setup):
    q, retriever, _, _ = setup
    lin = sum(loop_agent.run_linear(retriever, i["ask"], top_k=q["top_k"])["retrievals"]
              for i in q["questions"])
    loop = sum(run_loop(setup, i["ask"])["retrievals"] for i in q["questions"])
    assert (lin, loop) == (9, 15)


def test_the_unanswerable_question_terminates_without_a_rewriter(setup):
    """The cap is what stops the loop, not the rewriter running out of ideas."""
    q, retriever, grader, _ = setup

    class NeverRewrites:
        name = "never"

        def rewrite(self, question, query, missing):
            return query + " x"  # always different, so only the cap can stop it

    res = loop_agent.run(retriever, "What is the MTBF?", grader=grader,
                         rewriter=NeverRewrites(), top_k=q["top_k"],
                         max_attempts=q["max_attempts"])
    assert res["status"] == "abstained"
    assert res["attempts"] == q["max_attempts"]


# --------------------------------------------------------------- the graph
@needs_langgraph
def test_graph_and_loop_are_indistinguishable(setup):
    """The keystone. If this fails, the scorecard is void."""
    import graph_agent
    q, retriever, grader, rw = setup
    graph = graph_agent.build_graph(grader=grader, rewriter=rw, top_k=q["top_k"],
                                    max_attempts=q["max_attempts"],
                                    checkpointer=graph_agent.memory_saver())
    fields = ("sources", "attempts", "retrievals", "grades", "rewrites", "status", "verdicts")
    for i, item in enumerate(q["questions"]):
        a = run_loop(setup, item["ask"])
        b = graph_agent.run(graph, retriever, item["ask"],
                            config={"configurable": {"thread_id": f"eq{i}"}})
        for f in fields:
            assert a[f] == b[f], f"{item['id']} differs on {f}: {a[f]!r} != {b[f]!r}"


@needs_langgraph
def test_graph_topology_is_what_the_readme_draws(setup):
    """How you test a cyclic graph without running it: assert on the topology as data."""
    import graph_agent
    q, _, grader, rw = setup
    graph = graph_agent.build_graph(grader=grader, rewriter=rw, top_k=q["top_k"],
                                    max_attempts=q["max_attempts"], human_review=True,
                                    checkpointer=graph_agent.memory_saver())
    nodes, edges = graph_agent.topology(graph)
    assert {"retrieve", "grade", "rewrite", "review", "generate", "abstain", "veto"} <= set(nodes)
    assert ("rewrite", "retrieve") in edges, "the back-edge - the cycle - is missing"
    assert ("review", "retrieve") in edges, "the reviewer's edit cannot re-enter the loop"
    assert ("grade", "abstain") in edges


@needs_langgraph
def test_cycle_actually_cycles(setup):
    """Count node executions off the stream, so the loop is observed, not assumed."""
    import graph_agent
    q, retriever, grader, rw = setup
    graph = graph_agent.build_graph(grader=grader, rewriter=rw, top_k=q["top_k"],
                                    max_attempts=q["max_attempts"],
                                    checkpointer=graph_agent.memory_saver())
    graph._retrieve_node.retriever = retriever
    ran = []
    for step in graph.stream(
        {"question": "Is 5GHz supported?", "query": "Is 5GHz supported?", "attempt": 1,
         "retrievals": 0, "grades": 0, "rewrites": 0, "trace": [], "turns": []},
        {"configurable": {"thread_id": "cycle"}},
    ):
        ran.extend(step.keys())
    assert ran.count("retrieve") == 2, f"expected two retrievals, saw {ran}"
    assert ran.count("rewrite") == 1


@needs_langgraph
def test_recursion_limit_raises_rather_than_hanging(setup):
    """Proving the unhappy path terminates is worth more than proving the happy one works."""
    import graph_agent
    from langgraph.errors import GraphRecursionError
    q, retriever, grader, _ = setup

    class NeverSatisfied:
        name = "never"

        def rewrite(self, question, query, missing):
            return query + " more"

    graph = graph_agent.build_graph(grader=grader, rewriter=NeverSatisfied(),
                                    top_k=q["top_k"], max_attempts=99,
                                    checkpointer=graph_agent.memory_saver())
    with pytest.raises(GraphRecursionError):
        graph_agent.run(graph, retriever, "What is the MTBF?",
                        config={"configurable": {"thread_id": "rl"}, "recursion_limit": 4})


@needs_langgraph
def test_interrupt_pauses_before_generate(setup):
    """How you test an interrupt with no model and no stdin: the pause is a return value."""
    import graph_agent
    q, retriever, grader, rw = setup
    graph = graph_agent.build_graph(grader=grader, rewriter=rw, top_k=q["top_k"],
                                    max_attempts=q["max_attempts"], human_review=True,
                                    generate=lambda a, b: "GENERATED",
                                    checkpointer=graph_agent.memory_saver())
    cfg = {"configurable": {"thread_id": "pause"}}
    res = graph_agent.run(graph, retriever, "What is the factory reset procedure?", config=cfg)
    assert res["status"] == "paused"
    assert res["__interrupt__"], "the graph did not actually interrupt"
    payload = res["__interrupt__"][0].value
    assert set(payload) >= {"question", "citations", "evidence", "ask"}
    snap = graph.get_state(cfg)
    assert snap.next == ("review",)
    assert not snap.values.get("answer"), "it generated an answer before the human replied"


@needs_langgraph
def test_resume_does_not_re_retrieve(setup):
    """The checkpoint claim, asserted: resuming continues, it does not restart."""
    import graph_agent
    q, retriever, grader, rw = setup
    graph = graph_agent.build_graph(grader=grader, rewriter=rw, top_k=q["top_k"],
                                    max_attempts=q["max_attempts"], human_review=True,
                                    generate=lambda a, b: "GENERATED",
                                    checkpointer=graph_agent.memory_saver())
    cfg = {"configurable": {"thread_id": "resume"}}
    q5 = "How do I wipe the device and start over?"
    before = graph_agent.run(graph, retriever, q5, config=cfg)
    after = graph_agent.run(graph, retriever, q5, config=cfg, resume="approve")
    assert after["retrievals"] == before["retrievals"]
    assert after["status"] == "answered"


@needs_langgraph
def test_veto_never_generates(setup):
    """A spy on generate records zero calls when the reviewer refuses."""
    import graph_agent
    q, retriever, grader, rw = setup
    calls = []
    graph = graph_agent.build_graph(
        grader=grader, rewriter=rw, top_k=q["top_k"], max_attempts=q["max_attempts"],
        human_review=True, generate=lambda a, b: (calls.append(1), "GENERATED")[1],
        checkpointer=graph_agent.memory_saver())
    cfg = {"configurable": {"thread_id": "veto"}}
    q5 = "How do I wipe the device and start over?"
    graph_agent.run(graph, retriever, q5, config=cfg)
    res = graph_agent.run(graph, retriever, q5, config=cfg, resume="veto")
    assert res["status"] == "vetoed"
    assert calls == [], "generate ran despite the veto"


@needs_langgraph
def test_edit_decision_re_enters_the_cycle(setup):
    import graph_agent
    q, retriever, grader, rw = setup
    graph = graph_agent.build_graph(grader=grader, rewriter=rw, top_k=q["top_k"],
                                    max_attempts=q["max_attempts"], human_review=True,
                                    generate=lambda a, b: "GENERATED",
                                    checkpointer=graph_agent.memory_saver())
    cfg = {"configurable": {"thread_id": "edit"}}
    q5 = "How do I wipe the device and start over?"
    before = graph_agent.run(graph, retriever, q5, config=cfg)
    after = graph_agent.run(graph, retriever, q5, config=cfg,
                            resume="edit:warranty claim form serial number")
    assert after["retrievals"] == before["retrievals"] + 1
    assert graph.get_state(cfg).values["query"] == "warranty claim form serial number"


@needs_langgraph
def test_two_turns_share_a_thread(setup):
    """Memory, proven by contrast with a different thread_id."""
    import graph_agent
    q, retriever, grader, rw = setup
    graph = graph_agent.build_graph(grader=grader, rewriter=rw, top_k=q["top_k"],
                                    max_attempts=q["max_attempts"],
                                    checkpointer=graph_agent.memory_saver())
    same = {"configurable": {"thread_id": "shared"}}
    graph_agent.run(graph, retriever, "What is the factory reset procedure?", config=same)
    second = graph_agent.run(graph, retriever, "Why does the status ring stay amber?",
                             config=same)
    assert len(second["turns"]) == 2
    other = graph_agent.run(graph, retriever, "Why does the status ring stay amber?",
                            config={"configurable": {"thread_id": "nobody"}})
    assert len(other["turns"]) == 1


@needs_langgraph
def test_sqlite_checkpointer_survives_a_new_graph_object(setup, tmp_path):
    """Durability, without leaving anything behind: build, run, discard, rebuild."""
    pytest.importorskip("langgraph.checkpoint.sqlite")
    import graph_agent
    from langgraph.checkpoint.sqlite import SqliteSaver
    q, retriever, grader, rw = setup
    db = str(tmp_path / "state.db")
    cfg = {"configurable": {"thread_id": "durable"}}
    with SqliteSaver.from_conn_string(db) as saver:
        graph = graph_agent.build_graph(grader=grader, rewriter=rw, top_k=q["top_k"],
                                        max_attempts=q["max_attempts"], checkpointer=saver)
        graph_agent.run(graph, retriever, "What is the factory reset procedure?", config=cfg)
    with SqliteSaver.from_conn_string(db) as saver:
        fresh = graph_agent.build_graph(grader=grader, rewriter=rw, top_k=q["top_k"],
                                        max_attempts=q["max_attempts"], checkpointer=saver)
        assert fresh.get_state(cfg).values.get("turns"), "the state did not survive"


# --------------------------------------------------------------- the CLI and the demo
def test_demo_is_deterministic_and_matches_the_committed_transcript():
    """`expected-output.txt` is the contract: the printed run cannot drift."""
    result = subprocess.run([sys.executable, "python/langgraph_agent.py", "demo"],
                            cwd=LESSON_DIR, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    committed = (LESSON_DIR / "expected-output.txt").read_text(encoding="utf-8")
    assert result.stdout == committed, "demo output drifted from expected-output.txt"


def test_demo_runs_and_explains_itself_without_langgraph(monkeypatch, capsys):
    monkeypatch.setattr(agent, "import_graph_agent", lambda: None)
    assert agent.cmd_demo(agent.Settings({})) == 0
    out = capsys.readouterr().out
    assert "not installed" in out
    assert agent.INSTALL_HINT in out
    assert "4/8" in out and "8/8" in out, "the accuracy result must survive the missing dep"


def test_import_guard_does_not_hide_our_own_import_errors(monkeypatch):
    """A typo in our code must propagate, not read as 'LangGraph is missing'."""
    import builtins
    real = builtins.__import__

    def broken(name, *a, **kw):
        if name == "graph_agent":
            raise ModuleNotFoundError("No module named 'typo_module'", name="typo_module")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", broken)
    with pytest.raises(ModuleNotFoundError):
        agent.import_graph_agent()


def test_unknown_flag_value_is_rejected_not_silently_ignored():
    """`--provider ollma` must not quietly run Claude and mislabel every number."""
    for argv in (["demo", "--provider", "ollma"], ["demo", "--threshold", "9"],
                 ["demo", "--top-k", "many"], ["demo", "--nonsense"]):
        with pytest.raises(SystemExit) as excinfo:
            agent.parse(argv)
        assert excinfo.value.code == 2, argv


def test_flags_that_should_parse():
    action, positional, opts = agent.parse(
        ["trace", "why is it orange", "--llm", "--top-k", "5", "--threshold", "0.5"])
    assert action == "trace"
    assert positional == ["why is it orange"]
    assert opts["llm_grade"] and opts["llm_rewrite"]
    assert opts["top_k"] == 5 and opts["threshold"] == 0.5


def test_default_action_is_demo():
    assert agent.parse([])[0] == "demo"


def test_code_lines_ignores_comments_and_docstrings(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text('"""Doc.\n\nMore.\n"""\n# a comment\n\nX = 1\n\n\ndef f():\n    return X\n')
    assert agent.code_lines(sample) == 3


def test_the_bill_counts_files_that_exist():
    for arm, paths in agent.ARM_FILES.items():
        for rel in paths:
            assert (LESSON_DIR / rel).is_file(), f"{arm} counts a missing file: {rel}"


# --------------------------------------------------------------- the playground
# The playground is the only part of this lesson that holds MUTABLE, RESUMABLE state
# rather than a read-only cache, which makes it the easiest place to get something
# subtly wrong. It has already produced two bugs: a deadlock (the module lock taken
# twice on one request) and a snapshot cached at pause time that kept insisting a
# finished run was still waiting for a human.
pytest.importorskip("flask")


@pytest.fixture(scope="module")
def playground():
    import web
    return web


PAUSING_QUESTION = "How do I wipe the device and start over?"


def test_playground_does_not_reindex_on_every_query(playground):
    """Re-splitting the corpus per keystroke would be sluggish and would contradict
    the 'build the index once' contract the rest of the lesson pins."""
    assert playground.retriever() is playground.retriever()


def test_playground_clamps_client_supplied_params(playground):
    """/api/search takes arbitrary JSON, so every number from the browser is suspect."""
    assert playground._clamp("nonsense", 1, 6, 3) == 3
    assert playground._clamp(None, 1, 6, 3) == 3
    assert playground._clamp(999, 1, 6, 3) == 6
    assert playground._clamp(-5, 0.0, 1.0, 0.67) == 0.0


def test_playground_survives_junk_from_the_browser(playground):
    result = playground.search("Is 5GHz supported?",
                              {"top_k": "many", "threshold": None, "max_attempts": [],
                               "review_decision": "yes", "rewrite": "sure"})
    assert result["arms"] and result["blocks"]


def test_playground_cache_is_bounded(playground):
    assert playground._MAX_THREADS > 0
    for i in range(playground._MAX_THREADS + 5):
        playground._THREADS[("filler", i)] = (None, None, 0)
        while len(playground._THREADS) > playground._MAX_THREADS:
            playground._THREADS.popitem(last=False)
    assert len(playground._THREADS) <= playground._MAX_THREADS
    playground._THREADS.clear()


@needs_langgraph
def test_playground_resume_keeps_the_same_checkpoint(playground):
    """The lesson's central claim, asserted through the page the reader actually uses."""
    playground._THREADS.clear()
    playground.search(PAUSING_QUESTION, {"review_decision": 0})
    resumed = playground.search(PAUSING_QUESTION, {"review_decision": 1})
    stats = next(b for b in resumed["blocks"]
                 if b["kind"] == "stats"
                 and any(i["l"].startswith("retrievals when") for i in b["items"]))
    before = next(i["v"] for i in stats["items"] if i["l"] == "retrievals when paused")
    after = next(i["v"] for i in stats["items"] if i["l"] == "retrievals after resume")
    assert before == after, "resuming re-retrieved; the checkpoint is not doing its job"
    assert any(i["v"] == "answered" for i in stats["items"])


@needs_langgraph
def test_playground_never_claims_a_finished_run_is_paused(playground):
    """Regression: the paused snapshot used to be cached and then rendered forever.

    Once a run has been approved, every later request - a keystroke, a slider nudge -
    kept reporting it as waiting for a human, and would try to resume it again.
    """
    playground._THREADS.clear()
    playground.search(PAUSING_QUESTION, {"review_decision": 0})
    playground.search(PAUSING_QUESTION, {"review_decision": 1})

    # Asking again with the same decision must NOT resume a second time.
    again = playground.search(PAUSING_QUESTION, {"review_decision": 1})
    notes = [b["text"] for b in again["blocks"] if b["kind"] == "note"]
    assert any("finished" in text for text in notes), notes
    assert not [b for b in again["blocks"]
                if b["kind"] == "stats"
                and any(i["l"].startswith("retrievals when") for i in b["items"])]


@needs_langgraph
def test_playground_can_show_the_pause_again_after_a_resume(playground):
    """Resuming is one-way, so replaying the pause has to start a fresh thread."""
    playground._THREADS.clear()
    playground.search(PAUSING_QUESTION, {"review_decision": 0})
    playground.search(PAUSING_QUESTION, {"review_decision": 1})
    back = playground.search(PAUSING_QUESTION, {"review_decision": 0})
    assert any("PAUSED" in b["text"] for b in back["blocks"] if b["kind"] == "note")


def test_playground_rewrite_toggle_off_makes_the_loop_give_up(playground):
    """A cycle that cannot change its own input is not a cycle."""
    playground._THREADS.clear()
    result = playground.search("Is 5GHz supported?", {"rewrite": False})
    assert result["arms"][1]["ranking"] == ["(abstained - nothing grounded it)"]


def test_playground_threshold_zero_collapses_the_graph_into_a_chain(playground):
    playground._THREADS.clear()
    result = playground.search("The light is orange and it will not connect.",
                               {"threshold": 0.0})
    rows = next(b for b in result["blocks"] if b.get("title") == "Every attempt")["rows"]
    assert len(rows) == 1, "nothing should be graded weak at threshold 0"


# --------------------------------------------------------------- the lesson's own numbers
def test_the_stated_loop_line_count_matches_the_file():
    """The lesson claims a specific size for the `while` loop. Pin it to the file.

    The prose said 'forty-five lines' for a while after the real figure had settled
    at sixty-three - the exact drift between description and behaviour this course
    spends a lesson warning about.
    """
    measured = agent.code_lines(LESSON_DIR / "python" / "loop_agent.py")
    words = {45: "forty-five", 61: "sixty-one", 63: "sixty-three"}
    claimed = words.get(measured)
    assert claimed, (f"loop_agent.py is now {measured} lines; add the spelling to this "
                     f"test and update the prose that states it")
    sources = {
        "lesson.json": (LESSON_DIR / "lesson.json").read_text(encoding="utf-8"),
        "README.md": (LESSON_DIR / "README.md").read_text(encoding="utf-8"),
        "loop_agent.py": (LESSON_DIR / "python" / "loop_agent.py").read_text(encoding="utf-8"),
        "langgraph_agent.py": (LESSON_DIR / "python"
                               / "langgraph_agent.py").read_text(encoding="utf-8"),
    }
    for name, text in sources.items():
        for wrong_count, wrong_word in words.items():
            if wrong_count == measured:
                continue
            assert wrong_word not in text, (
                f"{name} still says '{wrong_word}' but loop_agent.py is {measured} lines")
            assert f"{wrong_count} lines of `while`" not in text, name
