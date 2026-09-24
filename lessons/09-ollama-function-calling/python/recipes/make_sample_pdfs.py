"""Lesson 9 - write the two sample PDFs that `pdf_index.py` searches by default.

The recipe owns its fixtures: `docs/pdf/` is rebuilt whenever a lesson's
Markdown changes, so page numbers there move under any test pinned to them.
These two files change only when this script is run on purpose.

  aurora-field-handbook.pdf        3 pages: mounting, calibration, cold-weather storage
  aurora-service-bulletin-07.pdf   2 pages: a firmware issue, then its fix

Content is fictional and agrees with Lesson 7's Aurora X1 corpus. The output
is byte-stable across runs: ReportLab's `invariant` mode fixes the creation
date and document ID it would otherwise stamp in. Needs `markdown` and
`xhtml2pdf` (imported lazily; the recipes themselves only need pypdf).

  python python/recipes/make_sample_pdfs.py           writes data/pdfs/
  python python/recipes/make_sample_pdfs.py --out DIR
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import Dict, List, Optional

OUT = Path(__file__).resolve().parents[2] / "data" / "pdfs"
HINT = "make_sample_pdfs needs markdown and xhtml2pdf - pip install markdown xhtml2pdf"

# One Markdown string per page. Each file's pages are joined with a forced page break.
PDFS: Dict[str, List[str]] = {
    "aurora-field-handbook.pdf": [
        """# Aurora X1 Field Handbook

## 1. Mounting

Mount the unit vertically, sensing face downward, at least three hundred
millimetres from any metal surface. Horizontal mounting traps condensation
against the sensing face. Keep two metres between neighbouring units and
survey the radio signal from the intended position before drilling.
""",
        """## 2. Calibration

Recalibrate after any ambient shift of more than five degrees Celsius, and at
least once every ninety days. Place the unit on a level surface, hold the
pairing pin for five seconds, and wait for the status ring to settle to steady
green. Calibration takes roughly two minutes.
""",
        """## 3. Cold-weather storage

Store spare units above minus ten degrees Celsius; colder storage shortens
battery life sharply. After cold storage, let the unit rest at room temperature
for two hours before calibration, so condensation can clear from the sensing
face. Calibrating a cold unit bakes the temperature error into its offsets.
""",
    ],
    "aurora-service-bulletin-07.pdf": [
        """# Service Bulletin 07 - Aurora X1

## Issue: readings stop after 49 days

Units on firmware 2.4.1 stop sending readings after 49 days of continuous
uptime. The status ring stays green and the unit still answers the local API,
so the fault shows up only as a gap in the gateway's data.
""",
        """## Fix: update to firmware 2.4.2

Update every affected unit to firmware 2.4.2. Run the update on mains power;
updates below twenty percent battery are refused. A soft reset clears the
fault until the update is installed and keeps every stored setting.
""",
    ],
}


def render(pages: List[str]) -> bytes:
    import markdown
    from reportlab import rl_config
    from xhtml2pdf import pisa

    rl_config.invariant = 1  # no timestamp or random ID: same input, same bytes
    body = "<pdf:nextpage />".join(markdown.markdown(p) for p in pages)
    html = (f"<html><head><style>@page {{ size: a5; margin: 1.5cm; }} "
            f"body {{ font-family: Helvetica; font-size: 10pt; }}</style></head>"
            f"<body>{body}</body></html>")
    buf = io.BytesIO()
    status = pisa.CreatePDF(html, dest=buf)
    if status.err:
        raise RuntimeError("xhtml2pdf could not render the page")
    return buf.getvalue()


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", help="folder to write into (default: data/pdfs/)")
    args = p.parse_args(argv)
    try:
        import markdown  # noqa: F401
        import xhtml2pdf  # noqa: F401
    except ImportError:
        print(HINT)
        return 0
    out = Path(args.out) if args.out else OUT
    out.mkdir(parents=True, exist_ok=True)
    for name, pages in PDFS.items():
        data = render(pages)
        (out / name).write_bytes(data)
        print(f"wrote {name}: {len(pages)} pages, {len(data)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
