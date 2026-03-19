"""
Shared pytest fixtures for IronForge tests.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from zoneinfo import ZoneInfo

# Ensure ironforge package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

CENTRAL_TZ = ZoneInfo("America/Chicago")


@pytest.fixture
def mock_config():
    """Return a BotConfig with known values."""
    from trading.models import BotConfig
    return BotConfig(
        bot_name="FLAME",
        min_dte=2,
        dte_mode="2DTE",
        starting_capital=5000.0,
        sd_multiplier=1.2,
        spread_width=5.0,
        min_credit=0.05,
        profit_target_pct=30.0,
        stop_loss_pct=200.0,
        vix_skip=32.0,
        max_contracts=10,
        buying_power_usage_pct=0.85,
        min_win_probability=0.42,
    )


@pytest.fixture
def mock_db():
    """Return a mocked TradingDatabase."""
    db = MagicMock()
    db.bot_name = "FLAME"
    db.dte_mode = "2DTE"
    db.get_bot_active.return_value = True
    db.set_bot_active.return_value = True
    db.save_config.return_value = True
    db.load_config.return_value = None
    db.get_paper_account.return_value = MagicMock(
        starting_balance=5000.0,
        balance=5000.0,
        buying_power=5000.0,
        collateral_in_use=0.0,
        total_trades=0,
        cumulative_pnl=0.0,
        high_water_mark=5000.0,
        max_drawdown=0.0,
        is_active=True,
    )
    db.get_position_count.return_value = 0
    db.save_position.return_value = True
    db.close_position.return_value = True
    db.update_paper_balance.return_value = True
    db.log_pdt_entry.return_value = True
    db.update_pdt_close.return_value = True
    db.save_equity_snapshot.return_value = True
    db.update_daily_performance.return_value = True
    db.log.return_value = None
    return db


@pytest.fixture
def mock_position():
    """Return an IronCondorPosition with known values."""
    from trading.models import IronCondorPosition, PositionStatus
    return IronCondorPosition(
        position_id="FLAME-20260225-ABC123",
        ticker="SPY",
        expiration="2026-02-27",
        put_short_strike=580.0,
        put_long_strike=575.0,
        put_credit=0.25,
        call_short_strike=595.0,
        call_long_strike=600.0,
        call_credit=0.20,
        contracts=2,
        spread_width=5.0,
        total_credit=0.45,
        max_loss=910.0,
        max_profit=90.0,
        underlying_at_entry=587.50,
        vix_at_entry=18.0,
        expected_move=2.34,
        status=PositionStatus.OPEN,
        open_time=datetime(2026, 2, 25, 10, 0, 0, tzinfo=CENTRAL_TZ),
        collateral_required=910.0,
    )


@pytest.fixture
def mock_signal():
    """Return an IronCondorSignal with known values."""
    from trading.models import IronCondorSignal
    return IronCondorSignal(
        spot_price=587.50,
        vix=18.0,
        expected_move=2.34,
        put_short=580.0,
        put_long=575.0,
        call_short=595.0,
        call_long=600.0,
        expiration="2026-02-27",
        estimated_put_credit=0.25,
        estimated_call_credit=0.20,
        total_credit=0.45,
        max_loss=455.0,
        max_profit=45.0,
        confidence=0.70,
        oracle_win_probability=0.72,
        oracle_confidence=0.70,
        oracle_advice="TRADE_FULL",
        is_valid=True,
        reasoning="Test signal",
        source="TRADIER_LIVE",
    )
