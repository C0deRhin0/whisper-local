"""
md_to_pdf.py
------------
Converts a Markdown file (.md) to a styled PDF.
Matches the look of session_summary.pdf with wider side margins.

Dependencies:
    pip install markdown weasyprint
"""

import sys
import os
from pathlib import Path
import markdown
from weasyprint import HTML, CSS


# ─────────────────────────────────────────────
#  STYLESHEET — tweak this to adjust the look
# ─────────────────────────────────────────────
STYLESHEET = """
/* ── Page setup ─────────────────────────── */
@page {
    size: A4;
    margin: 25mm 30mm 25mm 30mm;   /* top right bottom left */

    @bottom-center {
        content: counter(page);
        font-family: 'Latin Modern Roman', serif;
        font-size: 9pt;
        color: #888;
    }
}

/* ── Base typography — Latin Modern Roman (LaTeX default) ── */
body {
    font-family: 'Latin Modern Roman', 'LM Roman 10', serif;
    font-size: 10.5pt;
    line-height: 1.65;
    color: #1a1a1a;
    orphans: 3;
    widows: 3;
}

/* ── Headings ────────────────────────────── */
h1 {
    font-family: 'Latin Modern Roman', serif;
    font-size: 18pt;
    font-weight: bold;
    margin-top: 0;
    margin-bottom: 4pt;
    padding-bottom: 6pt;
    border-bottom: 2px solid #1a1a1a;
    page-break-after: avoid;
}

h2 {
    font-family: 'Latin Modern Roman', serif;
    font-size: 13pt;
    font-weight: bold;
    margin-top: 18pt;
    margin-bottom: 4pt;
    page-break-after: avoid;
}

h3 {
    font-family: 'Latin Modern Roman', serif;
    font-size: 11.5pt;
    font-weight: bold;
    margin-top: 14pt;
    margin-bottom: 3pt;
    page-break-after: avoid;
}

h4 {
    font-family: 'Latin Modern Roman', serif;
    font-size: 10.5pt;
    font-weight: bold;
    font-style: italic;
    margin-top: 10pt;
    margin-bottom: 2pt;
    page-break-after: avoid;
}

/* ── Subtitle / italic line under h1 ─────── */
h1 + h3 {
    font-weight: normal;
    font-style: italic;
    font-size: 10.5pt;
    color: #555;
    margin-top: 2pt;
    border: none;
}

/* ── Paragraphs ──────────────────────────── */
p {
    margin-top: 0;
    margin-bottom: 7pt;
}

/* ── Bullet / ordered lists ──────────────── */
ul, ol {
    margin-top: 3pt;
    margin-bottom: 7pt;
    padding-left: 18pt;
}

li {
    margin-bottom: 3pt;
}

/* Nested lists */
li > ul, li > ol {
    margin-top: 2pt;
    margin-bottom: 2pt;
}

/* ── Horizontal rule (section dividers) ──── */
hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 14pt 0;
}

/* ── Blockquotes (direct quotes) ─────────── */
blockquote {
    border-left: 3px solid #aaa;
    margin: 8pt 0 8pt 12pt;
    padding: 4pt 10pt;
    color: #444;
    font-style: italic;
}

/* ── Bold / strong ───────────────────────── */
strong {
    font-weight: bold;
}

/* ── Inline code — Latin Modern Mono ─────── */
code {
    font-family: 'Latin Modern Mono', 'LM Mono 10', 'Courier New', monospace;
    font-size: 9pt;
    background: #f4f4f4;
    padding: 1pt 3pt;
    border-radius: 2pt;
}

/* ── Page break helpers ───────────────��──── */
h2, h3 {
    break-before: auto;
}
"""


def convert(md_text: str, out_path: Path, base_path: Path = None) -> None:
    """Convert markdown text to a styled PDF."""

    # Convert Markdown → HTML
    # 'extra' enables tables, fenced code blocks, definition lists, etc.
    html_body = markdown.markdown(
        md_text,
        extensions=["extra", "sane_lists"],
    )

    # Wrap in a minimal HTML document
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Meeting Record</title>
</head>
<body>
{html_body}
</body>
</html>"""

    # Determine base_url for relative resources
    base_url = str(base_path.parent) if base_path else str(Path.cwd())

    # Render to PDF via WeasyPrint
    HTML(string=full_html, base_url=base_url).write_pdf(
        str(out_path),
        stylesheets=[CSS(string=STYLESHEET)],
    )

    print(f"PDF saved → {out_path}")


def convert_from_file(md_path: Path, out_path: Path = None) -> Path:
    """Read a .md file and write a styled PDF.
    
    Returns the path to the generated PDF.
    """
    if not md_path.exists():
        raise FileNotFoundError(f"File not found: {md_path}")
    
    if out_path is None:
        out_path = md_path.with_suffix(".pdf")
    
    md_text = md_path.read_text(encoding="utf-8")
    convert(md_text, out_path, base_path=md_path)
    
    return out_path