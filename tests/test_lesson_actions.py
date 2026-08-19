"""Every lesson offers the same core actions.

The course grew in two eras: Lessons 1-2 are dispatched by the `run` bash script,
Lessons 3+ by `lesson.json`. That split let the two drift - `./run -h` advertised
`show` and `preview` for every lesson while Lessons 1 and 2 rejected both, so the
only way to read Lesson 1 without GitHub Pages was to know that it was in
`docs/lesson-1-rag.html` and serve it yourself.

These tests pin the contract instead of trusting it: whatever a lesson is
implemented with, `demo`, `test`, `show` and `preview` all have to work.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORE_ACTIONS = ("demo", "test", "show", "preview")

# Lessons 1-2 predate lesson.json and are dispatched by the bash script.
BASH_LESSONS = (1, 2)


def config_driven_lessons():
    found = {}
    for entry in sorted((ROOT / "lessons").iterdir()):
        m = re.match(r"^(\d+)-", entry.name)
        if m and (entry / "lesson.json").is_file():
            found[int(m.group(1))] = entry / "lesson.json"
    return found


def actions_in(lesson_json: Path) -> set:
    data = json.loads(lesson_json.read_text(encoding="utf-8"))
    return {
        el["action"]
        for el in data.get("elements", [])
        if el.get("type") == "command" and el.get("action")
    }


@pytest.mark.parametrize("number", sorted(config_driven_lessons()))
def test_config_driven_lesson_offers_demo_and_test(number):
    """show/preview come free from the engine; demo and test are the lesson's own."""
    actions = actions_in(config_driven_lessons()[number])
    for action in ("demo", "test"):
        assert action in actions, f"lesson {number} has no `{action}` action"


@pytest.mark.parametrize("number", BASH_LESSONS)
def test_bash_lesson_offers_every_core_action(number):
    """Lessons 1-2 have to spell all four out, since they bypass the engine."""
    run = (ROOT / "run").read_text(encoding="utf-8")
    body = run.split(f"run_lesson_{number}()", 1)[1].split("\n}", 1)[0]
    for action in CORE_ACTIONS:
        assert re.search(rf"^\s*{action}\)", body, re.M), (
            f"`./run -l {number} {action}` is not handled in run_lesson_{number}"
        )


@pytest.mark.parametrize("number", BASH_LESSONS)
def test_bash_lesson_guide_sources_exist(number):
    """`show` needs the Markdown guide; `preview` needs the published page."""
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from lesson import guide_sources

    md, page = guide_sources(number)
    assert md is not None, f"LESSON{number}.md is missing, so `show` has nothing to print"
    assert page is not None, f"no docs/ page for lesson {number}, so `preview` has nothing to serve"


def test_help_lists_the_core_actions():
    """The help text is the contract most readers actually see."""
    help_text = (ROOT / "run").read_text(encoding="utf-8")
    block = help_text.split("Every lesson understands", 1)
    assert len(block) == 2, "the help no longer documents a shared action set"
    for action in CORE_ACTIONS:
        assert re.search(rf"^\s+{action}\s", block[1], re.M), f"help does not list `{action}`"
