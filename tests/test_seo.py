"""tools/seo.py: the SEO block, the sitemap, and the check that keeps them current.

Each test builds a tiny site in a temporary directory (one static page, one
config-driven lesson) and points the module at it, so nothing under docs/ is
touched. The checks are probed in the direction that matters: each one must fail
on the defect it names and pass on a correct page.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import seo  # noqa: E402

LESSON = {"title": "Toy Lesson", "slug": "toy", "status": "working", "languages": ["python"],
          "seo": {"description": "A toy lesson for the SEO tests.", "keywords": ["toy"]}}
STATIC_PAGE = ("<!doctype html>\n<html><head>\n  <title>{title}</title>\n"
               '  <meta name="description" content="old" />\n</head><body></body></html>\n')


@pytest.fixture
def site(tmp_path, monkeypatch):
    docs, lessons = tmp_path / "docs", tmp_path / "lessons"
    (docs / "assets").mkdir(parents=True)
    (docs / "assets" / "og-image.png").write_bytes(b"png")
    (lessons / "03-toy").mkdir(parents=True)
    (lessons / "03-toy" / "lesson.json").write_text(json.dumps(LESSON), encoding="utf-8")
    static = {"about.html": dict(seo.STATIC["about.html"])}
    monkeypatch.setattr(seo, "DOCS", docs)
    monkeypatch.setattr(seo, "LESSONS", lessons)
    monkeypatch.setattr(seo, "STATIC", {**static, "index.html": seo.STATIC["index.html"]})
    for name in ("about.html", "index.html"):
        (docs / name).write_text(STATIC_PAGE.format(title=seo.STATIC[name]["title"]),
                                 encoding="utf-8")
    page = seo.lesson_pages()["lesson-3-toy.html"]
    (docs / "lesson-3-toy.html").write_text(
        f"<html><head>\n  <title>{page['title']}</title>\n"
        f"{seo.head_for('lesson-3-toy.html', page)}</head></html>\n", encoding="utf-8")
    seo.write()
    return docs, lessons


def test_a_written_site_passes(site):
    assert seo.problems() == []


def test_write_is_idempotent(site):
    docs, _ = site
    before = {p.name: p.read_text(encoding="utf-8") for p in docs.glob("*.*")}
    seo.write()
    assert before == {p.name: p.read_text(encoding="utf-8") for p in docs.glob("*.*")}


def test_write_replaces_the_old_description(site):
    text = (site[0] / "about.html").read_text(encoding="utf-8")
    assert 'content="old"' not in text
    assert text.count('name="description"') == 1


def test_write_refuses_a_page_without_a_title(site):
    (site[0] / "about.html").write_text("<html><head></head></html>", encoding="utf-8")
    with pytest.raises(SystemExit, match="no </title>"):
        seo.write()


def test_title_on_the_same_line_as_head_still_gets_a_block():
    block = "  <!-- seo -->\n  <!-- /seo -->\n"
    out = seo._with_block("about.html", "<head><title>x</title></head>", block)
    assert "<!-- seo -->" in out


@pytest.mark.parametrize("break_it,message", [
    (lambda docs, lessons: (docs / "lesson-3-toy.html").write_text(
        "<html><head><title>x</title></head></html>"),
     "SEO block missing or stale"),
    (lambda docs, lessons: (docs / "sitemap.xml").unlink(), "sitemap.xml is stale"),
    (lambda docs, lessons: (docs / "assets" / "og-image.png").unlink(), "share image"),
    (lambda docs, lessons: _edit_lesson(lessons, description="x" * 161), "161 chars"),
    (lambda docs, lessons: _edit_lesson(lessons, keywords=[]), "no keywords"),
    (lambda docs, lessons: _append(docs / "about.html", '<link rel="canonical" href="x" />'),
     'one rel="canonical"'),
    (lambda docs, lessons: _append(docs / "about.html", '<meta property="og:title" content="x" />'),
     'one property="og:title"'),
])
def test_each_check_fails_on_its_defect(site, break_it, message):
    docs, lessons = site
    break_it(docs, lessons)
    assert any(message in p for p in seo.problems()), seo.problems()


def test_a_title_that_differs_from_og_title_fails(site):
    path = site[0] / "about.html"
    path.write_text(path.read_text(encoding="utf-8").replace("<title>About", "<title>Changed"),
                    encoding="utf-8")
    assert any("<title> does not match" in p for p in seo.problems())


def test_an_escaped_ampersand_in_a_title_is_not_a_mismatch(site, monkeypatch):
    monkeypatch.setitem(seo.STATIC["about.html"], "title", "About & more - local-ai-lab")
    path = site[0] / "about.html"
    path.write_text(STATIC_PAGE.format(title="About &amp; more - local-ai-lab"), encoding="utf-8")
    seo.write()
    assert seo.problems() == []


def test_two_pages_cannot_share_a_description(site, monkeypatch):
    monkeypatch.setitem(seo.STATIC["about.html"], "description", LESSON["seo"]["description"])
    seo.write()
    assert any("same description" in p for p in seo.problems())


def test_a_planned_lesson_has_no_page_and_no_sitemap_entry(site):
    _edit_lesson(site[1], status="planned")
    assert "lesson-3-toy.html" not in seo.sitemap()


def test_json_ld_parses_and_uses_only_learning_resource_properties(site):
    block = seo.head_for("lesson-3-toy.html", seo.lesson_pages()["lesson-3-toy.html"])
    data = json.loads(block.split('ld+json">', 1)[1].split("</script>", 1)[0])
    assert data["@type"] == "LearningResource"
    assert "programmingLanguage" not in data  # not a LearningResource property


def _edit_lesson(lessons: Path, **changes) -> None:
    path = lessons / "03-toy" / "lesson.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if key in ("description", "keywords"):
            data["seo"][key] = value
        else:
            data[key] = value
    path.write_text(json.dumps(data), encoding="utf-8")


def _append(path: Path, tag: str) -> None:
    path.write_text(path.read_text(encoding="utf-8").replace("</head>", tag + "</head>"),
                    encoding="utf-8")
