from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import valor_mes_v35_dual_leader as v35


def _frame(day: str, base: float, instrument_id: int) -> pd.DataFrame:
    opening, closing, _ = v35.v33.cash.session(day)
    timestamp = pd.date_range(
        pd.Timestamp(opening).tz_convert("UTC"),
        pd.Timestamp(closing).tz_convert("UTC") - pd.Timedelta(minutes=1),
        freq="1min",
    )
    price = np.full(len(timestamp), float(base))
    return pd.DataFrame({
        "timestamp": timestamp, "instrument_id": instrument_id,
        "open": price, "high": price + 0.25, "low": price - 0.25,
        "close": price, "volume": 100,
    })


def _session(day: str = "2023-06-01") -> v35.TripleSession:
    return v35.TripleSession(
        day, _frame(day, 4_000, 11), _frame(day, 14_000, 22),
        _frame(day, 2_000, 33),
    )


def _signal(frame: pd.DataFrame, position: int, side: int) -> None:
    base = float(frame.close.iloc[0])
    price = base + side * 0.5
    if side > 0:
        frame.loc[position, ["open", "high", "close"]] = price
    else:
        frame.loc[position, ["open", "low", "close"]] = price


def _summary(year: int, passes: bool) -> dict:
    count = 60 if passes else 10
    net, average, pf = ((600.0, 10.0, 1.2) if passes else (-100.0, -10.0, 0.5))
    views = {}
    for name, _ in v35.v33.COST_CASES:
        views[name] = {
            "trade_count": count, "net_dollars": net, "average_trade": average,
            "gross_profit": max(net, 0), "gross_loss": 1.0,
            "profit_factor": pf, "profit_factor_infinite": False,
            "maximum_drawdown": 100.0, "monthly_pnl": {},
        }
    return {"year": year, "fill_convention": "test", "cost_views": views}


def test_both_leader_ranges_exclude_their_signal_bars():
    session = _session()
    _signal(session.mnq, 30, 1)
    _signal(session.m2k, 30, 1)

    trade = v35.generate_trades([session], 2023)[0]
    assert trade["prior_mnq_high"] == 14_000.25
    assert trade["mnq_signal_close"] == 14_000.5
    assert trade["prior_m2k_high"] == 2_000.25
    assert trade["m2k_signal_close"] == 2_000.5
    assert trade["side"] == 1


def test_three_market_builder_uses_the_m2k_tenth_point_grid():
    day = "2023-06-01"
    mes, mnq, m2k = _frame(day, 4_000, 11), _frame(day, 14_000, 22), _frame(day, 2_000, 33)
    m2k["high"] = m2k.open + 0.10
    m2k["low"] = m2k.open - 0.10
    assert [row.date for row in v35.build_triple_sessions([mes], [mnq], [m2k])] == [day]

    m2k.loc[0, "high"] = 2_000.05
    with pytest.raises(ValueError, match="Off-grid"):
        v35.build_triple_sessions([mes], [mnq], [m2k])


@pytest.mark.parametrize("mnq_side,m2k_side", [(1, 0), (0, -1), (1, -1), (-1, 1)])
def test_mixed_and_one_sided_breakouts_are_no_signal(mnq_side, m2k_side):
    session = _session()
    if mnq_side:
        _signal(session.mnq, 30, mnq_side)
    if m2k_side:
        _signal(session.m2k, 30, m2k_side)
    assert v35.generate_trades([session], 2023) == []


def test_next_minute_entry_and_preclose_exit_do_not_read_future_bars():
    session = _session()
    _signal(session.mnq, 380, 1)
    _signal(session.m2k, 380, 1)
    session.mes.loc[381, ["open", "high", "close"]] = 4_001.0
    session.mes.loc[384, ["high", "close"]] = 4_002.0
    session.mes.loc[385:, ["open", "high", "low", "close"]] = 9_999.0

    trade = v35.generate_trades([session], 2023)[0]
    _, _, flat = v35.v33.cash.session(session.date)
    assert trade["decision_time"] == session.mes.timestamp.iloc[381].isoformat()
    assert trade["entry_time"] == session.mes.timestamp.iloc[381].isoformat()
    assert trade["entry_price"] == 4_001.0
    assert trade["actual_hold_minutes"] == 4
    assert trade["exit_reason"] == "v8_preclose"
    assert trade["exit_time"] == pd.Timestamp(flat).tz_convert("UTC").isoformat()
    assert trade["exit_price"] == 4_002.0


def test_exact_exit_reentry_is_allowed():
    session = _session()
    _signal(session.mnq, 30, 1)
    _signal(session.m2k, 30, 1)
    session.mnq.loc[31:269, ["open", "high", "low", "close"]] = [14_000.5, 14_000.75, 14_000.25, 14_000.5]
    session.m2k.loc[31:269, ["open", "high", "low", "close"]] = [2_000.5, 2_000.75, 2_000.25, 2_000.5]
    session.mnq.loc[270, ["open", "high", "close"]] = 14_001.0
    session.m2k.loc[270, ["open", "high", "close"]] = 2_001.0

    trades = v35.generate_trades([session], 2023)
    assert len(trades) == 2
    assert trades[1]["entry_time"] == trades[0]["exit_time"]


def test_leader_gaps_contract_changes_and_mes_path_switches_skip_candidates():
    leader_contract = _session()
    _signal(leader_contract.mnq, 30, 1)
    _signal(leader_contract.m2k, 30, 1)
    leader_contract.m2k.loc[20:, "instrument_id"] = 34
    assert v35.generate_trades([leader_contract], 2023) == []

    leader_gap = _session()
    _signal(leader_gap.mnq, 30, 1)
    _signal(leader_gap.m2k, 30, 1)
    leader_gap.mnq.loc[29, "timestamp"] += pd.Timedelta(seconds=30)
    assert v35.generate_trades([leader_gap], 2023) == []

    mes_contract = _session()
    _signal(mes_contract.mnq, 30, 1)
    _signal(mes_contract.m2k, 30, 1)
    mes_contract.mes.loc[100:, "instrument_id"] = 12
    assert v35.generate_trades([mes_contract], 2023) == []


def test_cost_views_charge_fee_and_both_sides_and_report_drawdown():
    trades = [
        {"date": "2023-01-03", "gross_dollars": 20.0},
        {"date": "2023-01-04", "gross_dollars": -10.0},
        {"date": "2023-02-01", "gross_dollars": 5.0},
    ]
    for trade in trades:
        for name, ticks in v35.v33.COST_CASES[1:]:
            trade[name] = v35.v33._cost(trade["gross_dollars"], ticks)
    two = v35.v33.summarize_cell(trades, 2023)["cost_views"]["selection_2t"]
    assert [trade["selection_2t"] for trade in trades] == [12.0, -18.0, -3.0]
    assert two["net_dollars"] == -9.0
    assert two["maximum_drawdown"] == 21.0
    assert two["monthly_pnl"]["2023-01"] == -6.0


@pytest.mark.parametrize(
    ("outcomes", "expected_years", "expected_verdict"),
    [
        ([False], [2023], "FAILED_2023_DISCOVERY"),
        ([True, False], [2023, 2024], "FAILED_2024_VALIDATION"),
    ],
)
def test_later_years_remain_unopened_after_failure(
        monkeypatch, outcomes, expected_years, expected_verdict):
    loaded: list[tuple[str, int]] = []
    evaluated: list[int] = []
    outcome_iter = iter(outcomes)

    def loader(symbol: str, year: int) -> pd.DataFrame:
        loaded.append((symbol, year))
        return pd.DataFrame()

    def generate(sessions, year):
        evaluated.append(year)
        return []

    monkeypatch.setattr(v35, "build_triple_sessions", lambda *args, **kwargs: [])
    monkeypatch.setattr(v35, "generate_trades", generate)
    monkeypatch.setattr(
        v35.v33, "summarize_cell", lambda trades, year: _summary(year, next(outcome_iter)),
    )

    result, _ = v35.run_study(loader)
    assert result["verdict"] == expected_verdict
    assert result["years_loaded"] == expected_years
    assert evaluated == expected_years
    unopened = set(v35.ALLOWED_YEARS).difference(expected_years)
    assert all((symbol, year) not in loaded for year in unopened for symbol in v35.SYMBOLS)
