"""Lesson 7 - offline tests. No network, no model, no API key.

Two rules this file exists to enforce:

  1. The lesson still works when LangChain is NOT installed. The comparison is the
     point, but a reader who has not run the install must still get something.
  2. The comparison is fair. Both pipelines get the same corpus, the same system
     prompt, and the same user-prompt shape - otherwise the scorecard is theatre.

Everything that needs LangChain is guarded with importorskip, so this file passes
on a bare course venv and again after `./run -l 7`.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import handrolled_pipeline as handrolled  # noqa: E402
import langchain_rag  # noqa: E402

LESSON_DIR = Path(__file__).resolve().parent.parent
SETTINGS = json.loads((LESSON_DIR / "data" / "questions.json").read_text(encoding="utf-8"))


def hand_chunks():
    return handrolled.split(
        handrolled.load(), SETTINGS["chunk_size"], SETTINGS["chunk_overlap"]
    )


def lc_module():
    pytest.importorskip("langchain_core")
    import lc_pipeline
    return lc_pipeline


# --------------------------------------------------------------- works without LangChain

def test_handrolled_side_grounds_every_question():
    """Lesson 1's pipeline answers from the corpus, with a citation, for every question."""
    chunks = hand_chunks()
    assert chunks, "the corpus produced no chunks"
    for question in SETTINGS["questions"]:
        hits = handrolled.retrieve(chunks, question, SETTINGS["top_k"])
        assert hits, f"no chunks retrieved for {question!r}"
        cites = handrolled.sources(hits)
        assert cites and all(":" in c for c in cites), f"missing citations for {question!r}"


def test_demo_runs_and_explains_itself_without_langchain(monkeypatch, capsys):
    """With LangChain absent the demo still exits 0 and prints the install command."""
    monkeypatch.setattr(langchain_rag, "import_langchain", lambda: None)
    assert langchain_rag.cmd_demo() == 0
    out = capsys.readouterr().out
    assert "not installed" in out
    assert langchain_rag.INSTALL_HINT in out


def test_scorecard_counts_real_files():
    """Line counts are read off disk, so the scorecard cannot drift from the code."""
    for _step, rel, _component in langchain_rag.COMPONENTS:
        path = langchain_rag.ROOT / rel
        assert path.exists(), f"scorecard points at a missing file: {rel}"
        assert langchain_rag.code_lines(path) > 0


def test_code_lines_ignores_comments_and_docstrings(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text('"""Doc.\n\nMore.\n"""\n# a comment\n\nx = 1\ny = 2\n', encoding="utf-8")
    assert langchain_rag.code_lines(sample) == 2


# --------------------------------------------------------------- needs LangChain

def test_both_pipelines_see_the_same_corpus():
    lc = lc_module()
    hand_sources = {c["source"] for c in hand_chunks()}
    lc_sources = {d.metadata["source"] for d in lc.load()}
    assert hand_sources == lc_sources


def test_both_pipelines_share_one_system_prompt():
    """The fairness guarantee: LangChain is handed Lesson 1's prompt, not a nicer one."""
    lc = lc_module()
    chunks = hand_chunks()
    hits = handrolled.retrieve(chunks, SETTINGS["questions"][0], SETTINGS["top_k"])
    hand_system, hand_user = handrolled.render_prompt(SETTINGS["questions"][0], hits)

    lc_chunks = lc.split(lc.load(), SETTINGS["chunk_size"], SETTINGS["chunk_overlap"])
    lc_hits = lc.bm25_retriever(lc_chunks, SETTINGS["top_k"]).invoke(SETTINGS["questions"][0])
    lc_system, lc_user = lc.render_prompt(SETTINGS["questions"][0], lc_hits)

    assert hand_system == lc_system
    for marker in ("DOCUMENT CONTEXT:", "QUESTION:", "citing [filename:page]"):
        assert marker in hand_user and marker in lc_user


def test_langchain_retrieval_is_cited_and_bounded():
    lc = lc_module()
    chunks = lc.split(lc.load(), SETTINGS["chunk_size"], SETTINGS["chunk_overlap"])
    hits = lc.bm25_retriever(chunks, SETTINGS["top_k"]).invoke(SETTINGS["questions"][0])
    assert 0 < len(hits) <= SETTINGS["top_k"]
    assert all(":" in c for c in lc.sources(hits))


def test_both_pipelines_lead_with_the_same_source():
    """Chunk boundaries differ, so full agreement is not guaranteed - the top source is."""
    lc = lc_module()
    lc_chunks = lc.split(lc.load(), SETTINGS["chunk_size"], SETTINGS["chunk_overlap"])
    retriever = lc.bm25_retriever(lc_chunks, SETTINGS["top_k"])
    chunks = hand_chunks()
    for question in SETTINGS["questions"]:
        hand = handrolled.sources(handrolled.retrieve(chunks, question, SETTINGS["top_k"]))
        got = lc.sources(retriever.invoke(question))
        assert hand[0] == got[0], f"top source diverged for {question!r}"


def test_chat_model_adapter_forwards_system_and_user():
    """The escape hatch works: messages in, provider.chat out. No subprocess, no network."""
    lc_module()
    import lc_provider
    from langchain_core.messages import HumanMessage, SystemMessage

    seen = {}

    class FakeProvider:
        def chat(self, system, user):
            seen["system"], seen["user"] = system, user
            return "grounded answer [manual.md:1]"

    original = lc_provider.get_provider
    lc_provider.get_provider = lambda name, config: FakeProvider()
    try:
        model = lc_provider.LocalRagChatModel(config=None, provider_name="claude")
        out = model.invoke([SystemMessage(content="RULES"), HumanMessage(content="QUESTION")])
    finally:
        lc_provider.get_provider = original

    assert seen == {"system": "RULES", "user": "QUESTION"}
    assert out.content == "grounded answer [manual.md:1]"


def test_demo_output_matches_the_committed_transcript(capsys):
    """The lesson README quotes this output; the test keeps it true."""
    lc_module()
    expected = (LESSON_DIR / "expected-output.txt").read_text(encoding="utf-8")
    assert langchain_rag.cmd_demo() == 0
    assert capsys.readouterr().out == expected
