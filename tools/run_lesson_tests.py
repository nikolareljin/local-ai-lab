#!/usr/bin/env python3
"""Run every lesson's own test suite, each in its own process.

The repo-root suite (`pytest -q`, which `pyproject.toml` pins to `tests/`) covers
the engine and the action contract. It does not run the lessons' tests, so until
this existed a lesson could ship a broken suite and CI would stay green.

**One process per lesson is not a style choice.** Lessons own their code under
`lessons/NN-slug/python/`, and each test adds that directory to `sys.path` so it
can `import langgraph_agent` and friends by bare name. Several lessons legitimately
have a file with the same name - `web.py` is in six of them - so a single pytest
session resolves `import web` to whichever lesson happens to be earlier on
`sys.path`, and one lesson's tests silently exercise another lesson's module.
That is not hypothetical: running all six together fails six of Lesson 7's
playground tests against Lesson 8's `web`.

Optional dependencies are not installed here. A lesson that needs one skips those
tests rather than failing, which is the same contract `./run -l N test` honours.

    python3 tools/run_lesson_tests.py            # every lesson
    python3 tools/run_lesson_tests.py 7 8        # just these
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def lesson_suites(only: set[int] | None = None) -> list[tuple[int, Path]]:
    """Every `lessons/NN-slug/python/test_*.py`, in lesson order."""
    found: list[tuple[int, Path]] = []
    for directory in sorted((ROOT / "lessons").glob("[0-9]*")):
        match = re.match(r"(\d+)", directory.name)
        if not match:
            continue
        number = int(match.group(1))
        if only and number not in only:
            continue
        for test_file in sorted((directory / "python").glob("test_*.py")):
            found.append((number, test_file))
    return found


def main(argv: list[str]) -> int:
    try:
        only = {int(a) for a in argv} or None
    except ValueError:
        print(f"[ERROR] lesson numbers only, got {argv}", file=sys.stderr)
        return 2

    suites = lesson_suites(only)
    if not suites:
        print("[ERROR] no lesson tests found" + (f" for {sorted(only)}" if only else ""),
              file=sys.stderr)
        return 1  # an empty run must not read as success

    failures = []
    for number, test_file in suites:
        rel = test_file.relative_to(ROOT)
        print(f"\n=== Lesson {number}: {rel} ", flush=True)
        # cwd is the lesson directory: the tests resolve `python/...` and their data
        # files relative to it, exactly as `./run -l N test` does.
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", test_file.name],
                                cwd=test_file.parent)
        if result.returncode != 0:
            failures.append(f"Lesson {number} ({rel})")

    print()
    if failures:
        print(f"{len(failures)} lesson suite(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"All {len(suites)} lesson suites passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
