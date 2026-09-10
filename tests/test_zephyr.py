"""
ZEPHYR pure-logic tests - fee model, vig-strip, scalp signal, exit risk.

These cover the strategy heart that decides profitability. No DB/network.
Run: pytest tests/test_zephyr.py -v
"""

from datetime import datetime, timedelta

import pytest

from trading.zephyr.models import (
    CENTRAL_TZ, FairValueQuote, GameEvent, ScalpPosition, Side,
    PositionStatus, ExitReason, SignalAction, kalshi_fee, round_trip_fee,
)
from trading.zephyr import signals as sig
from trading.zephyr import risk
from trading.zephyr.fairvalue import (
    american_to_implied, strip_vig_two_way, fair_from_american,
)


def _fair(market_id="MKT", prob=0.60, conf=0.75):
    return FairValueQuote(market_id=market_id, fair_prob=prob, source="test",
                          ts=datetime.now(CENTRAL_TZ), confidence=conf)


# ---------------------------------------------------------------- fee model
def test_fee_is_zero_for_makers():
    assert kalshi_fee(50, 5, coeff=0.0) == 0.0


def test_fee_peaks_at_mid_price():
    mid = kalshi_fee(50, 100, 0.07)
    edge = kalshi_fee(10, 100, 0.07)
    assert mid > edge  # fee is maximized at 50c, cheaper at the extremes


def test_fee_rounds_up_to_cent():
    # 0.07 * 1 * 0.5 * 0.5 = 0.0175 -> rounds up to 0.02
    assert kalshi_fee(50, 1, 0.07) == 0.02


def test_round_trip_doubles_single_side():
    one = kalshi_fee(50, 10, 0.07)
    assert round_trip_fee(50, 50, 10, 0.07, 0.07) == pytest.approx(2 * one)


# ---------------------------------------------------------------- vig strip
def test_american_to_implied_favorite_and_dog():
    assert american_to_implied(-200) == pytest.approx(2 / 3, abs=1e-6)
    assert american_to_implied(+150) == pytest.approx(0.4, abs=1e-6)


def test_strip_vig_normalizes_to_one():
    p = strip_vig_two_way(0.55, 0.52)  # raw sums to 1.07 (vig)
    q = strip_vig_two_way(0.52, 0.55)
    assert p + q == pytest.approx(1.0, abs=1e-9)
    assert p > 0.5  # the bigger raw prob stays the favorite


def test_fair_from_american_pickem():
    # symmetric -110/-110 -> 50/50 after stripping vig
    assert fair_from_american(-110, -110) == pytest.approx(0.5, abs=1e-9)


# ---------------------------------------------------------------- signal
def test_no_trade_when_fair_matches_market():
    s = sig.evaluate("MKT", "MLB", yes_bid=59, yes_ask=61, fair=_fair(prob=0.60))
    assert s.action == SignalAction.NONE
    assert not s.is_trade


def test_buy_yes_maker_when_yes_underpriced():
    # fair 70c, market 58/60 -> YES cheap, maker post inside spread
    s = sig.evaluate("MKT", "MLB", yes_bid=58, yes_ask=60, fair=_fair(prob=0.70))
    assert s.side == Side.YES
    assert s.action in (SignalAction.BUY_YES_MAKER, SignalAction.BUY_YES_TAKER)
    assert s.edge_cents >= s.required_edge_cents


def test_buy_no_when_yes_overpriced():
    # fair 30c, market 58/60 -> YES rich -> buy NO
    s = sig.evaluate("MKT", "MLB", yes_bid=58, yes_ask=60, fair=_fair(prob=0.30))
    assert s.side == Side.NO
    assert s.is_trade


def test_fee_gate_blocks_thin_edge():
    # fair only 1c above mid -> edge below fee+buffer gate
    s = sig.evaluate("MKT", "MLB", yes_bid=59, yes_ask=61, fair=_fair(prob=0.61))
    assert s.action == SignalAction.NONE


def test_low_confidence_fair_blocks():
    s = sig.evaluate("MKT", "MLB", yes_bid=50, yes_ask=52, fair=_fair(prob=0.80, conf=0.10))
    assert s.action == SignalAction.NONE


def test_wide_spread_blocks():
    s = sig.evaluate("MKT", "MLB", yes_bid=40, yes_ask=60, fair=_fair(prob=0.80))
    assert s.action == SignalAction.NONE


# ---------------------------------------------------------------- risk/exit
def _pos(side=Side.YES, entry=60.0, secs_ago=10):
    return ScalpPosition(
        position_id="p1", market_id="MKT", sport="MLB", side=side, contracts=5,
        entry_cents=entry, open_time=datetime.now(CENTRAL_TZ) - timedelta(seconds=secs_ago),
        status=PositionStatus.OPEN,
    )


def test_score_kill_takes_priority():
    pos = _pos()
    ev = GameEvent(market_id="MKT", sport="MLB", event_type="score",
                   ts=datetime.now(CENTRAL_TZ))
    reason = risk.evaluate_exit(pos, yes_bid=58, yes_ask=60, fair=_fair(prob=0.60),
                                game_events=[ev])
    assert reason == ExitReason.SCORE_KILL


def test_max_hold_guillotine():
    pos = _pos(secs_ago=10_000)
    reason = risk.evaluate_exit(pos, yes_bid=60, yes_ask=62, fair=_fair(prob=0.61))
    assert reason == ExitReason.MAX_HOLD


def test_stop_loss_on_adverse_move():
    pos = _pos(entry=60.0, secs_ago=5)
    # YES exit price = yes_bid = 54 -> 6c underwater > 4c stop
    reason = risk.evaluate_exit(pos, yes_bid=54, yes_ask=56, fair=_fair(prob=0.55))
    assert reason == ExitReason.STOP_LOSS


def test_revert_to_fair_takes_profit():
    pos = _pos(entry=58.0, secs_ago=5)
    # price now 60/62 (mid 61) matching fair 61 -> revert, and exit>=entry
    reason = risk.evaluate_exit(pos, yes_bid=60, yes_ask=62, fair=_fair(prob=0.61))
    assert reason == ExitReason.REVERT_TO_FAIR


def test_no_exit_when_holding_in_band():
    pos = _pos(entry=60.0, secs_ago=5)
    # small move, no score, within time/stop, gap to fair still open
    reason = risk.evaluate_exit(pos, yes_bid=60, yes_ask=62, fair=_fair(prob=0.75))
    assert reason is None


def test_pnl_sign_for_yes():
    pos = _pos(entry=60.0)
    assert pos.gross_pnl(65.0) == pytest.approx((5 / 100) * 5)
    assert pos.gross_pnl(55.0) == pytest.approx((-5 / 100) * 5)
