"""Lesson 9 - recording a real model once, replaying it forever.

The demo must print the same thing on every machine with no model installed,
because its output is committed and diffed by a test. A scripted fake would do
that, but then the demo would be about a fake. So the model's replies are
**recorded** from real Ollama runs (`./run -l 9 record`) and **replayed** here.

Only the model is replayed. The loop, the schema validation, the guards and the
tools all run for real on every replay. Each recorded turn carries a digest of
the exact conversation the model was shown; if anything upstream changes - a
tool's output, the system prompt, a schema - the digest stops matching and the
replay refuses, instead of quietly replaying answers to a conversation that no
longer happens.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List


class CassetteDrift(RuntimeError):
    pass


def digest(messages: List[dict], tools: List[dict]) -> str:
    shown = {
        "messages": [{k: m.get(k) for k in ("role", "content", "tool_calls", "tool_name")}
                     for m in messages],
        "tools": tools,
    }
    blob = json.dumps(shown, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class Recorder:
    """Wraps a live model and writes down every reply, per task."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.turns: List[dict] = []

    def chat(self, messages: List[dict], tools: List[dict]) -> Dict:
        reply = self.inner.chat(messages, tools)
        self.turns.append({"digest": digest(messages, tools), "seconds": reply["seconds"],
                           "message": reply["message"]})
        return reply


class Replay:
    """Plays one task's recorded turns back, checking each one still applies."""

    def __init__(self, turns: List[dict], label: str = "", *, strict: bool = True) -> None:
        self.turns = list(turns)
        self.label = label
        self.strict = strict
        self.used = 0
        self.diverged = False

    def _drift(self, why: str) -> Dict:
        # strict (demo, tests): refuse. Not strict (playground): end the run
        # honestly, because switching a guard off changes what the model would
        # have been shown next, and nobody recorded its reply to that.
        if self.strict:
            raise CassetteDrift(f"{self.label}: {why}")
        self.diverged = True
        return {"message": {"role": "assistant", "content": ""}, "seconds": 0.0}

    def chat(self, messages: List[dict], tools: List[dict]) -> Dict:
        if self.used >= len(self.turns):
            return self._drift(f"the loop asked for turn {self.used + 1}, "
                               f"only {len(self.turns)} were recorded")
        turn = self.turns[self.used]
        if turn["digest"] != digest(messages, tools):
            return self._drift(f"turn {self.used + 1} was recorded against a different "
                               "conversation - re-record with ./run -l 9 record")
        self.used += 1
        return {"message": turn["message"], "seconds": turn["seconds"]}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
