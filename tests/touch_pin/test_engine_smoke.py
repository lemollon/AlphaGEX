"""Smoke test for backtest.touch_pin.engine.run_one_day."""
import datetime as dt
import os
import pytest

from backtest.touch_pin.engine import run_one_day, TradeRow


@pytest.mark.db
def test_run_one_day_smoke():
    db_url_main = os.environ["DATABASE_URL"]
    db_url_orat = os.environ.get("ORAT_DATABASE_URL", db_url_main)
    rows = run_one_day(
        db_url_main=db_url_main,
        db_url_orat=db_url_orat,
        trade_date=dt.date(2025, 6, 2),
        target_minute=5,
        exit_minute=385,
        slippage_ticks_per_leg=1,
        commission_per_leg=1.30,
    )
    assert isinstance(rows, list)
    assert len(rows) <= 2
    for r in rows:
        assert isinstance(r, TradeRow)
        assert r.trade_date == dt.date(2025, 6, 2)
        assert r.side in {"PIN-CALL", "PIN-PUT"}
        # Sanity: pnl_net should be in a sensible per-contract range
        assert -200.0 <= r.pnl_net <= 200.0
