"""Lesson 4 - interactive RAG-safety GUI (experiment locally).

Type a question and toggle the three defences — quarantine, isolation, output
filter — then watch the **undefended** answer (the model obeying a poisoned
document) next to the **defended** one, with a breakdown of which document was
poisoned, which rule caught it, and what each defence did. There is **nothing to
edit**: the toggles feed the very same `assess` function the one-shot `demo` and
the test use.

Run:  ./run -l 4        (or:  ./run -l 4 web)

The byte-checked `demo` action uses the tiny data/ corpus; this GUI searches the
richer help-centre `story/` corpus so the attack is fun to feel on real prose.
"""

import sys
from pathlib import Path

# Reach the shared GUI scaffold under tools/ (this file runs with cwd = the lesson
# dir, so locate the repo root from the file path, not the working directory).
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

from lesson_web import serve  # the shared L1-style experiment GUI

from safe_rag_demo import assess, tokenize

STORY_DIR = Path(__file__).resolve().parent.parent / "story"


def load_story():
    docs = []
    for path in sorted(STORY_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        docs.append({"name": path.name, "raw": raw, "tokens": tokenize(raw)})
    return docs


DOCS = load_story()

# The defences exposed in the GUI — all on by default, so the page opens on the
# safe behaviour the demo and test pin. Turn them off to watch the attack land.
PARAMS = [
    {"name": "quarantine", "label": "Quarantine — drop docs that look like instructions",
     "kind": "toggle", "default": True},
    {"name": "isolate", "label": "Isolate — treat retrieved text as data, never commands",
     "kind": "toggle", "default": True},
    {"name": "output_filter", "label": "Output filter — block answers that leak secrets",
     "kind": "toggle", "default": True},
]

# Queries chosen for the story corpus. The first two retrieve a poisoned page (an
# instruction-override "community tip" and an exfiltration "account recovery" note);
# the third retrieves only benign pages, so both pipelines agree.
EXAMPLES = [
    {"label": "Looks benign, hits a poisoned tip", "query": "how do I get a refund"},
    {"label": "Account help → data exfiltration", "query": "I cannot sign in to my account"},
    {"label": "A clean query (no poisoned page)", "query": "my device will not turn on"},
]


def _status(name, flagged, values):
    """What the defended pipeline did with a retrieved document."""
    if not flagged.get(name):
        return "trusted", "text"
    if values["quarantine"]:
        return "quarantined", "num"
    if values["isolate"]:
        return "isolated (inert)", "num"
    return "reached the model", "miss"


def _blocks(query, undefended, defended, values):
    retrieved = undefended["retrieved"]
    flagged = undefended["flagged"]
    poisoned = undefended["poisoned"]
    defences_on = sum(1 for k in ("quarantine", "isolate", "output_filter") if values[k])

    if defended["blocked"]:
        verdict = "leak blocked"
    elif defended["followed_injection"]:
        verdict = "HIJACKED"
    else:
        verdict = "safe"

    blocks = [{
        "kind": "stats",
        "items": [
            {"v": str(len(retrieved)), "l": "documents retrieved"},
            {"v": str(len(poisoned)), "l": "poisoned among them"},
            {"v": "%d / 3" % defences_on, "l": "defences enabled"},
            {"v": verdict, "l": "defended result"},
        ],
    }]

    # Which injection rules fired, and in which document (rule order = INJECTION_PATTERNS).
    hits = [{"text": label, "note": "in " + name, "muted": True}
            for name in retrieved for label in flagged.get(name, [])]
    if hits:
        blocks.append({"kind": "tokens",
                       "title": "Injection patterns detected in the retrieved text", "items": hits})
    else:
        blocks.append({"kind": "note",
                       "text": "No injection patterns in the retrieved documents — nothing to defend "
                               "against for this query, so both pipelines agree."})

    columns = ["document", "injection?", "status under your defences"]
    rows = []
    for name in retrieved:
        is_pois = bool(flagged.get(name))
        status, scls = _status(name, flagged, values)
        rows.append([
            {"v": name, "cls": "text"},
            {"v": "yes" if is_pois else "no", "cls": "miss" if is_pois else "text"},
            {"v": status, "cls": scls},
        ])
    blocks.append({"kind": "table", "title": "What each defence did to each document",
                   "columns": columns, "rows": rows})

    # Plain-English verdict comparing the two pipelines.
    if undefended["followed_injection"] and verdict == "safe":
        msg = ("Undefended, the model obeyed the poisoned document and answered with the attacker's "
               "script. Your defences stripped the instruction out and answered from the trusted "
               "page instead.")
    elif undefended["followed_injection"] and verdict == "leak blocked":
        msg = ("Undefended, the model leaked a secret the poisoned document told it to exfiltrate. "
               "The output filter caught the leak — but note it is a backstop: turn quarantine and "
               "isolation off and only the filtered leaks are stopped, not other manipulation.")
    elif undefended["followed_injection"] and verdict == "HIJACKED":
        msg = ("Both pipelines were hijacked: with every defence off, the injected instruction in a "
               "retrieved document runs. Enable a defence and watch the defended answer recover.")
    else:
        msg = ("No poisoned page was retrieved for this query, so the model answers normally from the "
               "documents — the safe baseline.")
    blocks.append({"kind": "note", "text": msg})
    blocks.append({"kind": "note",
                   "text": "Here isolation is modelled two ways: the model never executes instructions "
                           "found in a flagged document, and it never quotes a flagged document as the "
                           "answer — so an 'ignore previous instructions' line is inert. In a real system "
                           "you'd enforce this by delimiting retrieved text (e.g. <<DATA … DATA>>) and "
                           "telling the model to treat anything inside as content to quote, never commands."})
    return blocks


def search(query, values):
    if not query:
        return {"arms": [], "blocks": [{"kind": "note", "text": "Type a query — or pick an example above."}]}

    undefended = assess(query, DOCS, quarantine=False, isolate=False, output_filter=False)
    defended = assess(query, DOCS,
                      quarantine=values["quarantine"],
                      isolate=values["isolate"],
                      output_filter=values["output_filter"])
    arms = [
        {"label": "Undefended — model obeys the document", "ranking": [undefended["text"]]},
        {"label": "Defended — answers from data only", "ranking": [defended["text"]], "highlight": True},
    ]
    return {"arms": arms, "blocks": _blocks(query, undefended, defended, values)}


def main():
    serve(
        title="Lesson 4 · RAG safety — a help centre with poisoned pages",
        subtitle="Retrieved documents are untrusted input. Toggle the defences and watch the "
                 "undefended answer (the model obeying a poisoned page) next to the defended one.",
        hint="Searching a bundled help-centre corpus with two poisoned pages. Try a refund or a "
             "sign-in question, then turn the defences off.",
        params=PARAMS,
        examples=EXAMPLES,
        search=search,
    )


if __name__ == "__main__":
    main()
