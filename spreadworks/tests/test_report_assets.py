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
