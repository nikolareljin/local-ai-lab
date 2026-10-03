"""Lesson 10 - Jev and System One models vs a local LLM, on fake support tickets.

    python python/jev.py demo                      # recorded replies; no model, no network
    python python/jev.py ask "My card was charged twice"   # one ticket, live
    python python/jev.py live --backend local      # score a backend now
    python python/jev.py record --backend local    # re-record what demo replays
    python python/jev.py serve                     # the Jev-like adapter on 127.0.0.1

Backends:
  keywords   rules, no model
  llm-json   a local chat model asked to write JSON (Ollama)
  local      the Jev-like adapter, in process (Ollama, one call per question)
  typesafe   any System One server: TypeSafe's Jev by default, or the adapter
             when TYPESAFE_BASE_URL=http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import sys
import time
from pathlib import Path

import engines
import local_adapter
import policy
import scorecard
import systemone

LESSON = Path(__file__).resolve().parents[1]
DATA = LESSON / "data"
CASSETTES = DATA / "cassettes"
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
LOCAL_MODEL = os.environ.get("OLLAMA_MODEL", local_adapter.DEFAULT_MODEL)

# What the demo replays, in the order the scorecard prints them: (backend, model).
RECORDED_MODELS = [
    ("llm-json", "qwen3:1.7b"),
    ("local", "qwen3:1.7b"),
    ("local", "qwen3.5:4b"),
    ("typesafe", "jev-latest"),
]


def cassette_name(backend: str, model: str, dataset: str = "tickets") -> str:
    """jev-like-qwen3-1.7b.json for the tickets; other datasets add their name."""
    suffix = "" if dataset == "tickets" else f"-{dataset}"
    if backend == "typesafe":
        return f"typesafe-jev{suffix}.json"
    prefix = {"llm-json": "llm-json", "local": "jev-like"}[backend]
    return f"{prefix}-{model.replace(':', '-').replace('/', '-')}{suffix}.json"


# The prompt each engine's recordings depend on (None: the model's own API, no prompt).
PROMPT_VERSIONS = {"local": local_adapter.PROMPT_VERSION, "llm-json": engines.PROMPT_VERSION,
                   "typesafe": None}


RECORDED = [(backend, cassette_name(backend, model)) for backend, model in RECORDED_MODELS]


def load_dataset(name: str) -> tuple[dict, list[dict]]:
    questions = json.loads((DATA / "questions.json").read_text(encoding="utf-8"))[name]
    lines = (DATA / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return questions, [json.loads(line) for line in lines if line.strip()]


# --------------------------------------------------------------------------- one backend, one record
def run_live(backend: str, body: dict, model: str) -> dict:
    """Ask one backend about one record. Returns what a cassette stores."""
    started = time.monotonic()
    if backend == "keywords":
        return {"response": engines.keywords_response(body), "seconds": 0.0, "calls": 0}
    if backend == "llm-json":
        text = engines.llm_json_text(body, model, OLLAMA_URL)
        return {"text": text, "seconds": time.monotonic() - started, "calls": 1}
    if backend == "local":
        response = local_adapter.answer(body, model, OLLAMA_URL)
        return {"response": response, "seconds": time.monotonic() - started,
                "calls": len(body["questions"])}
    if backend == "typesafe":
        url = os.environ.get("TYPESAFE_BASE_URL", systemone.TYPESAFE_URL)
        key = os.environ.get("TYPESAFE_API_KEY", "")
        if not key and not systemone.is_loopback(url):
            raise SystemExit("TYPESAFE_API_KEY is not set (get one at https://console.typesafe.ai)")
        response, seconds = systemone.post(url, body, key)
        return {"response": response, "seconds": seconds, "calls": 1}
    raise SystemExit(f"unknown backend {backend!r}")


def to_run(questions: dict, stored: dict) -> dict:
    """A stored reply -> {"answers", "seconds", "calls", "problems"}."""
    if "text" in stored:  # llm-json: parse what the model wrote, every time
        body = {"questions": questions}
        response, problems = engines.parse_llm_json(body, stored["text"])
    else:
        response, problems = stored["response"], []
    answers, more = systemone.read_answers(questions, response)
    return {"answers": answers, "seconds": stored["seconds"], "calls": stored["calls"],
            "problems": problems + more}


# --------------------------------------------------------------------------- cassettes
class StaleCassette(RuntimeError):
    pass


def load_cassette(file: str, questions: dict, records: list[dict], dataset: str) -> dict | None:
    path = CASSETTES / file
    if not path.is_file():
        return None
    tape = json.loads(path.read_text(encoding="utf-8"))
    if tape.get("dataset") != dataset:
        return None
    want_prompt = PROMPT_VERSIONS.get(tape.get("engine"))
    if tape.get("prompt_version") != want_prompt:
        raise StaleCassette(f"{file}: recorded with prompt {tape.get('prompt_version')}, "
                            f"current is {want_prompt} - re-record it")
    for rec in records:
        stored = tape["calls"].get(rec["id"])
        if stored is None:
            raise StaleCassette(f"{file}: has no recording of {rec['id']} - re-record it "
                                f"without --limit")
        want = systemone.digest(systemone.build_request(rec["text"], questions, tape["model"]))
        if stored["digest"] != want:
            raise StaleCassette(f"{file}: {rec['id']} was recorded for a different question "
                                f"or text - re-record it")
    return tape


def record(backend: str, dataset: str, model: str, hardware: str, limit: int = 0) -> Path:
    questions, records = load_dataset(dataset)
    records = records[:limit] if limit else records
    file = cassette_name(backend, model, dataset)
    if limit:  # a partial run never replaces what the demo replays
        file = file.removesuffix(".json") + f"-first{limit}.json"
    wire_model = model if backend != "typesafe" else os.environ.get("TYPESAFE_DEFAULT_MODEL",
                                                                    "jev-latest")
    calls = {}
    for i, rec in enumerate(records, 1):
        body = systemone.build_request(rec["text"], questions, wire_model)
        stored = run_live(backend, body, model)
        stored["seconds"] = round(stored["seconds"], 2)
        calls[rec["id"]] = {"digest": systemone.digest(body), **stored}
        print(f"  {i:>2}/{len(records)} {rec['id']}  {stored['seconds']:.1f}s", flush=True)
    tape = {
        "engine": backend, "model": wire_model, "dataset": dataset,
        "recorded": datetime.date.today().isoformat(), "hardware": hardware,
        "prompt_version": PROMPT_VERSIONS[backend],
        "calls": calls,
    }
    CASSETTES.mkdir(parents=True, exist_ok=True)
    path = CASSETTES / file
    path.write_text(json.dumps(tape, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- printing
def label_for(backend: str, tape: dict | None, model: str = "") -> str:
    if backend == "keywords":
        return "keywords (rules)"
    name = tape["model"] if tape else model
    return {"llm-json": f"LLM writes JSON ({name})",
            "local": f"Jev-like adapter ({name.removeprefix('local-')})",
            "typesafe": f"TypeSafe Jev ({name})"}[backend]


def short_name(backend: str, tape: dict | None) -> str:
    """"jev-like 4b": the engine and the model's size tag, for narrow columns."""
    if tape is None:
        return backend
    prefix = {"llm-json": "llm-json", "local": "jev-like", "typesafe": "typesafe"}[backend]
    return f"{prefix} {tape['model'].split(':')[-1]}"


def fmt_row(label: str, s: dict, questions: dict) -> str:
    cells = [f"{s['correct'][q]:>2}/{s['n']}" for q in questions]
    return (f"{label:<34}" + "".join(f"{c:>8}" for c in cells)
            + f"{s['typed'] * 100 // s['asked']:>6}%{s['brier']:>7.3f}"
            + f"{s['actions']:>5}/{s['n']}{s['wrong_pages']:>6}{s['missed_pages']:>7}"
            + f"{s['seconds']:>8.1f}{s['calls']:>6}")


def header(questions: dict) -> str:
    short = {"queue": "queue", "urgency": "urgency", "refund_request": "refund",
             "needs_human": "human"}
    cols = "".join(f"{short.get(q, q[:7]):>8}" for q in questions)
    return (f"{'engine':<34}{cols}{'typed':>7}{'brier':>7}{'action':>8}{'wrong':>6}"
            f"{'missed':>7}{'s/item':>8}{'calls':>6}")


def demo(dataset: str = "tickets", out=None) -> int:
    out = out or sys.stdout
    questions, records = load_dataset(dataset)
    p = lambda line="": print(line, file=out)  # noqa: E731
    p(f"Lesson 10 · Jev and System One models - {len(records)} labelled fake {dataset}, "
      f"{len(questions)} typed questions")
    p("Replayed from recorded replies: no model, no network. Live: ./run -l 10 live --backend local")
    p()
    p(header(questions))
    rows = [("keywords", None, {r["id"]: to_run(questions, run_live("keywords", systemone.build_request(
        r["text"], questions), "")) for r in records})]
    missing = []
    for backend, model in RECORDED_MODELS:
        file = cassette_name(backend, model, dataset)
        tape = load_cassette(file, questions, records, dataset)
        if tape is None:
            missing.append((backend, model))
            continue
        rows.append((backend, tape, {r["id"]: to_run(questions, tape["calls"][r["id"]])
                                     for r in records}))
    scores = {}
    for backend, tape, runs in rows:
        scores[backend] = scorecard.score(questions, records, runs)
        p(fmt_row(label_for(backend, tape), scores[backend], questions))
    for backend, model in missing:
        hint = ("needs TYPESAFE_API_KEY: ./run -l 10 record --backend typesafe"
                if backend == "typesafe" else f"./run -l 10 record --backend {backend}")
        hint = hint if backend == "typesafe" else f"{hint} --model {model}"
        p(f"{label_for(backend, None, model):<34}not recorded - {hint}")
    p()
    p("accuracy = right/total per question; typed = answers that were a valid option;")
    p("brier = probability error, 0 best, 2 = certain and wrong; action = policy matches the")
    p("labels' action; wrong/missed = pages to on-call; s/item = median seconds; calls = model calls.")

    if "queue" in questions:
        p()
        p("Where they disagree - the traps (label -> each engine's queue / urgency):")
        traps = [r for r in records if r["trap"]][:8]
        for r in traps:
            p(f"  {r['id']}  {r['trap']}")
            p(f"    {'labels':<14} {r['labels']['queue']:<13} {r['labels']['urgency']}")
            for backend, tape, runs in rows:
                a = runs[r["id"]]["answers"]
                q = a.get("queue", {}).get("pick", "-")
                u = a.get("urgency", {}).get("pick", "-")
                conf = a.get("queue", {}).get("confidence")
                note = f"  ({conf:.2f})" if conf is not None and backend != "keywords" else ""
                p(f"    {short_name(backend, tape):<14} {q:<13} {u}{note}")

        p()
        p("The threshold is a business decision. Pages to on-call as PAGE moves:")
        p(f"  {'engine':<34}" + "".join(f"{'PAGE ' + format(t, '.1f'):>20}" for t in (0.5, 0.7, 0.9)))
        for backend, tape, runs in rows:
            cells = []
            for t in (0.5, 0.7, 0.9):
                s = scorecard.score(questions, records, runs, page=t)
                cells.append(f"{s['wrong_pages']} wrong {s['missed_pages']} missed")
            p(f"  {label_for(backend, tape):<34}" + "".join(f"{c:>20}" for c in cells))
        p("  Rules and JSON answers are always 0 or 1, so the knob does nothing for them.")
    return 0


# --------------------------------------------------------------------------- live
BACKENDS = ["keywords", "llm-json", "local", "typesafe"]


def live(backends: list[str], dataset: str, model: str, limit: int, out=None) -> int:
    """Score each backend now, on the same records, and print one scorecard.

    A backend that cannot run - no TYPESAFE_API_KEY, Ollama not started - gets a row
    saying why, and the others still run.
    """
    out = out or sys.stdout
    questions, records = load_dataset(dataset)
    records = records[:limit] if limit else records
    rows = []
    for backend in backends:
        wire_model = model if backend != "typesafe" else os.environ.get(
            "TYPESAFE_DEFAULT_MODEL", "jev-latest")
        label = label_for(backend, None, wire_model if backend != "keywords" else "")
        print(f"{label}:", file=out, flush=True)
        runs = {}
        try:
            for rec in records:
                body = systemone.build_request(rec["text"], questions, wire_model)
                runs[rec["id"]] = to_run(questions, run_live(backend, body, model))
                bad = runs[rec["id"]]["problems"]
                print(f"  {rec['id']}  {runs[rec['id']]['seconds']:.1f}s"
                      + (f"  invalid: {', '.join(bad)}" if bad else ""), file=out, flush=True)
        except (SystemExit, RuntimeError, OSError, ValueError) as err:
            rows.append((label, None, str(err) or type(err).__name__))
            print(f"  skipped: {err}", file=out, flush=True)
            continue
        rows.append((label, scorecard.score(questions, records, runs), ""))
    print(file=out)
    print(header(questions), file=out)
    for label, score, why in rows:
        print(fmt_row(label, score, questions) if score else f"{label:<34}not run - {why}",
              file=out)
    return 0 if any(score for _l, score, _w in rows) else 1


def parse_backends(text: str) -> list[str]:
    names = [b.strip() for b in text.split(",") if b.strip()]
    unknown = [b for b in names if b not in BACKENDS]
    if unknown or not names:
        raise argparse.ArgumentTypeError(f"backends are {', '.join(BACKENDS)}; got {text!r}")
    return names


def ask(text: str, backend: str, model: str, out=None) -> int:
    out = out or sys.stdout
    questions, _ = load_dataset("tickets")
    wire_model = model if backend != "typesafe" else os.environ.get("TYPESAFE_DEFAULT_MODEL",
                                                                    "jev-latest")
    body = systemone.build_request(text, questions, wire_model)
    run = to_run(questions, run_live(backend, body, model))
    print(f"{label_for(backend, None, wire_model)}  {run['seconds']:.1f}s, "
          f"{run['calls']} model call(s)", file=out)
    for name, q in questions.items():
        a = run["answers"].get(name)
        if a is None:
            print(f"  {name:<15} (no valid answer)", file=out)
            continue
        probs = "  ".join(f"{k} {v:.2f}" for k, v in a["probs"].items())
        print(f"  {name:<15} {a['pick']:<13} {probs}", file=out)
    for problem in run["problems"]:
        print(f"  ! {problem}", file=out)
    print(f"  -> action: {policy.decide(run['answers'])}", file=out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lesson 10: Jev and System One models")
    sub = ap.add_subparsers(dest="command")
    d = sub.add_parser("demo")
    d.add_argument("--dataset", default="tickets", choices=["tickets", "reviews", "incidents"])
    for name in ("live", "record"):
        sp = sub.add_parser(name)
        if name == "live":
            sp.add_argument("--backend", required=True, type=parse_backends,
                            help="one or more, comma-separated: " + ",".join(BACKENDS))
        else:
            sp.add_argument("--backend", required=True, choices=BACKENDS)
        sp.add_argument("--dataset", default="tickets", choices=["tickets", "reviews", "incidents"])
        sp.add_argument("--model", default=LOCAL_MODEL)
        sp.add_argument("--limit", type=int, default=0)
        sp.add_argument("--hardware", default=f"{platform.machine()} {os.cpu_count()} threads")
    a = sub.add_parser("ask")
    a.add_argument("text")
    a.add_argument("--backend", default="local", choices=BACKENDS)
    a.add_argument("--model", default=LOCAL_MODEL)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--model", default=LOCAL_MODEL)
    args = ap.parse_args(argv)

    if args.command in (None, "demo"):
        return demo(getattr(args, "dataset", "tickets"))
    if args.command == "live":
        return live(args.backend, args.dataset, args.model, args.limit)
    if args.command == "record":
        if args.backend == "keywords":
            raise SystemExit("keywords needs no recording; demo runs the rules every time")
        path = record(args.backend, args.dataset, args.model, args.hardware, args.limit)
        print(f"wrote {path.relative_to(LESSON)}")
        return 0
    if args.command == "ask":
        return ask(args.text, args.backend, args.model)
    local_adapter.serve(args.port, args.model, OLLAMA_URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
