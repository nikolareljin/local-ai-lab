"""Lesson 10 - the System One wire format, by hand.

A System One request is one `state` (the thing to judge) plus named, typed
`questions`. The answer is a probability for every option of every question, in
one response. Three question types:

  noul    yes/no              -> {"type": "noul",   "noul": 0.93}
  choice  one of 2-255 labels -> {"type": "choice", "choice": "billing",
                                  "probabilities": {...}, "confidence": 0.81}
  score   2-10 ordered levels -> {"type": "score",  "score": 1.05, "legend": {...},
                                  "probabilities": {"0": 0.0, "1": 0.95, ...},
                                  "confidence": 0.92}

This module builds requests, sends them (stdlib only), and checks that what came
back has the shape the questions promised. TypeSafe's hosted Jev and this lesson's
local adapter speak the same format, so everything downstream - the policy, the
scorecard - cannot tell them apart.

Reference: https://docs.typesafe.ai/api
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

MAX_QUESTIONS = 64
MAX_CHOICES = 255
SCORE_LEVELS = (2, 10)
SYSTEM_ONE_PATH = "/v1/systemone"
TYPESAFE_URL = "https://api.typesafe.ai"


def fsum(values) -> float:
    """sum() as Python 3.12+ does it (Neumaier compensation), on every Python version.

    The demo's output is byte-compared with the Node and C# ports, which do the same.
    """
    total = comp = 0.0
    for v in values:
        v = float(v)
        t = total + v
        comp += (total - t) + v if abs(total) >= abs(v) else (v - t) + total
        total = t
    return total + comp


def options(question: dict) -> list[str]:
    """The labels a question can be answered with, in order."""
    kind = question["type"]
    if kind == "noul":
        return ["yes", "no"]
    if kind == "choice":
        return list(question["criteria"])
    if kind == "score":
        return list(question["criteria"])
    raise ValueError(f"unknown question type {kind!r}")


def request_problems(body: dict) -> list[str]:
    """What TypeSafe would reject with HTTP 422, checked before anything is sent."""
    found = []
    if not isinstance(body.get("model"), str) or not body["model"]:
        found.append("model: required")
    if "state" not in body:
        found.append("state: required")
    questions = body.get("questions")
    if not isinstance(questions, dict) or not questions:
        return found + ["questions: at least one question"]
    if len(questions) > MAX_QUESTIONS:
        found.append(f"questions: at most {MAX_QUESTIONS}, got {len(questions)}")
    for name, q in questions.items():
        kind = q.get("type")
        if kind not in ("noul", "choice", "score"):
            found.append(f"questions.{name}.type: noul, choice or score")
            continue
        if not q.get("instructions"):
            found.append(f"questions.{name}.instructions: required")
        criteria = q.get("criteria")
        if kind == "choice" and not (isinstance(criteria, dict) and 2 <= len(criteria) <= MAX_CHOICES):
            found.append(f"questions.{name}.criteria: 2-{MAX_CHOICES} options")
        if kind == "score" and not (isinstance(criteria, list)
                                    and SCORE_LEVELS[0] <= len(criteria) <= SCORE_LEVELS[1]):
            found.append(f"questions.{name}.criteria: {SCORE_LEVELS[0]}-{SCORE_LEVELS[1]} levels")
    return found


def build_request(state, questions: dict, model: str = "jev-latest") -> dict:
    body = {"model": model, "state": state, "questions": questions}
    problems = request_problems(body)
    if problems:
        raise ValueError("; ".join(problems))
    return body


def digest(body: dict) -> str:
    """A short fingerprint of exactly what was asked, used to refuse stale recordings."""
    blob = json.dumps({k: body[k] for k in ("state", "questions")},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- reading answers
def read_answers(questions: dict, response: dict) -> tuple[dict, list[str]]:
    """Turn a wire response into {question: {"pick", "probs", "confidence"}}.

    Every pick is a label from `options()` ("yes"/"no" for a noul, the level name for
    a score), so the caller compares labels and never cares about the wire shape.
    A question with a missing or malformed answer is left out and reported.
    """
    answers, problems = {}, []
    got = response.get("answers") or {}
    for name, q in questions.items():
        a = got.get(name)
        labels = options(q)
        if not isinstance(a, dict) or a.get("type") != q["type"]:
            problems.append(f"{name}: no {q['type']} answer")
            continue
        if q["type"] == "noul":
            p = a.get("noul")
            if not isinstance(p, (int, float)) or not 0 <= p <= 1:
                problems.append(f"{name}: noul must be a number in [0, 1]")
                continue
            probs = {"yes": float(p), "no": 1.0 - float(p)}
            pick = "yes" if p >= 0.5 else "no"
            confidence = max(p, 1 - p)
        else:
            raw = a.get("probabilities")
            raw = raw if isinstance(raw, dict) else {}
            if q["type"] == "score":
                raw = {labels[int(k)]: v for k, v in raw.items()
                       if isinstance(k, str) and k.isascii() and k.isdigit() and int(k) < len(labels)}
            numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in raw.values())
            if set(raw) != set(labels) or not numeric or abs(fsum(raw.values()) - 1.0) > 0.01:
                problems.append(f"{name}: probabilities must cover {labels} and sum to 1")
                continue
            probs = {label: float(raw[label]) for label in labels}
            pick = a.get("choice") if q["type"] == "choice" else max(labels, key=probs.get)
            if pick not in labels:
                problems.append(f"{name}: {pick!r} is not an option")
                continue
            confidence = a.get("confidence")
            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
                confidence = max(probs.values())
            confidence = float(confidence)
        answers[name] = {"pick": pick, "probs": probs, "confidence": confidence}
    return answers, problems


# --------------------------------------------------------------------------- sending
def is_loopback(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def post(base_url: str, body: dict, api_key: str = "", timeout: float = 120.0) -> tuple[dict, float]:
    """POST one request; return (response, seconds).

    A key is only ever sent to TypeSafe or to this machine: anything else is refused,
    so a typo in TYPESAFE_BASE_URL cannot hand the key (or the tickets) to a stranger.
    """
    if not (base_url.rstrip("/") == TYPESAFE_URL or is_loopback(base_url)):
        raise ValueError(f"refusing {base_url}: only {TYPESAFE_URL} or a loopback address")
    req = urllib.request.Request(
        base_url.rstrip("/") + SYSTEM_ONE_PATH,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {api_key}"} if api_key else {})},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {err.code} from {base_url}: {detail}") from None
    except (urllib.error.URLError, socket.timeout) as err:
        raise RuntimeError(f"cannot reach {base_url}: {err}") from None
    return data, time.monotonic() - started
