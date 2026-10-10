"""Resend email delivery for morning/intraday reports.

Reuses the RESEND_API_KEY already live for IronForge's email verification
funnel (same Resend account, separate sender). Additive to the existing
Discord delivery: never blocks it, never replaces it, and a failed/disabled
send here must not fail the caller's own delivery path. Gated on explicit
opt-in plus real Resend credentials; no secrets are hardcoded. Attaches the
same verified chart PDF the report's own /charts.pdf route serves, built
from the already-persisted, already-checked image evidence — never
re-rendered or fabricated for the email.
"""
from __future__ import annotations
import base64
import html
import logging
import os
from datetime import datetime, timezone

import requests

from .report_policy import display, render_opening_html, ct_str

logger = logging.getLogger(__name__)
UTC = timezone.utc

REPORT_EMAIL_ENABLED_ENV = "REPORT_EMAIL_ENABLED"
RESEND_API_KEY_ENV = "RESEND_API_KEY"
REPORT_EMAIL_TO_ENV = "REPORT_EMAIL_TO"
REPORT_EMAIL_FROM_ENV = "REPORT_EMAIL_FROM"
DEFAULT_FROM = "reports@spreadworks-backend.onrender.com"


def report_email_enabled() -> bool:
    return (os.getenv(REPORT_EMAIL_ENABLED_ENV, "").strip().lower() in ("1", "true", "yes")
            and bool(os.getenv(RESEND_API_KEY_ENV, "").strip())
            and bool(os.getenv(REPORT_EMAIL_TO_ENV, "").strip()))


def _recipients() -> list[str]:
    return [a.strip() for a in os.getenv(REPORT_EMAIL_TO_ENV, "").split(",") if a.strip()]


def _email_html(payload: dict, kind: str) -> str:
    blocks = payload.get("report_blocks") or {}
    opening = render_opening_html(payload) if blocks else "<p>Report blocks unavailable for this send.</p>"
    bottom = "".join(
        "<p>" + html.escape(line) + "</p>"
        for line in (
            "Regime: " + display((blocks.get("risk_on_defensive") or {}).get("verdict")),
            "Opportunity / premium: " + display((blocks.get("premium_selling") or {}).get("suitability")),
            "Next test: recorded entry confirmation plus fresh per-leg BBO; "
            "dated context alone cannot activate a trade.",
        )
    ) if blocks else ""
    links = " &middot; ".join(
        f'<a href="{html.escape(url)}">{html.escape(label)}</a>'
        for label, url in (
            ("Open the full dark report", payload.get("report_url")),
            ("Markdown", payload.get("markdown_url")),
        )
        if url
    )
    return (
        f"<h1>{html.escape(kind.title())} Options Report</h1>"
        f'<p>{html.escape(ct_str(payload.get("generated_at")))} | '
        f'{html.escape(str(payload.get("report_completeness") or "UNKNOWN"))}</p>'
        f"<p>{links}</p>" + opening + bottom
    )


def _chart_pdf_bytes(report_id: str) -> bytes | None:
    try:
        from .full_options_report import get_assets
        from .report_assets import portable_pdf
        assets = get_assets(report_id)
        if not assets.get("complete"):
            logger.warning("[ReportEmail] chart assets incomplete for %s: %s", report_id, assets.get("failures"))
            return None
        return portable_pdf(assets["images"])
    except Exception as exc:  # noqa: BLE001 — a missing/odd chart attachment must not block the email
        logger.warning("[ReportEmail] chart PDF build failed for %s: %s", report_id, type(exc).__name__)
        return None


def send_report_email_sync(payload: dict, kind: str) -> bool:
    """Send one report email via Resend. Returns False (never raises) on any failure or when disabled."""
    if not report_email_enabled():
        logger.info("[ReportEmail] disabled (%s/%s/%s not fully set) — skipping",
                    REPORT_EMAIL_ENABLED_ENV, RESEND_API_KEY_ENV, REPORT_EMAIL_TO_ENV)
        return False
    to_addrs = _recipients()
    if not to_addrs:
        logger.warning("[ReportEmail] %s is empty — skipping", REPORT_EMAIL_TO_ENV)
        return False
    report_id = payload.get("report_id")
    body = {
        "from": os.getenv(REPORT_EMAIL_FROM_ENV, "").strip() or DEFAULT_FROM,
        "to": to_addrs,
        "subject": f"{kind.title()} Options Report — "
                   f"{str(payload.get('generated_at') or datetime.now(UTC).isoformat())[:10]} — "
                   f"{payload.get('report_completeness') or 'UNKNOWN'}",
        "html": _email_html(payload, kind),
    }
    pdf_bytes = _chart_pdf_bytes(report_id) if report_id else None
    if pdf_bytes:
        body["attachments"] = [{
            "filename": f"options-report-{report_id}-charts.pdf",
            "content": base64.b64encode(pdf_bytes).decode(),
        }]
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {os.getenv(RESEND_API_KEY_ENV, '').strip()}",
                     "Content-Type": "application/json"},
            json=body, timeout=20,
        )
        if resp.status_code not in (200, 201, 202):
            logger.warning("[ReportEmail] Resend rejected send: %s %s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — a failed send must not take down the caller's delivery job
        logger.warning("[ReportEmail] send failed: %s", type(exc).__name__)
        return False
