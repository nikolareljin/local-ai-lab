"""Every lesson offers the same way in: read it, or run it.

The course grew in two eras: Lessons 1-2 are dispatched by the `run` bash script,
Lessons 3+ by `lesson.json`. That split let the two drift - `./run -h` advertised
a browser preview for every lesson while Lessons 1 and 2 rejected it, so the only
way to read Lesson 1 without GitHub Pages was to know it lived in
`docs/lesson-1-rag.html` and serve it yourself.

These tests pin the contract instead of trusting it:

  lesson  training  - read it in a browser, locally     (every lesson)
  demo    running   - run it with no model, no network  (every lesson)
  test    running   - the offline test                  (every lesson)

`show` is deliberately NOT in that set. It walks a lesson's elements in the
terminal, which only config-driven lessons have; Lessons 1-2 keep a Markdown
guide that `less` already reads better.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORE_ACTIONS = ("lesson", "demo", "test")

# Lessons 1-2 predate lesson.json and are dispatched by the bash script.
BASH_LESSONS = (1, 2)


def config_driven_lessons():
    found = {}
    for entry in sorted((ROOT / "lessons").iterdir()):
        m = re.match(r"^(\d+)-", entry.name)
        if m and (entry / "lesson.json").is_file():
            found[int(m.group(1))] = entry / "lesson.json"
    return found


def dispatcher_body(number: int) -> str:
    """The body of `run_lesson_<number>()` in the run script.

    Asserts the function exists first: splitting on a missing marker would raise
    IndexError and tell whoever renamed it nothing useful.
    """
    run = (ROOT / "run").read_text(encoding="utf-8")
    marker = f"run_lesson_{number}()"
    assert marker in run, f"`run` no longer defines {marker}; update BASH_LESSONS or the dispatcher"
    return run.split(marker, 1)[1].split("\n}", 1)[0]


def actions_in(lesson_json: Path) -> set:
    data = json.loads(lesson_json.read_text(encoding="utf-8"))
    return {
        el["action"]
        for el in data.get("elements", [])
        if el.get("type") == "command" and el.get("action")
    }


@pytest.mark.parametrize("number", sorted(config_driven_lessons()))
def test_config_driven_lesson_offers_demo_and_test(number):
    """`lesson` comes free from the engine; demo and test are the lesson's own."""
    actions = actions_in(config_driven_lessons()[number])
    for action in ("demo", "test"):
        assert action in actions, f"lesson {number} has no `{action}` action"


@pytest.mark.parametrize("number", BASH_LESSONS)
def test_bash_lesson_offers_every_core_action(number):
    """Lessons 1-2 have to spell every core action out, since they bypass the engine."""
    body = dispatcher_body(number)
    for action in CORE_ACTIONS:
        # Case labels may be alternations, e.g. `lesson|preview)`.
        assert re.search(rf"^\s*[\w|]*\b{action}\b[\w|]*\)", body, re.M), (
            f"`./run -l {number} {action}` is not handled in run_lesson_{number}"
        )


@pytest.mark.parametrize("number", BASH_LESSONS)
def test_bash_lesson_guide_sources_exist(number):
    """`lesson` serves the published page, so that page has to exist."""
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from lesson import guide_sources

    _, page = guide_sources(number)
    assert page is not None, f"no docs/ page for lesson {number}, so `lesson` has nothing to serve"


def help_output(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / "run"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_global_help_keeps_only_the_shared_interface():
    """Global help stays scannable and points to contextual details."""
    result = help_output("-h")
    assert result.returncode == 0
    for action in CORE_ACTIONS:
        assert re.search(rf"^  {action}\b", result.stdout, re.M)
    assert "./run -l <N> -h" in result.stdout
    assert "build" in result.stdout
    assert "--llm-grade" not in result.stdout
    assert "--model NAME" not in result.stdout


@pytest.mark.parametrize(
    "number, expected",
    [
        (1, ("ask", "repl", "index")),
        (2, ("serve", "register")),
        (7, ("--native", "--arm bm25|embed")),
        (8, ("trace", "review", "--recursion-limit", "--sqlite")),
        (9, ("bench", "record", "recipe", "--max-turns")),
    ],
)
def test_lesson_help_shows_only_relevant_details(number, expected):
    result = help_output("-l", str(number), "-h")
    assert result.returncode == 0
    assert f"Lesson {number}" in result.stdout
    assert all(item in result.stdout for item in expected)
    if number < 7:
        assert "--llm-grade" not in result.stdout


def test_help_rejects_an_unknown_lesson():
    result = help_output("-l", "99", "-h")
    assert result.returncode != 0
    assert "Unknown lesson '99'" in result.stderr


def test_show_is_not_offered_for_the_hand_authored_lessons():
    """Lessons 1-2 have no elements to walk, so `show` must not pretend otherwise."""
    for number in BASH_LESSONS:
        body = dispatcher_body(number)
        assert not re.search(r"^\s*show\)", body, re.M), (
            f"run_lesson_{number} handles `show`, which the contract excludes"
        )


@pytest.mark.parametrize("number", BASH_LESSONS)
def test_hand_authored_lessons_offer_a_downloadable_pdf(number):
    """Older pages keep the same explicit PDF-download affordance as the template."""
    slug = "rag" if number == 1 else "mcp"
    html = (ROOT / "docs" / f"lesson-{number}-{slug}.html").read_text(encoding="utf-8")
    assert f'href="./pdf/LESSON{number}.pdf"' in html
    assert f'download="LESSON{number}.pdf"' in html
    assert "PDF · downloadable" in html
