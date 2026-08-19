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


def test_help_separates_training_from_running():
    """The help text is the contract most readers actually see."""
    help_text = (ROOT / "run").read_text(encoding="utf-8")
    assert "TRAINING" in help_text and "RUNNING" in help_text, (
        "the help no longer distinguishes reading a lesson from running it"
    )
    for action in CORE_ACTIONS:
        assert re.search(rf"\./run -l <N> {action}\b", help_text), f"help does not show `{action}`"


def test_show_is_not_offered_for_the_hand_authored_lessons():
    """Lessons 1-2 have no elements to walk, so `show` must not pretend otherwise."""
    for number in BASH_LESSONS:
        body = dispatcher_body(number)
        assert not re.search(r"^\s*show\)", body, re.M), (
            f"run_lesson_{number} handles `show`, which the contract excludes"
        )
