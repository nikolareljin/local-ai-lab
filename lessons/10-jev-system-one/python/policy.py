"""Lesson 10 - the decision. The model answers questions; this code decides.

A System One model never chooses the action. It returns probabilities, and the
business rule that turns them into "page someone at 3 a.m." lives here, in code
you can read, test and change without retraining anything. The thresholds are
the knobs: raise PAGE and fewer people are woken up, and more outages wait.
"""

from __future__ import annotations

PAGE = 0.7      # P(urgency is high or critical) needed to page on-call
REFUND = 0.8    # P(refund requested) needed to draft a refund for approval
CONFIDENT = 0.6  # below this queue confidence, a person triages instead

ACTIONS = ("escalate: trust & safety", "page on-call", "draft refund for approval",
           "human triage", "auto-route")


def decide(answers: dict, page: float = PAGE, refund: float = REFUND,
           confident: float = CONFIDENT) -> str:
    """One action per ticket, from the answers to the four ticket questions."""
    queue = answers.get("queue")
    if queue is None:
        return "human triage"  # no usable answer: never guess
    urgency = answers.get("urgency", {}).get("probs", {})
    p_urgent = urgency.get("high", 0.0) + urgency.get("critical", 0.0)
    p_refund = answers.get("refund_request", {}).get("probs", {}).get("yes", 0.0)
    p_human = answers.get("needs_human", {}).get("probs", {}).get("yes", 1.0)

    if queue["probs"].get("trust_safety", 0.0) >= 0.5:
        return "escalate: trust & safety"
    if p_urgent >= page and queue["pick"] == "technical":
        return "page on-call"
    if p_refund >= refund and queue["pick"] == "billing":
        return "draft refund for approval"
    if p_human >= 0.5 or queue["confidence"] < confident:
        return "human triage"
    return "auto-route"
