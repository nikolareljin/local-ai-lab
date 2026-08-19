"""Lesson 1 - the pipeline, printed, with no model involved.

`./run -l 1` and `./run -l 1 ask` both call a provider, which needs Claude Code,
Ollama, or an API key, and produces different prose every run. This is the
`demo` action every other lesson has: it walks the same pipeline and stops one
step short of generation, so you can read what RAG actually does - and what the
model would have been handed - with nothing installed and nothing to configure.

  extract -> chunk -> retrieve -> the grounded prompt

Deterministic and offline. Run:  ./run -l 1 demo
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from localrag.chunk import chunk_pages  # noqa: E402
from localrag.config import load_config  # noqa: E402
from localrag.engine import dedup_sources  # noqa: E402
from localrag.extract import discover_files, extract_pages  # noqa: E402
from localrag.prompts import SYSTEM_PROMPT, build_user_prompt  # noqa: E402
from localrag.retriever import Bm25Retriever  # noqa: E402

QUESTIONS = [
    "How do I reset the device?",
    "How long does a full charge take?",
    "What is the capital of France?",
]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    config = load_config()
    questions = [" ".join(argv)] if argv else QUESTIONS

    paths = discover_files(config.docs_dir)
    if not paths:
        print(f"No documents under {config.docs_dir}. Drop a .md/.txt/.pdf/.docx in there first.")
        return 1

    pages = []
    for path in paths:
        pages.extend(extract_pages(path))
    chunks = chunk_pages(pages)
    retriever = Bm25Retriever(chunks)

    print("Lesson 1 · RAG pipeline  -  no model is called anywhere in this demo")
    print()
    print(f"  1. extract   {len(paths)} file(s) -> {len(pages)} page(s)")
    print(f"     {', '.join(p.name for p in paths)}")
    print(f"  2. chunk     {len(pages)} page(s) -> {len(chunks)} chunk(s)")
    print(f"  3. retrieve  BM25, top {config.top_k} per question")
    print()

    for i, question in enumerate(questions, start=1):
        hits = retriever.search(question, config.top_k)
        print(f"Q{i}  {question}")
        if not hits:
            print("    no chunks matched - the model would be told to say so")
            print()
            continue
        print(f"    sources: {' . '.join(dedup_sources(hits))}")
        for hit in hits[:2]:
            snippet = " ".join(hit["text"].split())[:110]
            print(f"      [{hit['source']}:{hit['page_number']}] {snippet}...")
        print()

    # The last step before generation: exactly what the provider would receive.
    last = questions[-1]
    system, user = SYSTEM_PROMPT, build_user_prompt(last, retriever.search(last, config.top_k))
    print("The grounded prompt for the final question, in full:")
    print("-" * 72)
    print(system.strip())
    print()
    print(user[:900] + ("..." if len(user) > 900 else ""))
    print("-" * 72)
    print()
    print("That prompt is the whole trick: the model only sees retrieved text, and is")
    print("told to cite it and to refuse anything it cannot find there.")
    print(f"Send it for real with:  ./run -l 1 ask \"{questions[0]}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
