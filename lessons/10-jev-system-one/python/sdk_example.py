"""Lesson 10 - the official TypeSafe SDK, against TypeSafe's Jev or the local adapter.

The same code, two destinations. Only the environment changes:

  TypeSafe (internet, real Jev):   TYPESAFE_API_KEY=<your key>
  local adapter (simulated):       TYPESAFE_BASE_URL=http://127.0.0.1:8765 TYPESAFE_API_KEY=local
                                   (start it first: ./run -l 10 serve)

    ./run -l 10 install-sdk     # once: the pinned SDK into lessons/10-*/.venv-sdk
    ./run -l 10 sdk "Caller: someone dented my parked car, I have a photo"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

LESSON = Path(__file__).resolve().parents[1]
VENV = LESSON / ".venv-sdk"


def ensure_sdk_python() -> None:
    """Re-run this file with the SDK venv's Python if the SDK is not importable here."""
    try:
        import typesafe_sdk  # noqa: F401
        return
    except ImportError:
        pass
    for rel in ("bin/python", "Scripts/python.exe"):
        py = VENV / rel
        if py.exists() and Path(sys.executable).resolve() != py.resolve():
            os.execv(str(py), [str(py), *sys.argv])
    sys.exit("typesafe-sdk is not installed. Run: ./run -l 10 install-sdk")


def main() -> int:
    ensure_sdk_python()
    from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

    text = " ".join(sys.argv[1:]) or (
        "Caller: My camera fell into the sea on the first day. No receipt, I paid cash. "
        "The same thing happened on my last two trips.")
    import systemone  # the same destination rule as python/systemone.post

    systemone.load_typesafe_env(LESSON.parents[1] / ".env")

    url = os.environ.get("TYPESAFE_BASE_URL", systemone.TYPESAFE_URL)
    try:
        systemone.check_destination(url)  # TypeSafe or this machine, nothing else
    except ValueError as err:
        sys.exit(str(err))
    if not systemone.is_loopback(url):
        print("Sending this text to TypeSafe (it leaves this machine). Use fake data only.")

    # --- the whole integration -------------------------------------------------
    client = TypeSafeClient()  # reads TYPESAFE_API_KEY and TYPESAFE_BASE_URL
    result = client.system_one(text, {
        "intent": Choice(
            instructions="What does the caller want from this call?",
            criteria={"new_claim": "Reports a loss or sends in a bill to be paid",
                      "claim_status": "Asks where an existing claim stands",
                      "coverage_question": "Asks whether something is covered",
                      "complaint": "Complains about price, service or a decision",
                      "cancel_policy": "Wants to end the policy"}),
        "severity": Score(instructions="How serious is the damage, loss or harm described?",
                          criteria=["none", "minor", "moderate", "major", "catastrophic"]),
        "fraud_signals": Noul(instructions="Does the story have warning signs of a dishonest claim?"),
    })
    intent = result.choices["intent"]
    severity = result.scores["severity"]
    fraud = result.nouls["fraud_signals"]
    # -----------------------------------------------------------------------------

    print(f"model     {result.model}")
    print(f"intent    {intent.choice}  (confidence {intent.confidence:.2f})")
    print("          " + "  ".join(f"{k} {v:.2f}" for k, v in intent.probabilities.items()))
    level = max(severity.probabilities, key=severity.probabilities.get)
    print(f"severity  {severity.legend[level]}  (score {severity.score:.2f} of 0-4)")
    print(f"fraud     P(yes) = {fraud.noul:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
