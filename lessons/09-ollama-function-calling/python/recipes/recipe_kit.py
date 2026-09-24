"""Lesson 9 recipes - the few lines every recipe shares.

A scripted stand-in model, a trace printer, and the `--live` switch. The loop
itself is not here: every recipe calls `tool_loop.run`, the same loop the core
lesson uses, so a recipe is only ever a new ToolSet plus a question.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, List, Union

# recipes/ -> python/ : the lesson's modules (tools, tool_loop, guards, ...)
PYTHON_DIR = Path(__file__).resolve().parent.parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

# A step is either a fixed list of calls, a final answer string, or a function of
# the messages so far that returns one of those. Functions let the script react
# to what a tool returned, which is what a model does.
Step = Union[str, List[dict], Callable[[List[dict]], Union[str, List[dict]]]]


def call(tool: str, /, **args) -> dict:
    """One tool call in the shape Ollama returns it."""
    return {"function": {"name": tool, "arguments": args}}


class ScriptedModel:
    """A 'model' that plays back a fixed script. Labelled as scripted wherever
    its output is printed: it shows what the tools and guards do, not what a
    real model would choose. `--live` swaps in a real one."""

    def __init__(self, steps: List[Step]) -> None:
        self.steps = list(steps)
        self.turn = 0

    def chat(self, messages: List[dict], tools: List[dict]) -> dict:
        step = self.steps[self.turn] if self.turn < len(self.steps) else "(script ended)"
        self.turn += 1
        if callable(step):
            step = step(messages)
        if isinstance(step, str):
            return {"message": {"role": "assistant", "content": step}, "seconds": 0.0}
        return {"message": {"role": "assistant", "content": "", "tool_calls": step},
                "seconds": 0.0}


def tool_results(messages: List[dict]) -> List[str]:
    """Every tool result the model has seen so far, oldest first."""
    return [m["content"] for m in messages if m.get("role") == "tool"]


# PDF text brings arrows, dashes and bullets with it; the recipes print plain ASCII.
_PLAIN = str.maketrans({"\u00b7": "-", "\u2022": "-", "\u2013": "-", "\u2014": "-",
                        "\u2192": "->", "\u2018": "'", "\u2019": "'", "\u201c": '"',
                        "\u201d": '"', "\u2026": "...", "\u00a0": " "})


def ascii_only(text: str) -> str:
    return text.translate(_PLAIN).encode("ascii", "replace").decode("ascii")


def short(value, width: int = 90) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    text = ascii_only(" ".join(text.split()))
    return text if len(text) <= width else text[: width - 3] + "..."


def print_trace(result: dict) -> None:
    """One line per proposed call: turn, call, what the loop or tool said."""
    for c in result["calls"]:
        print(f"  turn {c['turn']}  {c['name']}({short(c['args'], 70)})")
        print(f"          {c['status']:<13} {short(c['result'])}")
    print(f"  stopped: {result['stopped']} after {result['turns']} turn(s)")
    print(f"  answer:  {short(result['answer'] or '(none)', 300)}")


def parser(doc: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=doc.splitlines()[0])
    p.add_argument("--live", action="store_true",
                   help="use the local Ollama model instead of the scripted stand-in")
    p.add_argument("--model", help="Ollama model for --live (default: OLLAMA_MODEL)")
    return p


def pick_model(args, script: Callable[[], ScriptedModel]):
    """The scripted stand-in by default; OllamaModel only when --live is given."""
    if not args.live:
        return script()
    from lesson_core import ollama_settings
    from ollama_chat import OllamaModel

    url, default = ollama_settings()
    return OllamaModel(url, args.model or default)


def label(model) -> str:
    if isinstance(model, ScriptedModel):
        return "scripted stand-in (no model, no network)"
    return f"live Ollama model {getattr(model, 'model', '?')}"
