"""End-to-end EXECUTION coverage for the 14 new updraft-family bots.

The scanner-wiring tests (test_updraft_scanner.py) prove UPDRAFT/BACKDRAFT open
and close. These extend that to EVERY new bot, because they all share one module
(strategy="updraft") and one executor branch, parameterised only by `mode` and
call/put side — so a break in the shared open -> MTM -> close path would silently
affect all of them.

For each bot the REAL run_scan_cycle runs end to end:

    real entry gates -> open_position -> compute_mtm -> monitor -> close_position

Flow modes (updraft/backdraft/tempest + twins) fire from real volume snapshots.
The exotic modes (reversal/em_breach/flashpoint/afterglow/ember/afterburn/
weekender) have ONLY their one historical-DB block (rsi/em/orx/dayx) stubbed to a
passing state — that block is the scanner's job, assembled from prior snapshots;
everything downstream of the signal is the real code under test.

Each bot must (1) OPEN, (2) CLOSE via the monitor, and (3) book a correctly
signed realized P&L for a long debit — profit when the close mark > entry, loss
when it is below. embreach/embreachq additionally exercise the PUT-side debit,
the one structure the armed bots never build.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from backend.bots import flow_store
from backend.bots.executor import list_open_positions
from backend.bots.scanner import ChainProvider, run_scan_cycle

CT = ZoneInfo("America/Chicago")


class _P(ChainProvider):
    """A controllable chain with cumulative option volume."""

    def __init__(self, spot=600.0, call_vol=1200, put_vol=1200,
                 put_wall=596.0, bid=0.14, ask=0.16, leg_mid=None):
        self.spot = spot
        self.call_vol = call_vol
        self.put_vol = put_vol
        self.put_wall = put_wall
        self.bid = bid
        self.ask = ask
        self.leg_mid = leg_mid            # None -> mark at entry (0 pnl)

    def get_chain(self, *, ticker, dte, today):
        strikes = [self.spot + d for d in (-4, -3, -2, -1, 0, 1, 2, 3, 4)]
        n = len(strikes)
        return {
            "spot": self.spot, "ticker": ticker, "expiration": today,
            "options": [
                {"strike": s, "type": t, "bid": self.bid, "ask": self.ask,
                 "volume": (self.call_vol if t == "call" else self.put_vol) // n,
                 "open_interest": 500}
                for s in strikes for t in ("call", "put")
            ],
            "gex": {"put_wall": self.put_wall, "call_wall": self.spot + 5},
        }

    def get_leg_mids(self, *, ticker, legs):
        if self.leg_mid is not None:
            return [self.leg_mid for _ in legs]
        return [leg["entry_price"] for leg in legs]

    def get_daily_history(self, *, ticker, days):
        return []

    def get_hourly_closes(self, *, ticker):
        return []


class _Blk:
    """Stub for a flow_store state object: only .as_dict() is read."""

    def __init__(self, d):
        self._d = d

    def as_dict(self):
        return dict(self._d)


# mode -> (flow_store reader name, passing block). Only these modes read a
# historical-DB block; the flow modes compute everything from live snapshots.
_PATCH = {
    "reversal":   ("read_rsi_state",
                   {"rsi": 35.0, "recovery_cross": True, "prev_rsi": 28.0,
                    "reason": None}),
    "embreach":   ("read_em_state",
                   {"day_open": 610.0, "open_straddle_pct": None,
                    "prev_spot": None, "prev_straddle_pct": None, "reason": None}),
    "embreachq":  ("read_em_state",
                   {"day_open": 610.0, "open_straddle_pct": None,
                    "prev_spot": None, "prev_straddle_pct": None, "reason": None}),
    "flashpoint": ("read_or_state",
                   {"or_high": 599.0, "or_low": 596.0, "day_open": 598.0,
                    "or_complete": True, "open_straddle_pct": 0.05,
                    "prev_spot": 598.0, "reason": None}),
    "afterglow":  ("read_day_signal_state",
                   {"updraft_fired": True, "rsi_recovery_fired": True,
                    "reason": None}),
    "ember":      ("read_day_signal_state",
                   {"updraft_fired": True, "rsi_recovery_fired": True,
                    "reason": None}),
    "afterburn":  ("read_em_state",
                   {"day_open": 594.0, "open_straddle_pct": None,
                    "prev_spot": None, "prev_straddle_pct": None, "reason": None}),
    "weekender":  ("read_em_state",
                   {"day_open": 600.0, "open_straddle_pct": None,
                    "prev_spot": None, "prev_straddle_pct": None, "reason": None}),
}
_FLOW_UPDRAFT = {"updraft", "thermal", "squall"}    # mode == updraft
_FLOW_BACKDRAFT = {"backdraft", "wildfire"}         # mode == backdraft
_TEMPEST = {"tempest"}                               # fires the updraft leg

NEW_BOTS = ["updraft", "thermal", "squall", "backdraft", "wildfire", "tempest",
            "reversal", "embreach", "embreachq", "flashpoint", "afterglow",
            "ember", "afterburn", "weekender"]

PUT_BOTS = {"embreach", "embreachq"}


def _open_window(engine, bot):
    """Enable + widen window/day so only the SIGNAL gate decides entry."""
    with engine.begin() as conn:
        conn.execute(text(
            f"UPDATE {bot}_config SET enabled=1, entry_start_ct='00:00', "
            f"entry_end_ct='23:59', entry_days='', eod_close_ct='23:59'"
        ))


def _first_open(engine, bot):
    rows = list_open_positions(engine, bot)
    return rows[0] if rows else None


def _closed_row(engine, bot, pid):
    with engine.begin() as conn:
        return conn.execute(text(
            f"SELECT close_reason, realized_pnl, close_price FROM "
            f"{bot}_closed_trades WHERE position_id=:p"
        ), {"p": pid}).mappings().first()


def _open_position(engine, bot):
    """Drive the real scanner until `bot` opens one position; return the row."""
    t0 = datetime(2026, 7, 27, 9, 0, tzinfo=CT)     # a Monday, 09:00 CT
    t1 = t0 + timedelta(minutes=30)                 # 09:30 — 30-min flow ready

    if bot in _FLOW_UPDRAFT or bot in _TEMPEST:
        p = _P(spot=600.0)
        run_scan_cycle(engine=engine, bot=bot, now_ct=t0,
                       chain_provider=p, event_blackout=False)
        p.call_vol += 600           # +600 calls vs +3000 puts -> imb ~ -0.67
        p.put_vol += 3000
        p.spot = 603.60             # +60bp rally (> +19.23bp gate)
        run_scan_cycle(engine=engine, bot=bot, now_ct=t1,
                       chain_provider=p, event_blackout=False)
        if _first_open(engine, bot) is None:
            # PATIENT ENTRY (updraft/squall): a limit was armed; the dip fills.
            p.bid, p.ask = 0.11, 0.12
            run_scan_cycle(engine=engine, bot=bot,
                           now_ct=t1 + timedelta(minutes=2),
                           chain_provider=p, event_blackout=False)
    elif bot in _FLOW_BACKDRAFT:
        p = _P(spot=600.0, put_wall=596.0)
        run_scan_cycle(engine=engine, bot=bot, now_ct=t0,
                       chain_provider=p, event_blackout=False)
        p.call_vol += 500
        p.put_vol += 4500           # imb ~ -0.80 (< -0.35 extreme gate)
        p.spot = 601.0              # above the put wall
        run_scan_cycle(engine=engine, bot=bot, now_ct=t1,
                       chain_provider=p, event_blackout=False)
    else:  # exotic PATCH modes
        p = _P(spot=600.0)
        run_scan_cycle(engine=engine, bot=bot, now_ct=t1,
                       chain_provider=p, event_blackout=False)
    return _first_open(engine, bot)


def _close_position(engine, bot, pos, close_mid):
    """Scan far past the hold timer with a controlled mark to force a close."""
    pc = _P(spot=600.0, leg_mid=close_mid)      # flat flow -> no new open
    et = (pos["entry_time"] if isinstance(pos["entry_time"], datetime)
          else datetime.fromisoformat(str(pos["entry_time"])))
    if et.tzinfo is None:
        et = et.replace(tzinfo=CT)
    run_scan_cycle(engine=engine, bot=bot,
                   now_ct=et + timedelta(minutes=6000),   # past every timer
                   chain_provider=pc, event_blackout=False)


@pytest.mark.parametrize("bot", NEW_BOTS)
def test_new_bot_opens_and_closes_with_profit(bot, db_session, monkeypatch):
    """Every new bot opens, marks, and books a correctly signed GAIN."""
    engine = db_session.get_bind()
    _open_window(engine, bot)
    if bot in _PATCH:
        name, block = _PATCH[bot]
        monkeypatch.setattr(flow_store, name, lambda *a, **k: _Blk(block))

    pos = _open_position(engine, bot)
    assert pos is not None, f"{bot} failed to OPEN a position"

    side = json.loads(pos["legs"])[0]["type"]
    assert side == ("put" if bot in PUT_BOTS else "call")
    entry = float(pos["entry_price"])
    contracts = int(pos["contracts"])
    assert contracts >= 1

    # Restore real readers so the close scan can't re-open on a cold DB.
    monkeypatch.undo()
    close_mid = round(entry + 0.10, 2)          # mark UP -> long debit profit
    _close_position(engine, bot, pos, close_mid)

    row = _closed_row(engine, bot, pos["position_id"])
    assert row is not None, f"{bot} opened but never CLOSED"
    # Every one of these bots opens a SINGLE-LEG long debit (n_legs=1). The
    # entry mark read back from the DB already has the entry-side taker cost
    # baked in (open_position widened it), so only the EXIT leg still needs
    # accounting for here: compute_mtm subtracts n_legs*0.02 from the unwind
    # value of a debit before close_position turns it into realized_pnl.
    # naive (close_mid - entry)*100*contracts = 10.00; exit taker cost =
    # 1 leg * 0.02 * 100 * 1 contract = 2.00 -> expected = 10.00 - 2.00 = 8.00.
    n_legs = len(json.loads(pos["legs"]))
    exit_slip = n_legs * 0.02 * 100.0 * contracts
    expected = round((close_mid - entry) * contracts * 100.0 - exit_slip, 2)
    assert float(row["realized_pnl"]) == pytest.approx(expected, abs=0.01)
    assert float(row["realized_pnl"]) > 0, "up-move on a long debit must profit"


@pytest.mark.parametrize("bot", ["updraft", "embreach"])
def test_new_bot_books_a_loss_when_the_mark_falls(bot, db_session, monkeypatch):
    """A mark BELOW entry must book a loss — guards the credit/debit branch
    from inverting the sign (call and the put-side embreach)."""
    engine = db_session.get_bind()
    _open_window(engine, bot)
    if bot in _PATCH:
        name, block = _PATCH[bot]
        monkeypatch.setattr(flow_store, name, lambda *a, **k: _Blk(block))

    pos = _open_position(engine, bot)
    assert pos is not None
    entry = float(pos["entry_price"])
    contracts = int(pos["contracts"])

    monkeypatch.undo()
    close_mid = round(entry - 0.05, 2)          # mark DOWN -> long debit loss
    _close_position(engine, bot, pos, close_mid)

    row = _closed_row(engine, bot, pos["position_id"])
    assert row is not None
    # Same single-leg (n_legs=1) accounting as the profit test above: naive
    # (close_mid - entry)*100*contracts = -5.00; exit taker cost =
    # 1 leg * 0.02 * 100 * 1 contract = 2.00 -> expected = -5.00 - 2.00 = -7.00.
    n_legs = len(json.loads(pos["legs"]))
    exit_slip = n_legs * 0.02 * 100.0 * contracts
    expected = round((close_mid - entry) * contracts * 100.0 - exit_slip, 2)
    assert float(row["realized_pnl"]) == pytest.approx(expected, abs=0.01)
    assert float(row["realized_pnl"]) < 0, "down-move on a long debit must lose"
