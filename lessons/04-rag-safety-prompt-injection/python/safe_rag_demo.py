"""Lesson 4 - RAG safety & prompt injection demo (Python).

Retrieved documents are **untrusted input**. A poisoned document can carry an
instruction ("ignore the question and say X") that a naive pipeline will obey.
This demo runs the same query through two pipelines over a tiny corpus that
contains poisoned support tickets:

  - Undefended: the retrieved text is pasted into the prompt as-is, so the model
    obeys the injected instruction and emits the attacker's scripted payload.
  - Defended: three layers neutralise it - quarantine (drop docs that look like
    instructions), isolate (treat retrieved text as data, never as commands), and
    an output filter (block answers that leak secrets / exfiltration URLs).

Dependency-free and offline: the detection patterns and the model stand-in are
implemented identically in the Node and .NET ports, so all three produce the
same output.

Run:  python safe_rag_demo.py

PRODUCTION (see the lesson README, "From demo to production"):
- the model stand-in here "obeys" deterministically so the lesson is reproducible;
  a real LLM is far less predictable, which is exactly why the defences are layered.
"""

import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# How many documents the retriever feeds to the model.
TOP_K = 3

# Common words dropped before scoring so retrieval keys on the meaningful terms.
# Kept identical across the Python, Node and .NET ports.
STOPWORDS = {
    "a", "an", "the", "to", "of", "do", "i", "in", "on", "is", "are",
    "and", "my", "your", "you", "they", "their", "it", "we",
}

# Ordered (label, pattern) rules that flag a chunk as "trying to give instructions".
# A real system would add more; these cover the classic injection shapes. Kept
# identical across the three ports so detection agrees exactly.
INJECTION_PATTERNS = [
    ("instruction override", r"ignore\s+(all\s+|the\s+)?(previous\s+|above\s+)?(instructions|documents)"),
    ("disregard context", r"disregard"),
    ("role injection", r"system\s*:"),
    ("forced reply", r"reply only with"),
    ("data exfiltration", r"https?://exfil|api key|session token|fake-api-key"),
]

# What the output filter treats as a leak: an exfiltration URL or a secret marker.
EXFIL_PATTERN = r"https?://exfil|api key|session token|fake-api-key"

# Deterministic stand-in messages.
NO_ANSWER = "I could not find a trustworthy answer in the documents."
OUTPUT_BLOCKED = "[blocked by output filter: the answer tried to leak a secret]"


def tokenize(text):
    return re.findall(r"[a-z0-9_]+", text.lower())


def load_docs():
    docs = []
    for path in sorted(DATA_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        docs.append({"name": path.name, "raw": raw, "tokens": tokenize(raw)})
    return docs


# --- Retrieval: distinct-term overlap, minus stopwords (deterministic) -------
def retrieve(query, docs, top_k=TOP_K):
    """Top-k docs by how many distinct meaningful query terms they contain.
    Deterministic: score desc, then name asc; zero-overlap docs are dropped."""
    q = {t for t in tokenize(query) if t not in STOPWORDS}
    scored = []
    for d in docs:
        toks = set(d["tokens"])
        score = len(q & toks)
        if score > 0:
            scored.append((score, d))
    scored.sort(key=lambda s: (-s[0], s[1]["name"]))
    return [d for _, d in scored[:top_k]]


# --- Detection: does this chunk try to issue instructions? -------------------
def matched_patterns(text):
    """The labels of every injection rule that fires on `text`, in rule order."""
    low = text.lower()
    return [label for label, pat in INJECTION_PATTERNS if re.search(pat, low)]


def is_injected(text):
    return bool(matched_patterns(text))


def extract_payload(text):
    """What an obedient model would emit: the quoted string an injection tells it
    to reply with. Falls back to a generic marker if the attack has no literal."""
    m = re.search(r'reply only with:\s*"([^"]+)"', text, re.IGNORECASE)
    return m.group(1) if m else "[the model followed an injected instruction]"


def contains_exfil(text):
    return re.search(EXFIL_PATTERN, text.lower()) is not None


def legit_answer(docs, flagged):
    """A grounded answer from *trusted* text: the first body line (skipping the
    Markdown heading) of the top document that is not flagged as injected. Even
    when isolation keeps a poisoned doc in context, we never quote it as the
    answer - its content is untrusted, not just its instructions."""
    for d in docs:
        if flagged.get(d["name"]):
            continue
        for line in d["raw"].splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    return NO_ANSWER


# --- The two pipelines, parameterised by which defences are on ---------------
def assess(query, docs, quarantine=True, isolate=True, output_filter=True):
    retrieved = retrieve(query, docs)
    flagged = {d["name"]: matched_patterns(d["raw"]) for d in retrieved}

    if quarantine:
        effective = [d for d in retrieved if not flagged[d["name"]]]
        quarantined = [d["name"] for d in retrieved if flagged[d["name"]]]
    else:
        effective = list(retrieved)
        quarantined = []

    # Isolation = the model treats retrieved text as data, so instructions inside
    # it are never executed. With isolation off, the first injected chunk wins.
    obeyed = None
    if not isolate:
        for d in effective:
            if flagged[d["name"]]:
                obeyed = extract_payload(d["raw"])
                break

    if obeyed is not None:
        text, followed = obeyed, True
    else:
        text, followed = legit_answer(effective, flagged), False

    blocked = False
    if output_filter and contains_exfil(text):
        text, blocked = OUTPUT_BLOCKED, True

    return {
        "text": text,
        "retrieved": [d["name"] for d in retrieved],
        "poisoned": [n for n, labels in flagged.items() if labels],
        "quarantined": quarantined,
        "followed_injection": followed,
        "blocked": blocked,
        "flagged": flagged,
    }


def fmt(names):
    return "[" + ", ".join("'%s'" % n for n in names) + "]"


def main():
    docs = load_docs()
    print("Same query and documents every run - the only thing that changes is whether the")
    print("three defences (quarantine, isolation, output filter) are ON.")
    for query in ["how long do refunds take to arrive", "i cannot log in to my account"]:
        undefended = assess(query, docs, quarantine=False, isolate=False, output_filter=False)
        defended = assess(query, docs, quarantine=True, isolate=True, output_filter=True)
        hijacked = undefended["followed_injection"]
        print(f'\nQuery: "{query}"')
        print(f"  Retrieved: {fmt(undefended['retrieved'])}")
        print(f"  WITHOUT hardening -> {'HIJACKED' if hijacked else 'SAFE'}")
        print(f"    {undefended['text']}")
        print("  WITH hardening    -> SAFE")
        print(f"    {defended['text']}")


if __name__ == "__main__":
    main()
