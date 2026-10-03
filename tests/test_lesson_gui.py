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


def test_a_search_shows_a_spinner_until_its_result_is_drawn():
    """A lesson that calls a model can take minutes: the page must say it is working."""
    assert "@keyframes spin" in PAGE and 'class="arms" aria-live="polite"' in PAGE
    # Search, Enter and an example chip ask for it at once; typing and sliders go through the delay.
    assert '$("go").addEventListener("click", () => search(true))' in PAGE
    assert PAGE.count("search(true)") == 3
    # Both ways out of a request (result, error) take the spinner down, after the stale check.
    assert PAGE.count("if (seq !== reqSeq) return;") == PAGE.count("        stopBusy();\n") == 2
    assert "#go.working::after" in PAGE  # Rankings can be below the fold; the button spins too
