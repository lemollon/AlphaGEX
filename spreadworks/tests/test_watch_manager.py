from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base
from backend import intraday_watch as watch
from backend import watch_manager as manager
from backend.models import (
    IntradayAlertDedup,
    IntradaySelectedWatchlist,
    IntradaySetup,
    IntradaySetupOutcome,
    IntradayTradePlan,
)

UTC = timezone.utc
TRADING_DATE = date(2026, 9, 21)
NOW = datetime(2026, 9, 21, 14, 0, tzinfo=UTC)


@pytest.fixture
def manager_store(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            IntradayTradePlan.__table__,
            IntradaySelectedWatchlist.__table__,
            IntradaySetup.__table__,
            IntradayAlertDedup.__table__,
            IntradaySetupOutcome.__table__,
        ],
    )
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(manager, "SessionLocal", Session)
    monkeypatch.setattr(watch, "SessionLocal", Session)
    yield Session
    engine.dispose()


def extracted_aapl() -> dict:
    return {
        "status": "watchable",
        "symbol": "AAPL",
        "strategy": "call_debit_spread",
        "thesis": "bullish",
        "entry": {
            "type": "breakout_hold",
            "breakout_level": 250.5,
            "confirmation_bars": 2,
        },
        "invalidation": {"type": "close_below", "level": 247.0},
        "sessions": ["regular"],
        "expiration_preference": "7-14 DTE",
        "thesis_reason": "Breakout above 250.50",
        "catalyst": "unavailable",
        "profit_taking_framework": "Take partial gains at 50%",
        "main_risks": "Failed breakout",
        "confirmation_defaulted": True,
    }


def manual_aapl_setup() -> dict:
    return manager.build_setup_from_extraction(
        "AAPL bullish call debit spread. Enter after a hold above 250.50. "
        "Invalidation is a completed close below 247.00. Prefer 7-14 DTE.",
        extracted_aapl(),
        TRADING_DATE,
        now=NOW,
    )


def qqq_setup() -> dict:
    return watch.validate_setup(
        {
            "setup_id": "cloud-qqq-long-call",
            "symbol": "QQQ",
            "strategy": "long_call",
            "thesis": "bullish",
            "entry": {
                "type": "breakout_hold",
                "breakout_level": 600,
                "confirmation_bars": 2,
            },
            "invalidation": {"type": "close_below", "level": 595},
            "sessions": ["regular"],
            "setup_state": "WAIT",
        },
        TRADING_DATE,
    )


def spy_setup() -> dict:
    return watch.validate_setup(
        {
            "setup_id": "cloud-spy-long-put",
            "symbol": "SPY",
            "strategy": "long_put",
            "thesis": "bearish",
            "entry": {
                "type": "failed_reclaim",
                "reclaim_level": 650,
                "confirmation_bars": 2,
            },
            "invalidation": {"type": "close_above", "level": 653},
            "sessions": ["regular"],
            "setup_state": "WAIT",
        },
        TRADING_DATE,
    )


def test_build_setup_requires_levels_to_exist_in_original_text():
    setup = manual_aapl_setup()
    assert setup["symbol"] == "AAPL"
    assert setup["entry"]["breakout_level"] == 250.5
    assert setup["source_metadata"]["origin"] == "paste_to_watch"
    assert setup["source_metadata"]["confirmation_defaulted"] is True

    invented = extracted_aapl()
    invented["entry"] = dict(invented["entry"], breakout_level=251.25)
    with pytest.raises(HTTPException, match="not an explicit number"):
        manager.build_setup_from_extraction(
            "AAPL call debit spread above 250.50; close below 247 invalidates.",
            invented,
            TRADING_DATE,
            now=NOW,
        )


def test_build_setup_rejects_missing_explicit_invalidation():
    extracted = extracted_aapl()
    extracted["invalidation"] = {"type": "none"}
    with pytest.raises(HTTPException, match="explicit invalidation"):
        manager.build_setup_from_extraction(
            "AAPL call debit spread above 250.50.",
            extracted,
            TRADING_DATE,
            now=NOW,
        )


def test_session_token_expires_and_rejects_tampering(monkeypatch):
    monkeypatch.setenv("INTRADAY_WATCH_UI_ACCESS_KEY", "operator-key-123")
    monkeypatch.setenv("INTRADAY_WATCH_API_TOKEN", "high-entropy-plan-token")
    token, expires = manager.issue_session_token(NOW)
    assert manager.verify_session_token(token, NOW + timedelta(days=1)) is True
    assert manager.verify_session_token(token + "x", NOW + timedelta(days=1)) is False
    assert manager.verify_session_token(token, expires + timedelta(seconds=1)) is False


def test_manual_watch_merges_without_replacing_morning_plan(manager_store):
    morning = qqq_setup()
    watch.store_morning_plan_atomic(
        TRADING_DATE,
        [],
        [morning],
        {
            "trading_date": TRADING_DATE.isoformat(),
            "symbols": [],
            "setups": [morning],
            "generated_by": "render-cloud-morning-options-v1",
            "run_status": "SUCCESS",
        },
        ingested_at=NOW,
    )

    result = manager.merge_setup_into_plan(manual_aapl_setup(), now=NOW)
    assert result["added"] is True
    assert result["registered_setup_count"] == 2
    assert result["registered_symbol_count"] == 1

    duplicate = manager.merge_setup_into_plan(manual_aapl_setup(), now=NOW)
    assert duplicate["added"] is False

    db = manager_store()
    try:
        plan = json.loads(db.get(IntradayTradePlan, TRADING_DATE).payload_json)
        assert {item["symbol"] for item in plan["setups"]} == {"QQQ", "AAPL"}
        assert plan["symbols"] == ["AAPL"]
        assert plan["parity"]["valid"] is True
        assert db.get(IntradaySetup, morning["setup_id"]).active == 1
    finally:
        db.close()


def test_morning_refresh_preserves_manual_watch(manager_store):
    manager.merge_setup_into_plan(manual_aapl_setup(), now=NOW)
    incoming = spy_setup()
    result = watch.store_morning_plan_atomic(
        TRADING_DATE,
        [],
        [incoming],
        {
            "trading_date": TRADING_DATE.isoformat(),
            "symbols": [],
            "setups": [incoming],
            "generated_by": "render-cloud-morning-options-v1",
            "run_status": "SUCCESS",
        },
        ingested_at=NOW + timedelta(minutes=5),
        preserve_manual=True,
    )
    assert result["preserved_manual_setup_count"] == 1
    assert {item["symbol"] for item in result["stored_setups"]} == {"AAPL", "SPY"}
    assert result["stored_symbols"] == ["AAPL"]

    db = manager_store()
    try:
        assert db.get(IntradaySetup, manual_aapl_setup()["setup_id"]).active == 1
        assert db.get(IntradaySetup, incoming["setup_id"]).active == 1
    finally:
        db.close()


def test_history_retains_alerts_and_winner_loser_label(manager_store):
    setup = manual_aapl_setup()
    manager.merge_setup_into_plan(setup, now=NOW)
    db = manager_store()
    try:
        db.add(IntradayAlertDedup(
            event_key=f"{TRADING_DATE}:{setup['setup_id']}:ENTRY_READY:1",
            trading_date=TRADING_DATE,
            setup_id=setup["setup_id"],
            state="ENTRY_READY",
            transition_at=NOW + timedelta(minutes=10),
            payload_json="{}",
            posted_at=NOW + timedelta(minutes=10),
        ))
        db.commit()
    finally:
        db.close()

    first = manager.label_watch_outcome(
        setup["setup_id"],
        "winner",
        now=NOW + timedelta(hours=2),
    )
    assert first["outcome"] == "WINNER"
    changed = manager.label_watch_outcome(
        setup["setup_id"],
        "LOSER",
        now=NOW + timedelta(hours=3),
    )
    assert changed["outcome"] == "LOSER"

    history = manager.list_watch_history()
    assert history["total"] == 1
    assert history["watches"][0]["outcome"] == "LOSER"
    assert history["watches"][0]["alerts"] == [{
        "state": "ENTRY_READY",
        "transition_at": (NOW + timedelta(minutes=10)).isoformat(),
        "posted": True,
    }]
