"""Command-line entry point: `python -m localrag <index|ask> ...`."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .chunk import Chunk
from .config import Config, load_config
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .providers import get_provider
from .retriever import build_retriever
from .store import build_index, is_stale, load_chunks


def _ensure_index(config: Config, force: bool = False) -> List[Chunk]:
    if force or is_stale(config):
        chunks, n_files = build_index(config)
        print(f"[localrag] Indexed {n_files} file(s) into {len(chunks)} chunk(s).")
        return chunks
    return load_chunks(config)


def _answer(question: str, retriever, config: Config) -> None:
    hits = retriever.search(question, config.top_k)
    provider = get_provider(config.provider, config)
    user_prompt = build_user_prompt(question, hits)
    answer = provider.chat(SYSTEM_PROMPT, user_prompt)

    print("\n" + answer.strip() + "\n")
    if hits:
        seen = []
        for h in hits:
            tag = f"{h['source']}:{h['page_number']}"
            if tag not in seen:
                seen.append(tag)
        print("Sources: " + ", ".join(seen))
    else:
        print("Sources: (none — nothing relevant found in your documents)")


def _cmd_index(args: argparse.Namespace, config: Config) -> int:
    _ensure_index(config, force=args.reindex)
    return 0


def _cmd_ask(args: argparse.Namespace, config: Config) -> int:
    chunks = _ensure_index(config, force=args.reindex)
    retriever = build_retriever(chunks, config)
    print(f"[localrag] provider={config.provider} retriever={getattr(retriever, 'name', '?')}")

    if args.question:
        _answer(" ".join(args.question), retriever, config)
        return 0

    print("Ask a question about your documents (Ctrl-D or 'exit' to quit).")
    while True:
        try:
            question = input("\n> ").strip()
        except EOFError:
            print()
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            break
        try:
            _answer(question, retriever, config)
        except Exception as exc:
            print(f"[localrag] Error: {exc}")
    return 0


def _cmd_web(args: argparse.Namespace, config: Config) -> int:
    from .web import run

    run(host=args.host, port=args.port, config=config)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="localrag", description="Tiny local RAG demo.")
    parser.add_argument("--provider", help="Override RAG_PROVIDER (claude|ollama|gemini|openai).")
    parser.add_argument("--retriever", help="Override RAG_RETRIEVER (bm25|embeddings).")
    parser.add_argument("--k", type=int, help="Number of chunks to retrieve.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Build/refresh the document index.")
    p_index.add_argument("--reindex", action="store_true", help="Force a full rebuild.")
    p_index.set_defaults(func=_cmd_index)

    p_ask = sub.add_parser("ask", help="Ask a question (REPL if none given).")
    p_ask.add_argument("question", nargs="*", help="Optional one-shot question.")
    p_ask.add_argument("--reindex", action="store_true", help="Force a full rebuild first.")
    p_ask.set_defaults(func=_cmd_ask)

    p_web = sub.add_parser("web", help="Launch the drag-and-drop web UI.")
    p_web.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1).")
    p_web.add_argument("--port", type=int, default=5000, help="Bind port (default 5000).")
    p_web.set_defaults(func=_cmd_web)

    args = parser.parse_args(argv)

    config = load_config()
    if args.provider:
        config.provider = args.provider.lower()
    if args.retriever:
        config.retriever = args.retriever.lower()
    if args.k:
        config.top_k = args.k

    return args.func(args, config)


if __name__ == "__main__":
    sys.exit(main())
