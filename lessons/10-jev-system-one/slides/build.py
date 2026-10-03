"""Lesson 10 - build the slide deck PDF from deck.html and the recorded runs.

Every number on the slides is computed here from data/cassettes/, through the same
scorecard the demo uses, so the deck cannot disagree with `./run -l 10 demo`.

    python slides/build.py            # writes docs/pdf/LESSON10-SLIDES.pdf
    python slides/build.py --html     # only writes the filled HTML, for a browser

Needs Chromium (or Chrome) for the PDF: the HTML is printed at 960x540 per slide.
"""

from __future__ import annotations

import html
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LESSON = HERE.parent
ROOT = LESSON.parents[1]
sys.path.insert(0, str(LESSON / "python"))

import jev  # noqa: E402
import policy  # noqa: E402
import scorecard  # noqa: E402
import systemone  # noqa: E402

OUT = ROOT / "docs" / "pdf" / "LESSON10-SLIDES.pdf"


DATASET = jev.DEFAULT_DATASET
POL = policy.POLICIES[DATASET]


def rows():
    """[(label, backend, tape, runs)], questions, records - the demo's rows, in its order."""
    questions, records = jev.load_dataset(DATASET)
    out = [("keywords", None, {r["id"]: jev.to_run(questions, jev.run_live(
        "keywords", systemone.build_request(r["text"], questions), "", DATASET))
        for r in records})]
    for backend, model in jev.RECORDED_MODELS:
        tape = jev.load_cassette(jev.cassette_name(backend, model, DATASET),
                                 questions, records, DATASET)
        if tape:
            out.append((backend, tape, {r["id"]: jev.to_run(questions, tape["calls"][r["id"]])
                                        for r in records}))
    return [(jev.label_for(b, t), b, t, runs) for b, t, runs in out], questions, records


def scoreboard(table, questions, records) -> str:
    lines = []
    for label, _backend, _tape, runs in table:
        s = scorecard.score(questions, records, runs, POL)
        n = s["n"]
        lines.append(
            f"<tr><td>{html.escape(label)}</td>"
            + "".join(f"<td>{s['correct'][q]}/{n}</td>" for q in questions)
            + f"<td>{s['typed'] * 100 // s['asked']}%</td><td>{s['brier']:.3f}</td>"
            f"<td>{s['actions']}/{n}</td><td>{s['wrong']} / {s['missed']}</td>"
            f"<td>{s['seconds']:.1f}s</td></tr>")
    return "\n".join(lines)


def knob(table, questions, records) -> str:
    lines = []
    for label, _backend, _tape, runs in table:
        cells = []
        for t in POL.values:
            s = scorecard.score(questions, records, runs, POL, knob=t)
            cells.append(f"<td>{s['wrong']} wrong · {s['missed']} missed</td>")
        lines.append(f"<tr><td>{html.escape(label)}</td>{''.join(cells)}</tr>")
    return "\n".join(lines)


def side_by_side(table, questions) -> dict:
    """What the LLM wrote and what the best adapter answered for the hello call, as recorded."""
    out = {"LLM_MODEL": "-", "LLM_REPLY": "(not recorded)", "JEV_MODEL": "-",
           "JEV_REPLY": "(not recorded)"}
    for _label, backend, tape, runs in table:
        if tape is None:
            continue
        call = tape["calls"][jev.HELLO_CALL]
        if backend == "llm-json":
            text = call["text"].strip()
            out["LLM_MODEL"] = tape["model"]
            out["LLM_REPLY"] = html.escape(text if len(text) <= 420 else text[:420] + " ...")
        if backend == "local":  # the last adapter row wins: the bigger model
            answers = runs[jev.HELLO_CALL]["answers"]
            lines = []
            for name in questions:
                a = answers[name]
                lines.append(f"{name:<15}{a['pick']:<13}{a['probs'][a['pick']]:.2f}")
            lines.append(f"-> {POL.decide(answers)}")
            out["JEV_MODEL"] = tape["model"]
            out["JEV_REPLY"] = html.escape("\n".join(lines))
    return out


def fill() -> str:
    table, questions, records = rows()
    short = jev.DATASETS[DATASET]["short"]
    tapes = [t for _l, _b, t, _r in table if t]
    values = {
        "SCOREBOARD": scoreboard(table, questions, records),
        "KNOB": knob(table, questions, records),
        "QCOLS": "".join(f"<th>{short[q]}</th>" for q in questions),
        "KNOBCOLS": "".join(f"<th>{POL.knob.upper()} {v:.1f}</th>" for v in POL.values),
        "HARDWARE": html.escape(tapes[0]["hardware"]) if tapes else "-",
        **side_by_side(table, questions),
    }
    text = (HERE / "deck.html").read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def chromium() -> str:
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        path = shutil.which(name)
        if path:
            return path
    sys.exit("Chromium or Chrome is needed to print the PDF (or use --html).")


def main(argv: list[str]) -> int:
    page = fill()
    if "--html" in argv:
        out = HERE / "deck.filled.html"
        out.write_text(page, encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}")
        return 0
    # Snap-packaged Chromium can only read and write non-hidden paths under $HOME.
    with tempfile.TemporaryDirectory(dir=Path.home(), prefix="lesson10-slides-") as tmp:
        src, pdf = Path(tmp) / "deck.html", Path(tmp) / "deck.pdf"
        src.write_text(page, encoding="utf-8")
        subprocess.run([chromium(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=4000", f"--print-to-pdf={pdf}", src.as_uri()],
                       check=True, capture_output=True,
                       env={**os.environ, "TZ": "UTC"})
        OUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, OUT)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
