"""Offline test for the Lesson 6 repo-aware assistant (Python).

Encodes the lesson's claims:
- indexing carries a citation (path + 1-based line range) for every passage,
- a locate question is answered only from indexed lines, cited, and the top
  citation points at the file that actually implements the thing,
- an off-repo question is refused ("not found") instead of guessed,
- a change request yields a plan-before-edit (relevant files, cited behaviour,
  minimal change, tests, docs) and changes no files,
- retrieval is deterministic (score desc, then path, then start line).

Run:  python -m pytest test_repo_assistant.py
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from repo_assistant import (
    answer,
    build_index,
    chunk_file,
    cite,
    is_indexable,
    load_questions,
    plan,
    respond,
    retrieve,
)


def _index():
    return build_index()


def test_index_has_citable_line_ranges():
    files, chunks = _index()
    assert "src/chunker.py" in files and "README.md" in files
    for c in chunks:
        assert c["start"] >= 1 and c["end"] >= c["start"]
        assert cite(c) == "%s:%d-%d" % (c["path"], c["start"], c["end"])


def test_chunk_ranges_are_one_based_and_split_on_blank_lines():
    raw = "line one\n\nline three\nline four\n"
    chunks = chunk_file("x.txt", raw)
    assert [(c["start"], c["end"]) for c in chunks] == [(1, 1), (3, 4)]
    assert chunks[0]["first_line"] == "line one"


def test_locate_answer_is_grounded_and_cites_the_right_file():
    _, chunks = _index()
    result = answer("where is chunking implemented", chunks, top_k=3, min_score=2)
    assert result["kind"] == "grounded"
    assert result["citation"].startswith("src/chunker.py:")
    # every source is a real citation, not an invented reference
    assert all(":" in s for s in result["sources"])


def test_off_repo_question_is_refused_not_guessed():
    _, chunks = _index()
    result = answer("how do i configure kubernetes autoscaling", chunks, top_k=3, min_score=2)
    assert result["kind"] == "not_found"
    assert result["best"] < 2


def _corpus_snapshot(corpus):
    """(size, mtime_ns, sha256) per corpus file - any create/delete/modify shows up."""
    state = {}
    for p in sorted(corpus.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            st = p.stat()
            state[p.relative_to(corpus).as_posix()] = (
                st.st_size, st.st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
    return state


def test_plan_before_edit_is_grounded_and_changes_no_files():
    files, chunks = _index()
    corpus = Path(__file__).resolve().parents[1] / "data" / "repo"

    before = _corpus_snapshot(corpus)
    result = plan("where should i add a new embedding provider", files, chunks, top_k=3)
    after = _corpus_snapshot(corpus)

    assert result["kind"] == "plan"
    assert result["behaviour"]["citation"].startswith("src/providers.py:")
    assert result["relevant"] and result["tests"] == "tests/test_retriever.py"
    assert result["docs"] == "README.md"
    # a plan is advisory: producing it must not create, delete, or modify any corpus file
    assert after == before


def test_retrieval_is_deterministic_ordered():
    _, chunks = _index()
    hits = retrieve("which tests cover the retriever", chunks, top_k=5)
    scores = [s for s, _ in hits]
    assert scores == sorted(scores, reverse=True)
    # top hit is the tests file that actually covers the retriever
    assert hits[0][1]["path"] == "tests/test_retriever.py"


def test_is_indexable_skips_noise_and_non_text():
    # source and docs are indexed...
    assert is_indexable("src/app.py")
    assert is_indexable("README.md")
    assert is_indexable("tests/test_x.py")
    # ...vendored/build dirs and binaries are not (so a real repo stays signal)
    assert not is_indexable(".git/config")
    assert not is_indexable("node_modules/left-pad/index.js")
    assert not is_indexable("build/out.o")
    assert not is_indexable("assets/logo.png")


def test_respond_routes_plan_vs_locate():
    files, chunks = _index()
    cfg = load_questions()
    kinds = {q["id"]: respond(q, files, chunks, cfg["top_k"], cfg["min_score"])["kind"]
             for q in cfg["questions"]}
    assert kinds["chunking"] == "grounded"
    assert kinds["add-provider"] == "plan"
    assert kinds["off-repo"] == "not_found"
