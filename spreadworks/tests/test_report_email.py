"""Report email delivery: additive to Discord, never blocks it, never raises.

A disabled/misconfigured sender must take the no-network path (no Resend
call at all), and a Resend rejection or network failure must return False
rather than propagate — the calling delivery job's own lease/posted outcome
must never ride on this module's exceptions.
"""
import base64
import pytest
from backend import report_email as re_mod
from backend.report_contract import REQUIREMENTS


def empty_blocks():
    return {n: {f: {"status": "unavailable", "reason": "No source observation"} for f in fs}
            for n, fs in REQUIREMENTS.items()}


def minimal_payload(report_id="abc123"):
    return {
        "report_id": report_id,
        "generated_at": "2026-10-08T13:00:00+00:00",
        "report_completeness": "INCOMPLETE",
        "report_url": "https://spreadworks-backend.onrender.com/api/spreadworks/reports/abc123/view",
        "markdown_url": "https://spreadworks-backend.onrender.com/api/spreadworks/reports/abc123.md",
        "report_blocks": empty_blocks(),
    }


def clear_env(monkeypatch):
    for key in (re_mod.REPORT_EMAIL_ENABLED_ENV, re_mod.RESEND_API_KEY_ENV,
                re_mod.REPORT_EMAIL_TO_ENV, re_mod.REPORT_EMAIL_FROM_ENV):
        monkeypatch.delenv(key, raising=False)


def test_email_header_shows_central_time_not_bare_utc():
    """Same bare-UTC-timestamp bug as the /view page header, in the email surface — Leron
    reads these on his phone in Texas (Central Time); "2026-10-08T13:00:00+00:00" read as a
    different, unlabeled hour. 13:00 UTC on 2026-10-08 (CDT) = 08:00 AM CT."""
    html = re_mod._email_html(minimal_payload(), "intraday")
    assert "2026-10-08 08:00:00 AM CT" in html
    assert "2026-10-08T13:00:00+00:00" not in html


def test_disabled_by_default_never_touches_the_network(monkeypatch):
    clear_env(monkeypatch)
    def boom(*a, **k): raise AssertionError("must not call Resend when disabled")
    monkeypatch.setattr(re_mod.requests, "post", boom)
    assert re_mod.send_report_email_sync(minimal_payload(), "morning") is False


@pytest.mark.parametrize("missing", ["enabled", "key", "to"])
def test_any_single_missing_setting_disables_sending(monkeypatch, missing):
    clear_env(monkeypatch)
    if missing != "enabled":monkeypatch.setenv(re_mod.REPORT_EMAIL_ENABLED_ENV, "true")
    if missing != "key":monkeypatch.setenv(re_mod.RESEND_API_KEY_ENV, "re_fake")
    if missing != "to":monkeypatch.setenv(re_mod.REPORT_EMAIL_TO_ENV, "leron@example.com")
    assert re_mod.report_email_enabled() is False


def _enable(monkeypatch, to="leron@example.com,second@example.com"):
    monkeypatch.setenv(re_mod.REPORT_EMAIL_ENABLED_ENV, "true")
    monkeypatch.setenv(re_mod.RESEND_API_KEY_ENV, "re_fake-key")
    monkeypatch.setenv(re_mod.REPORT_EMAIL_TO_ENV, to)


def test_successful_send_attaches_the_verified_chart_pdf(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr("backend.full_options_report.get_assets",
                         lambda report_id: {"complete": True, "images": [{"name": "market_map"}]})
    monkeypatch.setattr("backend.report_assets.portable_pdf", lambda images: b"%PDF-fake-bytes")
    calls = []
    class FakeResp:
        status_code = 200
        text = ""
    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append((url, headers, json))
        return FakeResp()
    monkeypatch.setattr(re_mod.requests, "post", fake_post)

    assert re_mod.send_report_email_sync(minimal_payload(), "morning") is True
    assert len(calls) == 1
    url, headers, body = calls[0]
    assert url == "https://api.resend.com/emails"
    assert headers["Authorization"] == "Bearer re_fake-key"
    assert body["to"] == ["leron@example.com", "second@example.com"]
    assert body["attachments"][0]["content"] == base64.b64encode(b"%PDF-fake-bytes").decode()
    assert "Morning Options Report" in body["html"]


def test_incomplete_chart_assets_sends_without_an_attachment(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr("backend.full_options_report.get_assets",
                         lambda report_id: {"complete": False, "failures": {"flow": "no data"}})
    calls = []
    class FakeResp:
        status_code = 200
        text = ""
    monkeypatch.setattr(re_mod.requests, "post", lambda *a, **k: (calls.append(1), FakeResp())[1])

    assert re_mod.send_report_email_sync(minimal_payload(), "intraday") is True
    assert calls == [1]


def test_resend_rejection_returns_false_without_raising(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr("backend.full_options_report.get_assets", lambda report_id: {"complete": False})
    class FakeResp:
        status_code = 422
        text = "unverified domain"
    monkeypatch.setattr(re_mod.requests, "post", lambda *a, **k: FakeResp())
    assert re_mod.send_report_email_sync(minimal_payload(), "morning") is False


def test_network_exception_returns_false_without_raising(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr("backend.full_options_report.get_assets", lambda report_id: {"complete": False})
    def boom(*a, **k): raise ConnectionError("down")
    monkeypatch.setattr(re_mod.requests, "post", boom)
    assert re_mod.send_report_email_sync(minimal_payload(), "morning") is False


def test_missing_report_id_still_sends_without_an_attachment(monkeypatch):
    _enable(monkeypatch)
    payload = minimal_payload();del payload["report_id"]
    class FakeResp:
        status_code = 200
        text = ""
    monkeypatch.setattr(re_mod.requests, "post", lambda *a, **k: FakeResp())
    assert re_mod.send_report_email_sync(payload, "morning") is True
