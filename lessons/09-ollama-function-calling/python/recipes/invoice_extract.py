"""Lesson 9 recipe - pull structured records out of invoices, and check the sums.

Models a back-office job: a folder of supplier invoices becomes rows in a
ledger. The model reads each document and fills `record_invoice`; the tool, not
the model, decides whether the numbers hold up. Two rules live in the tool:

  - every amount must appear in the document it came from (no invented numbers)
  - the total must equal the sum of the lines, or the call is sent back

A model that insists on a total that does not add up gets the invoice filed as
`needs_review` for a person, never as clean. `data/inbox/inv-1002-harbor-lane.md`
is built to trip this: its printed total is 1,240.00, its lines sum to 1,204.00.

  python python/recipes/invoice_extract.py           offline, scripted stand-in
  python python/recipes/invoice_extract.py --live    a local Ollama model (OLLAMA_MODEL)
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import recipe_kit as kit  # noqa: E402
import tool_loop  # noqa: E402
from lesson_core import DATA_DIR  # noqa: E402

from tools import Tool, ToolSet  # noqa: E402

INBOX = DATA_DIR / "inbox"
SYSTEM = (
    "You enter supplier invoices into a ledger. Call read_document for each file, then "
    "record_invoice with every value copied exactly as printed. Never change a printed "
    "number to make it add up. If record_invoice rejects the total, re-read the document; "
    "if the printed total really differs from the lines, call record_invoice again with a "
    "note saying so, which files the invoice for human review."
)
QUESTION = "Record every invoice in the inbox."
_NUMBER = re.compile(r"\d[\d,]*\.\d{2}")


def money(value: float) -> str:
    return f"{value:,.2f}"


@dataclass
class InvoiceDesk(ToolSet):
    inbox: Path = INBOX
    records: Dict[str, dict] = field(default_factory=dict)
    strikes: Dict[str, int] = field(default_factory=dict)  # rejected totals per document
    tools: Dict[str, Tool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        names = sorted(p.name for p in self.inbox.glob("*.md"))
        line = {"type": "object", "required": ["description", "amount"],
                "properties": {"description": {"type": "string"}, "amount": {"type": "number"}}}
        self.add(
            Tool("read_document", "Return the full text of one invoice from the inbox.",
                 {"type": "object", "required": ["name"],
                  "properties": {"name": {"type": "string", "enum": names}}},
                 self.read_document),
            Tool("record_invoice",
                 "Record one invoice in the ledger. Copy every value exactly as printed in "
                 "the document. The tool checks that the total equals the sum of the lines.",
                 {"type": "object",
                  "required": ["document", "vendor", "invoice_date", "currency", "lines", "total"],
                  "properties": {
                      "document": {"type": "string", "enum": names},
                      "vendor": {"type": "string", "maxLength": 120},
                      "invoice_date": {"type": "string", "description": "YYYY-MM-DD"},
                      "currency": {"type": "string", "enum": ["USD", "EUR", "GBP"]},
                      "lines": {"type": "array", "items": line},
                      "total": {"type": "number"},
                      "note": {"type": "string", "maxLength": 200,
                               "description": "Why a rejected total is being submitted again."},
                  }},
                 self.record_invoice),
        )

    def read_document(self, name: str) -> str:
        # The schema enum already limits `name`; checked again so a direct or
        # unguarded call cannot read "../../.env" either.
        if name not in self.tools["read_document"].parameters["properties"]["name"]["enum"]:
            raise ValueError(f"{name!r} is not in the inbox")
        return (self.inbox / name).read_text(encoding="utf-8")

    def record_invoice(self, document: str, vendor: str, invoice_date: str, currency: str,
                       lines: List[dict], total: float, note: Optional[str] = None) -> str:
        if document in self.records:
            return f"error: {document} is already recorded ({self.records[document]['status']})."
        # guards.validate has no `pattern` keyword, so the date format is checked here.
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", invoice_date):
                raise ValueError
            datetime.date.fromisoformat(invoice_date)
        except ValueError:
            return f"error: invoice_date {invoice_date!r} is not a real date in YYYY-MM-DD form."
        if not lines:
            return "error: an invoice needs at least one line."
        # Every amount must be one the document prints: the model copies, it does not compute.
        printed = {float(n.replace(",", "")) for n in _NUMBER.findall(self.read_document(document))}
        for amount in [item["amount"] for item in lines] + [total]:
            if round(float(amount), 2) not in printed:
                return (f"error: {money(amount)} does not appear in {document}; copy the "
                        "amounts exactly as printed.")
        lines_sum = round(sum(float(item["amount"]) for item in lines), 2)
        status = "clean"
        if round(float(total), 2) != lines_sum:
            self.strikes[document] = self.strikes.get(document, 0) + 1
            if self.strikes[document] < 2:
                return (f"error: total {money(total)} does not match the sum of lines "
                        f"{money(lines_sum)}; re-read the document.")
            status = "needs_review"  # asked twice: a person decides, the ledger does not
        self.records[document] = {
            "document": document, "vendor": vendor, "invoice_date": invoice_date,
            "currency": currency, "lines": len(lines), "lines_sum": lines_sum,
            "total": round(float(total), 2), "status": status, "note": note or "",
        }
        return f"Recorded {document} as {status}."


# --- the scripted stand-in -------------------------------------------------------------


def _read_results(messages: List[dict]) -> Dict[str, str]:
    """document name -> text, pairing each read_document call with its result."""
    out, pending = {}, []
    for m in messages:
        for c in m.get("tool_calls", []):
            if c["function"]["name"] == "read_document":
                pending.append(c["function"]["arguments"]["name"])
        if m.get("role") == "tool" and m.get("tool_name") == "read_document" and pending:
            out[pending.pop(0)] = m["content"]
    return out


def _parse(document: str, text: str) -> dict:
    """What a model would copy off the page, read with regexes."""
    def field_(name):
        return re.search(rf"^{name}:\s*(.+)$", text, re.M).group(1).strip()

    rows = re.findall(r"^\|\s*([^|]+?)\s*\|\s*([\d,]+\.\d{2})\s*\|$", text, re.M)
    return {"document": document, "vendor": field_("Vendor"),
            "invoice_date": field_("Invoice date"), "currency": field_("Currency"),
            "lines": [{"description": d, "amount": float(a.replace(",", ""))} for d, a in rows],
            "total": float(field_("Total due").replace(",", ""))}


def _record_all(messages):
    return [kit.call("record_invoice", **_parse(d, t))
            for d, t in sorted(_read_results(messages).items())]


def _insist_on_rejected(messages):
    """Re-submit, with a note, each invoice whose total was just sent back."""
    docs = _read_results(messages)
    last = [m for m in messages if m.get("role") == "tool"][-len(docs):]
    redo = [d for d, m in zip(sorted(docs), last) if "does not match" in m["content"]]
    if not redo:
        return "All invoices recorded."
    return [kit.call("record_invoice", **_parse(d, docs[d]),
                     note="Printed total re-read and confirmed; it differs from the lines.")
            for d in redo]


def standin() -> kit.ScriptedModel:
    names = sorted(p.name for p in INBOX.glob("*.md"))
    return kit.ScriptedModel([
        [kit.call("read_document", name=n) for n in names],
        _record_all,
        _insist_on_rejected,
        "Recorded the inbox. One invoice has a total that does not match its lines and "
        "is filed for review.",
    ])


def main(argv: Optional[List[str]] = None) -> int:
    args = kit.parser(__doc__).parse_args(argv)
    model = kit.pick_model(args, standin)
    desk = InvoiceDesk()
    print(f"invoice_extract - {kit.label(model)}")
    print(f"question: {QUESTION}")
    result = tool_loop.run(model, QUESTION, desk, max_turns=10, system=SYSTEM)
    kit.print_trace(result)
    print("ledger:")
    print(json.dumps([desk.records[k] for k in sorted(desk.records)], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
