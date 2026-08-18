"""Lesson 7 - Rebuild RAG with LangChain, and count what it cost.

Runs the Lesson 1 pipeline and the LangChain pipeline over the same corpus, with
the same system prompt, and prints:

  1. per question, what each side retrieved and cited - do they ground the same way?
  2. component by component, which hand-rolled file each LangChain piece replaced
  3. what the framework cost: your lines of code against your dependency surface

The default run is deterministic and offline: it compares *grounding*, not
generated text. Retrieval and the rendered prompt are reproducible; a model's
prose is not, and comparing what both pipelines feed the model is the sharper
test anyway.

Run:
  python langchain_rag.py                    # the comparison (offline, no model)
  python langchain_rag.py --measure          # re-derive the dependency numbers here
  python langchain_rag.py ask "question"     # real answer, via your chat model adapter
  python langchain_rag.py ask --native "..." # real answer, via framework-native ChatOllama

PRODUCTION (see the lesson README, "From demo to production"):
- the comparison is the teaching artefact, not the product; in a real system you
  pick one pipeline. What carries over is the citation contract and the habit of
  measuring the dependency you are about to take.
"""

import ast
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import handrolled_pipeline as handrolled  # noqa: E402

LESSON_DIR = Path(__file__).resolve().parent.parent
ROOT = handrolled.ROOT
CONFIG_FILE = LESSON_DIR / "data" / "questions.json"

INSTALL_HINT = "pip install -r lessons/07-langchain-rag/requirements.txt"
# Not in requirements.txt on purpose - see the note at the bottom of that file.
OLLAMA_HINT = "pip install langchain-ollama"

# Retrieval arms `ask --arm` accepts. bm25 is offline; embed needs Ollama running.
ARMS = {"bm25", "embed"}

# Which LangChain component stands in for which Lesson 1 file.
COMPONENTS = [
    ("load", "localrag/extract.py", "Document(...)"),
    ("split", "localrag/chunk.py", "RecursiveCharacterTextSplitter"),
    ("index", "localrag/store.py", "InMemoryVectorStore"),
    ("retrieve", "localrag/retriever.py", "BaseRetriever subclass (yours)"),
    ("prompt", "localrag/prompts.py", "ChatPromptTemplate"),
    ("provider", "localrag/providers/__init__.py", "SimpleChatModel subclass (yours)"),
    ("chain", "localrag/engine.py", "LCEL  ( | )"),
]

# The lesson's own LangChain code - the part you still write.
LC_FILES = ["python/lc_pipeline.py", "python/lc_provider.py"]

# Dependency numbers, measured the same way on both sides so the columns compare.
# "requirements" counts the lines you write; "packages" is the FULL resolved
# closure pip actually installs, which is the number that matters and the one
# people habitually under-estimate. Reproduce either column with:
#
#   pip download -d /tmp/base -r requirements.txt
#   pip download -d /tmp/lc   -r requirements.txt langchain-core langchain-text-splitters
#
# `--measure` re-derives them against the environment you are actually running.
DEPS = {
    "handrolled": {"direct": 8, "packages": 49, "size_mb": 34},
    "langchain": {"direct": 10, "packages": 67, "size_mb": 43},
}
# What the sunset package would have cost, had we used its BM25Retriever.
DEPS_WITH_COMMUNITY = {"packages": 80, "size_mb": 52}


def code_lines(path: Path) -> int:
    """Lines that are actually code: no blanks, no comments, no docstrings.

    Both sides are counted the same way, so a teaching file full of explanation
    is not unfairly penalised against a terse one.
    """
    source = path.read_text(encoding="utf-8")
    doc_lines = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    doc_lines.update(range(body[0].lineno, body[0].end_lineno + 1))
    counted = set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                        tokenize.DEDENT, tokenize.ENDMARKER, tokenize.ENCODING):
            continue
        if tok.start[0] not in doc_lines:
            counted.add(tok.start[0])
    return len(counted)


def total_lines(rel_paths) -> int:
    return sum(code_lines(ROOT / rel) for rel in rel_paths)


def load_settings() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as fh:
        return json.load(fh)


# Only these count as "LangChain is not installed". Anything else that fails to
# import is a real bug and must not be disguised as a missing dependency.
LANGCHAIN_PACKAGES = {"langchain_core", "langchain_text_splitters", "langchain_ollama"}


def import_langchain():
    """Return the LangChain pipeline module, or None when LangChain is not installed.

    Deliberately narrow: a `ModuleNotFoundError` is swallowed only when the module
    that is actually missing is a LangChain package. A typo or a genuine import-time
    failure inside `lc_pipeline` propagates, instead of being reported to the reader
    as "not installed" and sending them to reinstall a package they already have.
    """
    try:
        import lc_pipeline
        return lc_pipeline
    except ModuleNotFoundError as exc:
        if (exc.name or "").split(".")[0] in LANGCHAIN_PACKAGES:
            return None
        raise


def print_questions(settings, lc) -> None:
    size, overlap, k = settings["chunk_size"], settings["chunk_overlap"], settings["top_k"]
    hand_chunks = handrolled.split(handrolled.load(), size, overlap)
    lc_chunks = lc.split(lc.load(), size, overlap) if lc else []
    docs = len({c["source"] for c in hand_chunks})

    print(f"Rebuild RAG with LangChain  -  {docs} documents, same corpus, same system prompt")
    print(f"chunked at size={size} overlap={overlap}, retrieving top {k}")
    print()
    print(f"  hand-rolled  {len(hand_chunks):3} chunks   (chunk.py: collapse whitespace, "
          f"break on sentences)")
    if lc:
        print(f"  langchain    {len(lc_chunks):3} chunks   (RecursiveCharacterTextSplitter: "
              f"keep text, split on separators)")
    print()

    # Both arms build their index once and answer every question from it, which is
    # what makes the timing side of this comparison honest as well as the grounding.
    hand_retriever = handrolled.build_retriever(hand_chunks)
    retriever = lc.bm25_retriever(lc_chunks, k) if lc else None
    agreements = 0
    for i, question in enumerate(settings["questions"], start=1):
        hand_sources = handrolled.sources(handrolled.retrieve(hand_retriever, question, k))
        print(f"Q{i}  {question}")
        print(f"    hand-rolled   sources: {' . '.join(hand_sources)}")
        if not lc:
            print("    langchain     not installed")
            print()
            continue
        lc_sources = lc.sources(retriever.invoke(question))
        print(f"    langchain     sources: {' . '.join(lc_sources)}")
        if hand_sources == lc_sources:
            agreements += 1
            print("    GROUNDING AGREES  -  same sources, same order")
        else:
            only_lc = [s for s in lc_sources if s not in hand_sources]
            only_hand = [s for s in hand_sources if s not in lc_sources]
            extra = []
            if only_lc:
                extra.append("langchain also cites " + ", ".join(only_lc))
            if only_hand:
                extra.append("hand-rolled also cites " + ", ".join(only_hand))
            print(f"    GROUNDING DIFFERS  -  {'; '.join(extra)}")
        print()
    if lc:
        total = len(settings["questions"])
        print(f"    {agreements}/{total} questions grounded identically. "
              f"Different chunk boundaries, mostly the same evidence.")
        print()


def print_components(lc) -> None:
    print("Component by component")
    print(f"  {'step':9} {'hand-rolled (Lesson 1)':36} {'LangChain (Lesson 7)'}")
    print("  " + "-" * 79)
    hand_total = 0
    for step, rel, component in COMPONENTS:
        loc = code_lines(ROOT / rel)
        hand_total += loc
        shown = component if lc else "not installed"
        print(f"  {step:9} {rel:31}{loc:>4}L  {shown}")
    print("  " + "-" * 79)

    if not lc:
        print()
        print("LangChain is not installed, so only the hand-rolled side ran.")
        print(f"Install it to see the comparison:  {INSTALL_HINT}")
        return

    lc_total = total_lines([f"lessons/07-langchain-rag/{p}" for p in LC_FILES])
    print()
    print("What it cost")
    hand, lang = DEPS["handrolled"], DEPS["langchain"]
    print(f"  {'':22} {'hand-rolled':>14} {'LangChain':>14}")
    print(f"  {'code you maintain':22} {str(hand_total) + ' lines':>14} "
          f"{str(lc_total) + ' lines':>14}")
    print(f"  {'requirements lines':22} {hand['direct']:>14} {lang['direct']:>14}")
    print(f"  {'packages installed':22} {hand['packages']:>14} {lang['packages']:>14}")
    print(f"  {'install size':22} {'~' + str(hand['size_mb']) + ' MB':>14} "
          f"{'~' + str(lang['size_mb']) + ' MB':>14}")
    print()
    added = lang["packages"] - hand["packages"]
    print(f"  Two requirements lines cost {added} packages and "
          f"~{lang['size_mb'] - hand['size_mb']} MB.")
    print("  Taking BM25 from the sunset langchain-community, rather than writing the")
    print(f"  twenty-line retriever, would have made it "
          f"{DEPS_WITH_COMMUNITY['packages']} packages and "
          f"~{DEPS_WITH_COMMUNITY['size_mb']} MB.")


def cmd_demo() -> int:
    settings = load_settings()
    lc = import_langchain()
    print_questions(settings, lc)
    print_components(lc)
    return 0


def _langchain_closure() -> set:
    """Every installed distribution reachable from the lesson's two requirements."""
    from importlib.metadata import distribution, requires

    seen, queue = set(), ["langchain-core", "langchain-text-splitters"]
    while queue:
        name = queue.pop().lower().replace("_", "-")
        if name in seen:
            continue
        try:
            distribution(name)
        except Exception:
            continue
        seen.add(name)
        for raw in requires(name) or []:
            # "foo (>=1.0) ; extra == 'bar'" -> skip optional extras, keep the name.
            if "extra ==" in raw:
                continue
            dep = re.split(r"[\s\[<>=!;(]", raw.strip(), 1)[0]
            if dep:
                queue.append(dep)
    return seen


def _cold_import_seconds(module: str) -> str:
    """Time importing `module` in a fresh interpreter, so the number is a real cold start."""
    code = (f"import time,sys; sys.path.insert(0, {str(ROOT)!r}); "
            f"t=time.perf_counter(); __import__({module!r}); "
            f"print(f'{{time.perf_counter()-t:.3f}}s')")
    try:
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return "could not measure"
    return out.stdout.strip() if out.returncode == 0 else "import failed"


def cmd_measure() -> int:
    """Re-derive the dependency and start-up numbers against THIS environment.

    The table the demo prints is measured with `pip download`, which resolves a
    clean install. This re-derives the LangChain half from what is actually
    importable here, so you can check the claim rather than trust it.
    """
    from importlib.metadata import distributions

    lc = import_langchain()
    installed = len(list(distributions()))
    print("Measured here, now")
    print(f"  installed distributions:      {installed}")

    if lc:
        closure = _langchain_closure()
        print(f"  reachable from langchain-core: {len(closure)}")
        print(f"  the demo's printed figure:     {DEPS['langchain']['packages']} "
              f"(a clean `pip download` resolve, so the two differ by whatever")
        print("                                 else this environment has in it)")
    else:
        print("  langchain:                    not installed")

    # Timed in a fresh interpreter: by now this process has already imported both,
    # so timing them here would report ~0s and mean nothing.
    print(f"  cold import localrag.engine:  {_cold_import_seconds('localrag.engine')}")
    if lc:
        print(f"  cold import langchain_core:   "
              f"{_cold_import_seconds('langchain_core.runnables')}")
    print()
    print("Reproduce the demo's table from a clean resolve with:")
    print("  pip download -d /tmp/base -r requirements.txt")
    print("  pip download -d /tmp/lc   -r requirements.txt langchain-core "
          "langchain-text-splitters")
    return 0


def cmd_ask(question: str, native: bool, arm: str) -> int:
    lc = import_langchain()
    if lc is None:
        print(f"LangChain is not installed. Install it with:\n  {INSTALL_HINT}")
        return 1
    settings = load_settings()
    config = handrolled.lesson_config()
    chunks = lc.split(lc.load(), settings["chunk_size"], settings["chunk_overlap"])

    if arm == "embed":
        model = config.ollama_embed_model
        try:
            retriever = (lc.native_ollama_retriever(chunks, settings["top_k"], model) if native
                         else lc.embedding_retriever(chunks, settings["top_k"], config))
        except ModuleNotFoundError as exc:
            if (exc.name or "").split(".")[0] != "langchain_ollama":
                raise
            print("`--arm embed --native` needs the optional framework-native package:")
            print(f"  {OLLAMA_HINT}")
            return 1
    else:
        retriever = lc.bm25_retriever(chunks, settings["top_k"])

    hits = retriever.invoke(question)
    print(f"Q  {question}")
    print(f"   sources: {' . '.join(lc.sources(hits))}")
    print()

    if native:
        try:
            from langchain_ollama import ChatOllama
        except ModuleNotFoundError as exc:
            # Same narrow rule as import_langchain(): only a missing langchain_ollama
            # means "not installed". Anything else failing to import is a real fault
            # and must not be disguised as an absent optional package.
            if (exc.name or "").split(".")[0] != "langchain_ollama":
                raise
            print("`--native` needs the optional framework-native package:")
            print(f"  {OLLAMA_HINT}")
            return 1
        llm = ChatOllama(model=config.ollama_model)
        label = f"ChatOllama({config.ollama_model}) - framework-native"
    else:
        from lc_provider import LocalRagChatModel
        llm = LocalRagChatModel(config=config, provider_name=config.provider)
        label = f"LocalRagChatModel({config.provider}) - your adapter"

    print(f"   model: {label}")
    print()
    print(lc.build_chain(retriever, llm).invoke(question))
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    native = "--native" in argv
    argv = [a for a in argv if a != "--native"]
    arm = "bm25"
    if "--arm" in argv:
        i = argv.index("--arm")
        if i + 1 >= len(argv):
            print(f"--arm needs a value. Choose one of: {', '.join(sorted(ARMS))}.")
            return 2
        arm = argv[i + 1]
        del argv[i:i + 2]
        if arm not in ARMS:
            # Silently falling back to bm25 would make `--arm emebd` look like it
            # worked, and quietly answer the wrong question about the wrong arm.
            print(f"Unknown arm {arm!r}. Choose one of: {', '.join(sorted(ARMS))}.")
            return 2

    if argv and argv[0] == "--measure":
        return cmd_measure()
    if argv and argv[0] == "ask":
        question = " ".join(argv[1:]).strip()
        if not question:
            print('Usage: python langchain_rag.py ask "your question"')
            return 2
        return cmd_ask(question, native, arm)
    return cmd_demo()


if __name__ == "__main__":
    raise SystemExit(main())
