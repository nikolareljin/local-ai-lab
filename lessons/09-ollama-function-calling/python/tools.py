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

import ast
import math
import operator
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


# --- calculator: an AST whitelist, never eval() ---------------------------------

_BINOPS: Dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: Dict[type, Callable[[Any], Any]] = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 64:
            raise ValueError("exponent too large")
        result = _BINOPS[type(node.op)](left, right)
        # Bound every intermediate, or (9**64)**64 builds a 13,000-digit int.
        if isinstance(result, int) and result.bit_length() > 256:
            raise ValueError("result too large")
        return result
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    raise ValueError(f"not allowed in an expression: {type(node).__name__}")


def calculate(expression: str) -> str:
    """Evaluate plain arithmetic. Names, calls and attributes are refused."""
    text = expression.replace("^", "**").replace(",", "").strip()
    if len(text) > 200:
        return "error: expression longer than 200 characters"
    try:
        value = _eval(ast.parse(text, mode="eval"))
    except ZeroDivisionError:
        return "error: division by zero"
    except (SyntaxError, ValueError, TypeError, OverflowError) as exc:
        return f"error: {exc}"
    if isinstance(value, float) and not math.isfinite(value):
        return "error: result is not a finite number"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, float):
        value = round(value, 6)
    return f"{expression} = {value}"


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
