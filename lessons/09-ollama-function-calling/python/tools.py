"""Lesson 9 - the tools, and the JSON that describes them to a model.

A tool is three things: a name, a JSON schema for its arguments, and a function.
The model only ever sees the first two. Everything it knows about when to call
`search_docs` instead of `calculator` comes from the `description` strings below,
so those strings are prompt text and deserve the same care as a prompt.

`side_effect=True` marks the one tool that changes something outside the
process. The loop treats it differently (see guards.py): a read can be retried
or thrown away, a write cannot be taken back.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from lesson_core import TOP_K, build_retriever


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., str]
    side_effect: bool = False
    # A pattern the USER's message must match before a side effect may run.
    intent: str = ""

    def __post_init__(self) -> None:
        # A tuple of words here used to be the format; a regex string is now.
        # Fail at definition time rather than at the first side effect.
        if not isinstance(self.intent, str):
            raise TypeError(f"{self.name}: intent must be a regex string")

    def spec(self) -> dict:
        """The exact shape Ollama's `/api/chat` expects in its `tools` array."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# --- calculator: a 60-line grammar, never eval() ---------------------------------
#
#   expr   := term (("+" | "-") term)*
#   term   := unary (("*" | "/" | "//" | "%") unary)*
#   unary  := ("+" | "-") unary | power
#   power  := atom (("**" | "^") unary)?
#   atom   := number | "(" expr ")"
#
# Numbers, operators, parentheses: nothing else can even be parsed. The Node port
# is the same grammar line for line, so both runtimes give the same result and
# the same error for any input a model sends.

_NUMBER = r"\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?"
_TOKEN = re.compile(rf"\s*(?:({_NUMBER})|(\*\*|//|[-+*/%^()]))")


class CalcError(ValueError):
    pass


def _tokens(text: str) -> List[str]:
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            if text[pos:].strip() == "":
                break
            raise CalcError(f"unexpected {text[pos:].strip()[0]!r} at position {pos}")
        out.append(m.group(1) or m.group(2))
        pos = m.end()
    return out


class _Parser:
    def __init__(self, tokens: List[str]) -> None:
        self.t, self.i = tokens, 0

    def peek(self) -> Optional[str]:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self) -> str:
        tok = self.peek()
        if tok is None:
            raise CalcError("expression ends too early")
        self.i += 1
        return tok

    def expr(self) -> float:
        value = self.term()
        while self.peek() in ("+", "-"):
            value = value + self.term() if self.take() == "+" else value - self.term()
        return value

    def term(self) -> float:
        value = self.unary()
        while self.peek() in ("*", "/", "//", "%"):
            op, right = self.take(), self.unary()
            if op != "*" and right == 0:
                raise CalcError("division by zero")
            if op == "*":
                value = value * right
            elif op == "/":
                value = value / right
            elif op == "//":
                value = math.floor(value / right)
            else:
                value = value - right * math.floor(value / right)
        return value

    def unary(self) -> float:
        if self.peek() in ("+", "-"):
            return -self.unary() if self.take() == "-" else self.unary()
        return self.power()

    def power(self) -> float:
        base = self.atom()
        if self.peek() in ("**", "^"):
            self.take()
            exp = self.unary()
            if abs(exp) > 64:
                raise CalcError("exponent too large")
            if base < 0 and exp != int(exp):
                raise CalcError("result is not a real number")
            if base == 0 and exp < 0:
                raise CalcError("division by zero")
            try:
                return math.pow(base, exp)
            except OverflowError:  # JS returns Infinity here; match it
                return math.inf
        return base

    def atom(self) -> float:
        tok = self.take()
        if tok == "(":
            value = self.expr()
            if self.peek() != ")":
                raise CalcError("missing ')'")
            self.take()
            return value
        if tok[0].isdigit() or tok[0] == ".":
            return float(tok)
        raise CalcError(f"unexpected {tok!r}")


def calculate(expression: str) -> str:
    """Evaluate plain arithmetic, or return `error: ...` for the model to read.

    Commas are refused rather than guessed at: "2,5" is a decimal in half the
    world and a thousands separator in the other half.
    """
    if len(expression) > 200:
        return "error: expression longer than 200 characters"
    try:
        parser = _Parser(_tokens(expression))
        if parser.peek() is None:
            raise CalcError("expression is empty")
        value = parser.expr()
        if parser.peek() is not None:
            raise CalcError(f"unexpected {parser.peek()!r}")
    except CalcError as exc:
        return f"error: {exc}"
    if not math.isfinite(value) or abs(value) >= 1e15:
        return "error: result too large"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return f"{expression} = {'0' if text in ('-0', '') else text}"


# --- tool sets --------------------------------------------------------------------


class ToolSet:
    """What the loop needs from any set of tools. The recipes build their own."""

    tools: Dict[str, Tool]

    def add(self, *tools: Tool) -> None:
        for tool in tools:
            self.tools[tool.name] = tool

    def specs(self, only: Optional[List[str]] = None) -> List[dict]:
        return [t.spec() for n, t in self.tools.items() if only is None or n in only]

    def get(self, name: str) -> Optional[Tool]:
        return self.tools.get(name)


@dataclass
class Toolbox(ToolSet):
    """The core lesson's four tools, bound to one retriever and one outbox."""

    retriever: Any = None
    outbox: List[dict] = field(default_factory=list)
    tools: Dict[str, Tool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.retriever is None:
            self.retriever = build_retriever()
        for tool in (
            Tool(
                "search_docs",
                "Search the user's local documents about the Aurora X1 sensor and return "
                "the most relevant passages. Each passage starts with its source as "
                "[file:page]; cite it. Use this for any question about the device, its "
                "setup, networking, battery, warranty, API or support tickets.",
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "What to search for."},
                        "k": {"type": "integer", "minimum": 1, "maximum": 8,
                              "description": "How many passages (default 3)."},
                    },
                    "required": ["query"],
                },
                self.search_docs,
            ),
            Tool(
                "list_documents",
                "List the file names of the user's local documents.",
                {"type": "object", "properties": {}},
                self.list_documents,
            ),
            Tool(
                "calculator",
                "Evaluate an arithmetic expression such as '2340 * 0.175' or '(14 * 30) / 7'. "
                "Use it for every calculation instead of doing arithmetic yourself.",
                {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
                calculate,
            ),
            Tool(
                "create_ticket",
                "Open a support ticket. Only call this when the user explicitly asks "
                "for a ticket to be opened.",
                {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "maxLength": 120},
                        "severity": {"type": "string", "enum": ["low", "normal", "high"]},
                    },
                    "required": ["title", "severity"],
                },
                self.create_ticket,
                side_effect=True,
                # A verb and the object, not the bare noun: "Summarize support
                # ticket 9001" mentions a ticket and asks for nothing to be opened.
                intent=r"\b(open|create|file|raise|log)\b[^.?!]{0,40}\bticket\b",
            ),
        ):
            self.add(tool)

    # The tools themselves --------------------------------------------------------

    def search_docs(self, query: str, k: int = TOP_K) -> str:
        hits = self.retriever.search(query, max(1, int(k)))
        if not hits:
            return "No relevant passages found in the local documents."
        return "\n\n".join(f"[{h['source']}:{h['page_number']}] {h['text']}" for h in hits)

    def list_documents(self) -> str:
        names = sorted({c["source"] for c in self.retriever.chunks})
        return "\n".join(names) or "(no documents indexed)"

    def create_ticket(self, title: str, severity: str) -> str:
        ticket = {"id": f"T-{1001 + len(self.outbox)}", "title": title, "severity": severity}
        self.outbox.append(ticket)
        return f"Ticket {ticket['id']} opened: {title} ({severity})."
