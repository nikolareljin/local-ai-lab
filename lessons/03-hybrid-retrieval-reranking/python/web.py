"""Lesson 3 - interactive hybrid-search web UI.

Type a query; see the BM25, semantic, and fused (RRF) rankings side by side over
the demo corpus. Reuses the demo's retrieval logic (no duplication).

Run:  python web.py        (or:  ./run -l 3 web)

This is the interactive app for the lesson; the retrieval *algorithm* also ships
as the polyglot one-shot `demo` (Python / Node / .NET).
"""

import html
import socket
from pathlib import Path

from flask import Flask, request

from hybrid_demo import hybrid, tokenize

app = Flask(__name__)

# The interactive UI searches the Fictive Story corpus (a richer, fun document) —
# the best way to feel hybrid retrieval on real prose. The byte-checked `demo`
# action keeps using the tiny data/ corpus.
STORY_DIR = Path(__file__).resolve().parent.parent / "story"


def load_story():
    docs = []
    for path in sorted(STORY_DIR.glob("*.md")):
        docs.append({"name": path.name, "tokens": tokenize(path.read_text(encoding="utf-8"))})
    return docs


DOCS = load_story()

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Lesson 3 · Hybrid search</title>
<style>
  body {{ font: 16px/1.5 system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ font-size: 1.2rem; }}
  form {{ display: flex; gap: .5rem; margin: 1rem 0; }}
  input[type=text] {{ flex: 1; padding: .5rem; font-size: 1rem; }}
  button {{ padding: .5rem 1rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
  th, td {{ text-align: left; padding: .4rem .6rem; border-bottom: 1px solid #ddd; }}
  th {{ width: 9rem; color: #444; }}
  code {{ background: #f4f4f4; padding: .1rem .3rem; border-radius: 3px; }}
  .hint {{ color: #666; }}
</style></head><body>
<h1>Lesson 3 · Hybrid search — <em>The Voyage of Caretta the Magnificent</em></h1>
<p class="hint">Searching the 5-chapter fictive story. BM25 wins exact terms; the semantic stand-in wins
paraphrases; RRF fuses both. Try an exact name like <code>Nuevo Edén</code> or
<code>Alpha Centauri</code>, or a paraphrase like <code>who found the new planet</code>.</p>
<form method="get" action="/">
  <input type="text" name="q" value="{query}" placeholder="ask the docs…" autofocus>
  <button type="submit">Search ▶</button>
</form>
{results}
</body></html>"""


def render_results(query):
    if not query:
        return '<p class="hint">Enter a query above.</p>'
    lexical, semantic, fused = hybrid(query, DOCS)
    rows = [
        ("BM25 (lexical)", lexical),
        ("Semantic (stand-in)", semantic),
        ("Hybrid (RRF)", fused),
    ]
    body = "".join(
        f"<tr><th>{label}</th><td>{' · '.join(html.escape(n) for n in ranking)}</td></tr>"
        for label, ranking in rows
    )
    return f"<table>{body}</table>"


@app.route("/")
def index():
    query = request.args.get("q", "")
    return PAGE.format(query=html.escape(query, quote=True), results=render_results(query))


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    port = free_port()
    print(f"Lesson 3 · Hybrid search over the fictive story → http://127.0.0.1:{port}  (Ctrl-C to stop)", flush=True)
    app.run(host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
