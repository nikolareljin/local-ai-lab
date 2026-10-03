"""tools/templates/lesson-gui.html: the form every lesson's `web` action serves."""

from __future__ import annotations

from pathlib import Path

PAGE = (Path(__file__).resolve().parent.parent / "tools" / "templates"
        / "lesson-gui.html").read_text(encoding="utf-8")


def test_the_prompt_box_is_multi_line():
    """Prompts can be long (a call transcript, a pasted document): the box keeps line breaks.

    A single-line input drops them in the browser, and a lesson that matches or sends the
    text exactly then gets a different text from the one on screen.
    """
    assert '<textarea id="q"' in PAGE and '<input id="q"' not in PAGE


def test_enter_searches_and_shift_enter_adds_a_line():
    assert 'e.key === "Enter" && !e.shiftKey' in PAGE
    assert "fitPrompt()" in PAGE  # the box grows to fit a clicked or pasted prompt
