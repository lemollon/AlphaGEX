from backend.report_assets import markdown_report_pdf, _pdf_text


def test_pdf_text_strips_emoji_and_promotes_bold():
    assert _pdf_text('☀️ **Section summary**: up 2% — watch') \
        == ' <b>Section summary</b>: up 2% -- watch'


def test_pdf_text_escapes_html_special_chars():
    assert _pdf_text('A < B & C > D') == 'A &lt; B &amp; C &gt; D'


def test_markdown_report_pdf_renders_headings_bullets_table_and_skips_images():
    markdown = '\n\n'.join([
        '# ☀️ Morning Options Sentiment',
        '2026-10-13 * morning * COMPLETE',
        '## 30-second scoreboard',
        '| Decision | Current read |',
        '|---|---|',
        '| Regime / trend | RISK-ON |',
        '### Risk On Defensive',
        'Section summary: markets are calm today.',
        '- **verdict**: RISK-ON',
        '![Gamma Chart](https://example.com/gamma.png)',
        '**BOTTOM LINE**',
        'Regime: RISK-ON',
    ])
    pdf = markdown_report_pdf(markdown)
    assert pdf.startswith(b'%PDF-')
    assert len(pdf) > 500
    # No raw emoji byte sequence and no unresolved image markdown leaked into the PDF stream.
    assert '☀'.encode('utf-8') not in pdf
    assert b'![Gamma Chart]' not in pdf


def test_markdown_report_pdf_handles_no_tables_or_images():
    markdown = '\n\n'.join(['# Title', 'Just a plain paragraph.', '- a bullet'])
    pdf = markdown_report_pdf(markdown)
    assert pdf.startswith(b'%PDF-')


def test_markdown_report_pdf_survives_a_table_row_taller_than_a_page():
    """2026-10-16 production 500 on report.pdf and portable.zip: a 5-column setup table whose
    Trigger cell held a multi-KB dump got a fixed 1/5-width column, so one row was ~5000pt tall
    and reportlab raised LayoutError (a row must fit the page frame to be placed)."""
    huge = "catalyst " + "Fed speakers, yields fell sharply and opex pinning risk. " * 120
    markdown = "\n\n".join([
        "# Report",
        "| Horizon | Trigger | Invalidation | Status | Contracts |",
        "|---|---|---|---|---|",
        f"| day strategy | {huge} | close above 729.72 | WAIT | next weekly |",
        "After the table",
    ])
    pdf = markdown_report_pdf(markdown)
    assert pdf.startswith(b"%PDF-")
