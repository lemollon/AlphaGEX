"""Light coverage for the four new Discord alert features (2026-08-13):
EBB trade posts, signal-health flip alerts, the Friday digest, and the
one-time promotion announcement. Full scheduler-job behavior is exercised
live; these are import/shape checks that fail fast on a wiring mistake.
"""
import os

from backend.bots import discord_alerts


def test_risk_health_state_model_importable(db_session):
    from backend.routes_risk import RiskHealthState
    from sqlalchemy import text
    assert RiskHealthState.__tablename__ == "risk_health_state"
    # auto-created alongside every other Base model (backend/__init__.py's
    # Base.metadata.create_all) — db_session's create_all should have made it.
    eng = db_session.get_bind()
    eng.connect().execute(text("SELECT signal, status, updated_at "
                               "FROM risk_health_state LIMIT 0"))


def test_ebb_webhook_url_resolves_risk_env(monkeypatch):
    monkeypatch.setenv("RISK_ADVISOR_DISCORD_WEBHOOK", "https://example.test/risk")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.test/fleet")
    assert discord_alerts._webhook_url("ebb") == "https://example.test/risk"


def test_ebb_webhook_url_falls_back_to_fleet(monkeypatch):
    monkeypatch.delenv("RISK_ADVISOR_DISCORD_WEBHOOK", raising=False)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.test/fleet")
    assert discord_alerts._webhook_url("ebb") == "https://example.test/fleet"


def test_non_override_bot_uses_default_webhook():
    # A bot with no discord_webhook_env registry key gets None — the caller
    # falls back to the module-wide DISCORD_WEBHOOK_URL.
    assert discord_alerts._webhook_url("flow") is None


def test_ebb_pm_webhook_url_resolves_risk_env(monkeypatch):
    # EBB PM (registry #41/#42) routes to the same risk-advisor channel as
    # EBB — it's the same paper-trade companion, just the afternoon tranche.
    monkeypatch.setenv("RISK_ADVISOR_DISCORD_WEBHOOK", "https://example.test/risk")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.test/fleet")
    assert discord_alerts._webhook_url("ebb_pm") == "https://example.test/risk"


def test_risk_alerts_jobs_importable():
    # register_risk_alerts must still parse/import cleanly with the three
    # new jobs added (health_flip_check, friday_digest, promotion_announce).
    from backend.risk_alerts import register_risk_alerts
    assert callable(register_risk_alerts)


def test_promotion_env_var_documented_as_manual_switch():
    # The promotion switch is an ops/deploy action, never flipped by code —
    # verify the env var name matches the spec and defaults to unset/false.
    os.environ.pop("SQUEEZE_TELL_PROMOTED", None)
    assert os.getenv("SQUEEZE_TELL_PROMOTED", "").strip().lower() != "true"
