"""Paper accounts must behave like a real Hyperliquid account: real fills,
real margin, and they can never exceed limits.

Covers:
  - max_open_positions is enforced (position cap blocks the 4th entry)
  - the paper margin pre-check fails CLOSED on a margin-system exception
  - insufficient free margin blocks a new entry
  - account-level cross-margin liquidation trigger math
  - funding accrual sign (longs pay positive funding, shorts receive)
  - close fills cross the spread instead of marking at mid/last
"""
import importlib
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from trading.shared.margin_config import PERPETUAL_MARGIN_SPECS
from trading.shared.perp_realism import funding_cashflow, simulate_close_fill
import trading.shared.perp_realism as perp_realism

CENTRAL_TZ = ZoneInfo("America/Chicago")

# (models module, Config class, trader module, Trader class)
TRADER_CASES = [
    ("trading.agape_btc_perp.models", "AgapeBtcPerpConfig", "trading.agape_btc_perp.trader", "AgapeBtcPerpTrader"),
    ("trading.agape_eth_perp.models", "AgapeEthPerpConfig", "trading.agape_eth_perp.trader", "AgapeEthPerpTrader"),
    ("trading.agape_sol_perp.models", "AgapeSolPerpConfig", "trading.agape_sol_perp.trader", "AgapeSolPerpTrader"),
    ("trading.agape_xrp_perp.models", "AgapeXrpPerpConfig", "trading.agape_xrp_perp.trader", "AgapeXrpPerpTrader"),
    ("trading.agape_doge_perp.models", "AgapeDogePerpConfig", "trading.agape_doge_perp.trader", "AgapeDogePerpTrader"),
    ("trading.agape_avax_perp.models", "AgapeAvaxPerpConfig", "trading.agape_avax_perp.trader", "AgapeAvaxPerpTrader"),
    ("trading.agape_shib_perp.models", "AgapeShibPerpConfig", "trading.agape_shib_perp.trader", "AgapeShibPerpTrader"),
]


def _bare_trader(trader_cls, config):
    """Build a Trader instance without running __init__ (no DB connection)."""
    t = trader_cls.__new__(trader_cls)
    t.config = config
    t.db = MagicMock()
    t.executor = MagicMock()
    t._enabled = True
    t._liquidated = False
    t._liquidation_recovery_at = None
    t._cycle_count = 0
    t.consecutive_losses = 0
    t.loss_streak_pause_until = None
    return t


def _open_position(side="long", entry_price=100.0, quantity=1.0, position_id="P1",
                    accrued_funding_usd=0.0, open_time=None, last_funding_accrual=None):
    return {
        "position_id": position_id,
        "side": side,
        "entry_price": entry_price,
        "quantity": quantity,
        "accrued_funding_usd": accrued_funding_usd,
        "open_time": open_time,
        "last_funding_accrual": last_funding_accrual,
        "high_water_mark": entry_price,
        "stop_loss": None,
        "take_profit": None,
    }


# ----------------------------------------------------------------------
# 1) max_open_positions caps entry
# ----------------------------------------------------------------------

@pytest.mark.parametrize("model_mod,config_name,trader_mod,trader_name", TRADER_CASES)
def test_position_cap_blocks_the_next_entry(model_mod, config_name, trader_mod, trader_name):
    config_cls = getattr(importlib.import_module(model_mod), config_name)
    trader_cls = getattr(importlib.import_module(trader_mod), trader_name)
    cfg = config_cls(max_open_positions=3, starting_capital=10000.0)
    t = _bare_trader(trader_cls, cfg)

    t.db.get_open_positions.return_value = [
        _open_position(position_id=f"P{i}") for i in range(3)
    ]
    t.db.get_closed_trades.return_value = []
    t.executor.get_current_price.return_value = 100.0

    reason = t._check_entry_conditions(datetime.now(CENTRAL_TZ))

    assert reason is not None
    assert reason.startswith("BLOCKED_MAX_POSITIONS_3/3")


@pytest.mark.parametrize("model_mod,config_name,trader_mod,trader_name", TRADER_CASES)
def test_position_cap_does_not_block_below_the_cap(model_mod, config_name, trader_mod, trader_name):
    config_cls = getattr(importlib.import_module(model_mod), config_name)
    trader_cls = getattr(importlib.import_module(trader_mod), trader_name)
    cfg = config_cls(max_open_positions=3, starting_capital=10000.0)
    t = _bare_trader(trader_cls, cfg)

    t.db.get_open_positions.return_value = [_open_position(position_id="P0")]
    t.db.get_closed_trades.return_value = []
    t.executor.get_current_price.return_value = 100.0

    reason = t._check_entry_conditions(datetime.now(CENTRAL_TZ))

    assert not (reason and reason.startswith("BLOCKED_MAX_POSITIONS"))


# ----------------------------------------------------------------------
# 2) Paper margin check fails CLOSED on a margin-system exception
# ----------------------------------------------------------------------

def test_strict_margin_check_fails_closed_on_monitor_exception(monkeypatch):
    import trading.margin.margin_monitor as mm
    from trading.margin.pre_trade_check import check_margin_before_trade

    def boom(*a, **kw):
        raise RuntimeError("margin monitor unavailable")

    monkeypatch.setattr(mm, "get_margin_monitor", boom)

    approved, reason = check_margin_before_trade(
        bot_name="AGAPE_BTC_PERP", symbol="BTC-PERP", side="long",
        quantity=0.01, entry_price=100000.0, strict=True,
    )

    assert approved is False
    assert "strict" in reason


def test_strict_margin_check_fails_closed_when_data_unavailable(monkeypatch):
    import trading.margin.margin_monitor as mm
    from trading.margin.pre_trade_check import check_margin_before_trade

    fake_monitor = MagicMock()
    fake_monitor.check_margin_for_trade.return_value = None
    monkeypatch.setattr(mm, "get_margin_monitor", lambda **kw: fake_monitor)

    approved, reason = check_margin_before_trade(
        bot_name="AGAPE_BTC_PERP", symbol="BTC-PERP", side="long",
        quantity=0.01, entry_price=100000.0, strict=True,
    )

    assert approved is False
    assert "strict" in reason


def test_non_strict_margin_check_fails_open_when_data_unavailable(monkeypatch):
    """Sanity check that strict=True is the behavior change, not a global one."""
    import trading.margin.margin_monitor as mm
    from trading.margin.pre_trade_check import check_margin_before_trade

    fake_monitor = MagicMock()
    fake_monitor.check_margin_for_trade.return_value = None
    monkeypatch.setattr(mm, "get_margin_monitor", lambda **kw: fake_monitor)

    approved, _reason = check_margin_before_trade(
        bot_name="AGAPE_BTC_PERP", symbol="BTC-PERP", side="long",
        quantity=0.01, entry_price=100000.0, strict=False,
    )

    assert approved is True


# ----------------------------------------------------------------------
# 3) Insufficient free margin blocks a new entry
# ----------------------------------------------------------------------

def _fake_config(instrument="BTC-PERP", starting_capital=1000.0, bot_name="AGAPE_BTC_PERP"):
    return SimpleNamespace(instrument=instrument, starting_capital=starting_capital, bot_name=bot_name)


def test_insufficient_free_margin_blocks_oversized_entry():
    from trading.margin.pre_trade_check import check_free_margin_for_perp

    cfg = _fake_config(starting_capital=1000.0)
    db = MagicMock()
    db.get_open_positions.return_value = []
    db.get_closed_trades.return_value = []

    approved, reason = check_free_margin_for_perp(
        db=db, config=cfg, signal_side="long", signal_quantity=1.0,
        signal_entry_price=1_000_000.0, current_price=1_000_000.0,
    )

    assert approved is False
    assert "INSUFFICIENT_FREE_MARGIN" in reason


def test_sufficient_free_margin_approves_small_entry():
    from trading.margin.pre_trade_check import check_free_margin_for_perp

    cfg = _fake_config(starting_capital=1000.0)
    db = MagicMock()
    db.get_open_positions.return_value = []
    db.get_closed_trades.return_value = []

    approved, reason = check_free_margin_for_perp(
        db=db, config=cfg, signal_side="long", signal_quantity=0.001,
        signal_entry_price=50000.0, current_price=50000.0,
    )

    assert approved is True
    assert reason == "ok"


def test_free_margin_check_accounts_for_existing_open_positions():
    """A second entry should be blocked once the first position already
    consumed most of the free margin, even though a lone entry of that
    size would have been approved."""
    from trading.margin.pre_trade_check import check_free_margin_for_perp

    cfg = _fake_config(starting_capital=1000.0)
    db = MagicMock()
    db.get_open_positions.return_value = [
        _open_position(side="long", entry_price=50000.0, quantity=0.15, position_id="P1"),
    ]
    db.get_closed_trades.return_value = []

    approved, reason = check_free_margin_for_perp(
        db=db, config=cfg, signal_side="long", signal_quantity=0.15,
        signal_entry_price=50000.0, current_price=50000.0,
    )

    assert approved is False
    assert "INSUFFICIENT_FREE_MARGIN" in reason


def test_free_margin_check_fails_closed_on_missing_spec():
    from trading.margin.pre_trade_check import check_free_margin_for_perp

    cfg = _fake_config(instrument="NOT-A-REAL-PERP")
    db = MagicMock()

    approved, reason = check_free_margin_for_perp(
        db=db, config=cfg, signal_side="long", signal_quantity=1.0,
        signal_entry_price=100.0, current_price=100.0,
    )

    assert approved is False


# ----------------------------------------------------------------------
# 4) Liquidation trigger math (account-level cross margin)
# ----------------------------------------------------------------------

@pytest.mark.parametrize("model_mod,config_name,trader_mod,trader_name", TRADER_CASES)
def test_total_maintenance_margin_sums_every_open_position(model_mod, config_name, trader_mod, trader_name):
    config_cls = getattr(importlib.import_module(model_mod), config_name)
    trader_cls = getattr(importlib.import_module(trader_mod), trader_name)
    cfg = config_cls(starting_capital=1000.0)
    t = _bare_trader(trader_cls, cfg)

    positions = [
        _open_position(side="long", entry_price=100.0, quantity=1.0, position_id="P1"),
        _open_position(side="short", entry_price=100.0, quantity=1.0, position_id="P2"),
    ]
    one_position_total = t._total_maintenance_margin(positions[:1], mark_price=100.0)
    two_position_total = t._total_maintenance_margin(positions, mark_price=100.0)

    assert one_position_total > 0
    # Two open positions at the same notional must require roughly double
    # the maintenance margin of one - this is what makes the check an
    # account-level SUM instead of a flat % of starting capital.
    assert two_position_total == pytest.approx(one_position_total * 2, rel=0.05)


def test_total_maintenance_margin_matches_spec_rate_for_btc():
    from trading.agape_btc_perp.models import AgapeBtcPerpConfig
    from trading.agape_btc_perp.trader import AgapeBtcPerpTrader

    cfg = AgapeBtcPerpConfig(starting_capital=1000.0)
    t = _bare_trader(AgapeBtcPerpTrader, cfg)
    positions = [_open_position(side="long", entry_price=50000.0, quantity=1.0)]

    total = t._total_maintenance_margin(positions, mark_price=50000.0)

    spec = PERPETUAL_MARGIN_SPECS["BTC-PERP"]
    expected = 50000.0 * 1.0 * spec["maintenance_margin_rate"]
    assert total == pytest.approx(expected, rel=0.2)


def test_manage_positions_liquidates_when_equity_cannot_cover_maintenance():
    """Real liquidation: cross-margin across every open position, not the
    old flat 5%-of-starting-capital rule."""
    from trading.agape_btc_perp.models import AgapeBtcPerpConfig, TradingMode
    from trading.agape_btc_perp.trader import AgapeBtcPerpTrader

    cfg = AgapeBtcPerpConfig(starting_capital=1000.0, use_no_loss_trailing=False)
    t = _bare_trader(AgapeBtcPerpTrader, cfg)

    positions = [_open_position(side="long", entry_price=100.0, quantity=1.0, position_id="P1")]
    t.db.get_open_positions.return_value = positions
    # Deeply negative realized P&L blows through even a generous maintenance
    # requirement, so equity <= maintenance_required regardless of the
    # exact tiered margin math.
    t.db.get_closed_trades.return_value = [{"realized_pnl": -1200.0}]
    t.executor.get_current_price.return_value = 100.0

    closed_reasons = []

    def fake_close(pos, price, reason):
        closed_reasons.append(reason)
        return True

    t._close_position = fake_close

    managed, closed = t._manage_positions({"funding_rate": None})

    assert closed == 1
    assert closed_reasons == ["LIQUIDATION"]
    assert t._liquidated is True
    assert t._enabled is False
    assert t.config.mode == TradingMode.PAPER  # paper recovers instead of staying dead forever
    assert t._liquidation_recovery_at is not None


# ----------------------------------------------------------------------
# 5) Funding accrual sign (long pays / short receives)
# ----------------------------------------------------------------------

def test_funding_cashflow_sign_long_pays_short_receives():
    long_flow = funding_cashflow(notional=10000.0, side="long", funding_rate=0.0005, intervals=2.0)
    short_flow = funding_cashflow(notional=10000.0, side="short", funding_rate=0.0005, intervals=2.0)
    assert long_flow < 0
    assert short_flow > 0
    assert long_flow == -short_flow


def test_accrue_funding_persists_signed_cashflow_and_advances_clock():
    from trading.agape_btc_perp.models import AgapeBtcPerpConfig
    from trading.agape_btc_perp.trader import AgapeBtcPerpTrader

    cfg = AgapeBtcPerpConfig(starting_capital=1000.0)
    t = _bare_trader(AgapeBtcPerpTrader, cfg)
    t.executor.get_current_price.return_value = 50000.0

    now = datetime.now(CENTRAL_TZ)
    two_hours_ago = (now - timedelta(hours=2)).isoformat()

    long_pos = _open_position(
        side="long", entry_price=50000.0, quantity=1.0, position_id="LONG1",
        last_funding_accrual=two_hours_ago,
    )
    short_pos = _open_position(
        side="short", entry_price=50000.0, quantity=1.0, position_id="SHORT1",
        last_funding_accrual=two_hours_ago,
    )

    t._accrue_funding([long_pos, short_pos], {"funding_rate": 0.0002}, now)

    assert t.db.accrue_funding.call_count == 2
    calls = {c.args[0]: c.args[1] for c in t.db.accrue_funding.call_args_list}
    assert calls["LONG1"] < 0          # long pays
    assert calls["SHORT1"] > 0         # short receives
    assert calls["LONG1"] == pytest.approx(-calls["SHORT1"])
    # Hyperliquid pays hourly, prorated by elapsed time -> 2 hours elapsed
    # should be ~2x the 1-hour cashflow.
    expected_one_hour = funding_cashflow(notional=50000.0, side="long", funding_rate=0.0002, intervals=1.0)
    assert calls["LONG1"] == pytest.approx(expected_one_hour * 2, rel=0.01)


def test_accrue_funding_skips_when_no_elapsed_time():
    from trading.agape_btc_perp.models import AgapeBtcPerpConfig
    from trading.agape_btc_perp.trader import AgapeBtcPerpTrader

    cfg = AgapeBtcPerpConfig(starting_capital=1000.0)
    t = _bare_trader(AgapeBtcPerpTrader, cfg)
    t.executor.get_current_price.return_value = 50000.0

    now = datetime.now(CENTRAL_TZ)
    pos = _open_position(side="long", entry_price=50000.0, quantity=1.0, last_funding_accrual=now.isoformat())

    t._accrue_funding([pos], {"funding_rate": 0.0002}, now)

    t.db.accrue_funding.assert_not_called()


# ----------------------------------------------------------------------
# 6) Close fills cross the spread instead of marking at mid/last
# ----------------------------------------------------------------------

def test_close_fill_flips_to_the_closing_side(monkeypatch):
    """Closing a long must fill on the SHORT side of the book (sell-to-close)
    and vice versa - simulate_close_fill must flip the side it asks
    simulate_reference_fill for."""
    captured = {}

    def fake_simulate_reference_fill(symbol, side, quantity, fallback_price, **kwargs):
        captured["side"] = side
        return "FILL", "MARKET", "RULES"

    monkeypatch.setattr(perp_realism, "simulate_reference_fill", fake_simulate_reference_fill)

    perp_realism.simulate_close_fill(
        "BTC-PERP", "long", 1.0, 100000.0,
        default_leverage=10, max_leverage=50, fallback_maintenance_margin_rate=0.004,
    )
    assert captured["side"] == "short"

    perp_realism.simulate_close_fill(
        "BTC-PERP", "short", 1.0, 100000.0,
        default_leverage=10, max_leverage=50, fallback_maintenance_margin_rate=0.004,
    )
    assert captured["side"] == "long"


def test_close_fill_crosses_spread_against_the_closer(monkeypatch):
    """With no reference venue (fallback path), closing a long must fill
    BELOW the mark (sell-to-close hits the bid) and closing a short must
    fill ABOVE the mark (buy-to-close hits the ask) - never at mid."""
    monkeypatch.setattr(perp_realism, "get_reference_market", lambda symbol: None)

    long_close, _m, _r = simulate_close_fill(
        "BTC-PERP", "long", 1.0, 100000.0,
        default_leverage=10, max_leverage=50, fallback_maintenance_margin_rate=0.004,
    )
    short_close, _m, _r = simulate_close_fill(
        "BTC-PERP", "short", 1.0, 100000.0,
        default_leverage=10, max_leverage=50, fallback_maintenance_margin_rate=0.004,
    )

    assert long_close.fill_price < 100000.0
    assert short_close.fill_price > 100000.0
    assert long_close.fee_usd > 0
    assert short_close.fee_usd > 0


def test_trader_close_position_uses_close_fill_not_mark_price(monkeypatch):
    """End-to-end: _close_position must call the close-fill simulator (which
    crosses the spread + charges a fee) rather than booking P&L off the raw
    mark price, and must fold in any funding accrued while the position was
    open."""
    from trading.agape_btc_perp.models import AgapeBtcPerpConfig
    from trading.agape_btc_perp.trader import AgapeBtcPerpTrader

    cfg = AgapeBtcPerpConfig(starting_capital=1000.0, max_consecutive_losses=99)
    t = _bare_trader(AgapeBtcPerpTrader, cfg)
    t.db.close_position.return_value = True
    t.db.log.return_value = None

    pos = _open_position(side="long", entry_price=100.0, quantity=1.0, position_id="P1",
                          accrued_funding_usd=-0.50)

    t._simulate_close_fill = MagicMock(return_value=(99.0, 0.10))

    ok = t._close_position(pos, 100.0, "TAKE_PROFIT")

    assert ok is True
    t._simulate_close_fill.assert_called_once_with("long", 1.0, 100.0)
    # P&L = (close - entry) * qty * dir - fee + accrued_funding
    #     = (99 - 100) * 1 * 1 - 0.10 + (-0.50) = -1.60
    args, _kwargs = t.db.close_position.call_args
    close_price_arg, realized_pnl_arg = args[1], args[2]
    assert close_price_arg == 99.0
    assert realized_pnl_arg == pytest.approx(-1.60)
