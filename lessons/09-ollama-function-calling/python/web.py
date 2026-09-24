"""Lesson 9 - the playground: pick a model, switch the guards off, watch what runs.

The demo prints one fixed run. This page replays the recorded models through the
live loop and lets you change what the loop does with their replies:

  Guards          OFF runs every call exactly as the model sent it: unknown
                  tools crash, bad arguments go straight into your function, and
                  a document can open a ticket. The recording stops at the first
                  turn where that changes what the model would have seen next.
  Recover calls   ON parses tool calls a model wrote as JSON text. Try it on
  written as text qwen2.5-coder and the arithmetic task.
  Live Ollama     ON sends your question to OLLAMA_MODEL instead of replaying.
                  Any question works then; replay only knows the ten tasks.

Launch it with:  ./run -l 9
"""

import sys
from pathlib import Path

# this file -> python -> 09-ollama-function-calling -> lessons -> repo root
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cassette  # noqa: E402
import function_calling as fc  # noqa: E402
import router  # noqa: E402
import tool_loop  # noqa: E402
from lesson_core import load_tasks, ollama_settings  # noqa: E402
from lesson_web import serve  # noqa: E402

from tools import Toolbox  # noqa: E402

TASKS = load_tasks()["tasks"]
TAPES = fc.recorded_models()
RETRIEVER = Toolbox().retriever

PARAMS = [
    # The shared GUI has sliders and toggles but no select, so the recorded
    # models are stops on one slider, in the same order as the demo's columns.
    {"name": "model", "label": "Recorded model:  " + " · ".join(
        f"{i} {t['model']}" for i, t in enumerate(TAPES)),
     "kind": "range", "min": 0, "max": max(0, len(TAPES) - 1), "step": 1, "default": 0},
    {"name": "guards", "label": "Guards (schema, intent, confirmation, screening)",
     "kind": "toggle", "default": True},
    {"name": "lenient", "label": "Recover calls written as text", "kind": "toggle",
     "default": False},
    {"name": "max_turns", "label": "Max turns (your cap)", "kind": "range",
     "min": 1, "max": 6, "step": 1, "default": 5},
    {"name": "live", "label": "Live Ollama (OLLAMA_MODEL) instead of the recording",
     "kind": "toggle", "default": False},
]

EXAMPLES = [{"label": f"{t['id']} - {t['ask'][:38]}", "query": t["ask"]} for t in TASKS]


def search(query: str, values: dict) -> dict:
    task = next((t for t in TASKS if t["ask"].strip() == query.strip()), None)
    box = Toolbox(retriever=RETRIEVER)
    blocks = []
    if values["live"]:
        from ollama_chat import OllamaModel

        url, name = ollama_settings()
        model = OllamaModel(url, name)
        label = f"{name} (live)"
    elif task and TAPES:
        tape = TAPES[int(values["model"])]
        rec = tape["tasks"].get(task["id"])
        if rec is None:
            return {"arms": [], "blocks": [{"kind": "note", "text":
                    f"{tape['model']} has no recording of {task['id']}. Switch on Live Ollama."}]}
        if rec.get("error"):
            return {"arms": [], "blocks": [{"kind": "note", "text":
                    f"{tape['model']} crashed on this task when it was recorded: {rec['error']}"}]}
        model = cassette.Replay(rec["turns"], task["id"], strict=False)
        label = f"{tape['model']} (recorded {tape['recorded']})"
    else:
        picked = router.route(query)
        return {"arms": [{"label": "keyword router", "ranking": picked or ["(no tool)"]}],
                "blocks": [{"kind": "note", "text":
                            "Replay only knows the ten tasks - pick one of the examples, or "
                            "switch on Live Ollama to ask anything. The router's pick is "
                            "shown because it needs no model."}]}

    result = tool_loop.run(model, query, box, max_turns=int(values["max_turns"]),
                           guarded=values["guards"], lenient=values["lenient"],
                           confirm=fc.policy_confirm)
    proposed = [c["name"] for c in result["calls"]]
    arms = [{"label": "keyword router", "ranking": router.route(query) or ["(no tool)"]},
            {"label": label, "ranking": proposed or ["(no tool)"], "highlight": True}]
    if task:
        arms.insert(0, {"label": "expected", "ranking": task["expect"] or ["(no tool)"]})

    blocks.append({"kind": "stats", "items": [
        {"v": str(result["turns"]), "l": "model round trips"},
        {"v": str(len(result["calls"])), "l": "tool calls"},
        {"v": str(sum(c["status"] not in ("ok", "declined") for c in result["calls"])),
         "l": "stopped by a guard"},
        {"v": str(len(box.outbox)), "l": "tickets opened"},
        {"v": result["stopped"], "l": "how it ended"},
    ]})
    rows = []
    for c in result["calls"]:
        args = str(c["args"])
        rows.append([{"v": str(c["turn"]), "cls": "num"},
                     {"v": c["name"] + (" (from text)" if c["recovered"] else ""), "cls": "text"},
                     {"v": args if len(args) < 60 else args[:57] + "...", "cls": "text"},
                     {"v": c["status"], "cls": "text" if c["status"] == "ok" else "miss"},
                     {"v": ", ".join(c["flags"]) or "-", "cls": "miss" if c["flags"] else "text"}])
    if rows:
        blocks.append({"kind": "table", "title": "Every call the model proposed",
                       "columns": ["turn", "tool", "arguments", "status", "output flagged"],
                       "rows": rows})
    if getattr(model, "diverged", False):
        blocks.append({"kind": "note", "text":
                       "The recording ends here: with this setting the model would have been "
                       "shown something it never saw when it was recorded. Switch on Live "
                       "Ollama to see what it does next."})
    blocks.append({"kind": "note", "text": "Answer: " + (result["answer"] or "(none)")})
    return {"arms": arms, "blocks": blocks}


def main():
    serve(
        title="Lesson 9 · Ollama + function calling",
        subtitle="The model picks the tool. Your code decides whether it runs.",
        hint="Pick 't8 - Summarize support ticket 9001', then switch Guards off. "
             "Then try 't2' on qwen2.5-coder with and without 'Recover calls written as text'.",
        params=PARAMS,
        examples=EXAMPLES,
        search=search,
    )


if __name__ == "__main__":
    main()
