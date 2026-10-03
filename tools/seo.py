#!/usr/bin/env python3
"""Search and share metadata for every page under docs/, from one place.

Each page carries one block between `<!-- seo -->` and `<!-- /seo -->`: meta
description, keywords, canonical URL, Open Graph and Twitter card tags, and JSON-LD
(`Course` on the home page, `LearningResource` on each lesson). Generated lesson
pages get it from `tools/lesson.py` through `{{SEO}}`; the hand-authored pages get
it rewritten in place by `--write`. Both call `head_for()`, so the two cannot drift.

Lesson pages take their text from the `seo` object in `lessons/NN-slug/lesson.json`
(`description`, `keywords`). The hand-authored pages are described in `STATIC` below.

    python3 tools/seo.py --write   # rewrite the static pages' blocks and sitemap.xml
    python3 tools/seo.py --check   # exit 1 if anything is missing, stale or duplicated

No robots.txt: this is a GitHub Pages *project* site, served under /local-ai-lab/,
and crawlers only read robots.txt at the host root. Submit
https://nikolareljin.github.io/local-ai-lab/sitemap.xml in Google Search Console
instead.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
LESSONS = ROOT / "lessons"
SITE = "https://nikolareljin.github.io/local-ai-lab/"
# 1200x630: the size Open Graph and Twitter's large card display without cropping.
IMAGE = SITE + "assets/og-image.png"
IMAGE_SIZE = (1200, 630)
IMAGE_ALT = "local-ai-lab: a hands-on course for building local, private AI"
DESCRIPTION_MAX = 160
BLOCK = re.compile(r"[ \t]*<!-- seo -->.*?<!-- /seo -->\n?", re.S)

COURSE_KEYWORDS = ["local AI", "local LLM", "private AI", "Ollama", "AI course", "hands-on tutorial"]
LANG_NAMES = {"python": "Python", "node": "JavaScript", "csharp": "C#"}

# The hand-authored pages. Lessons 1-2 predate lesson.json, so their lesson facts live
# here too (number, title, languages) for the JSON-LD.
STATIC = {
    "index.html": {
        "title": "local-ai-lab - build local AI, hands-on",
        "description": "A free hands-on course for building local, private AI: RAG, MCP, "
                       "agents and function calling with Ollama, in Python, Node.js and C#.",
        "keywords": ["RAG tutorial", "MCP server", "LangChain", "LangGraph", "function calling"],
        "kind": "course",
    },
    "about.html": {
        "title": "About - local-ai-lab",
        "description": "About local-ai-lab and its author, Nik Reljin, plus related "
                       "local-first, developer-focused AI projects.",
        "keywords": ["about", "Nik Reljin"],
        "kind": "page",
    },
    "documentation.html": {
        "title": "Documentation - local-ai-lab",
        "description": "Install, run, test and experiment with local-ai-lab on Linux, macOS "
                       "and Windows, and how the course and its tools work.",
        "keywords": ["installation", "documentation", "Ollama setup"],
        "kind": "page",
    },
    "troubleshooting.html": {
        "title": "local-ai-lab - Troubleshooting & AI providers",
        "description": "Fix common local-ai-lab problems and set up a provider: Ollama "
                       "locally, Claude Code, Google Gemini or OpenAI, with keys and models.",
        "keywords": ["troubleshooting", "Ollama errors", "API keys", "Gemini", "OpenAI"],
        "kind": "page",
    },
    "lesson-1-rag.html": {
        "title": "Lesson 1 · RAG from scratch - local-ai-lab",
        "description": "Build Retrieval-Augmented Generation from scratch: chunk, retrieve with "
                       "BM25 and embeddings, answer with citations. Python, Node.js, C#.",
        "keywords": ["RAG from scratch", "retrieval augmented generation", "BM25", "embeddings",
                     "citations"],
        "kind": "lesson", "number": 1, "name": "RAG from scratch",
        "languages": ["python", "node", "csharp"],
    },
    "lesson-2-mcp.html": {
        "title": "Lesson 2 · MCP servers - local-ai-lab",
        "description": "Build a Model Context Protocol (MCP) server that exposes local "
                       "document search as a tool Claude Code can call. Python, Node.js, C#.",
        "keywords": ["MCP server", "Model Context Protocol", "Claude Code tools", "AI tools"],
        "kind": "lesson", "number": 2, "name": "MCP servers",
        "languages": ["python", "node", "csharp"],
    },
}


def lesson_pages() -> dict[str, dict]:
    """Every working config-driven lesson, keyed by its published filename."""
    pages = {}
    for directory in sorted(LESSONS.glob("[0-9]*")):
        config = directory / "lesson.json"
        if not config.is_file():
            continue
        lesson = json.loads(config.read_text(encoding="utf-8"))
        if lesson.get("status") != "working":
            continue
        number = int(re.match(r"(\d+)", directory.name).group(1))
        slug = lesson.get("slug") or re.sub(r"^\d+-", "", directory.name)
        seo = lesson.get("seo") or {}
        pages[f"lesson-{number}-{slug}.html"] = {
            "title": f"Lesson {number} · {lesson.get('title', '')} - local-ai-lab",
            "description": seo.get("description", ""),
            "keywords": seo.get("keywords", []),
            "kind": "lesson", "number": number, "name": lesson.get("title", ""),
            "languages": lesson.get("languages", []),
        }
    return pages


def all_pages() -> dict[str, dict]:
    return {**STATIC, **lesson_pages()}


def _json_ld(name: str, page: dict) -> dict:
    url = SITE if name == "index.html" else SITE + name
    course = {"@type": "Course", "name": "local-ai-lab", "url": SITE,
              "description": STATIC["index.html"]["description"],
              "provider": {"@type": "Person", "name": "Nik Reljin"}}
    if page["kind"] == "course":
        return {"@context": "https://schema.org", **course, "isAccessibleForFree": True,
                "inLanguage": "en", "image": IMAGE,
                "keywords": ", ".join(COURSE_KEYWORDS + page["keywords"])}
    if page["kind"] == "lesson":
        return {"@context": "https://schema.org", "@type": "LearningResource",
                "name": f"Lesson {page['number']}: {page['name']}", "url": url,
                "description": page["description"], "learningResourceType": "tutorial",
                "educationalLevel": "intermediate", "isAccessibleForFree": True,
                "inLanguage": "en", "image": IMAGE,
                # schema.org has no programmingLanguage on LearningResource; say it in text.
                "teaches": ", ".join(page["keywords"]),
                "keywords": ", ".join(LANG_NAMES.get(x, x) for x in page["languages"]),
                "position": page["number"], "isPartOf": course}
    return {"@context": "https://schema.org", "@type": "WebPage", "name": page["title"],
            "url": url, "description": page["description"], "isPartOf": course}


def head_for(name: str, page: dict | None = None) -> str:
    """The `<!-- seo -->` block for one page, indented for a `<head>`."""
    page = page or all_pages()[name]
    url = SITE if name == "index.html" else SITE + name
    esc = lambda s: html.escape(s, quote=True)  # noqa: E731
    keywords = ", ".join(dict.fromkeys(page["keywords"] + COURSE_KEYWORDS))
    og_type = "website" if page["kind"] == "course" else "article"
    # "</" cannot appear inside a script element; JSON allows the escaped slash.
    ld = json.dumps(_json_ld(name, page), ensure_ascii=False, separators=(",", ":"))
    ld = ld.replace("</", "<\\/")
    lines = [
        "<!-- seo -->",
        f'<meta name="description" content="{esc(page["description"])}" />',
        f'<meta name="keywords" content="{esc(keywords)}" />',
        '<meta name="author" content="Nik Reljin" />',
        f'<link rel="canonical" href="{esc(url)}" />',
        '<meta property="og:site_name" content="local-ai-lab" />',
        f'<meta property="og:type" content="{og_type}" />',
        f'<meta property="og:title" content="{esc(page["title"])}" />',
        f'<meta property="og:description" content="{esc(page["description"])}" />',
        f'<meta property="og:url" content="{esc(url)}" />',
        f'<meta property="og:image" content="{IMAGE}" />',
        f'<meta property="og:image:width" content="{IMAGE_SIZE[0]}" />',
        f'<meta property="og:image:height" content="{IMAGE_SIZE[1]}" />',
        f'<meta property="og:image:alt" content="{esc(IMAGE_ALT)}" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{esc(page["title"])}" />',
        f'<meta name="twitter:description" content="{esc(page["description"])}" />',
        f'<meta name="twitter:image" content="{IMAGE}" />',
        f'<meta name="twitter:image:alt" content="{esc(IMAGE_ALT)}" />',
        f'<script type="application/ld+json">{ld}</script>',
        "<!-- /seo -->",
    ]
    return "\n".join("  " + line for line in lines) + "\n"


def sitemap() -> str:
    names = sorted(all_pages(), key=lambda n: (n != "index.html", n))
    urls = "".join(f"  <url><loc>{SITE if n == 'index.html' else SITE + n}</loc></url>\n"
                   for n in names)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls}</urlset>\n")


def _with_block(name: str, text: str, block: str) -> str:
    """Replace the page's block, or insert it after <title> (dropping the old description)."""
    if BLOCK.search(text):
        return BLOCK.sub(lambda _m: block, text, count=1)
    text = re.sub(r'[ \t]*<meta name="description"[^>]*>\n?', "", text, count=1)
    text, count = re.subn(r"(</title>[ \t]*)\n?", lambda m: m.group(1) + "\n" + block, text, count=1)
    if count == 0:
        raise SystemExit(f"docs/{name}: no </title> to put the SEO block after")
    return text


def problems() -> list[str]:
    found = []
    pages = all_pages()
    seen: dict[str, str] = {}
    for name, page in pages.items():
        desc = page["description"]
        if not desc:
            found.append(f"{name}: no description (lesson.json `seo.description`)")
        elif len(desc) > DESCRIPTION_MAX:
            found.append(f"{name}: description is {len(desc)} chars, max {DESCRIPTION_MAX}")
        if not page["keywords"]:
            found.append(f"{name}: no keywords (lesson.json `seo.keywords`)")
        if desc in seen:
            found.append(f"{name}: same description as {seen[desc]}")
        seen.setdefault(desc, name)
        path = DOCS / name
        if not path.is_file():
            continue  # check_docs reports missing pages
        text = path.read_text(encoding="utf-8")
        if head_for(name, page) not in text:
            hint = "./run -l N build" if page["kind"] == "lesson" and name not in STATIC else \
                "python3 tools/seo.py --write"
            found.append(f"docs/{name}: SEO block missing or stale - run: {hint}")
        title = re.search(r"<title>(.*?)</title>", text, re.S)
        if not title or html.unescape(title.group(1)) != page["title"]:
            found.append(f"docs/{name}: <title> does not match the og:title in tools/seo.py")
        for tag in ('name="description"', 'rel="canonical"', 'property="og:title"'):
            if text.count(tag) != 1:
                found.append(f"docs/{name}: expected exactly one {tag} tag")
    path = DOCS / "sitemap.xml"
    if not path.is_file() or path.read_text(encoding="utf-8") != sitemap():
        found.append("docs/sitemap.xml is stale - run: python3 tools/seo.py --write")
    if not (DOCS / IMAGE.removeprefix(SITE)).is_file():
        found.append(f"docs/{IMAGE.removeprefix(SITE)} is missing (the share image)")
    return found


def write() -> None:
    for name in STATIC:
        path = DOCS / name
        text = path.read_text(encoding="utf-8")
        path.write_text(_with_block(name, text, head_for(name)), encoding="utf-8")
    (DOCS / "sitemap.xml").write_text(sitemap(), encoding="utf-8")


def main(argv: list[str]) -> int:
    if argv == ["--write"]:
        write()
        return 0
    if argv == ["--check"]:
        found = problems()
        for p in found:
            print(f"  - {p}")
        return 1 if found else 0
    print("usage: tools/seo.py --write | --check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
