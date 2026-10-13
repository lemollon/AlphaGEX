"""Portable report images: verify bytes before exposing attachments or embeds."""
from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
import zipfile

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

DELIVERY_VERSION = "2026-10-05.2"

# The report generator writes everything in plain Unicode (emoji section glyphs,
# smart quotes, em dashes, middle dots) but the base14 PDF fonts only cover
# Latin-1. Map the punctuation we can keep readable; anything else (emoji) is
# dropped rather than left to blow up font encoding or render as a tofu box.
_PDF_PUNCT = str.maketrans({
    "—": "--", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", "·": "*",
    "→": "->", "←": "<-",
})


def _pdf_text(value: str) -> str:
    """Make one line of report prose safe for a base14 PDF font, then escape
    and promote **bold** markers to <b> for reportlab's Paragraph markup."""
    value = str(value).translate(_PDF_PUNCT)
    value = "".join(ch for ch in value if ord(ch) < 256)
    value = html.escape(value)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)


def _is_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def _is_table_separator(line: str) -> bool:
    cells = [c.strip() for c in line.strip("|").split("|")]
    return bool(cells) and all(set(c) <= set("-: ") for c in cells)


def markdown_report_pdf(markdown: str) -> bytes:
    """Render the same durable report_markdown already served at
    GET /{report_id}.md into a paginated PDF. One source of narrative text,
    two transports -- this never re-derives section_summary/section_meaning,
    it only lays out the string the markdown endpoint already serves."""
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("PDFH1", parent=styles["Heading1"], fontSize=18, spaceAfter=10)
    h2 = ParagraphStyle("PDFH2", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6)
    h3 = ParagraphStyle("PDFH3", parent=styles["Heading3"], fontSize=11, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("PDFBody", parent=styles["Normal"], fontSize=9.5, leading=13, spaceAfter=6, alignment=TA_LEFT)
    bullet = ParagraphStyle("PDFBullet", parent=body, leftIndent=14, bulletIndent=2)
    cell = ParagraphStyle("PDFCell", parent=body, fontSize=8, leading=10, spaceAfter=0)
    cell_head = ParagraphStyle("PDFCellHead", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)

    story = []
    table_rows: list[list[str]] = []
    doc_width = LETTER[0] - 1.6 * inch

    def flush_table():
        if not table_rows:
            return
        n_cols = len(table_rows[0])
        col_width = doc_width / n_cols
        rendered = [[Paragraph(_pdf_text(cell_text), cell_head if r == 0 else cell) for cell_text in row]
                    for r, row in enumerate(table_rows)]
        table = Table(rendered, colWidths=[col_width] * n_cols, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b2330")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#2a3341")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
        ]))
        story.append(table)
        story.append(Spacer(1, 8))
        table_rows.clear()

    for para in markdown.split("\n\n"):
        line = para.strip()
        if not line:
            continue
        if _is_table_row(line):
            if not _is_table_separator(line):
                table_rows.append([c.strip() for c in line.strip("|").split("|")])
            continue
        flush_table()
        if line.startswith("### "):
            story.append(Paragraph(_pdf_text(line[4:]), h3))
        elif line.startswith("## "):
            story.append(Paragraph(_pdf_text(line[3:]), h2))
        elif line.startswith("# "):
            story.append(Paragraph(_pdf_text(line[2:]), h1))
        elif line.startswith("!["):
            continue  # Charts ship separately via the Chart PDF / Offline ZIP downloads.
        elif line.startswith("- "):
            story.append(Paragraph("&bull;&nbsp;" + _pdf_text(line[2:]), bullet))
        else:
            story.append(Paragraph(_pdf_text(line), body))
    flush_table()

    output = io.BytesIO()
    SimpleDocTemplate(output, pagesize=LETTER,
                       topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                       leftMargin=0.8 * inch, rightMargin=0.8 * inch).build(story)
    return output.getvalue()


def inspect_png(data: bytes, chart_id: str | None = None) -> dict:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Report chart is not PNG")
    digest = hashlib.sha256(data).hexdigest()
    if chart_id is not None and digest[:32] != chart_id:
        raise ValueError("Report chart checksum mismatch")
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        if image.format != "PNG" or image.width < 1000 or image.height < 600:
            raise ValueError("Report chart dimensions/format invalid")
        if image.convert("RGB").getpixel((0, 0)) != (11, 18, 32):
            raise ValueError("Report chart dark palette invalid")
        width, height = image.size
    return dict(sha256=digest, size_bytes=len(data), width=width, height=height,
                content_type="image/png", validated=True)


def chart_id_from_ref(ref: str) -> str:
    match = re.search(r"/charts/([a-f0-9]{32})\.png$", str(ref))
    if not match:
        raise ValueError("Invalid persistent report chart reference")
    return match.group(1)


def portable_pdf(images: list[dict]) -> bytes:
    pages = []
    try:
        for asset in images:
            data = base64.b64decode(asset["png_base64"], validate=True)
            inspect_png(data, asset["chart_id"])
            with Image.open(io.BytesIO(data)) as image:
                pages.append(image.convert("RGB"))
        if not pages:
            raise ValueError("No verified report images")
        output = io.BytesIO()
        pages[0].save(output, format="PDF", save_all=True,
                      append_images=pages[1:], resolution=144.0)
        return output.getvalue()
    finally:
        for page in pages:
            page.close()


def portable_zip(payload: dict, images: list[dict], html: str) -> bytes:
    output = io.BytesIO()
    manifest = dict(delivery_version=DELIVERY_VERSION,
                    report_id=payload["report_id"], generated_at=payload["generated_at"],
                    notice="Immutable observations; generating attachments does not refresh source clocks.",
                    images=[{k:v for k,v in image.items() if k != "png_base64"} for image in images])
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.html", html)
        archive.writestr("report.md", payload["report_markdown"])
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("report.pdf", markdown_report_pdf(payload["report_markdown"]))
        archive.writestr("charts.pdf", portable_pdf(images))
        for asset in images:
            archive.writestr(asset["filename"], base64.b64decode(asset["png_base64"], validate=True))
    return output.getvalue()
