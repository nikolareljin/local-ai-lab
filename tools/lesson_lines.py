#!/usr/bin/env python3
"""Keep the code excerpts in lesson pages pointing at the code they name.

A code step in `lesson.json` shows part of a source file:

    {"type": "code", "file": "python/policy.py", "lines": "26-45", "symbol": "decide"}

`lines` is what the page renders. Typed by hand it goes stale the moment someone adds a
line above the function, and the page then shows the wrong code without failing anything.
So every step also names a `symbol`, and this tool computes `lines` from it.

    python3 tools/lesson_lines.py            # check every lesson; exit 1 on drift
    python3 tools/lesson_lines.py --write    # recompute `lines` in every lesson.json
    python3 tools/lesson_lines.py --expect   # JSON for the browser tests in e2e/

What a `symbol` can be:

    decide                    a function, class or module-level name
    Replay.next               a method, or a function nested in another
    rank..rrf                 from the start of the first to the end of the second
    marker:the whole call     from the comment line with that text to the next
                              comment rule (a line ending in 20 or more dashes)
    around:"create_ticket"    Python only: the smallest call, list or dict that
                              spans the first line containing that text

Python is resolved with `ast` (decorators included). JavaScript and C# are resolved by
finding the declaration and matching brackets; the comment block directly above it is
part of the excerpt.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LESSONS = ROOT / "lessons"
RULE = re.compile(r"(#|//) ?-{20,}\s*$")  # a comment rule: "# ----------" closes a marker
NOT_A_DECLARATION = ("return", "await", "if", "else", "throw", "new", "yield", "case")


class Unresolved(ValueError):
    """The symbol is not in the file (renamed, removed, or misspelt in lesson.json)."""


# --------------------------------------------------------------------------- Python
def _python_node(tree: ast.AST, dotted: str) -> ast.AST:
    """`Replay.next` -> the ast node of method `next` in class `Replay`."""
    node = tree
    for name in dotted.split("."):
        found = None
        for child in ast.walk(node):  # breadth-first: the outermost definition wins
            if child is node:
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if child.name == name:
                    found = child
                    break
            elif isinstance(child, ast.Assign) and node is tree:
                if any(isinstance(t, ast.Name) and t.id == name for t in child.targets):
                    found = child
                    break
            elif isinstance(child, ast.AnnAssign) and node is tree:
                if isinstance(child.target, ast.Name) and child.target.id == name:
                    found = child
                    break
        if found is None:
            raise Unresolved(f"no {dotted!r}")
        node = found
    return node


def _python_range(text: str, symbol: str) -> tuple[int, int]:
    tree = ast.parse(text)
    if symbol.startswith("around:"):
        needle = symbol[len("around:"):]
        hit = next((i for i, line in enumerate(text.splitlines(), 1) if needle in line), None)
        if hit is None:
            raise Unresolved(f"no line contains {needle!r}")
        spans = [(n.end_lineno - n.lineno, n.lineno, n.end_lineno) for n in ast.walk(tree)
                 if isinstance(n, (ast.Call, ast.List, ast.Dict, ast.Tuple))
                 and n.lineno < n.end_lineno and n.lineno <= hit <= n.end_lineno]
        if not spans:
            raise Unresolved(f"nothing spans the line with {needle!r}")
        _, start, end = min(spans)
        return start, end
    node = _python_node(tree, symbol)
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return start, node.end_lineno


# --------------------------------------------------------------------------- JavaScript, C#
def _strip(line: str) -> str:
    """The line without string literals and `//` comments, so their brackets do not count."""
    line = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`', '""', line)
    return re.sub(r"//.*$", "", line)


def _declares(line: str, name: str) -> bool:
    """Is `name` declared on this line (as opposed to called or mentioned)?"""
    bare = _strip(line)
    for match in re.finditer(r"\b" + re.escape(name) + r"\b", bare):
        before, after = bare[:match.start()], bare[match.end():]
        words = before.split()
        if not words or words[0] in NOT_A_DECLARATION:
            continue
        if before.count("(") != before.count(")") or "=" in before or before.rstrip().endswith("."):
            continue
        if not re.match(r"\s*(\(|=(?![=>])|\{|<|$)", after):
            continue
        return True
    return False


def _method(line: str, name: str) -> bool:
    """`search(query, k) {` inside a JavaScript class: a declaration with nothing before it."""
    return bool(re.match(r"\s*(?:async |static |get |set |#)*" + re.escape(name) + r"\s*\(", line))


def _statement_end(lines: list[str], start: int) -> int:
    """Index of the line that closes the declaration starting at `start`."""
    depth = 0
    for k in range(start, len(lines)):
        bare = _strip(lines[k])
        depth += sum(bare.count(c) for c in "([{") - sum(bare.count(c) for c in ")]}")
        if depth == 0 and bare.rstrip().endswith((";", "}", "};", "},")):
            return k
        if depth < 0:
            break
    raise Unresolved("no closing bracket")


def _brace_range(text: str, symbol: str) -> tuple[int, int]:
    lines = text.splitlines()
    lo, hi, start = 0, len(lines), None
    parts = symbol.split(".")
    for depth, name in enumerate(parts):
        start = next((k for k in range(lo, hi) if _declares(lines[k], name)
                      or (depth > 0 and _method(lines[k], name))), None)
        if start is None:
            raise Unresolved(f"no {symbol!r}")
        lo, hi = start + 1, _statement_end(lines, start) + 1
    end = hi - 1
    while start > 0 and re.match(r"\s*(///|//|/\*|\*|\[\w)", lines[start - 1]):
        start -= 1  # the doc comment (or C# attribute) above belongs to the excerpt
    return start + 1, end + 1


# --------------------------------------------------------------------------- any file
def _marker_range(text: str, needle: str) -> tuple[int, int]:
    lines = text.splitlines()
    start = next((k for k, line in enumerate(lines) if needle in line), None)
    if start is None or not needle:
        raise Unresolved(f"no marker line contains {needle!r}")
    end = next((k for k in range(start + 1, len(lines)) if RULE.search(lines[k])), None)
    if end is None:
        raise Unresolved(f"no closing comment rule after the marker {needle!r}")
    return start + 1, end + 1


def _one(path: Path, text: str, symbol: str) -> tuple[int, int]:
    if symbol.startswith("marker:"):
        return _marker_range(text, symbol[len("marker:"):])
    if path.suffix == ".py":
        return _python_range(text, symbol)
    if symbol.startswith("around:"):
        raise Unresolved("around: works in Python files only")
    return _brace_range(text, symbol)


def resolve(path: Path, symbol: str) -> str:
    """Where `symbol` lives in `path`, as lesson.json writes it: "start-end" (1-based)."""
    text = Path(path).read_text(encoding="utf-8")
    if ".." in symbol and not symbol.startswith(("marker:", "around:")):
        first, last = symbol.split("..", 1)
        start, end = _one(path, text, first)[0], _one(path, text, last)[1]
        if end < start:
            raise Unresolved(f"{last!r} ends before {first!r} starts")
    else:
        start, end = _one(path, text, symbol)
    return f"{start}-{end}"


# --------------------------------------------------------------------------- lessons
def lesson_dirs(lessons: Path = LESSONS) -> list[Path]:
    return sorted(p.parent for p in lessons.glob("[0-9]*/lesson.json"))


def code_steps(ldir: Path) -> list[dict]:
    """Every element of the lesson that shows a range of a file."""
    lesson = json.loads((ldir / "lesson.json").read_text(encoding="utf-8"))
    return [el for el in lesson["elements"] if el.get("lines")]


def problems(ldir: Path) -> list[tuple[dict, str, str | None]]:
    """(element, message, correct range or None) for every step that is not right."""
    out = []
    for el in code_steps(ldir):
        where = f"{ldir.name}/{el['file']}"
        symbol = el.get("symbol")
        if not symbol:
            out.append((el, f"{where} lines {el['lines']}: no `symbol`", None))
            continue
        try:
            want = resolve(ldir / el["file"], symbol)
        except (Unresolved, SyntaxError, OSError) as err:
            out.append((el, f"{where} {symbol}: {err}", None))
            continue
        if el["lines"] != want:
            out.append((el, f"{where} {symbol}: lines {el['lines']} should be {want}", want))
    return out


def check(lessons: Path = LESSONS) -> list[str]:
    """Messages for every lesson step whose `lines` is not its `symbol`. Empty means clean."""
    return [message for ldir in lesson_dirs(lessons) for _, message, _ in problems(ldir)]


def write(lessons: Path = LESSONS) -> tuple[int, list[str]]:
    """Recompute stale `lines`. Returns (how many were rewritten, what could not be)."""
    changed, stuck = 0, []
    for ldir in lesson_dirs(lessons):
        path = ldir / "lesson.json"
        text = path.read_text(encoding="utf-8")
        for el, message, want in problems(ldir):
            if want is None:
                stuck.append(message)
                continue
            # Edit the text, not the parsed JSON: the file keeps its layout and key order.
            # A step is identified by its file, range and symbol together.
            block = re.compile(
                r'(\{[^{}]*?"file":\s*' + re.escape(json.dumps(el["file"]))
                + r'[^{}]*?"lines":\s*)' + re.escape(json.dumps(el["lines"]))
                + r'([^{}]*?"symbol":\s*' + re.escape(json.dumps(el["symbol"])) + r')', re.S)
            text, n = block.subn(lambda m: m.group(1) + json.dumps(want) + m.group(2), text)
            if n != 1:
                stuck.append(f"{message} (found {n} matching steps in lesson.json; fix by hand)")
                continue
            changed += 1
        path.write_text(text, encoding="utf-8")
    return changed, stuck


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def published_problems(lessons: Path = LESSONS, docs: Path = ROOT / "docs") -> list[str]:
    """Steps whose current excerpt is not on the published page: the page was not rebuilt."""
    import html
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import lesson as engine
    out = []
    for ldir in lesson_dirs(lessons):
        meta = json.loads((ldir / "lesson.json").read_text(encoding="utf-8"))
        number = int(ldir.name.split("-")[0])
        page = docs / f"lesson-{number}-{meta.get('slug') or ldir.name.split('-', 1)[1]}.html"
        if meta.get("status") != "working" or not page.exists():
            continue  # a missing page is check_docs's "published lesson pages" finding
        shown = _squash(html.unescape(re.sub(r"<[^>]+>", "", page.read_text(encoding="utf-8"))))
        for el in code_steps(ldir):
            if _squash(engine.read_ref(ldir, el)) not in shown:
                out.append(f"docs/{page.name} does not show {el['file']} {el['lines']} "
                           f"({el.get('symbol')}) as it is now - run: ./run -l {number} build")
    return out


def expectations(lessons: Path = LESSONS) -> list[dict]:
    """What a browser must see for every code step: used by e2e/code-excerpts.spec.mjs."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import lesson as engine  # the renderer's own reader, so both agree on the slice
    out = []
    for ldir in lesson_dirs(lessons):
        meta = json.loads((ldir / "lesson.json").read_text(encoding="utf-8"))
        if meta.get("status") != "working":
            continue
        number = int(ldir.name.split("-")[0])
        for el in code_steps(ldir):
            shown = [line for line in engine.read_ref(ldir, el).splitlines() if line.strip()]
            out.append({"page": f"lesson-{number}-{ldir.name.split('-', 1)[1]}.html",
                        "lesson": number, "lang": el.get("lang"), "file": el["file"],
                        "symbol": el.get("symbol"), "lines": el["lines"],
                        "first": shown[0].strip(), "last": shown[-1].strip(),
                        "count": len(shown)})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="recompute `lines` from `symbol`")
    group.add_argument("--expect", action="store_true", help="print JSON for the browser tests")
    args = parser.parse_args(argv)
    if args.expect:
        print(json.dumps(expectations(), indent=1))
        return 0
    if args.write:
        changed, stuck = write()
        print(f"rewrote {changed} range(s)")
        for message in stuck:
            print(f"  cannot fix: {message}", file=sys.stderr)
        if changed:
            print("now rebuild the pages of the lessons that changed: ./run -l <N> build")
        return 1 if stuck else 0
    found = check()
    for message in found:
        print(f"  {message}", file=sys.stderr)
    if found:
        print(f"{len(found)} code excerpt(s) do not show the code they name. "
              "Fix: python3 tools/lesson_lines.py --write", file=sys.stderr)
        return 1
    print(f"code excerpts ok ({sum(len(code_steps(d)) for d in lesson_dirs())} steps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
