"""Lesson 9 - run one recipe: `./run -l 9 recipe <name> [--live] [...]`.

  invoice_extract   internal document processing: invoices -> checked records
  home_automation   a smart home the model may change, except the front door
  doc_automation    draft a letter where every fact cites the corpus
  pdf_index         index a folder of PDFs, confined to one root, then search it
  doc_summary       read a document, return a summary whose every point quotes it
  doc_summary_graph the same summary as a LangGraph flow: verify, retry, human review

Each runs offline with a scripted stand-in by default; `--live` uses OLLAMA_MODEL.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "recipes"))

RECIPES = ["invoice_extract", "home_automation", "doc_automation", "pdf_index",
           "doc_summary", "doc_summary_graph"]


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in RECIPES:
        print(__doc__)
        return 0 if not argv else 2
    return importlib.import_module(argv[0]).main(argv[1:]) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
