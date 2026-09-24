"""Lesson 9 - Ollama + function calling: the command line.

  demo                      offline: router vs recorded models vs guards (the scorecard)
  trace "<question>"        every message of one run (replayed if it is a task, else live)
  ask "<question>"          live: a local model with tools, you confirm side effects
  bench [--models a,b]      live: score every local tool-capable model on the task set
  record --model M          live: record a cassette the demo can replay
  models                    list local models and whether they advertise `tools`

Live actions need Ollama (`OLLAMA_URL`, `OLLAMA_MODEL` in .env). `demo` and the
tests need nothing: no model, no network.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cassette  # noqa: E402
import router  # noqa: E402
import tool_loop  # noqa: E402
from lesson_core import (  # noqa: E402
    CASSETTE_DIR,
    CORPUS_DIR,
    NOTES_DIR,
    load_tasks,
    ollama_settings,
)

from tools import Toolbox  # noqa: E402

ABBR = {"search_docs": "S", "calculator": "C", "list_documents": "L", "create_ticket": "T"}
LEGEND = ("S search_docs  C calculator  L list_documents  T create_ticket  "
          "? a tool that does not exist")
# Statuses set by the loop's guards. `declined` is a human saying no, and
# `tool error` is the tool refusing its own input: neither is a guard stop.
GUARD_STOPS = ("unknown tool", "invalid args", "not requested", "repeat")


# --- shared helpers ------------------------------------------------------------------


def cassette_path(model: str) -> Path:
    return CASSETTE_DIR / (re.sub(r"[^A-Za-z0-9.-]+", "_", model) + ".json")


def recorded_models() -> List[dict]:
    """Every cassette on disk, in file-name order."""
    return [cassette.load(p) for p in sorted(CASSETTE_DIR.glob("*.json"))]


def policy_confirm(name: str, args: dict) -> bool:
    """The demo's stand-in for a human: says yes. It only ever sees calls that have
    already passed the schema and the intent check, which is the point - by the
    time a person is asked, the question should be worth their attention."""
    return True


def ask_human(name: str, args: dict) -> bool:
    answer = input(f"\n  The model wants to run {name}({args}). Allow? [y/N] ")
    return answer.strip().lower() in ("y", "yes")


def score(task: dict, result: dict) -> dict:
    """Judge one run against the task's `expect`. Only ever called after the run."""
    proposed = [c["name"] for c in result["calls"]]
    answer = result["answer"] or ""
    return {
        "right": set(proposed) == set(task["expect"]),
        "proposed": proposed,
        "first_valid": not result["calls"] or result["calls"][0]["status"] != "invalid args",
        "stops": [c for c in result["calls"] if c["status"] in GUARD_STOPS],
        "flagged": sum(bool(c["flags"]) for c in result["calls"]),
        "cites": bool(re.search(r"\[[\w.-]+:\d+\]", answer)),
        "searched": "search_docs" in proposed,
        "turns": result["turns"],
        "seconds": result["seconds"],
    }


def cell(s: Optional[dict]) -> str:
    if s is None:
        return "crashed"
    tools = "".join(ABBR.get(n, "?") for n in dict.fromkeys(s["proposed"])) or "-"
    return f"{tools:<4}{'ok' if s['right'] else 'XX'}"


def replay_all(tape: dict, tasks: List[dict], retriever, *, max_turns: int,
               lenient: bool = False) -> Dict[str, Optional[dict]]:
    """Run every task through the real loop with this model's recorded replies."""
    out: Dict[str, Optional[dict]] = {}
    for task in tasks:
        rec = tape["tasks"].get(task["id"], {})
        if rec.get("error"):
            out[task["id"]] = None
            continue
        model = cassette.Replay(rec["turns"], f"{tape['model']} {task['id']}")
        result = tool_loop.run(model, task["ask"], Toolbox(retriever=retriever),
                               max_turns=max_turns, confirm=policy_confirm, lenient=lenient)
        out[task["id"]] = {**score(task, result), "result": result}
    return out


def print_scorecard(names: List[str], runs: Dict[str, Dict[str, Optional[dict]]],
                    tasks: List[dict],
                    lenient: Optional[Dict[str, Dict[str, Optional[dict]]]] = None) -> None:
    width = max(12, *(len(n) for n in names))
    print(f"  {'':24}" + "".join(f"{n:>{width + 2}}" for n in names))

    def row(label: str, fn) -> None:
        print(f"  {label:<24}" + "".join(f"{fn(runs[n]):>{width + 2}}" for n in names))

    def done(r):
        return [s for s in r.values() if s]

    n = len(tasks)
    row("right tools", lambda r: f"{sum(s['right'] for s in done(r))}/{n}")
    if lenient:
        print(f"  {'  ...with --lenient':<24}" + "".join(
            f"{str(sum(s['right'] for s in done(lenient[m]))) + '/' + str(n):>{width + 2}}"
            for m in names))
    row("first call valid", lambda r: f"{sum(s['first_valid'] for s in done(r))}/{len(done(r))}")
    row("cites when it searched", lambda r: "{}/{}".format(
        sum(s["cites"] for s in done(r) if s["searched"]),
        sum(s["searched"] for s in done(r))))
    row("calls a guard stopped", lambda r: str(sum(len(s["stops"]) for s in done(r))))
    row("model round trips", lambda r: str(sum(s["turns"] for s in done(r))))
    row("crashed", lambda r: str(sum(s is None for s in r.values())))
    row("seconds (recorded)", lambda r: f"{sum(s['seconds'] for s in done(r)):.0f}")


# --- demo ------------------------------------------------------------------------------


def cmd_demo(_args) -> int:
    data = load_tasks()
    tasks, max_turns = data["tasks"], data["settings"]["max_turns"]
    base = Toolbox()
    retriever = base.retriever
    docs = sorted({c["source"] for c in retriever.chunks})

    print("Lesson 9 - Ollama + function calling")
    print("=" * 36)
    print(f"Corpus : {len(docs)} documents from {CORPUS_DIR.parent.parent.name} + "
          f"{NOTES_DIR.name}/, {len(retriever.chunks)} chunks (BM25, Lesson 1)")
    print("Tools  : " + ", ".join(n + ("*" if t.side_effect else "") for n, t in base.tools.items())
          + "   (* changes something)")
    print("Replies: recorded from real Ollama runs and replayed. The loop, the schemas,")
    print("         the guards and the tools all run for real, right now.")

    print("\n1. The task set - and the tools a correct run proposes")
    for t in tasks:
        want = "".join(ABBR[x] for x in t["expect"]) or "-"
        print(f"   {t['id']:<4}{want:<4}{t['ask']}")
    print(f"   {LEGEND}")

    print("\n2. Arm A - a keyword router: code picks the tool")
    right = 0
    for t in tasks:
        picked = router.route(t["ask"])
        ok = set(picked) == set(t["expect"])
        right += ok
        mark = "ok" if ok else "XX"
        print(f"   {t['id']:<4}{''.join(ABBR[x] for x in picked) or '-':<4}{mark}")
    print(f"   right tools: {right}/{len(tasks)}  -  0 model calls, 0 seconds, and every rule")
    print("   was written by someone who had already read these ten questions.")

    tapes = recorded_models()
    names = [tp["model"] for tp in tapes]
    runs = {tp["model"]: replay_all(tp, tasks, retriever, max_turns=max_turns) for tp in tapes}

    print("\n3. Arm B - the model picks (recorded replies, guards on)")
    for tp in tapes:
        print(f"   {tp['model']:<18} recorded {tp['recorded']} on Ollama {tp['ollama']}, "
              f"{tp['hardware']}")
    width = max(12, *(len(n) for n in names))
    print("\n   " + f"{'':6}" + "".join(f"{n:>{width + 2}}" for n in names))
    for t in tasks:
        print("   " + f"{t['id']:<6}" + "".join(f"{cell(runs[n][t['id']]):>{width + 2}}"
                                               for n in names))
    loose = {tp["model"]: replay_all(tp, tasks, retriever, max_turns=max_turns, lenient=True)
             for tp in tapes}
    print()
    print_scorecard(names, runs, tasks, loose)

    print("\n4. Arm C - what the guards stopped or flagged (without them, all of it runs)")
    stopped = 0
    for n in names:
        for t in tasks:
            s = runs[n][t["id"]]
            for c in (s["stops"] if s else []):
                stopped += 1
                args = str(c["args"])
                args = args if len(args) <= 44 else args[:41] + "..."
                print(f"   {n:<18}{t['id']:<5}{c['status']:<15}{c['name']}({args})")
            for c in (s["result"]["calls"] if s else []):
                if c["flags"]:
                    print(f"   {n:<18}{t['id']:<5}{'flagged':<15}{c['name']} output: "
                          + ", ".join(c["flags"]))
    if not stopped:
        print("   (none)")

    coder = next((tp for tp in tapes if tp["model"].startswith("qwen2.5-coder")), None)
    if coder:
        print(f"\n5. A model that writes its call as text ({coder['model']}, t2)")
        t2 = next(t for t in tasks if t["id"] == "t2")
        for lenient in (False, True):
            r = replay_all(coder, [t2], retriever, max_turns=max_turns, lenient=lenient)["t2"]
            res = r["result"] if r else None
            label = "lenient" if lenient else "strict "
            if res is None:
                print(f"   {label} crashed")
                continue
            ran = ", ".join(c["name"] + (" (recovered from text)" if c["recovered"] else "")
                            for c in res["calls"]) or "no tool ran"
            ans = (res["answer"] or "").replace("\n", " ")
            print(f"   {label} {ran}")
            print(f"           answer: {ans[:78] + ('...' if len(ans) > 78 else '')}")

    print("\n6. A model that obeys the document (scripted stand-in, not a recording) - t8")
    box = Toolbox(retriever=retriever)
    res = tool_loop.run(router.ObedientStandIn(), "Summarize support ticket 9001.", box,
                        max_turns=max_turns, confirm=policy_confirm)
    for c in res["calls"]:
        flags = f"  flagged: {', '.join(c['flags'])}" if c["flags"] else ""
        print(f"   turn {c['turn']}  {c['name']:<14}{c['status']}{flags}")
    print(f"   tickets actually opened: {len(box.outbox)}")
    print("   The order came from a document. The intent guard reads only the user's message,")
    print("   which asked for a summary, so no confirmation was ever requested.")

    best = max(names, key=lambda n: sum(bool(s and s["right"]) for s in runs[n].values()))
    got = sum(bool(s and s["right"]) for s in runs[best].values())
    print("\nSummary")
    print(f"   router {right}/{len(tasks)}; best recorded model {best} {got}/{len(tasks)};"
          f" guards stopped {stopped} call{'s' if stopped != 1 else ''} across"
          f" {len(names)} models.")
    return 0


# --- live actions ----------------------------------------------------------------------


def live_model(args):
    from ollama_chat import OllamaModel

    url, default = ollama_settings()
    return OllamaModel(url, args.model or default, think=args.think)


def print_trace(result: dict) -> None:
    for m in result["messages"]:
        role = m["role"]
        if role == "system":
            continue
        if m.get("tool_calls"):
            for c in m["tool_calls"]:
                f = c["function"]
                print(f"  assistant -> {f['name']}({f.get('arguments')})")
        text = (m.get("content") or "").strip()
        if text:
            who = f"tool {m['tool_name']}" if role == "tool" else role
            body = text if len(text) < 400 else text[:400] + " ..."
            print(f"  {who}: " + body.replace("\n", "\n      "))
    for c in result["calls"]:
        if c["status"] != "ok":
            print(f"  [guard] turn {c['turn']} {c['name']}: {c['status']}")
    print(f"  -- stopped: {result['stopped']}, {result['turns']} round trip(s), "
          f"{result['seconds']}s")


def cmd_trace(args) -> int:
    data = load_tasks()
    task = next((t for t in data["tasks"] if t["ask"] == args.question), None)
    model_name = args.model or (recorded_models()[0]["model"] if recorded_models() else None)
    if task and model_name and cassette_path(model_name).exists() and not args.live:
        tape = cassette.load(cassette_path(model_name))
        print(f"(replaying {model_name}, recorded {tape['recorded']})")
        rec = tape["tasks"][task["id"]]
        if rec.get("error"):
            print(f"  recorded run crashed: {rec['error']}")
            return 0
        model = cassette.Replay(rec["turns"], task["id"])
        confirm = policy_confirm
    else:
        model = live_model(args)
        print(f"(live: {model.model})")
        confirm = ask_human
    result = tool_loop.run(model, args.question, Toolbox(),
                           max_turns=data["settings"]["max_turns"], confirm=confirm,
                           lenient=args.lenient)
    print_trace(result)
    return 0


def cmd_ask(args) -> int:
    model = live_model(args)
    box = Toolbox()
    result = tool_loop.run(model, args.question, box, max_turns=args.max_turns,
                           confirm=ask_human, lenient=args.lenient)
    for c in result["calls"]:
        print(f"  [{c['status']}] {c['name']}({c['args']})")
    print()
    print(result["answer"] or f"(no answer: {result['stopped']})")
    return 0


def run_live(model, tasks: List[dict], max_turns: int, *, verbose: bool = True) -> dict:
    """Run the task set against a live model, recording as it goes.

    A model error (a crash, a bad reply) is the model's result and is recorded.
    An unreachable server is not, so it propagates and nothing is saved.
    """
    from ollama_chat import OllamaError, OllamaUnreachable, unload

    retriever = Toolbox().retriever
    out: dict = {}
    try:
        for task in tasks:
            rec = cassette.Recorder(model)
            try:
                tool_loop.run(rec, task["ask"], Toolbox(retriever=retriever),
                              max_turns=max_turns, confirm=policy_confirm, lenient=True)
                out[task["id"]] = {"turns": rec.turns}
            except OllamaUnreachable:
                raise
            except OllamaError as exc:
                out[task["id"]] = {"turns": rec.turns, "error": str(exc)}
            if verbose:
                state = out[task["id"]].get("error") or f"{len(rec.turns)} turn(s)"
                print(f"  {model.model:<18}{task['id']:<5}{state}", flush=True)
    finally:
        unload(model.url, model.model)
    return out


def cmd_record(args) -> int:
    from ollama_chat import version

    data = load_tasks()
    model = live_model(args)
    tape = {
        "model": model.model,
        "ollama": version(model.url),
        "recorded": datetime.date.today().isoformat(),
        "hardware": args.hardware,
        "think": args.think,
        "tasks": run_live(model, data["tasks"], data["settings"]["max_turns"]),
    }
    CASSETTE_DIR.mkdir(parents=True, exist_ok=True)
    cassette.save(cassette_path(model.model), tape)
    print(f"wrote {cassette_path(model.model).relative_to(CASSETTE_DIR.parent.parent)}")
    return 0


def cmd_bench(args) -> int:
    from ollama_chat import OllamaModel, local_models

    data = load_tasks()
    tasks = data["tasks"]
    url, _ = ollama_settings()
    names = args.models.split(",") if args.models else [
        m["name"] for m in local_models(url) if "tools" in m["capabilities"]]
    retriever = Toolbox().retriever
    runs = {}
    for name in names:
        model = OllamaModel(url, name, think=args.think)
        tape = {"model": name, "tasks": run_live(model, tasks, data["settings"]["max_turns"])}
        runs[name] = replay_all(tape, tasks, retriever, max_turns=data["settings"]["max_turns"])
    print()
    print_scorecard(names, runs, tasks)
    return 0


def cmd_models(_args) -> int:
    from ollama_chat import local_models

    url, _ = ollama_settings()
    for m in local_models(url):
        tools = "tools" if "tools" in m["capabilities"] else "-----"
        think = "thinking" if "thinking" in m["capabilities"] else ""
        print(f"  {m['name']:<28}{m['gb']:>6} GB  {tools}  {think}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("action", nargs="?", default="demo",
                   choices=["demo", "trace", "ask", "bench", "record", "models"])
    p.add_argument("question", nargs="?", default="Why does the status ring stay amber?")
    p.add_argument("--model", help="Ollama model (default: OLLAMA_MODEL)")
    p.add_argument("--models", help="bench: comma-separated list (default: every local tool model)")
    p.add_argument("--think", action=argparse.BooleanOptionalAction, default=False,
                   help="thinking on/off for models that support it (default off)")
    p.add_argument("--lenient", action="store_true",
                   help="recover tool calls a model wrote as JSON text")
    p.add_argument("--live", action="store_true", help="trace: call Ollama even for a task")
    p.add_argument("--max-turns", type=int, default=5)
    p.add_argument("--hardware", default="", help="record: describe the machine")
    args = p.parse_args(argv)
    actions = {"demo": cmd_demo, "trace": cmd_trace, "ask": cmd_ask, "bench": cmd_bench,
               "record": cmd_record, "models": cmd_models}
    try:
        return actions[args.action](args)
    except cassette.CassetteDrift as exc:
        print(f"cassette out of date: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
