"""Discord delivery must be TRUE, not merely attempted.

Every alert claimed its slot before posting and discarded `_send()`'s result,
so a broken webhook was indistinguishable from a working one: log row written,
page says fired, nothing delivered — and the slot was taken, so the alert
could never fire again that day. One dropped packet cost the whole day.
"""
from datetime import date

import backend.risk_alerts as ra


def test_a_failed_send_releases_the_slot_so_it_can_retry(monkeypatch):
    claimed, released = [], []
    monkeypatch.setattr("backend._claim_post_slot_db", lambda k, d: (claimed.append(k), True)[1])
    monkeypatch.setattr("backend._release_post_slot_db", lambda k, d: released.append(k))
    monkeypatch.setattr(ra, "_send", lambda *a, **k: False)      # webhook down

    ok = ra._post("risk_test", date(2026, 8, 20), {"title": "x"})
    assert ok is False
    assert claimed == ["risk_test"], "it must still claim first (dedupe across replicas)"
    assert released == ["risk_test"], "a failed send MUST hand the slot back"


def test_a_successful_send_keeps_the_slot(monkeypatch):
    released = []
    monkeypatch.setattr("backend._claim_post_slot_db", lambda k, d: True)
    monkeypatch.setattr("backend._release_post_slot_db", lambda k, d: released.append(k))
    monkeypatch.setattr(ra, "_send", lambda *a, **k: True)

    assert ra._post("risk_test", date(2026, 8, 20), {"title": "x"}) is True
    assert released == [], "a delivered alert must not be re-sent later"


def test_losing_the_race_does_not_send_at_all(monkeypatch):
    sent = []
    monkeypatch.setattr("backend._claim_post_slot_db", lambda k, d: False)
    monkeypatch.setattr("backend._release_post_slot_db", lambda k, d: None)
    monkeypatch.setattr(ra, "_send", lambda *a, **k: sent.append(1) or True)

    assert ra._post("risk_test", date(2026, 8, 20), {"title": "x"}) is False
    assert sent == [], "another replica owns today's slot; do not double-post"


def test_delivery_outcome_is_recorded_either_way(monkeypatch):
    monkeypatch.setattr("backend._claim_post_slot_db", lambda k, d: True)
    monkeypatch.setattr("backend._release_post_slot_db", lambda k, d: None)

    monkeypatch.setattr(ra, "_send", lambda *a, **k: True)
    ra._post("risk_ok", date(2026, 8, 20), {"title": "x"})
    assert ra._LAST_DELIVERY["ok"] is True and ra._LAST_DELIVERY["key"] == "risk_ok"

    monkeypatch.setattr(ra, "_send", lambda *a, **k: False)
    ra._post("risk_bad", date(2026, 8, 20), {"title": "x"})
    assert ra._LAST_DELIVERY["ok"] is False and ra._LAST_DELIVERY["key"] == "risk_bad"


def test_delivery_endpoint_never_leaks_a_webhook_url(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app
    monkeypatch.setenv("RISK_ADVISOR_DISCORD_WEBHOOK",
                       "https://discord.com/api/webhooks/SECRET/TOKEN")
    body = TestClient(app).get("/api/spreadworks/risk-advisor/delivery").text
    assert "SECRET" not in body and "TOKEN" not in body
    assert '"can_alert":true' in body.replace(" ", "")


# ── THE ALERT THAT DID NOT EXIST ────────────────────────────────────────────
# Every other alert fires on something HAPPENING; none fired on the machinery
# STOPPING. A dead watcher and a calm day both produce silence, and the
# 2026-08-17 lesson was precisely that silence is not evidence.

OPEN, CLOSE = 10 * 60 + 10, 14 * 60          # the confirmation window, CT


def test_a_stalled_tape_inside_the_window_fires():
    v = ra._watchdog_verdict(12 * 60 + 5, 10 * 60 + 30, OPEN, CLOSE)
    assert v and "95 min" in v


def test_no_reading_at_all_fires():
    assert ra._watchdog_verdict(12 * 60, None, OPEN, CLOSE) == "no reading at all today"


def test_one_skipped_poll_is_a_blip_not_a_page():
    """Polls are every 10 min. Firing on a single miss would page on ordinary
    jitter, and an alert that cries wolf is one you stop reading."""
    assert ra._watchdog_verdict(12 * 60, 11 * 60 + 40, OPEN, CLOSE) is None   # 20 min


def test_it_stays_quiet_before_the_window_has_had_time_to_produce_anything():
    """Otherwise it pages every single morning at 10:10 before the first poll."""
    assert ra._watchdog_verdict(OPEN + 5, None, OPEN, CLOSE) is None


def test_a_closed_window_is_not_a_fault():
    """After 14:00 the watchers are SUPPOSED to be quiet. A closed window must
    never read as a broken one."""
    assert ra._watchdog_verdict(14 * 60 + 45, 13 * 60 + 50, OPEN, CLOSE) is None


def test_post_does_not_NameError():
    """🚨 THE REGRESSION THAT KILLED EVERY ALERT ON 2026-08-20.

    `_post` calls `_claim_post_slot_db` / `_release_post_slot_db`, which live in
    backend/__init__ — not in this module. backend/__init__ imports this module,
    so they cannot be imported at top level without a cycle; they MUST be
    imported inside the function. #2863 shipped `_post` without that import, so
    every call raised NameError, every job swallowed it into a log warning, and
    every Discord alert silently stopped. Nothing on any page showed it.

    This calls the real function with only the network stubbed, so the import
    itself is exercised.
    """
    monkey = []
    real_send = ra._send
    ra._send = lambda *a, **k: monkey.append(1) or True
    try:
        ra._post("risk_nameerror_probe", date(2026, 8, 20), {"title": "probe"})
    finally:
        ra._send = real_send
    assert monkey == [1], "the send never ran — _post raised before reaching it"
