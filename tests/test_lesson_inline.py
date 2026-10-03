"""tools/lesson.py renders a small subset of Markdown in lesson.json bodies."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("lesson_tool", ROOT / "tools" / "lesson.py")
lesson_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lesson_tool)


def test_https_links_become_anchors():
    out = lesson_tool._inline("Get a key on the [keys page](https://example.com/keys?a=1&b=2).")
    assert ('<a href="https://example.com/keys?a=1&amp;b=2" target="_blank" '
            'rel="noopener">keys page</a>') in out


def test_only_https_links_are_rendered():
    for body in ("[x](javascript:alert(1))", "[x](http://example.com)", "[x](./local.md)"):
        assert "<a " not in lesson_tool._inline(body)


def test_markup_inside_a_link_is_still_escaped():
    assert "<b>" not in lesson_tool._inline("[<b>x</b>](https://example.com/a)")
    # a quote can never end the href early: such a URL is simply not a link
    assert "<a " not in lesson_tool._inline('[x](https://example.com/"onmouseover="x)')


def test_bold_italics_and_code_still_work():
    out = lesson_tool._inline("**bold** and *it* and `code`")
    assert "<strong>bold</strong>" in out and "<em>it</em>" in out and "<code>code</code>" in out
