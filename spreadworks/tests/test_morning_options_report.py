from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend import morning_options_report as report

UTC = timezone.utc


def _evidence(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "price": 101.5,
        "source": "Tradier production consolidated feed",
        "session": "premarket",
        "exchange_timestamp": "2026-09-22T12:00:00+00:00",
        "retrieval_timestamp": "2026-09-22T12:00:05+00:00",
        "quote_age_seconds": 5.0,
        "newest_completed_bar_timestamp": "2026-09-22T11:59:00+00:00",
        "newest_completed_bar_age_seconds": 65.0,
        "session_low": 99.0,
        "session_high": 102.0,
        "usable_for_actionable_levels": True,
    }


def _research() -> dict:
    return {
        "market_regime": "selective",
        "confidence": "medium",
        "spy_bias": "conditional bullish",
        "qqq_bias": "conditional bullish",
        "vix_regime": "unavailable",
        "gamma_regime": "positive",
        "overnight_change": "mixed",
        "flow_and_iv": "unavailable before the options open",
        "best_setup": "AMD call debit spread after confirmation",
        "what_changes_my_mind": ["A completed bar closes below the session low."],
        "recommendations": [{
            "symbol": "AMD", "rank": 1, "status": "actionable",
            "strategy": "call_debit_spread", "thesis": "bullish",
            "thesis_reason": "Current catalyst and relative strength align.",
            "catalyst": "Current company news.",
            "expiration_preference": "7-14 DTE",
            "profit_taking_framework": "Take partial gains near 50%.",
            "main_risks": "Gap and liquidity risk.",
        }],
        "watch_only": [],
        "news_sources": [{"title": "Current source", "url": "https://example.com/current"}],
    }


def test_extract_json_accepts_fenced_object():
    assert report._extract_json('```json\n{"recommendations": []}\n```') == {
        "recommendations": []
    }


def test_normalize_plan_binds_model_choice_to_fresh_tradier_levels():
    now = datetime(2026, 9, 22, 12, 0, 5, tzinfo=UTC)
    symbols, setups, rejected = report._normalize_plan(
        _research(), {"AMD": _evidence("AMD")}, now.date(), now,
    )
    assert symbols == ["AMD"]
    assert rejected == []
    assert setups[0]["entry"] == {
        "type": "opening_range_breakout",
        "range_high": 102.0,
        "confirmation_bars": 2,
    }
    assert setups[0]["invalidation"] == {"type": "close_below", "level": 99.0}
    assert setups[0]["source_metadata"]["underlying_source"].startswith("Tradier")


def test_normalize_plan_rejects_actionable_idea_without_fresh_levels():
    now = datetime(2026, 9, 22, 12, 0, 5, tzinfo=UTC)
    stale = _evidence("AMD")
    stale["usable_for_actionable_levels"] = False
    symbols, setups, rejected = report._normalize_plan(
        _research(), {"AMD": stale}, now.date(), now,
    )
    assert symbols == []
    assert setups == []
    assert rejected == ["AMD: fresh quote/bar evidence unavailable"]


@pytest.mark.asyncio
async def test_cloud_run_persists_one_atomic_plan_and_posts_digest(monkeypatch):
    now = datetime(2026, 9, 22, 12, 0, 5, tzinfo=UTC)
    stored: dict = {}
    delivered: dict = {}

    monkeypatch.setattr(report, "is_market_holiday", lambda _day: False)
    monkeypatch.setattr(report, "_latest_plan_payload", lambda _day: None)
    monkeypatch.setattr(report, "_load_trading_volatility_context", lambda _now: {
        "available": True,
        "source": "TradingVolatility v2 API",
        "top_setups": [{"ticker": "AMD", "rank": 1}],
        "universe_count": 1,
        "retrieval_timestamp": now.isoformat(),
    })

    async def collect(_app, symbols, _now):
        return {symbol: _evidence(symbol) for symbol in symbols}

    async def generate(_now, _tv, _evidence_by_symbol):
        return _research()

    def store(trading_date, symbols, setups, payload, *, ingested_at, preserve_manual):
        assert preserve_manual is True
        stored.update(
            trading_date=trading_date, symbols=symbols, setups=setups,
            payload=payload, ingested_at=ingested_at,
        )
        return {
            "trading_date": trading_date.isoformat(),
            "persisted": True,
            "registered_symbol_count": len(symbols),
            "registered_setup_count": len(setups),
            "registered_total_symbol_count": 4 + len(symbols),
            "plan_hash": "a" * 64,
            "ingested_at": ingested_at.isoformat(),
            "parity": {"valid": True},
            "preserved_manual_setup_count": 0,
            "dropped_incoming_setup_count": 0,
            "stored_symbols": symbols,
            "stored_setups": setups,
        }

    monkeypatch.setattr(report, "_collect_market_evidence", collect)
    monkeypatch.setattr(report, "_generate_research", generate)
    monkeypatch.setattr(report, "store_morning_plan_atomic", store)
    monkeypatch.setattr(report, "_send_discord", lambda payload: payload["run_status"] == "SUCCESS")
    monkeypatch.setattr(
        report, "_update_delivery",
        lambda trading_date, *, posted, attempted_at: delivered.update(
            trading_date=trading_date, posted=posted, attempted_at=attempted_at,
        ),
    )

    result = await report.run_morning_options_report(SimpleNamespace(), now=now)

    assert result["run_status"] == "SUCCESS"
    assert result["symbols"] == ["AMD"]
    assert len(result["setups"]) == 1
    assert stored["payload"]["generated_by"] == report.GENERATOR_ID
    assert delivered["posted"] is True


@pytest.mark.asyncio
async def test_generation_error_publishes_empty_failed_closed_plan(monkeypatch):
    now = datetime(2026, 9, 22, 12, 0, 5, tzinfo=UTC)
    stored: dict = {}

    monkeypatch.setattr(report, "is_market_holiday", lambda _day: False)
    monkeypatch.setattr(report, "_latest_plan_payload", lambda _day: None)
    monkeypatch.setattr(report, "_load_trading_volatility_context", lambda _now: {
        "available": False, "top_setups": [],
    })

    async def collect(_app, symbols, _now):
        return {symbol: _evidence(symbol) for symbol in symbols}

    async def fail(*_args):
        raise RuntimeError("provider unavailable")

    def store(trading_date, symbols, setups, payload, *, ingested_at, preserve_manual):
        assert preserve_manual is True
        stored.update(symbols=symbols, setups=setups, payload=payload)
        return {
            "trading_date": trading_date.isoformat(), "persisted": True,
            "registered_symbol_count": 0, "registered_setup_count": 0,
            "registered_total_symbol_count": 4, "plan_hash": "b" * 64,
            "ingested_at": ingested_at.isoformat(), "parity": {"valid": True},
            "preserved_manual_setup_count": 0,
            "dropped_incoming_setup_count": 0,
            "stored_symbols": symbols,
            "stored_setups": setups,
        }

    monkeypatch.setattr(report, "_collect_market_evidence", collect)
    monkeypatch.setattr(report, "_generate_research", fail)
    monkeypatch.setattr(report, "store_morning_plan_atomic", store)
    monkeypatch.setattr(report, "_send_discord", lambda _payload: False)
    monkeypatch.setattr(report, "_update_delivery", lambda *_args, **_kwargs: None)

    result = await report.run_morning_options_report(SimpleNamespace(), now=now)

    assert result["run_status"] == "FAILED_CLOSED"
    assert stored["symbols"] == []
    assert stored["setups"] == []
    assert "provider unavailable" not in stored["payload"]["reason"]


def test_register_arms_exact_central_time_schedule(monkeypatch):
    calls = []

    class Scheduler:
        def add_job(self, fn, trigger, **kwargs):
            calls.append((fn, trigger, kwargs))

        def get_job(self, _job_id):
            return None

    monkeypatch.setenv("MORNING_OPTIONS_CLOUD_ENABLED", "true")
    monkeypatch.setattr(report, "_latest_plan_payload", lambda _day: {
        "generated_by": report.GENERATOR_ID, "run_status": "SUCCESS",
    })
    assert report.register(Scheduler(), SimpleNamespace()) is True
    cron = next(item for item in calls if item[2].get("id") == report.JOB_ID)
    assert cron[1] == "cron"
    assert cron[2]["hour"] == 7
    assert cron[2]["minute"] == "0,10,20"
    assert cron[2]["day_of_week"] == "mon-fri"
    assert cron[2]["max_instances"] == 1
