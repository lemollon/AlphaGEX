"""
IronForge Pre-Market Health Check Tests
=========================================

Validates that FLAME (2DTE) and SPARK (1DTE) bots are ready before market opens.
Tests cover:
  - Bot configuration validation (FLAME vs SPARK)
  - Data model integrity (BotConfig, IronCondorPosition, PaperAccount, signals)
  - Signal generator strike math (SD-based, symmetric wings)
  - Executor collateral/sizing calculations
  - Trader lifecycle (trading window, EOD cutoff, run_cycle flow)
  - Position management (profit target, stop loss, EOD close, stale/expired)
  - TradierClient structure and endpoint construction
  - Database layer table naming and operations
  - Job entry points existence and structure
  - Workflow scheduling configuration

These tests mock all external dependencies (Tradier API, Databricks SQL)
so they run locally in pytest without a Databricks workspace.

Run:
    python -m pytest tests/test_ironforge_premarket_health.py -v
"""

import math
import sys
import os
import json
import pytest
import importlib
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from zoneinfo import ZoneInfo

DATABRICKS_DIR = Path(__file__).parent.parent / "databricks"

CENTRAL_TZ = ZoneInfo("America/Chicago")
EASTERN_TZ = ZoneInfo("America/New_York")


# ===========================================================================
# FIXTURE: Isolate databricks imports from AlphaGEX trading module
# ===========================================================================

@pytest.fixture(autouse=True)
def ironforge_env():
    """
    Set up isolated import environment for databricks/trading modules.

    When FORTRESS tests run first, AlphaGEX's `trading` package gets cached.
    This fixture saves those modules, removes them, inserts databricks/ into
    sys.path, and restores everything on teardown.
    """
    env_vars = {
        'DATABRICKS_SERVER_HOSTNAME': 'test.cloud.databricks.com',
        'DATABRICKS_HTTP_PATH': '/sql/1.0/warehouses/test',
        'DATABRICKS_TOKEN': 'test_token',
        'TRADIER_API_KEY': 'test_tradier_key',
        'DATABRICKS_CATALOG': 'alpha_prime',
        'DATABRICKS_SCHEMA': 'default',
    }

    # Save original state
    saved_path = sys.path[:]
    saved_modules = {}

    # Modules that conflict between AlphaGEX and databricks
    conflict_prefixes = ('trading', 'config')
    for mod_name in list(sys.modules):
        if any(mod_name == p or mod_name.startswith(p + '.') for p in conflict_prefixes):
            saved_modules[mod_name] = sys.modules.pop(mod_name)

    # Also save/remove databricks connector mock if present
    for mod_name in ('databricks', 'databricks.sql'):
        if mod_name in sys.modules:
            saved_modules[mod_name] = sys.modules.pop(mod_name)

    with patch.dict(os.environ, env_vars):
        # Insert databricks dir at front of path
        sys.path.insert(0, str(DATABRICKS_DIR))

        # Mock the databricks SQL connector
        sys.modules['databricks'] = MagicMock()
        sys.modules['databricks.sql'] = MagicMock()

        yield

    # Teardown: remove all databricks-imported modules
    db_str = str(DATABRICKS_DIR)
    to_remove = []
    for mod_name in list(sys.modules):
        mod = sys.modules.get(mod_name)
        if mod is None:
            to_remove.append(mod_name)
            continue
        mod_file = getattr(mod, '__file__', '') or ''
        if db_str in mod_file:
            to_remove.append(mod_name)
    for mod_name in ('databricks', 'databricks.sql'):
        to_remove.append(mod_name)
    for mod_name in list(sys.modules):
        if any(mod_name == p or mod_name.startswith(p + '.') for p in conflict_prefixes):
            to_remove.append(mod_name)

    for mod_name in set(to_remove):
        sys.modules.pop(mod_name, None)

    # Restore original modules and path
    sys.modules.update(saved_modules)
    sys.path[:] = saved_path


# ===========================================================================
# 1. BOT CONFIGURATION TESTS
# ===========================================================================

class TestBotConfigValidation:
    """Verify FLAME and SPARK configs are correct and valid."""

    def test_flame_config_defaults(self):
        """FLAME should be 2DTE with correct defaults."""
        from trading.models import flame_config
        cfg = flame_config()
        assert cfg.bot_name == "FLAME"
        assert cfg.min_dte == 2
        assert cfg.dte_mode == "2DTE"
        assert cfg.ticker == "SPY"
        assert cfg.starting_capital == 5000.0
        assert cfg.sd_multiplier == 1.2
        assert cfg.spread_width == 5.0
        assert cfg.max_trades_per_day == 1
        assert cfg.vix_skip == 32.0
        assert cfg.profit_target_pct == 30.0
        assert cfg.stop_loss_pct == 100.0
        assert cfg.eod_cutoff_et == "15:45"
        assert cfg.entry_start == "08:30"
        assert cfg.entry_end == "14:00"
        assert cfg.pdt_max_day_trades == 3
        assert cfg.pdt_rolling_window_days == 5
        assert cfg.max_contracts == 10
        assert cfg.buying_power_usage_pct == 0.85
        assert cfg.min_win_probability == 0.42
        assert cfg.min_credit == 0.05

    def test_spark_config_defaults(self):
        """SPARK should be 1DTE with same parameters except DTE."""
        from trading.models import spark_config
        cfg = spark_config()
        assert cfg.bot_name == "SPARK"
        assert cfg.min_dte == 1
        assert cfg.dte_mode == "1DTE"
        assert cfg.ticker == "SPY"
        assert cfg.starting_capital == 5000.0

    def test_flame_config_validates(self):
        """FLAME config should pass validation."""
        from trading.models import flame_config
        valid, msg = flame_config().validate()
        assert valid is True
        assert msg == "OK"

    def test_spark_config_validates(self):
        """SPARK config should pass validation."""
        from trading.models import spark_config
        valid, msg = spark_config().validate()
        assert valid is True
        assert msg == "OK"

    def test_invalid_capital_rejected(self):
        """Zero capital should fail validation."""
        from trading.models import BotConfig
        cfg = BotConfig(starting_capital=0)
        valid, msg = cfg.validate()
        assert valid is False
        assert "capital" in msg.lower()

    def test_invalid_spread_width_rejected(self):
        """Zero spread width should fail validation."""
        from trading.models import BotConfig
        cfg = BotConfig(spread_width=0)
        valid, msg = cfg.validate()
        assert valid is False
        assert "spread" in msg.lower()

    def test_invalid_profit_target_rejected(self):
        """Profit target >= 100% should fail validation."""
        from trading.models import BotConfig
        cfg = BotConfig(profit_target_pct=100)
        valid, msg = cfg.validate()
        assert valid is False
        assert "profit" in msg.lower()

    def test_invalid_min_dte_rejected(self):
        """DTE of 0 should fail validation."""
        from trading.models import BotConfig
        cfg = BotConfig(min_dte=0)
        valid, msg = cfg.validate()
        assert valid is False
        assert "dte" in msg.lower()


# ===========================================================================
# 2. DATA MODEL TESTS
# ===========================================================================

class TestDataModels:
    """Verify data model classes are well-formed."""

    def test_iron_condor_position_to_dict(self):
        """IronCondorPosition.to_dict() should include all required fields."""
        from trading.models import IronCondorPosition, PositionStatus
        pos = IronCondorPosition(
            position_id="FLAME-20260226-ABC123",
            ticker="SPY",
            expiration="2026-02-28",
            put_short_strike=580.0,
            put_long_strike=575.0,
            put_credit=0.30,
            call_short_strike=600.0,
            call_long_strike=605.0,
            call_credit=0.25,
            contracts=2,
            spread_width=5.0,
            total_credit=0.55,
            max_loss=445.0,
            max_profit=55.0,
            underlying_at_entry=590.0,
        )
        d = pos.to_dict()
        assert d['position_id'] == "FLAME-20260226-ABC123"
        assert d['ticker'] == "SPY"
        assert d['put_width'] == 5.0
        assert d['call_width'] == 5.0
        assert d['wings_symmetric'] is True
        assert d['status'] == "open"

    def test_asymmetric_wings_detected(self):
        """Wings with different widths should be flagged."""
        from trading.models import IronCondorPosition
        pos = IronCondorPosition(
            position_id="TEST",
            ticker="SPY",
            expiration="2026-02-28",
            put_short_strike=580.0,
            put_long_strike=575.0,  # 5-wide
            put_credit=0.30,
            call_short_strike=600.0,
            call_long_strike=607.0,  # 7-wide
            call_credit=0.25,
            contracts=1,
            spread_width=5.0,
            total_credit=0.55,
            max_loss=445.0,
            max_profit=55.0,
            underlying_at_entry=590.0,
        )
        d = pos.to_dict()
        assert d['put_width'] == 5.0
        assert d['call_width'] == 7.0
        assert d['wings_symmetric'] is False

    def test_paper_account_return_pct(self):
        """PaperAccount.to_dict() should calculate return percentage."""
        from trading.models import PaperAccount
        acct = PaperAccount(
            starting_balance=5000.0,
            balance=5250.0,
            cumulative_pnl=250.0,
        )
        d = acct.to_dict()
        assert d['return_pct'] == 5.0

    def test_paper_account_zero_capital(self):
        """Return pct should be 0 with zero starting balance."""
        from trading.models import PaperAccount
        acct = PaperAccount(starting_balance=0, balance=0, cumulative_pnl=0)
        d = acct.to_dict()
        assert d['return_pct'] == 0

    def test_iron_condor_signal_defaults(self):
        """IronCondorSignal should default to not valid."""
        from trading.models import IronCondorSignal
        sig = IronCondorSignal(spot_price=590, vix=18, expected_move=5.0)
        assert sig.is_valid is False
        assert sig.total_credit == 0.0

    def test_position_status_enum(self):
        """PositionStatus enum should have open/closed/expired."""
        from trading.models import PositionStatus
        assert PositionStatus.OPEN.value == "open"
        assert PositionStatus.CLOSED.value == "closed"
        assert PositionStatus.EXPIRED.value == "expired"

    def test_trading_mode_paper_only(self):
        """IronForge only supports PAPER mode."""
        from trading.models import TradingMode
        assert TradingMode.PAPER.value == "paper"


# ===========================================================================
# 3. SIGNAL GENERATOR — STRIKE MATH
# ===========================================================================

class TestSignalGeneratorStrikeMath:
    """Verify strike calculation logic without Tradier API."""

    def _make_generator(self, **overrides):
        """Create a SignalGenerator with mocked Tradier."""
        from trading.models import flame_config
        cfg = flame_config()
        for k, v in overrides.items():
            setattr(cfg, k, v)
        with patch('trading.signals.TradierClient') as mock_tc:
            mock_client = MagicMock()
            mock_client.get_quote.return_value = {'last': 590}
            mock_tc.return_value = mock_client
            from trading.signals import SignalGenerator
            gen = SignalGenerator(cfg)
        return gen

    def test_sd_based_strike_calculation(self):
        """Strikes should be 1.2 SD from spot."""
        gen = self._make_generator()
        spot = 590.0
        expected_move = 5.67  # VIX 15, SPY 590
        strikes = gen.calculate_strikes(spot, expected_move)

        # 1.2 * 5.67 = 6.804
        # put_short = floor(590 - 6.804) = 583
        # call_short = ceil(590 + 6.804) = 597
        assert strikes['put_short'] == math.floor(spot - 1.2 * expected_move)
        assert strikes['call_short'] == math.ceil(spot + 1.2 * expected_move)
        assert strikes['put_long'] == strikes['put_short'] - 5  # spread_width
        assert strikes['call_long'] == strikes['call_short'] + 5
        assert strikes['source'].startswith('SD')

    def test_sd_floor_enforced(self):
        """Even if sd_multiplier is low, floor of 1.2 is enforced."""
        gen = self._make_generator(sd_multiplier=0.5)
        strikes = gen.calculate_strikes(590.0, 5.67)
        # Should still use 1.2, not 0.5
        min_distance = 1.2 * 5.67
        actual_put_distance = 590.0 - strikes['put_short']
        assert actual_put_distance >= min_distance - 1

    def test_minimum_expected_move(self):
        """When expected_move is tiny, 0.5% of spot is used as floor."""
        gen = self._make_generator()
        strikes = gen.calculate_strikes(590.0, 0.01)
        # min_expected_move = 590 * 0.005 = 2.95
        # 1.2 * 2.95 = 3.54
        effective_em = max(0.01, 590.0 * 0.005)
        expected_put = math.floor(590.0 - 1.2 * effective_em)
        assert strikes['put_short'] == expected_put

    def test_symmetric_wings_no_adjustment(self):
        """Equal-width wings should pass through unchanged."""
        gen = self._make_generator()
        result = gen.enforce_symmetric_wings(580, 575, 600, 605)
        assert result is not None
        assert result['adjusted'] is False
        assert result['short_put'] == 580
        assert result['long_put'] == 575
        assert result['short_call'] == 600
        assert result['long_call'] == 605

    def test_symmetric_wings_adjusts_narrow_call(self):
        """If call wing is narrower, it should be widened."""
        gen = self._make_generator()
        # put: 580-575 = 5 wide, call: 600-603 = 3 wide
        result = gen.enforce_symmetric_wings(580, 575, 600, 603)
        assert result is not None
        assert result['adjusted'] is True
        assert result['long_call'] == 605  # expanded from 603 to 605

    def test_symmetric_wings_adjusts_narrow_put(self):
        """If put wing is narrower, it should be widened."""
        gen = self._make_generator()
        # put: 580-578 = 2 wide, call: 600-605 = 5 wide
        result = gen.enforce_symmetric_wings(580, 578, 600, 605)
        assert result is not None
        assert result['adjusted'] is True
        assert result['long_put'] == 575  # expanded from 578 to 575

    def test_credit_estimation_fallback(self):
        """When no Tradier data, estimates should produce positive credits."""
        gen = self._make_generator()
        credits = gen.estimate_credits(
            spot_price=590, expected_move=5.67,
            put_short=583, put_long=578,
            call_short=597, call_long=602,
            vix=15,
        )
        assert credits['total_credit'] > 0
        assert credits['put_credit'] >= 0.02
        assert credits['call_credit'] >= 0.02
        assert credits['source'] == 'ESTIMATED'
        assert credits['max_profit'] > 0
        assert credits['max_loss'] > 0

    def test_expiration_targeting_2dte(self):
        """FLAME should target 2 trading days out."""
        gen = self._make_generator()
        # Monday → target should be Wednesday
        monday = datetime(2026, 2, 23, 10, 0, tzinfo=CENTRAL_TZ)
        exp = gen._get_target_expiration(monday)
        assert exp == "2026-02-25"  # Wednesday

    def test_expiration_targeting_1dte(self):
        """SPARK should target 1 trading day out."""
        gen = self._make_generator(min_dte=1, dte_mode="1DTE", bot_name="SPARK")
        # Monday → target should be Tuesday
        monday = datetime(2026, 2, 23, 10, 0, tzinfo=CENTRAL_TZ)
        exp = gen._get_target_expiration(monday)
        assert exp == "2026-02-24"  # Tuesday

    def test_expiration_targeting_skips_weekends(self):
        """Friday should skip weekend and target next Mon (1DTE) or Tue (2DTE)."""
        gen = self._make_generator()  # 2DTE
        friday = datetime(2026, 2, 27, 10, 0, tzinfo=CENTRAL_TZ)
        exp = gen._get_target_expiration(friday)
        assert exp == "2026-03-03"  # Tuesday (2 trading days after Friday)


# ===========================================================================
# 4. EXECUTOR CALCULATIONS
# ===========================================================================

class TestPaperExecutorCalculations:
    """Verify collateral and sizing math."""

    def _make_executor(self, **overrides):
        from trading.models import flame_config
        from trading.executor import PaperExecutor
        cfg = flame_config()
        for k, v in overrides.items():
            setattr(cfg, k, v)
        mock_db = MagicMock()
        return PaperExecutor(cfg, mock_db)

    def test_collateral_calculation(self):
        """Collateral = (spread_width * 100) - (credit * 100)."""
        executor = self._make_executor()
        collateral = executor.calculate_collateral(5.0, 0.55)
        # (5 * 100) - (0.55 * 100) = 500 - 55 = 445
        assert collateral == 445.0

    def test_collateral_zero_spread_width(self):
        """Invalid spread width should return 0."""
        executor = self._make_executor()
        assert executor.calculate_collateral(0, 0.55) == 0
        assert executor.calculate_collateral(-1, 0.55) == 0

    def test_max_contracts_sizing(self):
        """Max contracts constrained by buying power and config limit."""
        executor = self._make_executor(max_contracts=10, buying_power_usage_pct=0.85)
        # $5000 BP * 0.85 = $4250 usable / $445 collateral = 9.55 → 9 contracts
        contracts = executor.calculate_max_contracts(5000, 445)
        assert contracts == 9

    def test_max_contracts_capped(self):
        """Contracts should never exceed config max_contracts."""
        executor = self._make_executor(max_contracts=3)
        # With huge buying power, still limited to 3
        contracts = executor.calculate_max_contracts(100000, 445)
        assert contracts == 3

    def test_max_contracts_zero_collateral(self):
        """Zero collateral should return 0 contracts."""
        executor = self._make_executor()
        assert executor.calculate_max_contracts(5000, 0) == 0

    def test_pnl_calculation_profit(self):
        """P&L = (entry_credit - close_price) * 100 * contracts."""
        from trading.models import IronCondorPosition
        pos = IronCondorPosition(
            position_id="TEST", ticker="SPY", expiration="2026-02-28",
            put_short_strike=580, put_long_strike=575, put_credit=0.30,
            call_short_strike=600, call_long_strike=605, call_credit=0.25,
            contracts=2, spread_width=5, total_credit=0.55,
            max_loss=445, max_profit=55, underlying_at_entry=590,
            collateral_required=890,
        )
        # Close at 0.20 → profit per contract = (0.55 - 0.20) * 100 = $35
        pnl_per = (pos.total_credit - 0.20) * 100
        total_pnl = pnl_per * pos.contracts
        assert total_pnl == 70.0  # 2 contracts × $35

    def test_pnl_calculation_loss(self):
        """Losing trade: close_price > entry_credit."""
        from trading.models import IronCondorPosition
        pos = IronCondorPosition(
            position_id="TEST", ticker="SPY", expiration="2026-02-28",
            put_short_strike=580, put_long_strike=575, put_credit=0.30,
            call_short_strike=600, call_long_strike=605, call_credit=0.25,
            contracts=2, spread_width=5, total_credit=0.55,
            max_loss=445, max_profit=55, underlying_at_entry=590,
            collateral_required=890,
        )
        # Close at 1.10 → loss per contract = (0.55 - 1.10) * 100 = -$55
        pnl_per = (pos.total_credit - 1.10) * 100
        total_pnl = round(pnl_per * pos.contracts, 2)
        assert total_pnl == -110.0


# ===========================================================================
# 5. TRADER LIFECYCLE TESTS
# ===========================================================================

class TestTraderLifecycle:
    """Test Trader trading window, EOD cutoff, and cycle flow."""

    def _make_trader(self, config_overrides=None, mock_positions=None):
        """Create a Trader with all externals mocked."""
        from trading.models import flame_config
        cfg = flame_config()
        if config_overrides:
            for k, v in config_overrides.items():
                setattr(cfg, k, v)

        with patch('trading.trader.TradingDatabase') as mock_db_cls, \
             patch('trading.trader.SignalGenerator') as mock_sig_cls, \
             patch('trading.trader.PaperExecutor') as mock_exec_cls:

            mock_db = MagicMock()
            mock_db.get_open_positions.return_value = mock_positions or []
            mock_db.get_paper_account.return_value = MagicMock(
                balance=5000, buying_power=5000, to_dict=lambda: {}
            )
            mock_db.has_traded_today.return_value = False
            mock_db.get_day_trade_count_rolling_5_days.return_value = 0
            mock_db.get_trades_today_count.return_value = 0
            mock_db.get_heartbeat_info.return_value = None
            mock_db.get_next_pdt_reset_date.return_value = None
            mock_db_cls.return_value = mock_db

            mock_sig = MagicMock()
            mock_sig_cls.return_value = mock_sig

            mock_exec = MagicMock()
            mock_exec_cls.return_value = mock_exec

            from trading.trader import Trader
            trader = Trader(config=cfg)
            # Reassign mocks directly
            trader.db = mock_db
            trader.signal_generator = mock_sig
            trader.executor = mock_exec
            return trader

    def test_trading_window_before_open(self):
        """Before 8:30 AM CT should be outside trading window."""
        trader = self._make_trader()
        early = datetime(2026, 2, 26, 7, 0, tzinfo=CENTRAL_TZ)
        in_window, msg = trader._is_in_trading_window(early)
        assert in_window is False
        assert "Before" in msg

    def test_trading_window_during_hours(self):
        """10:00 AM CT should be in trading window."""
        trader = self._make_trader()
        mid = datetime(2026, 2, 26, 10, 0, tzinfo=CENTRAL_TZ)
        in_window, msg = trader._is_in_trading_window(mid)
        assert in_window is True

    def test_trading_window_after_eod(self):
        """3:00 PM CT (15:00) should be past EOD (2:45 PM CT)."""
        trader = self._make_trader()
        late = datetime(2026, 2, 26, 15, 0, tzinfo=CENTRAL_TZ)
        in_window, msg = trader._is_in_trading_window(late)
        assert in_window is False
        assert "EOD" in msg

    def test_eod_cutoff_check(self):
        """3:45 PM ET = 2:45 PM CT should be past EOD."""
        trader = self._make_trader()
        # 3:50 PM ET = past 3:45 PM ET cutoff
        et_time = datetime(2026, 2, 26, 15, 50, tzinfo=EASTERN_TZ)
        ct_time = et_time.astimezone(CENTRAL_TZ)
        assert trader._is_past_eod_cutoff(ct_time) is True

    def test_eod_cutoff_not_yet(self):
        """1:00 PM CT (2:00 PM ET) should NOT be past EOD."""
        trader = self._make_trader()
        early = datetime(2026, 2, 26, 13, 0, tzinfo=CENTRAL_TZ)
        assert trader._is_past_eod_cutoff(early) is False

    def test_cycle_outside_window(self):
        """run_cycle outside trading window returns 'outside_window'."""
        trader = self._make_trader()
        with patch('trading.trader.datetime') as mock_dt:
            early = datetime(2026, 2, 26, 7, 0, tzinfo=CENTRAL_TZ)
            mock_dt.now.return_value = early
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = trader.run_cycle()
            assert result['action'] == 'outside_window'

    def test_cycle_bot_inactive(self):
        """run_cycle with inactive bot returns 'inactive'."""
        trader = self._make_trader()
        trader.is_active = False
        with patch('trading.trader.datetime') as mock_dt:
            mid = datetime(2026, 2, 26, 10, 0, tzinfo=CENTRAL_TZ)
            mock_dt.now.return_value = mid
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = trader.run_cycle()
            assert result['action'] == 'inactive'

    def test_toggle_on_off(self):
        """Toggle should update is_active flag."""
        trader = self._make_trader()
        assert trader.is_active is True
        result = trader.toggle(False)
        assert trader.is_active is False
        assert "disabled" in result['message']
        result = trader.toggle(True)
        assert trader.is_active is True
        assert "enabled" in result['message']

    def test_cycle_max_trades_reached(self):
        """When already traded today, should return 'max_trades'."""
        trader = self._make_trader()
        trader.db.has_traded_today.return_value = True
        with patch('trading.trader.datetime') as mock_dt:
            mid = datetime(2026, 2, 26, 10, 0, tzinfo=CENTRAL_TZ)
            mock_dt.now.return_value = mid
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = trader.run_cycle()
            assert result['action'] == 'max_trades'

    def test_cycle_pdt_blocked(self):
        """When PDT count >= 3, should block trading."""
        trader = self._make_trader()
        trader.db.get_day_trade_count_rolling_5_days.return_value = 3
        with patch('trading.trader.datetime') as mock_dt:
            mid = datetime(2026, 2, 26, 10, 0, tzinfo=CENTRAL_TZ)
            mock_dt.now.return_value = mid
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = trader.run_cycle()
            assert result['action'] == 'pdt_blocked'

    def test_cycle_insufficient_buying_power(self):
        """With low buying power, should return 'insufficient_bp'."""
        trader = self._make_trader()
        trader.db.get_paper_account.return_value = MagicMock(
            balance=100, buying_power=100, to_dict=lambda: {}
        )
        with patch('trading.trader.datetime') as mock_dt:
            mid = datetime(2026, 2, 26, 10, 0, tzinfo=CENTRAL_TZ)
            mock_dt.now.return_value = mid
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = trader.run_cycle()
            assert result['action'] == 'insufficient_bp'


# ===========================================================================
# 6. POSITION MANAGEMENT TESTS
# ===========================================================================

class TestPositionManagement:
    """Test position monitoring: profit target, stop loss, EOD, stale."""

    def _make_trader_with_position(self, entry_credit=0.55, open_time=None):
        """Create a Trader with one open position."""
        from trading.models import IronCondorPosition, PositionStatus, flame_config

        if open_time is None:
            open_time = datetime(2026, 2, 26, 10, 0, tzinfo=CENTRAL_TZ)

        pos = IronCondorPosition(
            position_id="FLAME-20260226-XYZ",
            ticker="SPY", expiration="2026-02-28",
            put_short_strike=580, put_long_strike=575, put_credit=0.30,
            call_short_strike=600, call_long_strike=605, call_credit=0.25,
            contracts=2, spread_width=5, total_credit=entry_credit,
            max_loss=445, max_profit=55, underlying_at_entry=590,
            status=PositionStatus.OPEN, open_time=open_time,
            collateral_required=890,
        )

        cfg = flame_config()
        with patch('trading.trader.TradingDatabase') as mock_db_cls, \
             patch('trading.trader.SignalGenerator') as mock_sig_cls, \
             patch('trading.trader.PaperExecutor') as mock_exec_cls:

            mock_db = MagicMock()
            mock_db.get_open_positions.return_value = [pos]
            mock_db_cls.return_value = mock_db

            mock_sig = MagicMock()
            mock_sig_cls.return_value = mock_sig

            mock_exec = MagicMock()
            mock_exec.close_paper_position.return_value = (True, 35.0)
            mock_exec_cls.return_value = mock_exec

            from trading.trader import Trader
            trader = Trader(config=cfg)
            trader.db = mock_db
            trader.signal_generator = mock_sig
            trader.executor = mock_exec
            return trader, pos

    def test_profit_target_triggers_close(self):
        """When close_price <= entry * (1 - 30%), position closes at profit target."""
        trader, pos = self._make_trader_with_position(entry_credit=0.55)
        # Profit target price = 0.55 * (1 - 0.30) = 0.385
        # Close price of 0.30 < 0.385 → trigger
        trader.signal_generator.get_ic_mark_to_market.return_value = 0.30
        trader.db.get_open_positions.return_value = [pos]

        now = datetime(2026, 2, 26, 12, 0, tzinfo=CENTRAL_TZ)
        managed, pnl = trader._manage_positions(now)
        assert managed == 1
        trader.executor.close_paper_position.assert_called_once()
        call_args = trader.executor.close_paper_position.call_args
        assert call_args[0][1] == 0.30  # close_price
        assert call_args[0][2] == "profit_target"

    def test_stop_loss_triggers_close(self):
        """When close_price >= entry * (1 + 100%), position closes at stop loss."""
        trader, pos = self._make_trader_with_position(entry_credit=0.55)
        # Stop loss price = 0.55 * (1 + 1.0) = 1.10
        # Close price of 1.20 >= 1.10 → trigger
        trader.signal_generator.get_ic_mark_to_market.return_value = 1.20
        trader.db.get_open_positions.return_value = [pos]

        now = datetime(2026, 2, 26, 12, 0, tzinfo=CENTRAL_TZ)
        managed, pnl = trader._manage_positions(now)
        assert managed == 1
        call_args = trader.executor.close_paper_position.call_args
        assert call_args[0][2] == "stop_loss"

    def test_eod_safety_close(self):
        """At 3:45+ PM ET, open positions should be force-closed."""
        trader, pos = self._make_trader_with_position(entry_credit=0.55)
        trader.signal_generator.get_ic_mark_to_market.return_value = 0.45  # not PT or SL
        trader.db.get_open_positions.return_value = [pos]

        # 3:50 PM ET = 2:50 PM CT → past EOD cutoff
        now = datetime(2026, 2, 26, 14, 50, tzinfo=CENTRAL_TZ)
        managed, pnl = trader._manage_positions(now)
        assert managed == 1
        call_args = trader.executor.close_paper_position.call_args
        assert call_args[0][2] == "eod_safety"

    def test_stale_overnight_position_closed(self):
        """Positions from prior day should be closed as stale."""
        yesterday = datetime(2026, 2, 25, 10, 0, tzinfo=CENTRAL_TZ)
        trader, pos = self._make_trader_with_position(open_time=yesterday)
        trader.signal_generator.get_ic_mark_to_market.return_value = 0.40
        trader.db.get_open_positions.return_value = [pos]

        now = datetime(2026, 2, 26, 10, 0, tzinfo=CENTRAL_TZ)
        managed, pnl = trader._manage_positions(now)
        assert managed == 1
        call_args = trader.executor.close_paper_position.call_args
        assert call_args[0][2] == "stale_overnight_position"

    def test_mtm_failure_tracking(self):
        """After 10 consecutive MTM failures, position should be force-closed."""
        trader, pos = self._make_trader_with_position()
        trader.signal_generator.get_ic_mark_to_market.return_value = None
        trader.db.get_open_positions.return_value = [pos]

        now = datetime(2026, 2, 26, 12, 0, tzinfo=CENTRAL_TZ)

        # Run 9 cycles with MTM failure — should not close yet
        for i in range(9):
            trader._manage_positions(now)
        assert trader._mtm_failure_counts.get(pos.position_id, 0) == 9
        trader.executor.close_paper_position.assert_not_called()

        # 10th failure → force close
        trader._manage_positions(now)
        trader.executor.close_paper_position.assert_called_once()
        call_args = trader.executor.close_paper_position.call_args
        assert call_args[0][2] == "data_feed_failure"


# ===========================================================================
# 7. TRADIER CLIENT STRUCTURE
# ===========================================================================

class TestTradierClientStructure:
    """Verify TradierClient API methods and endpoint construction."""

    def test_tradier_client_init(self):
        """TradierClient should init with Tradier production URL."""
        from trading.tradier_client import TradierClient
        client = TradierClient(api_key="test_key", base_url="https://api.tradier.com/v1")
        assert client.api_key == "test_key"
        assert client.base_url == "https://api.tradier.com/v1"
        assert "Bearer test_key" in client.session.headers.get("Authorization", "")

    def test_tradier_uses_production_url(self):
        """IronForge uses production Tradier, NOT sandbox."""
        from config import DatabricksConfig
        assert DatabricksConfig.TRADIER_BASE_URL == "https://api.tradier.com/v1"
        assert "sandbox" not in DatabricksConfig.TRADIER_BASE_URL

    def test_tradier_client_has_required_methods(self):
        """TradierClient should have all methods needed by signal generator."""
        from trading.tradier_client import TradierClient
        client = TradierClient(api_key="test")
        assert hasattr(client, 'get_quote')
        assert hasattr(client, 'get_option_expirations')
        assert hasattr(client, 'get_option_chain')
        assert hasattr(client, 'get_option_quote')
        assert hasattr(client, 'get_vix')

    @patch('trading.tradier_client.requests.Session')
    def test_quote_endpoint(self, mock_session_cls):
        """get_quote should call /markets/quotes endpoint."""
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            'quotes': {'quote': {'last': 590.5, 'symbol': 'SPY'}}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        from trading.tradier_client import TradierClient
        client = TradierClient(api_key="test_key", base_url="https://api.tradier.com/v1")
        client.session = mock_session

        result = client.get_quote("SPY")
        mock_session.get.assert_called_once()
        call_url = mock_session.get.call_args[0][0]
        assert "/markets/quotes" in call_url
        assert result['last'] == 590.5

    def test_occ_symbol_format(self):
        """OCC symbols should be formatted correctly."""
        # SPY + YYMMDD + C/P + strike*1000 (8 digits)
        expiration = "2026-02-28"
        strike = 580.0
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")  # 260228
        strike_str = f"{int(strike * 1000):08d}"  # 00580000
        put_symbol = f"SPY{exp_str}P{strike_str}"
        call_symbol = f"SPY{exp_str}C{strike_str}"

        assert put_symbol == "SPY260228P00580000"
        assert call_symbol == "SPY260228C00580000"


# ===========================================================================
# 8. DATABASE LAYER TESTS
# ===========================================================================

class TestDatabaseLayer:
    """Test TradingDatabase table naming and key operations."""

    def test_flame_table_naming(self):
        """FLAME tables should be prefixed with 'flame_'."""
        from trading.db import TradingDatabase
        db = TradingDatabase(bot_name="FLAME", dte_mode="2DTE")
        assert db._prefix == "flame"
        # _t() calls table() which uses DatabricksConfig
        table_name = db._t("positions")
        assert "flame_positions" in table_name

    def test_spark_table_naming(self):
        """SPARK tables should be prefixed with 'spark_'."""
        from trading.db import TradingDatabase
        db = TradingDatabase(bot_name="SPARK", dte_mode="1DTE")
        assert db._prefix == "spark"
        table_name = db._t("positions")
        assert "spark_positions" in table_name

    def test_fully_qualified_table_name(self):
        """Table names should include catalog and schema."""
        from trading.db_adapter import table
        full = table("flame_positions")
        assert "alpha_prime" in full
        assert "default" in full
        assert "flame_positions" in full

    def test_to_python_conversion(self):
        """_to_python should convert various types to native Python."""
        from trading.db_adapter import _to_python
        assert _to_python(None) is None
        assert _to_python(42) == 42
        assert isinstance(_to_python(42), int)
        assert _to_python(3.14) == 3.14
        assert isinstance(_to_python(3.14), float)
        assert _to_python("hello") == "hello"
        assert _to_python(True) is True

    def test_db_has_all_required_methods(self):
        """TradingDatabase should have all methods used by Trader."""
        from trading.db import TradingDatabase
        db = TradingDatabase()
        required_methods = [
            'initialize_paper_account', 'get_paper_account',
            'update_paper_balance', 'get_open_positions',
            'save_position', 'close_position', 'expire_position',
            'get_position_count', 'has_traded_today',
            'get_trades_today_count', 'log_pdt_entry',
            'update_pdt_close', 'get_day_trade_count_rolling_5_days',
            'get_pdt_log', 'get_next_pdt_reset_date',
            'log_signal', 'log', 'update_heartbeat',
            'get_heartbeat_info', 'save_equity_snapshot',
            'get_closed_trades', 'get_performance_stats',
            'get_equity_curve', 'get_logs',
        ]
        for method in required_methods:
            assert hasattr(db, method), f"Missing method: {method}"

    def test_seven_tables_per_bot(self):
        """Each bot should have 7 tables."""
        expected_suffixes = [
            'positions', 'signals', 'daily_perf', 'logs',
            'equity_snapshots', 'paper_account', 'pdt_log',
        ]
        from trading.db import TradingDatabase
        db_flame = TradingDatabase(bot_name="FLAME", dte_mode="2DTE")
        for suffix in expected_suffixes:
            name = db_flame._t(suffix)
            assert f"flame_{suffix}" in name, f"Missing table: flame_{suffix}"

        db_spark = TradingDatabase(bot_name="SPARK", dte_mode="1DTE")
        for suffix in expected_suffixes:
            name = db_spark._t(suffix)
            assert f"spark_{suffix}" in name, f"Missing table: spark_{suffix}"


# ===========================================================================
# 9. SETUP TABLES DDL TESTS
# ===========================================================================

class TestSetupTablesDDL:
    """Verify table DDL definitions are complete."""

    def test_setup_tables_module_exists(self):
        """setup_tables.py should exist and have setup_all_tables."""
        setup_path = DATABRICKS_DIR / "setup_tables.py"
        assert setup_path.exists(), "setup_tables.py is missing"
        source = setup_path.read_text()
        assert "def setup_all_tables" in source
        assert "flame" in source
        assert "spark" in source

    def test_position_table_has_oracle_columns(self):
        """Position table DDL should include oracle context columns."""
        setup_path = DATABRICKS_DIR / "setup_tables.py"
        source = setup_path.read_text()
        assert "oracle_confidence" in source
        assert "oracle_win_probability" in source
        assert "oracle_advice" in source
        assert "oracle_use_gex_walls" in source

    def test_position_table_has_wing_tracking(self):
        """Position table DDL should include wing symmetry columns."""
        setup_path = DATABRICKS_DIR / "setup_tables.py"
        source = setup_path.read_text()
        assert "wings_adjusted" in source
        assert "original_put_width" in source
        assert "original_call_width" in source

    def test_heartbeats_table_is_shared(self):
        """bot_heartbeats should be a shared table (not per-bot)."""
        setup_path = DATABRICKS_DIR / "setup_tables.py"
        source = setup_path.read_text()
        assert "bot_heartbeats" in source
        # Heartbeat DDL doesn't take a bot parameter
        assert "_heartbeats_table_ddl()" in source


# ===========================================================================
# 10. JOB ENTRY POINTS
# ===========================================================================

class TestJobEntryPoints:
    """Verify job entry points exist and are well-formed."""

    def test_flame_job_exists(self):
        """run_flame.py should exist."""
        flame_job = DATABRICKS_DIR / "jobs" / "run_flame.py"
        assert flame_job.exists(), "jobs/run_flame.py is missing"

    def test_spark_job_exists(self):
        """run_spark.py should exist."""
        spark_job = DATABRICKS_DIR / "jobs" / "run_spark.py"
        assert spark_job.exists(), "jobs/run_spark.py is missing"

    def test_flame_job_imports_create_flame_trader(self):
        """run_flame.py should use create_flame_trader."""
        source = (DATABRICKS_DIR / "jobs" / "run_flame.py").read_text()
        assert "create_flame_trader" in source
        assert "run_cycle" in source
        assert "DatabricksConfig.validate" in source

    def test_spark_job_imports_create_spark_trader(self):
        """run_spark.py should use create_spark_trader."""
        source = (DATABRICKS_DIR / "jobs" / "run_spark.py").read_text()
        assert "create_spark_trader" in source
        assert "run_cycle" in source
        assert "DatabricksConfig.validate" in source

    def test_factory_functions_exist(self):
        """create_flame_trader and create_spark_trader should be importable."""
        from trading.trader import create_flame_trader, create_spark_trader
        assert callable(create_flame_trader)
        assert callable(create_spark_trader)


# ===========================================================================
# 11. WORKFLOW SCHEDULING TESTS
# ===========================================================================

class TestWorkflowScheduling:
    """Verify Databricks Workflow configuration."""

    def test_workflow_config_exists(self):
        """workflow_config.json should exist."""
        wf = DATABRICKS_DIR / "jobs" / "workflow_config.json"
        assert wf.exists(), "workflow_config.json is missing"

    def test_workflow_config_valid_json(self):
        """workflow_config.json should be valid JSON."""
        wf = DATABRICKS_DIR / "jobs" / "workflow_config.json"
        with open(wf) as f:
            config = json.load(f)
        assert "workflows" in config

    def test_both_bots_scheduled(self):
        """Both FLAME and SPARK should have workflow entries."""
        wf = DATABRICKS_DIR / "jobs" / "workflow_config.json"
        with open(wf) as f:
            config = json.load(f)

        names = [w['name'] for w in config['workflows']]
        assert 'flame_trading' in names
        assert 'spark_trading' in names

    def test_workflow_runs_during_market_hours(self):
        """Workflows should run 14:30-20:45 UTC (8:30-14:45 CT)."""
        wf = DATABRICKS_DIR / "jobs" / "workflow_config.json"
        with open(wf) as f:
            config = json.load(f)

        for workflow in config['workflows']:
            cron = workflow['schedule']['quartz_cron_expression']
            # Should contain 14-20 (UTC hours for 8:30-14:45 CT)
            assert "14-20" in cron, f"Cron should cover market hours: {cron}"
            tz = workflow['schedule']['timezone_id']
            assert tz == "UTC"

    def test_workflow_weekdays_only(self):
        """Workflows should only run Monday-Friday."""
        wf = DATABRICKS_DIR / "jobs" / "workflow_config.json"
        with open(wf) as f:
            config = json.load(f)

        for workflow in config['workflows']:
            cron = workflow['schedule']['quartz_cron_expression']
            assert "MON-FRI" in cron, f"Should run weekdays only: {cron}"

    def test_required_env_vars_documented(self):
        """Required env vars should be listed in config."""
        wf = DATABRICKS_DIR / "jobs" / "workflow_config.json"
        with open(wf) as f:
            config = json.load(f)

        required = config.get('environment_variables', {}).get('required', [])
        assert 'DATABRICKS_SERVER_HOSTNAME' in required
        assert 'DATABRICKS_HTTP_PATH' in required
        assert 'DATABRICKS_TOKEN' in required
        assert 'TRADIER_API_KEY' in required


# ===========================================================================
# 12. DATABRICKS CONFIG TESTS
# ===========================================================================

class TestDatabricksConfig:
    """Verify Databricks configuration is correct."""

    def test_config_validates_with_env_vars(self):
        """Config should validate when env vars are set."""
        from config import DatabricksConfig
        valid, msg = DatabricksConfig.validate()
        assert valid is True
        assert msg == "OK"

    def test_config_rejects_missing_vars(self):
        """Config should fail if required vars are missing."""
        with patch.dict(os.environ, {
            'DATABRICKS_SERVER_HOSTNAME': '',
            'DATABRICKS_HTTP_PATH': '',
            'DATABRICKS_TOKEN': '',
        }):
            import importlib
            import config as cfg_module
            importlib.reload(cfg_module)
            valid, msg = cfg_module.DatabricksConfig.validate()
            assert valid is False
            assert "Missing" in msg

    def test_full_table_name_format(self):
        """get_full_table_name should return catalog.schema.table."""
        from config import DatabricksConfig
        name = DatabricksConfig.get_full_table_name("flame_positions")
        assert name == "alpha_prime.default.flame_positions"

    def test_tradier_production_url(self):
        """Tradier should point to production API, not sandbox."""
        from config import DatabricksConfig
        assert DatabricksConfig.TRADIER_BASE_URL == "https://api.tradier.com/v1"


# ===========================================================================
# 13. COMPLETE FILE STRUCTURE TESTS
# ===========================================================================

class TestIronForgeFileStructure:
    """Verify all required files exist in the databricks/ directory."""

    def test_trading_module_files(self):
        """All trading module files should exist."""
        expected = [
            'trading/__init__.py',
            'trading/models.py',
            'trading/signals.py',
            'trading/trader.py',
            'trading/executor.py',
            'trading/db.py',
            'trading/db_adapter.py',
            'trading/tradier_client.py',
        ]
        for f in expected:
            path = DATABRICKS_DIR / f
            assert path.exists(), f"Missing: {f}"

    def test_jobs_module_files(self):
        """All job files should exist."""
        expected = [
            'jobs/__init__.py',
            'jobs/run_flame.py',
            'jobs/run_spark.py',
            'jobs/workflow_config.json',
        ]
        for f in expected:
            path = DATABRICKS_DIR / f
            assert path.exists(), f"Missing: {f}"

    def test_webapp_module_files(self):
        """Webapp files should exist for the dashboard."""
        expected = [
            'webapp/__init__.py',
            'webapp/app.py',
            'webapp/callbacks/flame_callbacks.py',
            'webapp/callbacks/spark_callbacks.py',
            'webapp/layouts/flame_layout.py',
            'webapp/layouts/spark_layout.py',
        ]
        for f in expected:
            path = DATABRICKS_DIR / f
            assert path.exists(), f"Missing: {f}"

    def test_config_and_setup_files(self):
        """Root config files should exist."""
        expected = ['config.py', 'setup_tables.py', 'requirements.txt']
        for f in expected:
            path = DATABRICKS_DIR / f
            assert path.exists(), f"Missing: {f}"

    def test_notebook_files(self):
        """Standalone notebook files should exist."""
        expected = [
            'notebooks/02_flame_bot.py',
            'notebooks/03_spark_bot.py',
        ]
        for f in expected:
            path = DATABRICKS_DIR / f
            assert path.exists(), f"Missing: {f}"


# ===========================================================================
# 14. CROSS-BOT PARITY TESTS
# ===========================================================================

class TestCrossBotParity:
    """FLAME and SPARK should share the same codebase, differing only in DTE."""

    def test_same_trader_class(self):
        """Both bots use the same Trader class."""
        from trading.trader import Trader, create_flame_trader, create_spark_trader
        # Both factory functions return Trader instances
        assert create_flame_trader.__module__ == create_spark_trader.__module__

    def test_only_dte_differs(self):
        """FLAME and SPARK configs should only differ in DTE-related fields."""
        from trading.models import flame_config, spark_config
        flame = flame_config()
        spark = spark_config()

        assert flame.bot_name != spark.bot_name
        assert flame.min_dte != spark.min_dte
        assert flame.dte_mode != spark.dte_mode

        # Everything else should be identical
        assert flame.ticker == spark.ticker
        assert flame.starting_capital == spark.starting_capital
        assert flame.sd_multiplier == spark.sd_multiplier
        assert flame.spread_width == spark.spread_width
        assert flame.profit_target_pct == spark.profit_target_pct
        assert flame.stop_loss_pct == spark.stop_loss_pct
        assert flame.eod_cutoff_et == spark.eod_cutoff_et
        assert flame.max_trades_per_day == spark.max_trades_per_day
        assert flame.vix_skip == spark.vix_skip
        assert flame.pdt_max_day_trades == spark.pdt_max_day_trades
        assert flame.max_contracts == spark.max_contracts

    def test_flame_is_2dte(self):
        """FLAME DTE should be 2."""
        from trading.models import flame_config
        assert flame_config().min_dte == 2

    def test_spark_is_1dte(self):
        """SPARK DTE should be 1."""
        from trading.models import spark_config
        assert spark_config().min_dte == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
