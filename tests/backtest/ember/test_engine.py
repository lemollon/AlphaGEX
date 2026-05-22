# tests/backtest/ember/test_engine.py
import datetime as dt
import math
from backtest.ember.models import Quote, Leg, Position, MinuteChain, DayChain
from backtest.ember.policy import ExitPolicy
from backtest.ember.fills import FILL_ASK_CROSS, FILL_MID, CONTRACT_MULTIPLIER
from backtest.ember.engine import evaluate_exit, price_path


# Single short put credit spread: sell 95P / buy 90P.
LEGS = [Leg(95.0, "P", -1), Leg(90.0, "P", 1)]


def _chain(spread_mids_by_minute):
    """Build a DayChain where the combo mid follows the given path.
    We model it by setting the 95P mid to `value` and 90P mid to 0 (tight quotes)."""
    minutes = {}
    for m, val in spread_mids_by_minute.items():
        quotes = {
            (95.0, "P"): Quote(bid=val, ask=val, close=val),
            (90.0, "P"): Quote(bid=0.0, ask=0.0, close=0.0),  # mid falls back to close=0
        }
        minutes[m] = MinuteChain(minute=m, spot=100.0, quotes=quotes)
    return DayChain(dt.date(2024, 6, 3), dt.date(2024, 6, 4), minutes)


def _pos(entry_minute=0, credit=1.00):
    return Position(legs=LEGS, entry_minute=entry_minute, entry_credit=credit)


def test_profit_target_triggers():
    # Entry combo mid 1.00 (credit). Decays to 0.50 by minute 10 -> 50% captured.
    chain = _chain({0: 1.00, 5: 0.80, 10: 0.50, 385: 0.50})
    policy = ExitPolicy("pt50", profit_target_pct=50, stop_loss_mult=None, time_stop_minute=None, min_hold_minutes=1)
    r = evaluate_exit(chain, _pos(credit=1.00), policy, fill=FILL_MID)
    assert r.exit_reason == "PT"
    assert r.exit_minute == 10


def test_stop_loss_triggers():
    # Combo mid rises to 1.50 -> loss = 0.50 per spread = 0.5x credit.
    chain = _chain({0: 1.00, 5: 1.20, 8: 1.50, 385: 1.50})
    policy = ExitPolicy("sl05", profit_target_pct=None, stop_loss_mult=0.5, time_stop_minute=None, min_hold_minutes=1)
    r = evaluate_exit(chain, _pos(credit=1.00), policy, fill=FILL_MID)
    assert r.exit_reason == "SL"
    assert r.exit_minute == 8


def test_time_stop_triggers():
    chain = _chain({0: 1.00, 100: 0.95, 300: 0.90, 385: 0.90})
    policy = ExitPolicy("ts", profit_target_pct=None, stop_loss_mult=None, time_stop_minute=300, min_hold_minutes=1)
    r = evaluate_exit(chain, _pos(credit=1.00), policy, fill=FILL_MID)
    assert r.exit_reason == "TIME"
    assert r.exit_minute == 300


def test_eod_when_nothing_triggers():
    chain = _chain({0: 1.00, 200: 0.92, 385: 0.88})
    policy = ExitPolicy("eod", profit_target_pct=99, stop_loss_mult=99, time_stop_minute=None, min_hold_minutes=1)
    r = evaluate_exit(chain, _pos(credit=1.00), policy, fill=FILL_MID)
    assert r.exit_reason == "EOD"
    assert r.exit_minute == 385


def test_pnl_sign_and_commission():
    # Mid fill, credit 1.00 -> decays to 0.50, exit by PT. Gross profit per contract = 0.50*100 = 50.
    chain = _chain({0: 1.00, 10: 0.50, 385: 0.50})
    policy = ExitPolicy("pt50", profit_target_pct=50, stop_loss_mult=None, time_stop_minute=None, min_hold_minutes=1)
    r = evaluate_exit(chain, _pos(credit=1.00), policy, fill=FILL_MID)
    # gross = (open_cf + close_cf) * 100 ; open_cf=+1.00, close_cf=-0.50 -> +0.50*100 = 50
    # net = 50 - commission(2 legs) = 50 - 0.65*2*2 = 50 - 2.6 = 47.4
    assert math.isclose(r.pnl, 47.4, abs_tol=1e-6)


def test_min_hold_blocks_instant_exit():
    # PT would hit at minute 1 but min_hold=5 forces waiting; value back up by 5 -> EOD instead.
    chain = _chain({0: 1.00, 1: 0.40, 5: 0.95, 385: 0.95})
    policy = ExitPolicy("pt50", profit_target_pct=50, stop_loss_mult=None, time_stop_minute=None, min_hold_minutes=5)
    r = evaluate_exit(chain, _pos(credit=1.00), policy, fill=FILL_MID)
    assert r.exit_minute >= 5
    assert r.exit_reason in ("EOD", "PT")


def test_price_path_forward_fills_missing_minute():
    chain = _chain({0: 1.00, 10: 0.80, 385: 0.60})
    pos = _pos(credit=1.00)
    path = price_path(chain, pos, fill=FILL_MID)
    minutes = [m for m, _ in path]
    assert minutes == [0, 10, 385]   # only minutes present in the chain


def test_apply_policy_pt_on_precomputed_path():
    from backtest.ember.engine import apply_policy
    # path is [(minute, gross_dollars)]. credit 1.00 -> credit_dollars=100; PT50 target=50.
    path = [(0, 0.0), (5, 30.0), (10, 60.0), (385, 60.0)]
    policy = ExitPolicy("pt50", profit_target_pct=50, stop_loss_mult=None, time_stop_minute=None, min_hold_minutes=1)
    r = apply_policy(path, trade_date=dt.date(2024, 6, 3), entry_minute=0, entry_credit=1.00,
                     contracts=1, commission_dollars=5.20, policy=policy)
    assert r.exit_reason == "PT"
    assert r.exit_minute == 10
    assert abs(r.pnl - (60.0 - 5.20)) < 1e-9
    assert abs(r.exit_cost - 0.40) < 1e-9   # 1.00 - 60/100


def test_apply_policy_empty_path_returns_none():
    from backtest.ember.engine import apply_policy
    policy = ExitPolicy("x", profit_target_pct=50, stop_loss_mult=None, time_stop_minute=None)
    assert apply_policy([], trade_date=dt.date(2024, 6, 3), entry_minute=0, entry_credit=1.0,
                        contracts=1, commission_dollars=5.2, policy=policy) is None
