"""Lesson 10 - the official TypeSafe SDK, against TypeSafe's Jev or the local adapter.

The same code, two destinations. Only the environment changes:

  TypeSafe (internet, real Jev):   TYPESAFE_API_KEY=<your key>
  local adapter (simulated):       TYPESAFE_BASE_URL=http://127.0.0.1:8765 TYPESAFE_API_KEY=local
                                   (start it first: ./run -l 10 serve)

    ./run -l 10 install-sdk     # once: the pinned SDK into lessons/10-*/.venv-sdk
    ./run -l 10 sdk "I was charged twice, please refund one"
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

    text = " ".join(sys.argv[1:]) or "I was charged twice for my Pro plan. Please refund one."
    import systemone  # the same destination rule as python/systemone.post

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
        "queue": Choice(
            instructions="Which team queue should handle this support ticket?",
            criteria={"billing": "Charges, invoices, refunds",
                      "technical": "Bugs, outages, errors",
                      "account": "Login, users, account changes",
                      "sales": "Pricing, upgrades, quotes",
                      "trust_safety": "Security, takeover, data exposure, abuse"}),
        "urgency": Score(instructions="How urgent is it for the business?",
                         criteria=["none", "low", "medium", "high", "critical"]),
        "refund_request": Noul(instructions="Does the customer ask for money back?"),
    })
    queue = result.choices["queue"]
    urgency = result.scores["urgency"]
    refund = result.nouls["refund_request"]
    # -----------------------------------------------------------------------------

    print(f"model    {result.model}")
    print(f"queue    {queue.choice}  (confidence {queue.confidence:.2f})")
    print("         " + "  ".join(f"{k} {v:.2f}" for k, v in queue.probabilities.items()))
    level = max(urgency.probabilities, key=urgency.probabilities.get)
    print(f"urgency  {urgency.legend[level]}  (score {urgency.score:.2f} of 0-4)")
    print(f"refund   P(yes) = {refund.noul:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
