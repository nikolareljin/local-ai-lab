"""Lesson 10 - install TypeSafe's official Python SDK, pinned and hash-checked.

Into its own venv (lessons/10-jev-system-one/.venv-sdk), so the course venv is
not touched. `--require-hashes` makes pip refuse any file whose sha256 is not in
requirements-sdk.txt: a replaced package on PyPI, or a dependency nobody pinned,
fails the install instead of running.

Note the name: the package is `typesafe-sdk`. Do not `pip install qev` expecting
anything from TypeSafe - that PyPI name belongs to an unrelated project.
"""

from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

LESSON = Path(__file__).resolve().parents[1]
VENV = LESSON / ".venv-sdk"
REQUIREMENTS = LESSON / "requirements-sdk.txt"


def main() -> int:
    if not VENV.exists():
        print(f"creating {VENV.relative_to(LESSON)}")
        venv.create(VENV, with_pip=True)
    py = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    cmd = [str(py), "-m", "pip", "install", "--require-hashes", "--only-binary=:all:",
           "-r", str(REQUIREMENTS)]
    print("$ " + " ".join(cmd[1:]))
    code = subprocess.call(cmd)
    if code == 0:
        version = subprocess.check_output(
            [str(py), "-c", "import importlib.metadata as m; print(m.version('typesafe-sdk'))"],
            text=True).strip()
        print(f"typesafe-sdk {version} installed, every file hash-checked.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
