"""Lesson 10 - the decision. The model answers questions; this code decides.

A System One model never chooses the action. It returns probabilities, and the
business rule that turns them into "send an ambulance" or "send it to the fraud
team" lives here, in code you can read, test and change without retraining
anything. The thresholds are the knobs: lower SIU and more honest callers get
investigated; raise it and more staged accidents get paid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# ---- Kestrel Mutual claims line ------------------------------------------------------
EMERGENCY = 0.5   # P(someone needs help right now) to dispatch assistance
SIU = 0.6         # P(fraud signals) to send a claim to the Special Investigations Unit
FAST_TRACK = 0.8  # P(no fraud signals) needed to pay a small claim without a human
CONFIDENT = 0.6   # below this confidence in the caller's intent, a person takes the call


def _p(answers: dict, name: str, label: str, default: float = 0.0) -> float:
    return answers.get(name, {}).get("probs", {}).get(label, default)


def decide(answers: dict, siu: float = SIU, emergency: float = EMERGENCY,
           fast_track: float = FAST_TRACK, confident: float = CONFIDENT) -> str:
    """One action per insurance call, from the answers to the six questions."""
    intent = answers.get("intent")
    if _p(answers, "emergency", "yes") >= emergency:
        return "dispatch emergency help"  # first, whatever else the call is about
    if intent is None or intent["confidence"] < confident:
        return "human agent"  # no usable answer: never guess
    if intent["pick"] in ("complaint", "cancel_policy"):
        return "human agent"
    if intent["pick"] in ("claim_status", "coverage_question"):
        return "self-service answer"
    # a new claim
    p_fraud = _p(answers, "fraud_signals", "yes", 1.0)
    if p_fraud >= siu:
        return "special investigations"
    small = _p(answers, "severity", "none") + _p(answers, "severity", "minor") >= 0.5
    if small and _p(answers, "needs_adjuster", "yes", 1.0) < 0.5 and 1 - p_fraud >= fast_track:
        return "fast-track payout"
    return "assign adjuster"


# ---- The Harbour Ledger subscriber line ----------------------------------------------
RETAIN = 0.5  # P(high churn risk) to hand the call to the retention desk
REFUND = 0.8  # P(wants money back) to draft a refund for approval


def decide_media(answers: dict, retain: float = RETAIN, refund: float = REFUND) -> str:
    """One action per newspaper call."""
    topic = answers.get("topic")
    if topic is None:
        return "human agent"
    if topic["pick"] == "editorial":
        return "pass to newsroom"
    if topic["pick"] == "advertising":
        return "pass to ad sales"
    # a missing answer counts as "yes": it sends the call to people, never to self-service
    if topic["pick"] == "cancel" or _p(answers, "churn_risk", "high", 1.0) >= retain:
        return "retention desk"
    if _p(answers, "wants_refund", "yes", 1.0) >= refund:
        return "refund for approval"
    return "self-service answer"


# ---- what the scorecard needs to know about each policy ------------------------------
@dataclass(frozen=True)
class Policy:
    decide: Callable[..., str]
    knob: str            # the threshold the demo sweeps, as decide()'s keyword
    values: tuple        # the values it sweeps
    watch: str           # the action that threshold controls
    wrong: str           # what a wrong `watch` costs
    missed: str          # what a missed `watch` costs


POLICIES = {
    "insurance": Policy(decide, "siu", (0.3, 0.6, 0.9), "special investigations",
                        "honest callers investigated", "suspicious claims not investigated"),
    "media": Policy(decide_media, "retain", (0.3, 0.5, 0.9), "retention desk",
                    "happy readers sent to retention", "leaving readers not sent to retention"),
}
