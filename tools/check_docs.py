#!/usr/bin/env python3
"""Validate the documentation the main CI job deliberately ignores.

`ci.yml` skips `docs/**` and `**/*.md`, which is right for the Python suite and
wrong for everything else: a stale generated table, a broken relative link, or a
navigation label that no longer matches what it lists can never fail a build.
Every one of those has happened in this repository.

Checks, in order of how often they have actually broken:

  1. relative links   every `](./x)` / `](../x)` in a tracked Markdown file
                      resolves to something on disk
  2. README table     `tools/sync-readme-downloads.py --check` is clean
  3. curriculum       `lessons/CURRICULUM.md` matches the lesson registry
  4. lesson pages     every `status: working` lesson has a published page under
                      `docs/`, and every published page has a lesson behind it

Run it locally the same way CI does:

    python3 tools/check_docs.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {"node_modules", ".git", "venv", ".venv", "__pycache__", ".pytest_cache"}
LINK = re.compile(r"\]\((\.{1,2}/[^)#\s]+)")


def markdown_files() -> list[Path]:
    out = []
    for path in ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        out.append(path)
    return sorted(out)


def check_links() -> list[str]:
    """Relative links that point at nothing. CI ignores Markdown, so nothing else catches these."""
    problems = []
    for path in markdown_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in LINK.finditer(text):
            target = (path.parent / match.group(1)).resolve()
            if not target.exists():
                rel = path.relative_to(ROOT)
                problems.append(f"{rel}: broken link -> {match.group(1)}")
    return problems


def check_readme_table() -> list[str]:
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "sync-readme-downloads.py"),
                             "--check"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        return ["README 'Lessons & downloads' table is stale - "
                "run: python3 tools/sync-readme-downloads.py"]
    return []


def lesson_registry() -> list[tuple[int, dict]]:
    lessons = []
    for directory in sorted((ROOT / "lessons").glob("[0-9]*")):
        config = directory / "lesson.json"
        if not config.is_file():
            continue
        number = int(re.match(r"(\d+)", directory.name).group(1))
        lessons.append((number, json.loads(config.read_text(encoding="utf-8"))))
    return lessons


def check_curriculum() -> list[str]:
    """CURRICULUM.md is generated; a hand edit or a missed regeneration shows up here."""
    generated = ROOT / "lessons" / "CURRICULUM.md"
    if not generated.is_file():
        return ["lessons/CURRICULUM.md is missing - run: tools/sync-curriculum.sh"]
    text = generated.read_text(encoding="utf-8")
    problems = []
    for number, lesson in lesson_registry():
        title = lesson.get("title", "")
        if f"| {number} | {title} |" not in text:
            problems.append(f"lessons/CURRICULUM.md is missing lesson {number} ({title}) - "
                            "run: tools/sync-curriculum.sh")
    return problems


def check_published_pages() -> list[str]:
    """A working lesson with no page is unreachable; a page with no lesson is a ghost."""
    problems = []
    published = {p.name for p in (ROOT / "docs").glob("lesson-*.html")}
    for number, lesson in lesson_registry():
        if lesson.get("status") != "working":
            continue
        expected = f"lesson-{number}-{lesson.get('slug')}.html"
        if expected not in published:
            problems.append(f"docs/{expected} is missing - run: ./run -l {number} build")
    return problems


CHECKS = (
    ("relative links", check_links),
    ("README downloads table", check_readme_table),
    ("generated curriculum", check_curriculum),
    ("published lesson pages", check_published_pages),
)


def main() -> int:
    failures = []
    for label, check in CHECKS:
        problems = check()
        status = "ok" if not problems else f"{len(problems)} problem(s)"
        print(f"  {label:26} {status}")
        failures.extend(problems)
    if failures:
        print("\nDocumentation checks failed:")
        for problem in failures:
            print(f"  - {problem}")
        return 1
    print("\nAll documentation checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
