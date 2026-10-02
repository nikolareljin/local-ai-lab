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
import scorecard  # noqa: E402

OUT = ROOT / "docs" / "pdf" / "LESSON10-SLIDES.pdf"


def rows() -> list[tuple[str, dict, dict, dict | None]]:
    questions, records = jev.load_dataset("tickets")
    import systemone
    out = [("keywords", None, {r["id"]: jev.to_run(questions, jev.run_live(
        "keywords", systemone.build_request(r["text"], questions), "")) for r in records})]
    for backend, file in jev.RECORDED:
        tape = jev.load_cassette(file, questions, records, "tickets")
        if tape:
            out.append((backend, tape, {r["id"]: jev.to_run(questions, tape["calls"][r["id"]])
                                        for r in records}))
    return [(jev.label_for(b, t), runs, questions, t) for b, t, runs in out], records


def scoreboard() -> str:
    table, records = rows()
    lines = []
    for label, runs, questions, tape in table:
        s = scorecard.score(questions, records, runs)
        n = s["n"]
        lines.append(
            f"<tr><td>{html.escape(label)}</td>"
            + "".join(f"<td>{s['correct'][q]}/{n}</td>" for q in questions)
            + f"<td>{s['typed'] * 100 // s['asked']}%</td><td>{s['brier']:.3f}</td>"
            f"<td>{s['actions']}/{n}</td><td>{s['wrong_pages']} / {s['missed_pages']}</td>"
            f"<td>{s['seconds']:.1f}s</td></tr>")
    return "\n".join(lines)


def knob() -> str:
    table, records = rows()
    lines = []
    for label, runs, questions, _tape in table:
        cells = []
        for t in (0.5, 0.7, 0.9):
            s = scorecard.score(questions, records, runs, page=t)
            cells.append(f"<td>{s['wrong_pages']} wrong · {s['missed_pages']} missed</td>")
        lines.append(f"<tr><td>{html.escape(label)}</td>{''.join(cells)}</tr>")
    return "\n".join(lines)


def hardware() -> str:
    _table, _records = rows()
    tapes = [t for _l, _r, _q, t in _table if t]
    return html.escape(tapes[0]["hardware"]) if tapes else "-"


def fill() -> str:
    text = (HERE / "deck.html").read_text(encoding="utf-8")
    return (text.replace("{{SCOREBOARD}}", scoreboard())
                .replace("{{KNOB}}", knob())
                .replace("{{HARDWARE}}", hardware()))


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
