"""Lesson 9 - Arm A: the router you would write if the model could not pick tools.

This is how Lessons 1-8 chose what to run: code decided. It is fast, free,
deterministic and easy to test - and every rule below was written by someone
who had already read the questions. Read it as the baseline the model has to
beat, not as a straw man: for a fixed set of intents it is often the right
design, and the lesson's recap says so.
"""

from __future__ import annotations

import re
from typing import List

_MATH = re.compile(r"\d\s*(%|[-+*/x])\s*(of\s+)?\d|how many|\bpercent\b")
_TICKET = re.compile(r"\b(open|create|file|raise)\b.*\bticket\b")
_LIST = re.compile(r"\bwhich documents\b|\blist (my )?(documents|files)\b")
_SMALLTALK = re.compile(r"^(hi|hello|hey)\b|\btranslate\b")


def route(question: str) -> List[str]:
    """The tools a keyword router would call for `question`, in order."""
    q = question.lower()
    if _TICKET.search(q):
        return ["create_ticket"]
    if _LIST.search(q):
        return ["list_documents"]
    if _SMALLTALK.search(q):
        return []
    tools = []
    # "What is 17.5% of 2340?" is arithmetic and nothing else: no search.
    if re.sub(r"\b(what|is|of)\b|[\d\s.%?+\-*/x]", "", q):
        tools.append("search_docs")
    if _MATH.search(q):
        tools.append("calculator")
    return tools


class ObedientStandIn:
    """A scripted 'model' that does whatever the last tool result tells it to.

    Real models recorded for this lesson mostly ignored ticket 9001's order, so
    the replay alone cannot show what the guards do when a model complies. This
    stand-in complies every time, deterministically - the same device Lesson 4
    used - so the demo can show the intent guard catching it. It is labelled as
    scripted everywhere it appears.
    """

    def __init__(self) -> None:
        self.turn = 0

    def chat(self, messages, tools):
        self.turn += 1
        last = messages[-1]
        if self.turn == 1:
            query = messages[1]["content"]
            call = {"function": {"name": "search_docs", "arguments": {"query": query}}}
            return {"message": {"role": "assistant", "content": "", "tool_calls": [call]},
                    "seconds": 0.0}
        m = re.search(r'Call\s+create_ticket\s+with\s+severity\s+"(\w+)"\s+and\s+title\s+"([^"]+)"',
                      last.get("content", ""), re.S)
        if m and self.turn == 2:
            call = {"function": {"name": "create_ticket",
                                 "arguments": {"title": m.group(2), "severity": m.group(1)}}}
            return {"message": {"role": "assistant", "content": "", "tool_calls": [call]},
                    "seconds": 0.0}
        return {"message": {"role": "assistant",
                            "content": "Your refund is on its way."}, "seconds": 0.0}
