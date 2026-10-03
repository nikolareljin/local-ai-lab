"""Lesson 10 - the two engines a System One model is compared against.

  keywords   a rule list, no model. Lesson 9's router idea: free, instant, and
             right whenever the caller uses the expected word.
  llm-json   the usual way to make an LLM decide: ask a chat model to *write*
             JSON with the answers, then parse what it wrote. No probabilities,
             and nothing guarantees the text is JSON or the values are options.

Both return a System One-shaped response, so the policy and the scorecard treat
every engine the same. Neither has real probabilities: they put 1.0 on their pick,
which is exactly what the Brier score punishes when the pick is wrong.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import time
import urllib.request
from pathlib import Path

import systemone

# --------------------------------------------------------------------------- keywords
# data/rules.json: per dataset and question, an ordered list of [label, [words]].
# The first rule with a word in the transcript wins; the last rule is the default.
# Written from the question criteria in data/questions.json, in English, before
# reading any call - the way a rule list is written on day one. Tuning it on these
# calls would score well here and prove nothing.
RULES = json.loads((Path(__file__).resolve().parents[1] / "data" / "rules.json")
                   .read_text(encoding="utf-8"))


def _rule_pick(text: str, rules: list) -> str:
    low = text.lower()
    for label, words in rules:
        if any(w in low for w in words):
            return label
    return rules[-1][0]


def keywords_response(body: dict, dataset: str = "insurance") -> dict:
    """Answer by keyword. A question with no rules gets its first option."""
    rules = RULES[dataset]
    answers = {}
    for name, q in body["questions"].items():
        labels = systemone.options(q)
        pick = _rule_pick(str(body["state"]), rules[name]) if name in rules else labels[0]
        answers[name] = certain(q, pick)
    return {"model": "keywords", "answers": answers, "usage": {}}


def certain(question: dict, pick: str) -> dict:
    """A System One answer that puts all probability on one label."""
    labels = systemone.options(question)
    if question["type"] == "noul":
        return {"type": "noul", "noul": 1.0 if pick == "yes" else 0.0}
    probs = [1.0 if label == pick else 0.0 for label in labels]
    if question["type"] == "choice":
        return {"type": "choice", "choice": pick, "confidence": 1.0,
                "probabilities": dict(zip(labels, probs))}
    return {"type": "score", "score": float(labels.index(pick)), "confidence": 1.0,
            "legend": {str(i): label for i, label in enumerate(labels)},
            "probabilities": {str(i): p for i, p in enumerate(probs)}}


# --------------------------------------------------------------------------- llm-json
def llm_json_prompt(body: dict) -> list[dict]:
    """The prompt people usually write: describe the fields, ask for JSON."""
    fields = []
    for name, q in body["questions"].items():
        allowed = " | ".join(systemone.options(q))
        fields.append(f'  "{name}": {allowed}   ({q["instructions"]})')
    return [
        {"role": "system", "content": "You fill in a form about a call to a call center. "
                                      "Reply with JSON only."},
        {"role": "user", "content": "Call transcript:\n" + str(body["state"]) + "\n\n"
                                    "Return a JSON object with these fields:\n" + "\n".join(fields)},
    ]


def parse_llm_json(body: dict, text: str) -> tuple[dict, list[str]]:
    """Read what the model wrote. Anything that is not a valid option is a type error.

    Returns (response, errors). A field the model got wrong, or left out, is simply
    missing from the response: the scorecard counts it as unanswered.
    """
    errors = []
    match = re.search(r"\{.*\}", text, re.S)
    try:
        written = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        written = None
    if not isinstance(written, dict):
        return {"model": "llm-json", "answers": {}, "usage": {}}, ["not a JSON object"]
    answers = {}
    for name, q in body["questions"].items():
        value = written.get(name)
        if isinstance(value, bool):  # {"refund_request": true} is a fair reading
            value = "yes" if value else "no"
        if not isinstance(value, str) or value.strip().lower() not in systemone.options(q):
            errors.append(f"{name}={value!r}")
            continue
        answers[name] = certain(q, value.strip().lower())
    return {"model": "llm-json", "answers": answers, "usage": {}}, errors


def llm_json_text(body: dict, model: str, url: str, keep_alive="5m") -> str:
    """Ask the chat model once, with no output constraint, and return what it wrote."""
    req_body = {"model": model, "messages": llm_json_prompt(body), "stream": False,
                "think": False, "keep_alive": keep_alive,
                "options": {"temperature": 0, "seed": 10, "num_predict": 200}}
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", json.dumps(req_body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)["message"]["content"]


def chat(messages: list[dict], model: str, url: str, num_predict: int = 120) -> dict:
    """One plain chat turn: the text, total seconds, and Ollama's read/write counters."""
    body = {"model": model, "messages": messages, "stream": False, "think": False,
            "keep_alive": "5m", "options": {"temperature": 0, "seed": 10,
                                            "num_predict": num_predict}}
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=300) as resp:
        reply = json.load(resp)
    return {"text": reply["message"]["content"].strip(), "seconds": time.monotonic() - started,
            "read_tokens": reply.get("prompt_eval_count", 0),
            "read_seconds": reply.get("prompt_eval_duration", 0) / 1e9,
            "tokens": reply.get("eval_count", 0),
            "write_seconds": reply.get("eval_duration", 0) / 1e9}


# A change to the prompt makes recordings of this engine stale (see jev.load_cassette).
PROMPT_VERSION = hashlib.sha256(inspect.getsource(llm_json_prompt).encode()).hexdigest()[:12]
