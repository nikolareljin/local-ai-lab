#!/usr/bin/env python3
"""local-ai-lab lesson engine.

One small program that reads a lesson's `lesson.json` and serves the two
operations the course needs:

  A) run   — execute the command element(s) for a chosen action + language.
  B) show  — walk through every element (note, command, code, config, text,
             media) in order, optionally filtered to one language.

Lessons live in `lessons/NN-slug/`; the NN prefix IS the lesson number, so
reordering a lesson is just a directory rename. Lessons 1-2 are handled by the
bash `run` dispatcher and are not part of this registry.

Used by `./run`; can also be invoked directly:  python tools/lesson.py list
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LESSONS_DIR = ROOT / "lessons"


# --------------------------------------------------------------------------- registry
def registry():
    """Map lesson number -> directory, derived from the NN- prefix."""
    found = {}
    if not LESSONS_DIR.is_dir():
        return found
    for entry in sorted(LESSONS_DIR.iterdir()):
        if not entry.is_dir() or not (entry / "lesson.json").is_file():
            continue
        m = re.match(r"^(\d+)-", entry.name)
        if m:
            found[int(m.group(1))] = entry
    return found


def lesson_dir(number):
    return registry().get(int(number))


def load(number):
    d = lesson_dir(number)
    if d is None:
        sys.exit(f"[ERROR] No lesson numbered {number} in lessons/ (need lessons/NN-slug/lesson.json).")
    with open(d / "lesson.json", encoding="utf-8") as fh:
        return d, json.load(fh)


def warn(msg):
    print(f"[INFO] {msg}", file=sys.stderr)


# --------------------------------------------------------------------------- python resolution
def venv_python():
    for rel in ("venv/bin/python", "venv/Scripts/python.exe"):
        p = ROOT / rel
        if p.exists():
            return str(p)
    return ""


def ensure_venv_python():
    """Reuse the repo's bash ensure_venv (creates venv + installs deps), return its python."""
    script = f'source {shlex.quote(str(ROOT))}/scripts/include.sh && ensure_venv 1>&2 && printf "%s" "$PYTHON_BIN"'
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    py = out.stdout.strip()
    if not py:
        warn("Could not prepare the virtualenv; falling back to system Python.")
        return sys.executable
    return py


def python_for(need_venv):
    if need_venv:
        return ensure_venv_python()
    return os.environ.get("PYTHON_BIN") or venv_python() or sys.executable


# --------------------------------------------------------------------------- A) run
def matching_commands(lesson, action, lang):
    cmds = []
    for el in lesson.get("elements", []):
        if el.get("type") != "command" or el.get("action") != action:
            continue
        el_lang = el.get("lang")
        if el_lang in (None, lang):
            cmds.append(el)
    return cmds


def cmd_run(args):
    ldir, lesson = load(args.number)
    if lesson.get("status") != "working":
        warn(f"Lesson {args.number} status is '{lesson.get('status')}' — not runnable yet.")
        return 0
    action = args.action or lesson.get("defaultAction", "demo")
    lang = args.lang or lesson.get("defaultLanguage", "python")

    cmds = matching_commands(lesson, action, lang)
    if not cmds:
        actions = sorted({e.get("action") for e in lesson.get("elements", [])
                          if e.get("type") == "command" and e.get("action")})
        sys.exit(f"[ERROR] No '{action}' command for lang '{lang}'. Available actions: {', '.join(actions)}")

    for el in cmds:
        shell = el["shell"]
        el_lang = el.get("lang") or lang
        if el_lang == "node" and not which("node"):
            sys.exit("[ERROR] Node.js is required (https://nodejs.org).")
        if el_lang == "csharp" and not which("dotnet"):
            sys.exit("[ERROR] The .NET SDK is required (https://dotnet.microsoft.com).")
        if el_lang == "python":
            py = python_for(el.get("venv", False))
            if shell.startswith("python "):
                shell = shlex.quote(py) + shell[len("python"):]
        if args.rest:
            shell = shell + " " + " ".join(shlex.quote(a) for a in args.rest)
        warn(f"Lesson {args.number} · {action} · {el_lang}:  {el['shell']}")
        rc = subprocess.run(shell, shell=True, cwd=ldir).returncode
        if rc != 0:
            return rc
    return 0


def which(name):
    return any((Path(p) / name).exists() for p in os.environ.get("PATH", "").split(os.pathsep) if p)


# --------------------------------------------------------------------------- B) show
RULE = "─" * 72


def read_ref(ldir, el):
    if "file" in el:
        path = ldir / el["file"]
        if not path.exists():
            return f"[missing file: {el['file']}]"
        return path.read_text(encoding="utf-8").rstrip("\n")
    return el.get("text", "")


def cmd_show(args):
    ldir, lesson = load(args.number)
    lang = args.lang
    print(f"\n{RULE}\nLesson {args.number} · {lesson.get('title','')}")
    if lesson.get("summary"):
        print(lesson["summary"])
    print(RULE)

    for el in lesson.get("elements", []):
        el_lang = el.get("lang")
        if lang and el_lang not in (None, lang):
            continue
        tag = f" [{el_lang}]" if el_lang else ""
        etype = el.get("type")
        title = el.get("title")

        if etype == "note":
            if title:
                print(f"\n• {title}")
            print(indent(read_ref(ldir, el)))
        elif etype == "command":
            label = f"{el.get('action','run')}{tag}"
            print(f"\n$ {el['shell']}    ({label})")
            if el.get("note"):
                print(indent(el["note"]))
        elif etype in ("code", "config"):
            head = el.get("file", "(inline)")
            print(f"\n── {etype}: {head}{tag} ──")
            if el.get("note"):
                print(indent(el["note"]))
            print(read_ref(ldir, el))
        elif etype == "text":
            print(f"\n✎ copy/paste{(' — ' + title) if title else ''}{tag}:")
            print(indent(read_ref(ldir, el)))
        elif etype in ("media", "image", "video"):
            kind = el.get("kind", etype)
            ref = el.get("file") or el.get("url", "")
            extra = el.get("alt") or el.get("note") or ""
            # Inline terminal image rendering is environment-specific; print a
            # labeled reference (the same element embeds natively on the site).
            print(f"\n[{kind}] {ref}" + (f" — {extra}" if extra else ""))
        else:
            print(f"\n[unknown element type: {etype}]")
    print()
    return 0


def indent(text, prefix="    "):
    return "\n".join(prefix + line for line in text.splitlines())


# --------------------------------------------------------------------------- list
def cmd_list(args):
    reg = registry()
    if not reg and not args.md:
        print("(no config-driven lessons yet)")
        return 0
    for num in sorted(reg):
        with open(reg[num] / "lesson.json", encoding="utf-8") as fh:
            m = json.load(fh)
        langs = ", ".join(m.get("languages", []))
        if args.md:
            print(f"| {num} | {m.get('title','')} | {m.get('status','')} | {langs} |")
        else:
            print(f"L{num:<3} {m.get('title',''):<40} [{m.get('status','')}]  ({langs})")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="lesson", description="local-ai-lab lesson engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list", help="list config-driven lessons")
    sp.add_argument("--md", action="store_true", help="emit markdown table rows")
    sp.set_defaults(fn=cmd_list)

    sp = sub.add_parser("run", help="run a lesson action")
    sp.add_argument("number", type=int)
    sp.add_argument("action", nargs="?", default=None)
    sp.add_argument("--lang", default=None)
    sp.set_defaults(fn=cmd_run)

    sp = sub.add_parser("show", help="walk through a lesson's elements")
    sp.add_argument("number", type=int)
    sp.add_argument("--lang", default=None)
    sp.set_defaults(fn=cmd_show)

    # parse_known_args so any trailing passthrough args (after the known ones)
    # reach the lesson command without REMAINDER swallowing options like --lang.
    args, extra = p.parse_known_args(argv)
    args.rest = extra
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
