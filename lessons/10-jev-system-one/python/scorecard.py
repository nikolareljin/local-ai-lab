"""Lesson 10 - scoring an engine against the human labels.

Per engine, over every record:

  accuracy   right pick per question; an unanswered question counts as wrong
  typed      answers that came back as a valid option, out of all asked
  brier      mean squared error of the probabilities against the truth, per
             question (0 is perfect; an always-certain engine that is wrong
             scores 2 on that question). An unanswered question is scored as
             "every option equally likely". Lower is better.
  actions    the policy's action from the engine's answers, compared with the
             policy's action from the human labels
  wrong /    the action the policy's main threshold controls (for insurance:
  missed     "special investigations"), taken when it should not be, and not
             taken when it should

Accuracy says how often the top answer is right. Brier also says whether the
engine *knew* when it was unsure - which is what a threshold in the policy needs.
"""

from __future__ import annotations

import statistics

import policy
import systemone


def gold_answers(questions: dict, labels: dict) -> dict:
    """The human labels as certain answers, so the policy can run on them."""
    out = {}
    for name, q in questions.items():
        probs = {label: (1.0 if label == labels[name] else 0.0) for label in systemone.options(q)}
        out[name] = {"pick": labels[name], "probs": probs, "confidence": 1.0}
    return out


def brier(question: dict, answer: dict | None, truth: str) -> float:
    labels = systemone.options(question)
    if answer is None:
        probs = {label: 1.0 / len(labels) for label in labels}
    else:
        probs = answer["probs"]
    return systemone.fsum((probs[label] - (1.0 if label == truth else 0.0)) ** 2 for label in labels)


def score(questions: dict, records: list[dict], runs: dict, pol: policy.Policy,
          knob: float | None = None) -> dict:
    """`runs` maps record id -> {"answers": ..., "seconds": float, "calls": int}.

    `knob` overrides the policy's main threshold, for the engine and for the labels
    alike (the labels are certain, so it never changes their action).
    """
    kwargs = {} if knob is None else {pol.knob: knob}
    n = len(records)
    correct = {name: 0 for name in questions}
    typed = 0
    brier_sum = 0.0
    actions_right = wrong = missed = 0
    seconds = []
    for rec in records:
        run = runs[rec["id"]]
        answers = run["answers"]
        for name, q in questions.items():
            a = answers.get(name)
            typed += a is not None
            correct[name] += a is not None and a["pick"] == rec["labels"][name]
            brier_sum += brier(q, a, rec["labels"][name])
        got = pol.decide(answers, **kwargs)
        want = pol.decide(gold_answers(questions, rec["labels"]), **kwargs)
        actions_right += got == want
        wrong += got == pol.watch and want != pol.watch
        missed += want == pol.watch and got != pol.watch
        seconds.append(run["seconds"])
    return {
        "n": n,
        "correct": correct,
        "typed": typed,
        "asked": n * len(questions),
        "brier": brier_sum / (n * len(questions)) if n else 0.0,
        "actions": actions_right,
        "wrong": wrong,
        "missed": missed,
        "seconds": statistics.median(seconds) if seconds else 0.0,
        "calls": runs[records[0]["id"]]["calls"] if records else 0,
    }
