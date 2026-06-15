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
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import markdown
from xhtml2pdf import pisa

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "pdf"

# (source markdown path relative to repo root, output PDF stem).
# Lessons 1-2 are hand-authored at the root; the planned framework-tour outlines live under
# roadmap/ but publish as LESSON7..LESSON12 so their in-page "pdf/LESSONn.pdf" links resolve.
# The live lessons 3-5 are config-driven under lessons/ and publish as HTML, not root PDFs.
SOURCES = [
    ("CHEATSHEET.md", "CHEATSHEET"),
    ("INSTALL.md", "INSTALL"),
    ("LESSON1.md", "LESSON1"),
    ("LESSON2.md", "LESSON2"),
    ("roadmap/LESSON7-langchain.md", "LESSON7"),
    ("roadmap/LESSON8-langgraph.md", "LESSON8"),
    ("roadmap/LESSON9-ollama.md", "LESSON9"),
    ("roadmap/LESSON10-semantic-kernel.md", "LESSON10"),
    ("roadmap/LESSON11-bedrock.md", "LESSON11"),
    ("roadmap/LESSON12-google-adk.md", "LESSON12"),
]

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
        candidates.append(Path(env).expanduser())  # honour ~ in the override
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
    # Use POSIX-style paths in url() so Windows backslashes aren't treated as CSS escapes.
    faces = [
        f'@font-face {{ font-family: body; src: url("{reg.as_posix()}"); }}',
        f'@font-face {{ font-family: mono; src: url("{mono.as_posix()}"); }}',
    ]
    if bold.exists():  # only reference the bold face if the file is actually there
        faces.append(f'@font-face {{ font-family: body; src: url("{bold.as_posix()}"); font-weight: bold; }}')
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
      pre { background: #f6f8fa; color: #1f2430; border: 1px solid #d0d7de;
            padding: 7pt 9pt; font-size: 7.3pt; line-height: 1.3; }
      code { background: #eef2f7; color: #1f2430; font-size: 9pt; padding: 0 2pt; }
      table { border-collapse: collapse; width: 100%; margin: 8pt 0; }
      th, td { border: 1px solid #94a3b8; padding: 3pt 5pt; font-size: 8.8pt;
               text-align: left; vertical-align: top; }
      th { background: #e2e8f0; }
      blockquote { color: #475569; border-left: 3px solid #5b9dff;
                   padding: 2pt 0 2pt 9pt; margin: 8pt 0; }
      hr { border: none; border-top: 1px solid #e2e8f0; margin: 10pt 0; }
    """


def _resolve_asset(uri: str, rel: str | None = None) -> str:
    """Resolve <img>/url() references for xhtml2pdf to a real file path, confined
    to the repo.

    The PDF sources are trusted (our own Markdown plus the @font-face CSS), so this
    is defence-in-depth: it keeps builds deterministic and offline, and matches the
    "assets live under the repo" intent.

    - ``data:`` URIs (inline, deterministic) pass through.
    - Remote URIs (http/https/ftp) are rejected — the builder never fetches over the
      network; commit a local file under ``docs/`` instead.
    - ``file://`` URIs are normalized to a path; any ``?``/``#`` suffix is dropped.
    - Absolute paths are allowed only inside the repo root or the discovered DejaVu
      font directory (referenced from @font-face); anything else is rejected.
    - Relative paths resolve under ROOT and may not escape it via ``..``.
    """
    if uri.startswith("data:"):
        return uri
    if uri.startswith(("http://", "https://", "ftp://")):
        raise ValueError(f"remote asset not allowed (commit a local file): {uri!r}")
    if uri.startswith("file://"):
        uri = url2pathname(urlparse(uri).path)
    uri = uri.split("?", 1)[0].split("#", 1)[0]
    root = ROOT.resolve()
    p = Path(uri)
    if p.is_absolute():
        resolved = p.resolve()
        allowed = [root]
        font_dir = _font_dir()
        if font_dir is not None:
            allowed.append(font_dir.resolve())
        if any(resolved == base or base in resolved.parents for base in allowed):
            return str(resolved)
        raise ValueError(f"absolute asset path outside repo / font dir: {uri!r}")
    resolved = (root / p).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"asset path escapes repo root: {uri!r}") from exc
    return str(resolved)


def build(spec: tuple[str, str]) -> bool:
    md_name, out_stem = spec
    md_path = ROOT / md_name
    if not md_path.is_file():
        print(f"  ERR  {md_name}  (source not found)")
        return False
    raw = clean(md_path.read_text(encoding="utf-8"))
    body = markdown.markdown(
        raw, extensions=["fenced_code", "tables", "sane_lists", "toc"]
    )
    # xhtml2pdf doesn't reliably support the `pre code` descendant selector, so the
    # inline-code background would bleed onto code blocks. Unwrap <code> inside <pre>.
    body = re.sub(r"<pre><code[^>]*>", "<pre>", body)
    body = re.sub(r"</code></pre>", "</pre>", body)
    html = (
        "<html><head><meta charset='utf-8'>"
        f"<style>{css()}</style></head><body>{body}</body></html>"
    )
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / (out_stem + ".pdf")
    with open(out_path, "wb") as fh:
        result = pisa.CreatePDF(
            src=html, dest=fh, encoding="utf-8", link_callback=_resolve_asset
        )
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
