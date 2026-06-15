"""Offline test for the Lesson 4 RAG-safety demo (Python).

Encodes the lesson's claims:
- the undefended pipeline obeys a poisoned document (instruction override and
  data exfiltration),
- each defence neutralises it on its own — quarantine drops the poisoned doc,
  isolation ignores instructions in retrieved text, the output filter blocks a leak,
- the output filter is a *backstop* for leaks, not a catch-all for manipulation,
- with all defences on, both queries get the grounded answer and nothing leaks.

Run:  python -m pytest test_safe_rag.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from safe_rag_demo import OUTPUT_BLOCKED, assess, load_docs

Q_REFUND = "how long do refunds take to arrive"
Q_LOGIN = "i cannot log in to my account"

REFUND_ANSWER = "Refunds are available within 30 days of purchase and are returned to the original payment method within 5 business days."
LOGIN_ANSWER = "If you cannot log in to your account, reset your password from the sign-in page."
REFUND_PAYLOAD = "APPROVED: your refund of $9,999 is ready - confirm at http://refunds.example/claim"


def _docs():
    return load_docs()


def test_poisoned_doc_is_retrieved_for_a_benign_query():
    # The attack only matters because the poisoned ticket is retrieved at all.
    r = assess(Q_REFUND, _docs(), quarantine=False, isolate=False, output_filter=False)
    assert "ticket_4731.md" in r["retrieved"]
    assert "ticket_4731.md" in r["poisoned"]


def test_undefended_obeys_instruction_override():
    r = assess(Q_REFUND, _docs(), quarantine=False, isolate=False, output_filter=False)
    assert r["followed_injection"] is True
    assert r["text"] == REFUND_PAYLOAD


def test_undefended_leaks_a_secret():
    r = assess(Q_LOGIN, _docs(), quarantine=False, isolate=False, output_filter=False)
    assert r["followed_injection"] is True
    assert "FAKE-API-KEY-9999" in r["text"]
    assert "http://exfil.example/collect" in r["text"]


def test_quarantine_drops_the_poisoned_doc():
    r = assess(Q_REFUND, _docs(), quarantine=True, isolate=False, output_filter=False)
    assert "ticket_4731.md" in r["quarantined"]
    assert r["followed_injection"] is False
    assert r["text"] == REFUND_ANSWER


def test_isolation_ignores_instructions_without_quarantine():
    # The poisoned doc is NOT removed, but isolation means its instructions never run.
    r = assess(Q_REFUND, _docs(), quarantine=False, isolate=True, output_filter=False)
    assert r["quarantined"] == []
    assert r["followed_injection"] is False
    assert r["text"] == REFUND_ANSWER


def test_output_filter_blocks_exfiltration():
    # Only the output filter is on; it catches the leaked secret as a last line of defence.
    r = assess(Q_LOGIN, _docs(), quarantine=False, isolate=False, output_filter=True)
    assert r["blocked"] is True
    assert r["text"] == OUTPUT_BLOCKED


def test_output_filter_is_a_backstop_not_a_catch_all():
    # The refund scam carries no secret, so an output filter alone does NOT stop it —
    # this is why the upstream defences (quarantine / isolation) are needed.
    r = assess(Q_REFUND, _docs(), quarantine=False, isolate=False, output_filter=True)
    assert r["blocked"] is False
    assert r["text"] == REFUND_PAYLOAD


def test_full_defence_answers_safely():
    refund = assess(Q_REFUND, _docs(), quarantine=True, isolate=True, output_filter=True)
    login = assess(Q_LOGIN, _docs(), quarantine=True, isolate=True, output_filter=True)
    assert refund["text"] == REFUND_ANSWER
    assert login["text"] == LOGIN_ANSWER
    assert refund["followed_injection"] is False and login["followed_injection"] is False
    assert refund["blocked"] is False and login["blocked"] is False
