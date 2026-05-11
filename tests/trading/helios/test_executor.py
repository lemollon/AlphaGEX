"""Unit tests for trading/helios/executor.py — pure math + db plumbing."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from trading.helios.executor import close_paper, open_paper
from trading.helios.models import HeliosConfig, SpreadType


def test_open_paper_skips_invalid_debit():
    """long_mid < short_mid produces a non-positive debit; no insert occurs."""
    db = MagicMock()
    cfg = HeliosConfig()  # spread_width=2, risk_per_trade=1000

    result = open_paper(
        db=db,
        spread_type=SpreadType.BULL_CALL,
        long_symbol="SPY260508C00500000",
        short_symbol="SPY260508C00502000",
        long_strike=500.0,
        short_strike=502.0,
        long_mid=2.0,     # debit = 2.0 - 2.5 = -0.5  -> invalid
        short_mid=2.5,
        expiration_date=dt.date(2026, 5, 8),
        config=cfg,
    )

    assert result is None
    db.insert_position.assert_not_called()


def test_close_paper_pnl_math():
    """(mark - debit) * 100 * contracts; uses Decimal/int from DB row."""
    db = MagicMock()
    db.get_position.return_value = {
        "debit": Decimal("1.00"),
        "contracts": 5,
    }

    pnl = close_paper(
        db=db,
        position_id=42,
        mark_to_close=1.20,
        exit_reason="PROFIT_TARGET",
    )

    # (1.20 - 1.00) * 100 * 5 = $100 (subject to float precision)
    assert pnl == pytest.approx(100.0)

    # Verify the bookkeeping calls happened with consistent values.
    db.close_position.assert_called_once()
    args, kwargs = db.close_position.call_args
    assert args == (42,)
    assert kwargs["close_price"] == pytest.approx(1.20)
    assert kwargs["realized_pnl"] == pytest.approx(100.0)
    assert kwargs["exit_reason"] == "PROFIT_TARGET"

    db.bump_realized_pnl.assert_called_once()
    (bump_arg,), _ = db.bump_realized_pnl.call_args
    assert bump_arg == pytest.approx(100.0)
