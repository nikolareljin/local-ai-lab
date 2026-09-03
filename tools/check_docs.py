#!/usr/bin/env python3
"""Validate the documentation the main CI job deliberately ignores.

`ci.yml` skips `docs/**` and `**/*.md`, which is right for the Python suite and
wrong for everything else: a stale generated table, a broken relative link, or a
navigation label that no longer matches what it lists can never fail a build.
Every one of those has happened in this repository.

Checks, in order of how often they have actually broken:

  1. relative links   every `](./x)` / `](../x)` in a tracked Markdown file
                      resolves, and stays inside the repository
  2. README table     `tools/sync-readme-downloads.py --check` is clean
  3. curriculum       `lessons/CURRICULUM.md` matches the lesson registry
  4. lesson pages     every `status: working` lesson has a published page under
                      `docs/`, every published page has a lesson behind it, and the
                      hand-authored Lesson 1-2 pages are still there

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
    """Every Markdown file **git tracks**, which is the set that reaches GitHub.

    `rglob` would also pick up ignored local files - `.gitignore` names `/PLAN.md`,
    `/ANALYTICS_PLAN.md` and `/REORGANIZE_PLAN.md` precisely because they show up in
    working copies - and failing someone's local run over a scratch file they will
    never commit is a good way to teach them to stop running the check.

    Falls back to a filesystem walk when git is unavailable (a source tarball, say),
    since a slightly wider scan beats no check at all.
    """
    try:
        result = subprocess.run(["git", "ls-files", "-z", "*.md"], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        tracked = [ROOT / name for name in result.stdout.split("\0") if name]
        if tracked:
            return sorted(tracked)
    except (OSError, subprocess.CalledProcessError):
        pass  # not a git checkout, or no git on PATH - fall through
    return sorted(path for path in ROOT.rglob("*.md")
                  if not any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts))


def check_links() -> list[str]:
    """Relative links that point at nothing. CI ignores Markdown, so nothing else catches these.

    A target that resolves OUTSIDE the repository is treated as broken even when it
    exists. One `../` too many in a file near the root lands on the checkout's parent
    directory, which may well exist on a developer's machine and on the runner - and
    is still a 404 for anyone reading the file on GitHub or GitHub Pages.
    """
    problems = []
    for path in markdown_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT)
        for match in LINK.finditer(text):
            link = match.group(1)
            target = (path.parent / link).resolve()
            if not target.is_relative_to(ROOT):
                problems.append(f"{rel}: link escapes the repository -> {link}")
            elif not target.exists():
                problems.append(f"{rel}: broken link -> {link}")
    return problems


def check_readme_table() -> list[str]:
    """Delegate to the generator's own --check, and keep what it said.

    It fails for more than one reason - a stale table, but also missing HTML markers
    - and swallowing its output would leave a CI log saying only that something is
    wrong with a table.
    """
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "sync-readme-downloads.py"),
                             "--check"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode == 0:
        return []
    detail = " ".join((result.stdout + " " + result.stderr).split())
    message = ("README 'Lessons & downloads' table check failed - "
               "run: python3 tools/sync-readme-downloads.py")
    return [f"{message}\n      {detail}" if detail else message]


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


# Lessons 1-2 predate the config-driven layout: their pages are hand-authored and
# have no lesson.json to derive a filename from, so they are named here explicitly.
HAND_AUTHORED_PAGES = {
    "lesson-1-rag.html": "Lesson 1 (hand-authored)",
    "lesson-2-mcp.html": "Lesson 2 (hand-authored)",
}


def check_published_pages() -> list[str]:
    """A working lesson with no page is unreachable; a page with no lesson is a ghost.

    Both directions matter. A missing page means a lesson nobody can open. A leftover
    page means a stale URL still being served and still linked from the nav - which is
    what a renumber produces if only the directory is renamed.
    """
    problems = []
    published = {p.name for p in (ROOT / "docs").glob("lesson-*.html")}
    expected = dict(HAND_AUTHORED_PAGES)
    for number, lesson in lesson_registry():
        if lesson.get("status") != "working":
            continue
        expected[f"lesson-{number}-{lesson.get('slug')}.html"] = f"Lesson {number}"

    for name, label in sorted(expected.items()):
        if name not in published:
            hint = ("restore it - it is hand-authored, not generated"
                    if name in HAND_AUTHORED_PAGES
                    else f"run: ./run -l {name.split('-')[1]} build")
            problems.append(f"docs/{name} is missing ({label}) - {hint}")

    for name in sorted(published - set(expected)):
        problems.append(f"docs/{name} has no lesson behind it - delete it, or give the "
                        f"lesson status 'working'")
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
