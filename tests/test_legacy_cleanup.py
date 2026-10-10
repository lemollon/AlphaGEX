"""Legacy-strategy close + over-cap trim, shared across all 7 AGAPE perp bots.

Covers trading/perp_strategies/legacy_cleanup.py: a config.strategy_mode
flip (e.g. combined_signal -> weekly_breakout) must not leave old positions
open forever blocking every new entry under the new, smaller
max_open_positions cap.
"""
from types import SimpleNamespace

from trading.perp_strategies.legacy_cleanup import close_legacy_and_overcap_positions


def _trader(strategy_mode, max_open_positions, close_results=None):
    """SimpleNamespace trader stand-in, same style as test_weekly_breakout.py."""
    closes = []
    logs = []

    def _close_position(pos, price, reason):
        closes.append((pos["position_id"], price, reason))
        if close_results is not None:
            return close_results.get(pos["position_id"], True)
        return True

    trader = SimpleNamespace(
        config=SimpleNamespace(
            strategy_mode=strategy_mode,
            max_open_positions=max_open_positions,
            bot_name="AGAPE_TEST_PERP",
        ),
        db=SimpleNamespace(log=lambda level, action, message, details=None: logs.append((level, action, message))),
        _close_position=_close_position,
    )
    return trader, closes, logs


def _pos(pid, reasoning=None, open_time="2026-09-27T16:06:00+00:00"):
    return {"position_id": pid, "signal_reasoning": reasoning, "open_time": open_time}


def test_legacy_position_closed_when_mode_is_weekly_breakout():
    trader, closes, logs = _trader("weekly_breakout", max_open_positions=1)
    positions = [_pos("legacy1", reasoning="LOW_CONFIDENCE_LOW")]

    remaining, closed = close_legacy_and_overcap_positions(trader, positions, current_price=100.0)

    assert remaining == []
    assert closed == 1
    assert closes == [("legacy1", 100.0, "STRATEGY_CHANGED")]
    assert any(a == "STRATEGY_CHANGED" for _, a, _ in logs)


def test_legacy_position_with_no_reasoning_at_all_is_also_closed():
    """Positions opened before signal_reasoning existed (NULL column) are legacy too."""
    trader, closes, logs = _trader("weekly_breakout", max_open_positions=1)
    positions = [_pos("legacy2", reasoning=None)]

    remaining, closed = close_legacy_and_overcap_positions(trader, positions, current_price=50.0)

    assert remaining == []
    assert closed == 1
    assert closes == [("legacy2", 50.0, "STRATEGY_CHANGED")]


def test_weekly_breakout_position_is_kept():
    trader, closes, logs = _trader("weekly_breakout", max_open_positions=1)
    positions = [_pos("wb1", reasoning="WEEKLY_BREAKOUT_BREAKOUT_UP close=84500 range=[83000,84000] atr=500 funding=BALANCED")]

    remaining, closed = close_legacy_and_overcap_positions(trader, positions, current_price=84500.0)

    assert remaining == positions
    assert closed == 0
    assert closes == []


def test_combined_signal_mode_closes_nothing():
    """When still on the original strategy, no reasoning marker is 'legacy'."""
    trader, closes, logs = _trader("combined_signal", max_open_positions=5)
    positions = [_pos("c1", reasoning="LOW_CONFIDENCE_LOW"), _pos("c2", reasoning=None)]

    remaining, closed = close_legacy_and_overcap_positions(trader, positions, current_price=100.0)

    assert remaining == positions
    assert closed == 0
    assert closes == []


def test_over_cap_trims_oldest_first():
    trader, closes, logs = _trader("combined_signal", max_open_positions=1)
    positions = [
        _pos("oldest", reasoning="LOW_CONFIDENCE_LOW", open_time="2026-09-25T10:00:00+00:00"),
        _pos("middle", reasoning="LOW_CONFIDENCE_LOW", open_time="2026-09-26T10:00:00+00:00"),
        _pos("newest", reasoning="LOW_CONFIDENCE_LOW", open_time="2026-09-27T10:00:00+00:00"),
    ]

    remaining, closed = close_legacy_and_overcap_positions(trader, positions, current_price=1.0)

    assert closed == 2
    assert [p["position_id"] for p in remaining] == ["newest"]
    closed_ids = [c[0] for c in closes]
    assert closed_ids == ["oldest", "middle"]
    assert all(reason == "OVER_POSITION_CAP" for _, _, reason in closes)
    assert any(a == "OVER_POSITION_CAP" for _, a, _ in logs)


def test_legacy_close_then_overcap_trim_combine():
    """weekly_breakout mode: legacy positions close first, then any remaining excess trims."""
    trader, closes, logs = _trader("weekly_breakout", max_open_positions=1)
    positions = [
        _pos("legacy_old", reasoning="LOW_CONFIDENCE_LOW", open_time="2026-09-25T16:06:00+00:00"),
        _pos("legacy_new", reasoning=None, open_time="2026-09-27T16:06:00+00:00"),
        _pos("wb_current", reasoning="WEEKLY_BREAKOUT_BREAKOUT_DOWN", open_time="2026-09-28T09:00:00+00:00"),
    ]

    remaining, closed = close_legacy_and_overcap_positions(trader, positions, current_price=100.0)

    assert closed == 2
    assert [p["position_id"] for p in remaining] == ["wb_current"]
    closed_ids = {c[0] for c in closes}
    assert closed_ids == {"legacy_old", "legacy_new"}


def test_no_price_closes_nothing():
    trader, closes, logs = _trader("weekly_breakout", max_open_positions=1)
    positions = [_pos("legacy1", reasoning="LOW_CONFIDENCE_LOW")]

    remaining, closed = close_legacy_and_overcap_positions(trader, positions, current_price=None)

    assert remaining == positions
    assert closed == 0
    assert closes == []


def test_no_open_positions_is_a_noop():
    trader, closes, logs = _trader("weekly_breakout", max_open_positions=1)

    remaining, closed = close_legacy_and_overcap_positions(trader, [], current_price=100.0)

    assert remaining == []
    assert closed == 0
    assert closes == []


def test_failed_close_leaves_position_in_remaining():
    """A close that reports failure (e.g. DB error) must not be silently dropped."""
    trader, closes, logs = _trader(
        "weekly_breakout", max_open_positions=1, close_results={"legacy1": False},
    )
    positions = [_pos("legacy1", reasoning="LOW_CONFIDENCE_LOW")]

    remaining, closed = close_legacy_and_overcap_positions(trader, positions, current_price=100.0)

    assert remaining == positions
    assert closed == 0
