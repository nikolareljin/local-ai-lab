"""tools/lesson_lines.py: a lesson's code excerpt must be the code its step names."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import lesson_lines  # noqa: E402

PY = '''\
import re

LIMIT = 3
PATTERNS = [
    ("a", r"x"),
]


@decorated
def first(text):
    """Doc."""
    return {"k": [1, 2]}


class Box:
    def open(self):
        return call(
            "name",
            {"deep": True},
        )


def outer():
    def inner(state):
        return state
    return inner
'''

JS = '''\
const LIMIT = 3;
// Ordered rules.
const PATTERNS = [
  ["a", /x{2}/],
];

/**
 * Split text.
 */
function split(text, size) {
  const out = `${text} { not a brace`;
  return [out].map((t) => { return t; });
}

const answer = split("a", 1);

class Index {
  // Rank the documents.
  search(query, k) {
    return query ? [k] : [];
  }
}
'''

CS = '''\
var baseline = new Config("baseline", 3, false);
var candidate = new Config("candidate", 1, true);

static List<string> Tokenize(string text) =>
    Regex.Matches(text, "[a-z]+").Select(m => m.Value).ToList();

// --- Retrieval ---
List<Doc> Retrieve(string query, List<Doc> corpus, int topK)
{
    var hits = Tokenize(query);
    return corpus.Where(d => d.Has(hits)).ToList();
}

static class Policy
{
    /// <summary>One action.</summary>
    public static string Decide(Answers a)
    {
        return a.Ok ? "yes" : "no";
    }
}
'''


def _resolve(tmp_path, name, text, symbol):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    start, end = map(int, lesson_lines.resolve(path, symbol).split("-"))
    return text.splitlines()[start - 1:end]


@pytest.mark.parametrize("symbol, first, last", [
    ("first", "@decorated", '    return {"k": [1, 2]}'),
    ("PATTERNS", "PATTERNS = [", "]"),
    ("LIMIT", "LIMIT = 3", "LIMIT = 3"),
    ("Box", "class Box:", "        )"),
    ("Box.open", "    def open(self):", "        )"),
    ("outer.inner", "    def inner(state):", "        return state"),
    ("first..Box", "@decorated", "        )"),
    ('around:"name"', "        return call(", "        )"),
    ("around:deep", "        return call(", "        )"),  # one line: the call around it
])
def test_python(tmp_path, symbol, first, last):
    shown = _resolve(tmp_path, "a.py", PY, symbol)
    assert (shown[0], shown[-1]) == (first, last)


@pytest.mark.parametrize("symbol, first, last", [
    ("split", "/**", "}"),
    ("PATTERNS", "// Ordered rules.", "];"),
    ("LIMIT", "const LIMIT = 3;", "const LIMIT = 3;"),
    ("Index", "class Index {", "}"),
    ("Index.search", "  // Rank the documents.", "  }"),
    ("PATTERNS..split", "// Ordered rules.", "}"),
])
def test_javascript(tmp_path, symbol, first, last):
    shown = _resolve(tmp_path, "a.mjs", JS, symbol)
    assert (shown[0], shown[-1]) == (first, last)
    if symbol == "split":  # a brace inside a template string does not end the function
        assert len(shown) == 7


@pytest.mark.parametrize("symbol, first, last", [
    ("Tokenize", "static List<string> Tokenize(string text) =>",
     '    Regex.Matches(text, "[a-z]+").Select(m => m.Value).ToList();'),
    ("Retrieve", "// --- Retrieval ---", "}"),
    ("baseline..candidate", 'var baseline = new Config("baseline", 3, false);',
     'var candidate = new Config("candidate", 1, true);'),
    ("Policy.Decide", "    /// <summary>One action.</summary>", "    }"),
])
def test_csharp(tmp_path, symbol, first, last):
    shown = _resolve(tmp_path, "a.cs", CS, symbol)
    assert (shown[0], shown[-1]) == (first, last)
    if symbol == "Retrieve":  # the call inside the body is not the declaration
        assert len(shown) == 6


def test_marker(tmp_path):
    text = "x = 1\n# --- the whole call ---------------------\ny = 2\n# " + "-" * 40 + "\nz = 3\n"
    shown = _resolve(tmp_path, "a.py", text, "marker:the whole call")
    assert shown[0].startswith("# --- the whole call") and shown[-1] == "# " + "-" * 40
    assert len(shown) == 3


@pytest.mark.parametrize("name, text, symbol", [
    ("a.py", PY, "missing"), ("a.py", PY, "Box.missing"), ("a.py", PY, "around:nowhere"),
    ("a.mjs", JS, "missing"), ("a.mjs", JS, "answer.nothing"), ("a.cs", CS, "Missing"),
    ("a.mjs", JS, "around:x"), ("a.py", PY, "marker:nope"), ("a.py", PY, "Box..first"),
])
def test_a_symbol_that_is_not_there_is_an_error_not_a_guess(tmp_path, name, text, symbol):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    with pytest.raises(lesson_lines.Unresolved):
        lesson_lines.resolve(path, symbol)


def test_every_lesson_shows_the_code_it_names():
    assert lesson_lines.check() == []
    steps = [el for d in lesson_lines.lesson_dirs() for el in lesson_lines.code_steps(d)]
    assert len(steps) >= 89 and all(el.get("symbol") for el in steps)


def test_published_pages_show_the_current_excerpts():
    assert lesson_lines.published_problems() == []


@pytest.fixture
def copied_lesson(tmp_path):
    lessons = tmp_path / "lessons"
    shutil.copytree(ROOT / "lessons" / "06-repo-aware-assistant",
                    lessons / "06-repo-aware-assistant",
                    ignore=shutil.ignore_patterns("bin", "obj", "node_modules", "__pycache__"))
    return lessons


@pytest.mark.parametrize("file", ["python/repo_assistant.py", "node/repo_assistant.mjs",
                                  "dotnet/Program.cs"])
def test_an_edit_above_a_function_is_caught_and_repaired(copied_lesson, file):
    """The bug this tool exists for: two lines added at the top of a source file."""
    ldir = copied_lesson / "06-repo-aware-assistant"
    assert lesson_lines.check(copied_lesson) == []
    before = (ldir / "lesson.json").read_text(encoding="utf-8")
    source = ldir / file
    comment = "# added\n# later\n" if file.endswith(".py") else "// added\n// later\n"
    source.write_text(comment + source.read_text(encoding="utf-8"), encoding="utf-8")

    drift = lesson_lines.check(copied_lesson)
    assert len(drift) == 4 and all(file in message for message in drift)

    changed, stuck = lesson_lines.write(copied_lesson)
    assert (changed, stuck) == (4, [])
    assert lesson_lines.check(copied_lesson) == []
    after = (ldir / "lesson.json").read_text(encoding="utf-8")
    assert len(after.splitlines()) == len(before.splitlines())  # layout kept
    moved = [el for el in json.loads(after)["elements"] if el.get("file") == file]
    was = [el for el in json.loads(before)["elements"] if el.get("file") == file]
    for new, old in zip(moved, was):
        assert [int(n) for n in new["lines"].split("-")] == \
               [int(n) + 2 for n in old["lines"].split("-")]


def test_a_step_without_a_symbol_or_with_a_renamed_one_fails(copied_lesson):
    path = copied_lesson / "06-repo-aware-assistant" / "lesson.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"symbol": "retrieve"', '"symbol": "fetch"', 1)
                    .replace(', "symbol": "plan"', "", 1), encoding="utf-8")
    drift = lesson_lines.check(copied_lesson)
    assert any("no 'fetch'" in m for m in drift) and any("no `symbol`" in m for m in drift)
    changed, stuck = lesson_lines.write(copied_lesson)
    assert changed == 0 and len(stuck) == 2  # nothing is guessed


def test_a_page_that_was_not_rebuilt_is_caught(copied_lesson, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    page = "lesson-6-repo-aware-assistant.html"
    shutil.copy(ROOT / "docs" / page, docs / page)
    assert lesson_lines.published_problems(copied_lesson, docs) == []
    source = copied_lesson / "06-repo-aware-assistant" / "python" / "repo_assistant.py"
    source.write_text(source.read_text(encoding="utf-8").replace(
        "def retrieve(query, chunks, top_k):", "def retrieve(query, chunks, top_k=5):"),
        encoding="utf-8")
    stale = lesson_lines.published_problems(copied_lesson, docs)
    assert len(stale) == 1 and "./run -l 6 build" in stale[0]
