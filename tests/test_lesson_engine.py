"""Unit tests for the lesson engine's safety-critical helpers (tools/lesson.py).

Covers the edge cases that are easy to regress: read_ref() confining file reads
to the lesson directory, tolerant `lines` excerpt parsing, and the CSS-safe
language-class token. No network, no third-party deps.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import lesson  # noqa: E402

L3 = ROOT / "lessons" / "03-hybrid-retrieval-reranking"


def test_read_ref_blocks_paths_outside_the_lesson():
    for bad in ("../../run", "../../../etc/passwd", "/etc/hostname"):
        out = lesson.read_ref(L3, {"file": bad})
        assert out.startswith("[blocked path"), (bad, out[:60])


def test_read_ref_reads_a_file_inside_the_lesson():
    out = lesson.read_ref(L3, {"file": "data/error_codes.md"})
    assert out and not out.startswith("[")


def test_read_ref_lines_range_and_single_line():
    full = lesson.read_ref(L3, {"file": "python/hybrid_demo.py"}).splitlines()
    assert lesson.read_ref(L3, {"file": "python/hybrid_demo.py", "lines": "1"}) == full[0]
    assert lesson.read_ref(L3, {"file": "python/hybrid_demo.py", "lines": "1-3"}) == "\n".join(full[:3])


def test_read_ref_invalid_lines_spec_is_a_placeholder_not_a_crash():
    for bad in ("abc", "0-5", "20-10", "5-"):
        out = lesson.read_ref(L3, {"file": "python/hybrid_demo.py", "lines": bad})
        assert out.startswith("[invalid lines spec"), (bad, out[:60])


def test_media_path_is_confined_to_the_lesson():
    blocked = lesson._artifact(L3, {"type": "image", "file": "../../secret.png"}, "file:///x/")
    assert "blocked media path" in blocked
    # in-lesson and remote refs are still allowed
    assert "blocked" not in lesson._artifact(L3, {"type": "image", "file": "data/error_codes.md"}, "file:///x/")
    assert "blocked" not in lesson._artifact(L3, {"type": "image", "url": "https://x/y.png"}, "file:///x/")


def test_lang_token_is_a_safe_css_class():
    assert lesson._lang_token("python") == "python"
    assert lesson._lang_token("node js") == "node-js"
    # No angle brackets, quotes, or spaces can survive into the class attribute.
    for hostile in ('x"><b>', "a b c", "py;rm -rf"):
        assert re.fullmatch(r"[a-z0-9_-]*", lesson._lang_token(hostile)), hostile
