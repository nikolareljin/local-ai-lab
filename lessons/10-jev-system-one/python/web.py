"""Lesson 10 - the playground: one call, every engine, and the thresholds as sliders.

Pick a call to the Kestrel Mutual claims line, pick an engine, and move SIU,
FAST_TRACK and EMERGENCY. The answers do not change - the decision does. That is
the point of a System One model: it gives probabilities once, and the business
rule on top is yours to tune.

  Engine      0 keywords, then each recorded engine (same order as the demo)
  Live        ON asks the Jev-like adapter now (Ollama, OLLAMA_MODEL); any text works
  TypeSafe    ON asks the real Jev now (needs TYPESAFE_API_KEY; the text leaves this machine)
  Race        ON times ONE yes/no question on this text, live: the chat model writing its
              answer vs the adapter's single token (and the real Jev, with a key)

Launch it with:  ./run -l 10
"""

import os
import sys
from pathlib import Path

# this file -> python -> 10-jev-system-one -> lessons -> repo root
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import jev  # noqa: E402
import policy  # noqa: E402
import scorecard  # noqa: E402
import systemone  # noqa: E402
from lesson_web import serve  # noqa: E402

systemone.load_typesafe_env(ROOT / ".env")
DATASET = jev.DEFAULT_DATASET
QUESTIONS, RECORDS = jev.load_dataset(DATASET)


def _key(text: str) -> str:
    """A transcript without its whitespace, so a call is recognised however it was typed,
    pasted or re-wrapped in the prompt box."""
    return "".join(text.split())


BY_TEXT = {_key(r["text"]): r for r in RECORDS}
def _tape(backend: str, model: str):
    """A recording, or None when it is missing or stale: the page still opens without it."""
    try:
        return jev.load_cassette(jev.cassette_name(backend, model, DATASET),
                                 QUESTIONS, RECORDS, DATASET)
    except (jev.StaleCassette, ValueError) as err:
        print(f"[INFO] skipping a recording: {err}", file=sys.stderr)
        return None


TAPES = [("keywords", None)] + [
    (backend, tape) for backend, model in jev.RECORDED_MODELS
    if (tape := _tape(backend, model)) is not None]

PARAMS = [
    {"name": "engine", "label": "Engine:  " + " · ".join(
        f"{i} {jev.label_for(b, t)}" for i, (b, t) in enumerate(TAPES)),
     "kind": "range", "min": 0, "max": len(TAPES) - 1, "step": 1, "default": len(TAPES) - 1},
    {"name": "siu", "label": "SIU: P(fraud signals) needed to send a claim to investigations",
     "kind": "range", "min": 0.05, "max": 1.0, "step": 0.05, "default": policy.SIU},
    {"name": "fast_track", "label": "FAST_TRACK: P(no fraud) needed to pay a small claim "
     "with no human", "kind": "range", "min": 0.5, "max": 1.0, "step": 0.05,
     "default": policy.FAST_TRACK},
    {"name": "emergency", "label": "EMERGENCY: P(someone needs help now) needed to dispatch",
     "kind": "range", "min": 0.05, "max": 1.0, "step": 0.05, "default": policy.EMERGENCY},
    {"name": "live", "label": "Live: ask the Jev-like adapter now (Ollama, OLLAMA_MODEL)",
     "kind": "toggle", "default": False},
    {"name": "typesafe", "label": "Live: ask TypeSafe's Jev now (TYPESAFE_API_KEY; text leaves "
     "this machine)", "kind": "toggle", "default": False},
    {"name": "race", "label": "Race: time one yes/no question on this text - chat model vs "
     "one token (live, Ollama)", "kind": "toggle", "default": False},
]

EXAMPLES = [{"label": f"{r['id']}{' - ' + r['trap'] if r['trap'] else ''}", "query": r["text"]}
            for r in RECORDS]


def race_blocks(query: str) -> dict:
    """The race as page blocks: both runs, where their time went, and the ratio."""
    try:
        rows = jev.race_rows(query, jev.LOCAL_MODEL)
    except jev.LIVE_ERRORS as err:
        return {"arms": [], "blocks": [{"kind": "note", "text":
                f"Ollama did not answer: {err}. Run ./run -l 10 check."}]}
    question = QUESTIONS[jev.RACE_QUESTION]["instructions"]
    stats = [{"v": f"{r['seconds']:.2f}s", "l": r["engine"]} for r in rows]
    slow, fast = rows[0], rows[1]
    if fast["seconds"] > 0:
        stats.append({"v": f"{slow['seconds'] / fast['seconds']:.1f}x",
                      "l": "faster with one token (same model)"})
    sec = lambda r, k: {"v": f"{r[k]:.2f}" if k in r else "-", "cls": "num"}  # noqa: E731
    table = [[{"v": r["engine"], "cls": "text"}, {"v": r["answer"], "cls": "text"},
              sec(r, "read_seconds"), sec(r, "write_seconds"), sec(r, "seconds"),
              {"v": str(r["tokens"]), "cls": "num"}] for r in rows]
    return {"arms": [], "blocks": [
        {"kind": "note", "text": f"Question: {question}"},
        {"kind": "stats", "items": stats},
        {"kind": "table", "title": "Both runs", "columns":
         ["engine", "answer", "read s", "write s", "total s", "tokens written"], "rows": table},
        {"kind": "note", "text": " ".join(jev.race_summary(rows)) + " That is for ONE question: "
         "the adapter needs one model call per question; the real Jev answers all of a request's "
         "questions in one pass."}]}


def search(query: str, values: dict) -> dict:
    fallback = ""
    rec = BY_TEXT.get(_key(query))
    if rec:
        query = rec["text"]  # the transcript as recorded, line breaks and all
    if values.get("race"):
        return race_blocks(query)
    if values.get("typesafe"):
        model = os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest")
        body = systemone.build_request(query, QUESTIONS, model)
        try:
            run = jev.to_run(QUESTIONS, jev.run_live("typesafe", body, model))
        except (SystemExit, *jev.LIVE_ERRORS) as err:
            return {"arms": [], "blocks": [{"kind": "note", "text": f"TypeSafe: {err}"}]}
        label = (jev.label_for("typesafe", None) + ", live" if jev.typesafe_is_local()
                 else f"TypeSafe Jev ({model}, live)")
    elif values["live"]:
        body = systemone.build_request(query, QUESTIONS, jev.LOCAL_MODEL)
        try:
            run = jev.to_run(QUESTIONS, jev.run_live("local", body, jev.LOCAL_MODEL))
        except jev.LIVE_ERRORS as err:
            return {"arms": [], "blocks": [{"kind": "note", "text":
                    f"Ollama did not answer: {err}. Run ./run -l 10 check."}]}
        label = f"Jev-like adapter ({jev.LOCAL_MODEL}, live, simulated)"
    else:
        backend, tape = TAPES[max(0, min(int(values["engine"]), len(TAPES) - 1))]
        if backend != "keywords" and rec is None:
            # Your own text has no recording: answer with the rules instead of an empty page.
            fallback = (f"Recordings cover the {len(RECORDS)} example calls, so this text was "
                        "answered by the keyword rules. Switch on Live to ask a model.")
            backend, tape = "keywords", None
        if backend == "keywords":
            body = systemone.build_request(query, QUESTIONS)
            run = jev.to_run(QUESTIONS, jev.run_live("keywords", body, "", DATASET))
        else:
            run = jev.to_run(QUESTIONS, tape["calls"][rec["id"]])
        label = jev.label_for(backend, tape)

    knobs = {k: values[k] for k in ("siu", "fast_track", "emergency")}
    answers = run["answers"]
    action = policy.decide(answers, **knobs)
    arms = []
    rows = []
    for name, q in QUESTIONS.items():
        a = answers.get(name)
        ranked = sorted(a["probs"], key=a["probs"].get, reverse=True) if a else ["(no valid answer)"]
        arms.append({"label": f"{name}", "ranking": ranked[:3], "highlight": name == "intent"})
        for option in systemone.options(q):
            p = a["probs"][option] if a else None
            want = rec and rec["labels"][name] == option
            rows.append([{"v": name, "cls": "text"}, {"v": option + ("  <- label" if want else ""),
                                                        "cls": "text"},
                         {"v": "-" if p is None else f"{p:.2f}", "cls": "num"}])
    stats = [{"v": action, "l": f"action ({label})"},
             {"v": f"{run['seconds']:.1f}s", "l": f"{run['calls']} model call(s)"}]
    if rec:
        want = policy.decide(scorecard.gold_answers(QUESTIONS, rec["labels"]), **knobs)
        stats.append({"v": want, "l": "action from the human labels"})
    blocks = [{"kind": "stats", "items": stats},
              {"kind": "table", "title": "Probabilities per option",
               "columns": ["question", "option", "P"], "rows": rows}]
    for problem in run["problems"]:
        blocks.append({"kind": "note", "text": f"Invalid answer: {problem}"})
    if fallback:
        blocks.insert(0, {"kind": "note", "text": fallback})
    return {"arms": arms, "blocks": blocks}


def main():
    serve(
        title="Lesson 10 · Jev and System One models",
        subtitle="The model gives probabilities. Your policy decides.",
        hint="Pick 'K-1009 - polite caller, story does not add up', compare the engines, then "
             "drag SIU up and down and watch the action change while the answers do not. "
             "Switch on Race to time a chat answer against a one-token answer, live.",
        params=PARAMS,
        examples=EXAMPLES,
        search=search,
    )


if __name__ == "__main__":
    main()
