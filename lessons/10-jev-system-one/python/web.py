"""Lesson 10 - the playground: one ticket, every engine, and the thresholds as sliders.

Pick a ticket, pick an engine, and move PAGE / REFUND / CONFIDENT. The answers do
not change - the decision does. That is the point of a System One model: it gives
probabilities once, and the business rule on top is yours to tune.

  Engine      0 keywords, then each recorded engine (same order as the demo)
  Live        ON asks the Jev-like adapter now (Ollama, OLLAMA_MODEL); any text works

Launch it with:  ./run -l 10
"""

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

QUESTIONS, RECORDS = jev.load_dataset("tickets")
BY_TEXT = {r["text"]: r for r in RECORDS}
TAPES = [("keywords", None)] + [
    (backend, tape) for backend, file in jev.RECORDED
    if (tape := jev.load_cassette(file, QUESTIONS, RECORDS, "tickets")) is not None]

PARAMS = [
    {"name": "engine", "label": "Engine:  " + " · ".join(
        f"{i} {jev.label_for(b, t)}" for i, (b, t) in enumerate(TAPES)),
     "kind": "range", "min": 0, "max": len(TAPES) - 1, "step": 1, "default": min(2, len(TAPES) - 1)},
    {"name": "page", "label": "PAGE: P(high or critical) needed to wake on-call",
     "kind": "range", "min": 0.1, "max": 1.0, "step": 0.05, "default": policy.PAGE},
    {"name": "refund", "label": "REFUND: P(refund) needed to draft one",
     "kind": "range", "min": 0.1, "max": 1.0, "step": 0.05, "default": policy.REFUND},
    {"name": "confident", "label": "CONFIDENT: queue confidence below this goes to a person",
     "kind": "range", "min": 0.0, "max": 1.0, "step": 0.05, "default": policy.CONFIDENT},
    {"name": "live", "label": "Live: ask the Jev-like adapter now (Ollama, OLLAMA_MODEL)",
     "kind": "toggle", "default": False},
]

EXAMPLES = [{"label": f"{r['id']}{' - ' + r['trap'] if r['trap'] else ''}", "query": r["text"]}
            for r in RECORDS]


def search(query: str, values: dict) -> dict:
    rec = BY_TEXT.get(query.strip())
    if values["live"]:
        body = systemone.build_request(query, QUESTIONS, jev.LOCAL_MODEL)
        run = jev.to_run(QUESTIONS, jev.run_live("local", body, jev.LOCAL_MODEL))
        label = f"Jev-like adapter ({jev.LOCAL_MODEL}, live)"
    else:
        backend, tape = TAPES[int(values["engine"])]
        if backend == "keywords":
            body = systemone.build_request(query, QUESTIONS)
            run = jev.to_run(QUESTIONS, jev.run_live("keywords", body, ""))
        elif rec is None:
            return {"arms": [], "blocks": [{"kind": "note", "text":
                    "Recordings cover the 30 example tickets. Pick one, use engine 0 "
                    "(keywords), or switch on Live."}]}
        else:
            run = jev.to_run(QUESTIONS, tape["calls"][rec["id"]])
        label = jev.label_for(backend, tape)

    answers = run["answers"]
    action = policy.decide(answers, page=values["page"], refund=values["refund"],
                           confident=values["confident"])
    arms = []
    rows = []
    for name, q in QUESTIONS.items():
        a = answers.get(name)
        ranked = sorted(a["probs"], key=a["probs"].get, reverse=True) if a else ["(no valid answer)"]
        arms.append({"label": f"{name}", "ranking": ranked[:3], "highlight": name == "queue"})
        for option in systemone.options(q):
            p = a["probs"][option] if a else None
            want = rec and rec["labels"][name] == option
            rows.append([{"v": name, "cls": "text"}, {"v": option + ("  <- label" if want else ""),
                                                        "cls": "text"},
                         {"v": "-" if p is None else f"{p:.2f}", "cls": "num"}])
    stats = [{"v": action, "l": f"action ({label})"},
             {"v": f"{run['seconds']:.1f}s", "l": f"{run['calls']} model call(s)"}]
    if rec:
        want = policy.decide(scorecard.gold_answers(QUESTIONS, rec["labels"]),
                             page=values["page"], refund=values["refund"],
                             confident=values["confident"])
        stats.append({"v": want, "l": "action from the human labels"})
    blocks = [{"kind": "stats", "items": stats},
              {"kind": "table", "title": "Probabilities per option",
               "columns": ["question", "option", "P"], "rows": rows}]
    for problem in run["problems"]:
        blocks.append({"kind": "note", "text": f"Invalid answer: {problem}"})
    return {"arms": arms, "blocks": blocks}


def main():
    serve(
        title="Lesson 10 · Jev and System One models",
        subtitle="The model gives probabilities. Your policy decides.",
        hint="Pick 'T-1021 - prompt injection', compare engines 0-3, then drag PAGE down "
             "on 'T-1009 - sarcasm' and watch the action change while the answers do not.",
        params=PARAMS,
        examples=EXAMPLES,
        search=search,
    )


if __name__ == "__main__":
    main()
