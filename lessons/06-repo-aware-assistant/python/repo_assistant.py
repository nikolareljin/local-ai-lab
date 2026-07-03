"""Lesson 6 - Repo-aware AI assistant demo (Python).

A repo-aware assistant answers questions about *one codebase* - and only from
what is actually in it. This demo builds a tiny, offline version of that:

  1. INDEX   - walk the repo, split every file into line-numbered passages, and
               remember each passage's path and line range (its *citation*).
  2. ANSWER  - retrieve the passages that overlap the question, and answer *only*
               from them, always citing `path:start-end`. If nothing clears a
               minimum score, the assistant says "not found" instead of guessing.
  3. PLAN    - for a change request, produce a plan-before-edit: the relevant
               files, the current behaviour (cited), a minimal change, and which
               tests and docs to update - and it changes *no files*.

The corpus is a small sample repo under `data/repo/`; the questions live in
`data/questions.json`. Everything is deterministic and offline, and the Node and
.NET ports implement the same algorithm, so all three print byte-identical output.

Run:  python repo_assistant.py

PRODUCTION (see the lesson README, "From demo to production"):
- retrieval here is deterministic keyword overlap and the answer is extractive so
  the lesson is reproducible; point the same index/citation contract at your real
  repo, retriever and model and the shape is unchanged.
"""

import json
import os
import re
import sys
from pathlib import Path

LESSON_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = LESSON_DIR / "data" / "repo"
QUESTIONS = LESSON_DIR / "data" / "questions.json"

# Point the assistant at your OWN repo with:  REPO_PATH=/path/to/repo
# (unset, it indexes the sample repo under data/repo so the demo is reproducible).
# Directories/extensions worth skipping when indexing a real project - noise that
# would only dilute retrieval. The sample repo contains none of these, so the demo
# output is unchanged; on a real repo they keep the index to source and docs.
IGNORE_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    "bin", "obj", "target", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".idea",
}
TEXT_EXT = {
    ".md", ".txt", ".rst", ".py", ".sh", ".js", ".mjs", ".ts", ".tsx", ".jsx",
    ".cs", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".rs", ".go",
    ".java", ".kt", ".rb", ".php", ".html", ".css", ".c", ".h", ".cpp", ".hpp",
    ".sql", ".xml",
}

# Common words dropped before scoring so retrieval keys on the meaningful terms.
# Kept identical across the Python, Node and .NET ports.
STOPWORDS = {
    "a", "an", "the", "to", "of", "do", "i", "in", "on", "is", "are",
    "and", "my", "your", "you", "they", "their", "it", "we",
}


def tokenize(text):
    return re.findall(r"[a-z0-9_]+", text.lower())


def terms(text):
    """Distinct meaningful (non-stopword) tokens of `text`."""
    return {t for t in tokenize(text) if t not in STOPWORDS}


# --- Index: split every repo file into line-numbered passages ----------------
def is_indexable(rel_path):
    """Skip vendored/build dirs and non-text files - noise for a code assistant."""
    parts = rel_path.split("/")
    if any(p in IGNORE_DIRS or p.startswith(".") for p in parts[:-1]):
        return False
    return os.path.splitext(parts[-1])[1].lower() in TEXT_EXT


def chunk_file(rel_path, raw):
    """Split one file into passages separated by blank lines, remembering the
    1-based line range of each so we can cite `path:start-end`."""
    chunks = []
    lines = raw.splitlines()
    start = None
    for i, line in enumerate(lines):
        blank = line.strip() == ""
        if not blank and start is None:
            start = i
        elif blank and start is not None:
            chunks.append(_make_chunk(rel_path, lines, start, i - 1))
            start = None
    if start is not None:
        chunks.append(_make_chunk(rel_path, lines, start, len(lines) - 1))
    return chunks


def _make_chunk(rel_path, lines, first, last):
    body = lines[first:last + 1]
    text = "\n".join(body)
    return {
        "path": rel_path,
        "start": first + 1,          # citations are 1-based, human-facing
        "end": last + 1,
        "first_line": body[0].strip(),
        "tokens": terms(text),
    }


def build_index(repo_dir=REPO_DIR):
    """Walk the repo (files sorted by path) and index every indexable passage.
    Returns (sorted file list, passage list) - the passages carry the citations.
    Ignored directories are pruned during the walk, so a real repo's `.git/` and
    `node_modules/` are never descended into (not just filtered afterwards)."""
    repo_dir = Path(repo_dir)
    rels = []
    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for name in filenames:
            full = Path(dirpath) / name
            if full.is_symlink():
                continue  # don't index symlinked files: avoids reading outside the repo root
            rel = full.relative_to(repo_dir).as_posix()
            if is_indexable(rel):
                rels.append(rel)
    rels.sort()
    chunks = []
    for rel in rels:
        raw = (repo_dir / rel).read_text(encoding="utf-8", errors="replace")
        chunks.extend(chunk_file(rel, raw))
    return rels, chunks


def cite(chunk):
    return "%s:%d-%d" % (chunk["path"], chunk["start"], chunk["end"])


# --- Retrieve: keyword overlap, deterministic order --------------------------
def retrieve(query, chunks, top_k):
    """Top-k passages by how many distinct query terms they contain.
    Deterministic: score desc, then path asc, then start line asc."""
    q = terms(query)
    scored = []
    for c in chunks:
        s = len(q & c["tokens"])
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda sc: (-sc[0], sc[1]["path"], sc[1]["start"]))
    return scored[:top_k]


# --- Answer: only from retrieved passages, always cited, else "not found" ----
def answer(query, chunks, top_k, min_score):
    """Answer a locate question from the repo, or abstain. Returns a dict the
    reporter and the web GUI both render."""
    hits = retrieve(query, chunks, top_k)
    if not hits or hits[0][0] < min_score:
        best = hits[0][0] if hits else 0
        return {"kind": "not_found", "best": best}
    top_score, top = hits[0]
    return {
        "kind": "grounded",
        "score": top_score,
        "citation": cite(top),
        "line": top["first_line"],
        "sources": [cite(c) for _, c in hits],
    }


# --- Plan-before-edit: relevant files, behaviour, change, tests, docs --------
def _first_under(paths, prefix):
    for p in paths:
        if p.startswith(prefix):
            return p
    return None


def plan(query, files, chunks, top_k):
    """Produce a change plan grounded in retrieval - and change no files."""
    hits = retrieve(query, chunks, top_k)
    if not hits:
        return {"kind": "not_found", "best": 0}
    top = hits[0][1]
    tests_path = _first_under(files, "tests/")
    return {
        "kind": "plan",
        "relevant": [cite(c) for _, c in hits],
        "behaviour": {"citation": cite(top), "line": top["first_line"]},
        "change": "add the new code alongside %s, matching the pattern already there" % top["path"],
        "tests": tests_path or "add a test under tests/",
        "docs": "README.md" if "README.md" in files else "update the project docs",
    }


# --- Reporting (byte-identical across the three ports) ------------------------
def respond(q, files, chunks, top_k, min_score):
    if q["kind"] == "plan":
        return plan(q["question"], files, chunks, top_k)
    return answer(q["question"], chunks, top_k, min_score)


def print_response(n, q, result, min_score):
    tag = "   [plan-before-edit]" if q["kind"] == "plan" else ""
    print("\nQ%d  %s%s" % (n, q["question"], tag))
    if result["kind"] == "grounded":
        print("    GROUNDED  -  answered only from indexed repository lines")
        print("    %s" % result["citation"])
        print("      %s" % result["line"])
        print("    sources: %s" % " . ".join(result["sources"]))
    elif result["kind"] == "plan":
        print("    PLAN  -  no files changed, approve before editing")
        print("    1. relevant files    %s" % " . ".join(result["relevant"]))
        print("    2. current behaviour  %s  ->  %s" % (result["behaviour"]["citation"], result["behaviour"]["line"]))
        print("    3. minimal change     %s" % result["change"])
        print("    4. update tests       %s" % result["tests"])
        print("    5. update docs        %s" % result["docs"])
    else:
        print("    NOT FOUND  -  best match scored %d (< min %d), so the assistant abstains" % (result["best"], min_score))
        print("      no citation, no invented answer")


def load_questions():
    with open(QUESTIONS, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    """No args: run the canned demo over data/questions.json (byte-identical across
    ports). `ask "q"` / `plan "q"`: answer one free question about the repo. Set
    REPO_PATH to index your own repository instead of the bundled sample."""
    argv = sys.argv[1:] if argv is None else argv
    cfg = load_questions()
    env_repo = os.environ.get("REPO_PATH")
    repo_dir = Path(env_repo).expanduser().resolve() if env_repo else REPO_DIR
    label = str(repo_dir) if env_repo else "data/repo"
    files, chunks = build_index(repo_dir)

    if argv and argv[0] in ("ask", "plan"):
        question = " ".join(argv[1:]).strip()
        if not question:
            print('usage: repo_assistant.py [ask|plan] "your question"')
            return
        questions = [{"id": argv[0], "kind": "plan" if argv[0] == "plan" else "locate",
                      "question": question}]
    else:
        questions = cfg["questions"]

    print("Repo-aware assistant  -  indexed %d files, %d passages under %s"
          % (len(files), len(chunks), label))
    for i, q in enumerate(questions, start=1):
        result = respond(q, files, chunks, cfg["top_k"], cfg["min_score"])
        print_response(i, q, result, cfg["min_score"])


if __name__ == "__main__":
    main()
