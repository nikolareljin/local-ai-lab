"""Lesson 10 - the two engines Jev is compared against.

  keywords   a rule list, no model. Lesson 9's router idea: free, instant, and
             right whenever the customer uses the expected word.
  llm-json   the usual way to make an LLM decide: ask a chat model to *write*
             JSON with the answers, then parse what it wrote. No probabilities,
             and nothing guarantees the text is JSON or the values are options.

Both return a System One-shaped response, so the policy and the scorecard treat
every engine the same. Neither has real probabilities: they put 1.0 on their pick,
which is exactly what the Brier score punishes when the pick is wrong.
"""

from __future__ import annotations

import json
import re
import urllib.request

import systemone

# --------------------------------------------------------------------------- keywords
# First matching rule wins, per question. Lower-case substring match. Written from
# the question criteria in data/questions.json, in English, before looking at any
# ticket - the way a rule list is written on day one. Tuning it on these 30 tickets
# would score well here and prove nothing.
RULES = {
    "queue": [
        ("trust_safety", ["security", "hacked", "phishing", "breach", "leak", "abuse", "fraud"]),
        ("billing", ["charge", "invoice", "refund", "payment", "billing", "card"]),
        ("account", ["log in", "login", "2fa", "password", "account", "admin", "permission"]),
        ("sales", ["price", "pricing", "discount", "quote", "licence", "license", "upgrade"]),
        ("technical", [""]),  # the default queue
    ],
    "urgency": [
        ("critical", ["emergency", "outage", "all customers", "data loss"]),
        ("high", ["urgent", "asap", "down", "immediately", "now!"]),
        ("low", ["question", "how do i", "not urgent", "when you can"]),
        ("medium", [""]),
    ],
    "refund_request": [
        ("yes", ["refund", "money back", "chargeback"]),
        ("no", [""]),
    ],
    "needs_human": [
        ("yes", ["lawyer", "legal", "gdpr", "security", "emergency", "outage"]),
        ("no", [""]),
    ],
}


def _rule_pick(text: str, rules: list) -> str:
    low = text.lower()
    for label, words in rules:
        if any(w in low for w in words):
            return label
    return rules[-1][0]


def keywords_response(body: dict) -> dict:
    """Answer the ticket questions by keyword. Unknown questions get the first option."""
    answers = {}
    for name, q in body["questions"].items():
        labels = systemone.options(q)
        pick = _rule_pick(body["state"], RULES[name]) if name in RULES else labels[0]
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
        {"role": "system", "content": "You triage support tickets. Reply with JSON only."},
        {"role": "user", "content": "Ticket:\n" + str(body["state"]) + "\n\n"
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
