"""Lesson 10 - Jev and System One models vs a local LLM, on two fake call centers.

    python python/jev.py check                     # is this machine ready? (python/check.py)
    python python/jev.py hello                     # ONE real call to TypeSafe's Jev
    python python/jev.py race                      # one question: chat model vs one-token answer
    python python/jev.py demo                      # recorded replies; no model, no network
    python python/jev.py ask "Caller: my car was stolen"   # one call, live
    python python/jev.py live --backend keywords,llm-json,local   # score engines now
    python python/jev.py record --backend local    # re-record what demo replays
    python python/jev.py serve                     # the Jev-like adapter on 127.0.0.1

Datasets (--dataset): insurance (default), media.

Backends:
  keywords   rules, no model
  llm-json   a local chat model asked to write JSON (Ollama)
  local      the Jev-like adapter, in process (Ollama, one call per question) - simulated
  typesafe   TypeSafe's Jev over the internet (TYPESAFE_API_KEY), or any System One
             server on this machine when TYPESAFE_BASE_URL=http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import datetime
import http.client
import json
import os
import platform
import sys
import textwrap
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


DATASETS = json.loads((DATA / "datasets.json").read_text(encoding="utf-8"))
DEFAULT_DATASET = "insurance"


def cassette_name(backend: str, model: str, dataset: str = DEFAULT_DATASET) -> str:
    """jev-like-qwen3-1.7b-insurance.json: engine, model and dataset."""
    suffix = f"-{dataset}"
    if backend == "typesafe":
        return f"typesafe-jev{suffix}.json"
    prefix = {"llm-json": "llm-json", "local": "jev-like"}[backend]
    return f"{prefix}-{model.replace(':', '-').replace('/', '-')}{suffix}.json"


# The prompt each engine's recordings depend on (None: the model's own API, no prompt).
PROMPT_VERSIONS = {"local": local_adapter.PROMPT_VERSION, "llm-json": engines.PROMPT_VERSION,
                   "typesafe": None}


def load_dataset(name: str) -> tuple[dict, list[dict]]:
    questions = json.loads((DATA / "questions.json").read_text(encoding="utf-8"))[name]
    lines = (DATA / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return questions, [json.loads(line) for line in lines if line.strip()]


# What a live call can fail with: a dead or odd server, a refused URL, an unexpected reply.
LIVE_ERRORS = (RuntimeError, OSError, ValueError, KeyError, TypeError, AttributeError,
               http.client.HTTPException)


# --------------------------------------------------------------------------- one backend, one record
def run_live(backend: str, body: dict, model: str, dataset: str = DEFAULT_DATASET) -> dict:
    """Ask one backend about one record. Returns what a cassette stores."""
    started = time.monotonic()
    if backend == "keywords":
        return {"response": engines.keywords_response(body, dataset), "seconds": 0.0, "calls": 0}
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
        stored = run_live(backend, body, model, dataset)
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
def typesafe_is_local() -> bool:
    """TYPESAFE_BASE_URL points at this machine: a stand-in server, not TypeSafe's Jev."""
    return systemone.is_loopback(os.environ.get("TYPESAFE_BASE_URL", systemone.TYPESAFE_URL))


def label_for(backend: str, tape: dict | None, model: str = "") -> str:
    if backend == "keywords":
        return "keywords (rules)"
    if backend == "typesafe" and tape is None and typesafe_is_local():
        return "local System One server (simulated)"  # never call a stand-in "Jev"
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
    return (f"{label:<32}" + "".join(f"{c:>7}" for c in cells)
            + f"{s['typed'] * 100 // max(s['asked'], 1):>6}%{s['brier']:>7.3f}"
            + f"{s['actions']:>5}/{s['n']}{s['wrong']:>6}{s['missed']:>7}"
            + f"{s['seconds']:>8.1f}{s['calls']:>6}")


def header(questions: dict, dataset: str) -> str:
    short = DATASETS[dataset]["short"]
    cols = "".join(f"{short[q]:>7}" for q in questions)
    return (f"{'engine':<32}{cols}{'typed':>7}{'brier':>7}{'action':>8}{'wrong':>6}"
            f"{'missed':>7}{'s/call':>8}{'calls':>6}")


def demo(dataset: str = DEFAULT_DATASET, out=None) -> int:
    out = out or sys.stdout
    questions, records = load_dataset(dataset)
    pol = policy.POLICIES[dataset]
    meta = DATASETS[dataset]
    p = lambda line="": print(line, file=out)  # noqa: E731
    p(f"Lesson 10 · Jev and System One models - {meta['title']}: {len(records)} labelled fake "
      f"calls, {len(questions)} typed questions")
    p("Replayed from recorded replies: no model, no network. "
      "Live: ./run -l 10 live --backend keywords,llm-json,local")
    p()
    p(header(questions, dataset))
    rows = [("keywords", None, {r["id"]: to_run(questions, run_live(
        "keywords", systemone.build_request(r["text"], questions), "", dataset))
        for r in records})]
    missing = []
    for backend, model in RECORDED_MODELS:
        file = cassette_name(backend, model, dataset)
        tape = load_cassette(file, questions, records, dataset)
        if tape is None:
            missing.append((backend, model))
            continue
        rows.append((backend, tape, {r["id"]: to_run(questions, tape["calls"][r["id"]])
                                     for r in records}))
    for backend, tape, runs in rows:
        p(fmt_row(label_for(backend, tape), scorecard.score(questions, records, runs, pol),
                  questions))
    for backend, model in missing:
        hint = ("needs TYPESAFE_API_KEY: ./run -l 10 record --backend typesafe"
                if backend == "typesafe" else
                f"./run -l 10 record --backend {backend} --model {model}")
        hint += "" if dataset == DEFAULT_DATASET else f" --dataset {dataset}"
        p(f"{label_for(backend, None, model):<32}not recorded - {hint}")
    p()
    p("Columns: right/total per question; typed = answers that were a valid option;")
    p("brier = probability error, 0 best, 2 = certain and wrong; action = same action as the")
    p(f"human labels lead to; wrong = {pol.wrong}; missed = {pol.missed};")
    p("s/call = median seconds; calls = model calls per record.")

    p()
    p("The traps - the action each engine's answers lead to:")
    for r in [r for r in records if r["trap"]]:
        want = pol.decide(scorecard.gold_answers(questions, r["labels"]))
        p(f"  {r['id']}  {r['trap']}")
        p(f"    {'labels':<14} {want}")
        for backend, tape, runs in rows:
            got = pol.decide(runs[r["id"]]["answers"])
            p(f"    {short_name(backend, tape):<14} {got}{'' if got == want else '   <- wrong'}")

    name = pol.knob.upper()
    p()
    p(f"The threshold is a business decision. '{pol.watch}' as {name} moves:")
    p(f"  {'engine':<32}" + "".join(f"{name + ' ' + format(t, '.1f'):>20}" for t in pol.values))
    for backend, tape, runs in rows:
        cells = []
        for t in pol.values:
            s = scorecard.score(questions, records, runs, pol, knob=t)
            cells.append(f"{s['wrong']} wrong {s['missed']} missed")
        p(f"  {label_for(backend, tape):<32}" + "".join(f"{c:>20}" for c in cells))
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
                runs[rec["id"]] = to_run(questions, run_live(backend, body, model, dataset))
                bad = runs[rec["id"]]["problems"]
                print(f"  {rec['id']}  {runs[rec['id']]['seconds']:.1f}s"
                      + (f"  invalid: {', '.join(bad)}" if bad else ""), file=out, flush=True)
        except (SystemExit, *LIVE_ERRORS) as err:
            rows.append((label, None, str(err) or type(err).__name__))
            print(f"  skipped: {err}", file=out, flush=True)
            continue
        rows.append((label, scorecard.score(questions, records, runs, policy.POLICIES[dataset]),
                     ""))
    print(file=out)
    print(header(questions, dataset), file=out)
    for label, score, why in rows:
        print(fmt_row(label, score, questions) if score else f"{label:<32}not run - {why}",
              file=out)
    return 0 if any(score for _l, score, _w in rows) else 1


def limit_arg(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("--limit must be 0 (all records) or more")
    return value


def parse_backends(text: str) -> list[str]:
    names = [b.strip() for b in text.split(",") if b.strip()]
    unknown = [b for b in names if b not in BACKENDS]
    if unknown or not names:
        raise argparse.ArgumentTypeError(f"backends are {', '.join(BACKENDS)}; got {text!r}")
    return names


def print_answers(questions: dict, run: dict, out) -> None:
    for name, q in questions.items():
        a = run["answers"].get(name)
        if a is None:
            print(f"  {name:<15} (no valid answer)", file=out)
            continue
        print(f"  {name:<15} {a['pick']}", file=out)
        print("      " + "  ".join(f"{k} {v:.2f}" for k, v in a["probs"].items()), file=out)
    for problem in run["problems"]:
        print(f"  ! {problem}", file=out)


def ask(text: str, backend: str, model: str, dataset: str = DEFAULT_DATASET, out=None) -> int:
    out = out or sys.stdout
    questions, _ = load_dataset(dataset)
    wire_model = model if backend != "typesafe" else os.environ.get("TYPESAFE_DEFAULT_MODEL",
                                                                    "jev-latest")
    body = systemone.build_request(text, questions, wire_model)
    try:
        run = to_run(questions, run_live(backend, body, model, dataset))
    except LIVE_ERRORS as err:
        print(f"{label_for(backend, None, wire_model)} did not answer: {err}", file=out)
        print("Run ./run -l 10 check to see what is missing.", file=out)
        return 1
    print(f"{label_for(backend, None, wire_model)}  {run['seconds']:.1f}s, "
          f"{run['calls']} model call(s)", file=out)
    print_answers(questions, run, out)
    print(f"  -> action: {policy.POLICIES[dataset].decide(run['answers'])}", file=out)
    return 0


# --------------------------------------------------------------------------- race
RACE_CALL = ("Caller: A pipe has burst upstairs, water is coming through the kitchen ceiling "
             "and the light fitting is sparking. My mother is in there, she's 84.")
RACE_QUESTION = "emergency"  # one yes/no question: "Does someone need help right now?"


def race_rows(text: str, model: str) -> list[dict]:
    """Ask one yes/no question two ways (three with a TypeSafe key) and time each.

    Each row: {"engine", "answer", "seconds", "tokens"} plus, for the two local runs,
    Ollama's own counters: "read_tokens", "read_seconds" (taking in the prompt) and
    "write_seconds" (producing the answer). The first row is the chat model, the second
    the one-token adapter. Raises RuntimeError/OSError if Ollama is not there.
    """
    question = load_dataset(DEFAULT_DATASET)[0][RACE_QUESTION]
    ask_text = question["instructions"]
    # warm-up, not timed: loading the model into memory is not what is being compared
    engines.chat([{"role": "user", "content": "Say ok."}], model, OLLAMA_URL, num_predict=1)
    chat = engines.chat([{"role": "user", "content":
                          f"{text}\n\n{ask_text} Answer yes or no, then say why in one "
                          f"sentence."}], model, OLLAMA_URL)
    rows = [{"engine": f"Ollama chat ({model})", **chat,
             "answer": chat["text"].replace("\n", " ")}]
    stats: dict = {}
    started = time.monotonic()
    answer = local_adapter.answer_one(text, question, model, OLLAMA_URL, stats=stats)
    rows.append({"engine": f"Jev-like adapter ({model}, simulated)",
                 "answer": f"P(yes) = {answer['noul']:.2f}",
                 "seconds": time.monotonic() - started,
                 "read_tokens": 0, "read_seconds": 0.0, "write_seconds": 0.0, **stats,
                 "tokens": 1})
    url = os.environ.get("TYPESAFE_BASE_URL", systemone.TYPESAFE_URL)
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if key and not systemone.is_loopback(url):
        body = systemone.build_request(text, {RACE_QUESTION: question},
                                       os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest"))
        try:
            response, seconds = systemone.post(url, body, key)
            got, _ = systemone.read_answers({RACE_QUESTION: question}, response)
            usage = response.get("usage") or {}
            rows.append({"engine": "TypeSafe Jev (real, over the internet)",
                         "answer": f"P(yes) = {got[RACE_QUESTION]['probs']['yes']:.2f}",
                         "seconds": seconds, "tokens": usage.get("output_tokens") or 0,
                         "read_tokens": usage.get("input_tokens") or 0})
        except LIVE_ERRORS as err:
            rows.append({"engine": "TypeSafe Jev (real)", "answer": f"did not answer: {err}",
                         "seconds": 0.0, "tokens": 0})
    return rows


def race_summary(rows: list[dict]) -> list[str]:
    """What the two local runs show, in plain sentences."""
    slow, fast = rows[0], rows[1]
    lines = []
    if fast["seconds"] > 0:
        lines.append(f"Total: {slow['seconds']:.2f}s vs {fast['seconds']:.2f}s - the one-token "
                     f"answer is {slow['seconds'] / fast['seconds']:.1f}x faster here.")
    lines.append(f"Writing the answer: {slow['tokens']} tokens took {slow['write_seconds']:.2f}s; "
                 f"1 token took {fast['write_seconds']:.2f}s.")
    lines.append(f"Reading the prompt: {slow['read_seconds']:.2f}s ({slow['read_tokens']} tokens) "
                 f"vs {fast['read_seconds']:.2f}s ({fast['read_tokens']} tokens).")
    lines.append("The adapter's prompt also lists the options, so it reads more.")
    return lines


def race(text: str, model: str, out=None) -> int:
    """The same yes/no question, asked two ways of the same local model, timed.

    A chat model writes its answer token by token; the Jev-like adapter lets it write
    one token and reads the probability off it. With a TypeSafe key, the real Jev runs too.
    """
    out = out or sys.stdout
    p = lambda line="": print(line, file=out)  # noqa: E731
    for i, line in enumerate(textwrap.wrap(text, 88)):
        p(f"{'Call:' if i == 0 else '':<11}{line}")
    p(f"Question:  {load_dataset(DEFAULT_DATASET)[0][RACE_QUESTION]['instructions']}")
    p()
    try:
        rows = race_rows(text, model)
    except LIVE_ERRORS as err:
        p(f"Ollama did not answer: {err}")
        p("Run ./run -l 10 check to see what is missing.")
        return 1
    p(f"{'engine':<42}{'answer':<32}{'read':>7}{'write':>7}{'total':>7}{'tokens':>8}")
    for row in rows:
        read = f"{row['read_seconds']:.2f}s" if "read_seconds" in row else "-"
        write = f"{row['write_seconds']:.2f}s" if "write_seconds" in row else "-"
        answer = row["answer"] if len(row["answer"]) <= 30 else row["answer"][:27] + "..."
        p(f"{row['engine']:<42}{answer:<32}{read:>7}{write:>7}"
          f"{row['seconds']:>6.2f}s{row['tokens']:>8}")
    p()
    p("What the chat model wrote:")
    for line in textwrap.wrap(rows[0]["answer"], 96):
        p(f"  {line}")
    p()
    for line in race_summary(rows):
        p(line)
    p("That is for ONE question. The adapter needs one model call per question; the real Jev")
    p("answers all of a request's questions in one pass.")
    if not os.environ.get("TYPESAFE_API_KEY"):
        p("Add the real Jev to this table: export TYPESAFE_API_KEY=...")
        p("(create a key at https://console.typesafe.ai/keys)")
    return 0


# --------------------------------------------------------------------------- hello
HELLO_CALL = "K-1004"  # the calm caller in the upside-down car


def hello(model: str, out=None) -> int:
    """ONE real request to TypeSafe's Jev, shown in full: request, response, decision.

    Without TYPESAFE_API_KEY it explains how to get one and sends the same request
    to the local Jev-like adapter instead, so the lesson never stops here.
    """
    out = out or sys.stdout
    p = lambda line="": print(line, file=out)  # noqa: E731
    questions, records = load_dataset(DEFAULT_DATASET)
    rec = next(r for r in records if r["id"] == HELLO_CALL)
    url = os.environ.get("TYPESAFE_BASE_URL", systemone.TYPESAFE_URL)
    key = os.environ.get("TYPESAFE_API_KEY", "")
    real = bool(key) or systemone.is_loopback(url)
    if real:
        try:
            systemone.check_destination(url)
        except ValueError as err:
            p(str(err))
            return 1
    p(f"One call to the {DATASETS[DEFAULT_DATASET]['title']} ({rec['id']}, fake):")
    p()
    for line in rec["text"].splitlines():
        p(f"    {line}")
    p()
    if real:
        wire_model = os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest")
        if systemone.is_loopback(url):
            p(f"Sending it to {url}: a System One server on this machine.")
            p("That is a stand-in (simulated), NOT TypeSafe's Jev. Unset TYPESAFE_BASE_URL "
              "for the real one.")
        else:
            p(f"Sending it to {url} (TypeSafe). The text leaves this machine; it is fake.")
        backend, label = "typesafe", f"POST {url.rstrip('/')}{systemone.SYSTEM_ONE_PATH}"
    else:
        wire_model = model
        p("TYPESAFE_API_KEY is not set, so this is NOT the real Jev.")
        p("  1. Log in or create an account: https://console.typesafe.ai/playground")
        p("  2. Create an API key:           https://console.typesafe.ai/keys")
        p("  3. export TYPESAFE_API_KEY=...  and run ./run -l 10 hello again")
        p(f"Meanwhile: the same request to the local Jev-like adapter ({model}, simulated).")
        backend, label = "local", f"local adapter, {len(questions)} Ollama calls"
    body = systemone.build_request(rec["text"], questions, wire_model)
    p()
    p(f"Request, abridged ({label}): model, state, and {len(questions)} typed questions")
    shown = {"model": body["model"], "state": body["state"][:60] + "...",
             "questions": {name: {"type": q["type"], "instructions": q["instructions"]}
                           for name, q in questions.items()}}
    p(json.dumps(shown, indent=2, ensure_ascii=False))
    try:
        stored = run_live(backend, body, model, DEFAULT_DATASET)
        usage = stored["response"].get("usage") if real else None
    except LIVE_ERRORS as err:
        p()
        p(f"Could not get an answer: {err}")
        p("Run ./run -l 10 check to see what is missing.")
        return 1
    run = to_run(questions, stored)
    p()
    p(f"Response in {run['seconds']:.2f}s, {run['calls']} model call(s)"
      + (f", usage {json.dumps(usage)}" if real else "") + ":")
    print_answers(questions, run, out)
    p()
    action = policy.POLICIES[DEFAULT_DATASET].decide(run["answers"])
    p(f"The policy (python/policy.py) turns that into: {action}")
    p("No text was generated and nothing was parsed: every answer is one of your options,")
    p("with a probability your code can compare against a threshold.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lesson 10: Jev and System One models")
    sub = ap.add_subparsers(dest="command")
    d = sub.add_parser("demo")
    d.add_argument("--dataset", default=DEFAULT_DATASET, choices=list(DATASETS))
    for name in ("live", "record"):
        sp = sub.add_parser(name)
        if name == "live":
            sp.add_argument("--backend", required=True, type=parse_backends,
                            help="one or more, comma-separated: " + ",".join(BACKENDS))
        else:
            sp.add_argument("--backend", required=True, choices=BACKENDS)
        sp.add_argument("--dataset", default=DEFAULT_DATASET, choices=list(DATASETS))
        sp.add_argument("--model", default=LOCAL_MODEL)
        sp.add_argument("--limit", type=limit_arg, default=0,
                        help="only the first N records (0 = all)")
        sp.add_argument("--hardware", default=f"{platform.machine()} {os.cpu_count()} threads")
    a = sub.add_parser("ask")
    a.add_argument("text")
    a.add_argument("--backend", default="local", choices=BACKENDS)
    a.add_argument("--model", default=LOCAL_MODEL)
    a.add_argument("--dataset", default=DEFAULT_DATASET, choices=list(DATASETS))
    h = sub.add_parser("hello")
    h.add_argument("--model", default=LOCAL_MODEL)
    sub.add_parser("check")
    r = sub.add_parser("race")
    r.add_argument("text", nargs="?", default=RACE_CALL)
    r.add_argument("--model", default=LOCAL_MODEL)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--model", default=LOCAL_MODEL)
    args = ap.parse_args(argv)
    systemone.load_typesafe_env(LESSON.parents[1] / ".env")

    if args.command in (None, "demo"):
        try:
            return demo(getattr(args, "dataset", DEFAULT_DATASET))
        except (StaleCassette, json.JSONDecodeError) as err:
            print(f"StaleCassette: {err}", file=sys.stderr)
            return 1
    if args.command == "hello":
        return hello(args.model)
    if args.command == "race":
        return race(args.text, args.model)
    if args.command == "check":
        import check
        return check.main()
    if args.command == "live":
        return live(args.backend, args.dataset, args.model, args.limit)
    if args.command == "record":
        if args.backend == "keywords":
            raise SystemExit("keywords needs no recording; demo runs the rules every time")
        if args.backend == "typesafe" and typesafe_is_local():
            raise SystemExit("TYPESAFE_BASE_URL points at this machine; that is not Jev. Unset it "
                             "to record TypeSafe, or use --backend local for the adapter.")
        path = record(args.backend, args.dataset, args.model, args.hardware, args.limit)
        print(f"wrote {path.relative_to(LESSON)}")
        return 0
    if args.command == "ask":
        return ask(args.text, args.backend, args.model, args.dataset)
    local_adapter.serve(args.port, args.model, OLLAMA_URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
