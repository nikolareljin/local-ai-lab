#!/usr/bin/env python3
"""Generate a PDF for the install guide and every lesson, from the Markdown sources.

Pure-Python (``markdown`` + ``xhtml2pdf``), so it runs on Linux, macOS, and Windows:

    pip install markdown xhtml2pdf
    python3 tools/build_lesson_pdfs.py

For correct box-drawing/arrow glyphs, DejaVu fonts are used when found. Set
``DEJAVU_FONT_DIR`` to point at a folder containing DejaVuSans.ttf /
DejaVuSansMono.ttf if they live somewhere non-standard (e.g. on macOS/Windows).

PDFs are written to ``docs/pdf/`` so the GitHub Pages site can link them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import markdown
from xhtml2pdf import pisa

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "pdf"

SOURCES = ["INSTALL.md"] + [f"LESSON{i}.md" for i in range(1, 9)]

# DejaVu covers arrows, box-drawing and ✓; emoji (astral plane) do not render in
# PDF fonts, so map the ones we use to short text and strip the rest.
EMOJI = {
    "🏠": "", "💻": "", "👤": "", "💡": "", "🎓": "", "📄": "", "📘": "",
    "🐙": "", "💼": "", "🧰": "", "🧩": "", "🔗": "", "▶": "▶",
    "✅": "[done] ", "🚧": "[planned] ", "⚠": "", "◔": "(planned)",
}


def clean(text: str) -> str:
    text = text.replace("️", "").replace("︎", "")  # variation selectors
    for k, v in EMOJI.items():
        text = text.replace(k, v)
    # Drop any remaining astral-plane characters (emoji) that have no PDF glyph.
    return "".join(ch for ch in text if ord(ch) <= 0xFFFF)


def _font_dir():
    """Locate a folder with DejaVuSans.ttf + DejaVuSansMono.ttf, cross-platform.

    Honours $DEJAVU_FONT_DIR first, then probes common Linux/macOS/Windows paths.
    Returns None if not found (the PDF then falls back to Helvetica/Courier).
    """
    candidates = []
    env = os.environ.get("DEJAVU_FONT_DIR")
    if env:
        candidates.append(Path(env))
    candidates += [
        Path("/usr/share/fonts/truetype/dejavu"),   # Debian/Ubuntu
        Path("/usr/share/fonts/dejavu"),            # Fedora/Arch
        Path("/opt/homebrew/share/fonts"),          # macOS (Homebrew font-dejavu)
        Path("/usr/local/share/fonts"),             # macOS/Linux
        Path("/Library/Fonts"),                     # macOS
        Path.home() / "Library" / "Fonts",          # macOS (user)
        Path("C:/Windows/Fonts"),                   # Windows
    ]
    for d in candidates:
        if (d / "DejaVuSans.ttf").exists() and (d / "DejaVuSansMono.ttf").exists():
            return d
    return None


def font_face_css() -> str:
    d = _font_dir()
    if d is None:
        return ""  # fall back to built-in Helvetica/Courier
    reg, mono = d / "DejaVuSans.ttf", d / "DejaVuSansMono.ttf"
    bold = d / "DejaVuSans-Bold.ttf"
    faces = [
        f'@font-face {{ font-family: body; src: url("{reg}"); }}',
        f'@font-face {{ font-family: mono; src: url("{mono}"); }}',
    ]
    if bold.exists():  # only reference the bold face if the file is actually there
        faces.append(f'@font-face {{ font-family: body; src: url("{bold}"); font-weight: bold; }}')
    faces.append("body, p, li, td, th, h1, h2, h3, h4, blockquote { font-family: body; }")
    faces.append("code, pre { font-family: mono; }")
    return "\n      ".join(faces)


def css() -> str:
    return font_face_css() + """
      @page { size: A4; margin: 1.8cm 1.6cm; }
      body { font-size: 10.5pt; line-height: 1.45; color: #222; }
      h1 { font-size: 19pt; color: #14532d; border-bottom: 2px solid #cbd5e1;
           padding-bottom: 4pt; margin: 0 0 8pt; }
      h2 { font-size: 14pt; color: #1e3a8a; border-bottom: 1px solid #e2e8f0;
           padding-bottom: 2pt; margin: 16pt 0 6pt; }
      h3 { font-size: 11.5pt; color: #1e293b; margin: 12pt 0 4pt; }
      p, li { font-size: 10.5pt; }
      a { color: #1558d6; text-decoration: none; }
      pre { background: #0f141b; color: #e6e8ee; padding: 7pt 9pt; font-size: 7.2pt;
            line-height: 1.3; }
      code { background: #eef2f7; font-size: 9pt; padding: 0 2pt; }
      pre code { background: transparent; color: #e6e8ee; padding: 0; }
      table { border-collapse: collapse; width: 100%; margin: 8pt 0; }
      th, td { border: 1px solid #94a3b8; padding: 3pt 5pt; font-size: 8.8pt;
               text-align: left; vertical-align: top; }
      th { background: #e2e8f0; }
      blockquote { color: #475569; border-left: 3px solid #5b9dff;
                   padding: 2pt 0 2pt 9pt; margin: 8pt 0; }
      hr { border: none; border-top: 1px solid #e2e8f0; margin: 10pt 0; }
    """


def build(md_name: str) -> bool:
    md_path = ROOT / md_name
    raw = clean(md_path.read_text(encoding="utf-8"))
    body = markdown.markdown(
        raw, extensions=["fenced_code", "tables", "sane_lists", "toc"]
    )
    html = (
        "<html><head><meta charset='utf-8'>"
        f"<style>{css()}</style></head><body>{body}</body></html>"
    )
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / (md_path.stem + ".pdf")
    with open(out_path, "wb") as fh:
        result = pisa.CreatePDF(src=html, dest=fh, encoding="utf-8")
    kb = out_path.stat().st_size // 1024
    print(f"  {'ok ' if not result.err else 'ERR'}  {out_path.relative_to(ROOT)}  ({kb} KB)")
    return not result.err


def main() -> int:
    print(f"Building PDFs into {OUT.relative_to(ROOT)}/ ...")
    ok = all(build(s) for s in SOURCES)
    print("Done." if ok else "Completed with errors.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
