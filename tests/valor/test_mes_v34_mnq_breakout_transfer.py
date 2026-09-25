from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import valor_mes_v34_mnq_breakout_transfer as v34


def _frame(day: str, base: float, instrument_id: int) -> pd.DataFrame:
    opening, closing, _ = v34.v33.cash.session(day)
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


def _session(day: str = "2023-06-01") -> v34.v33.PairSession:
    mes = _frame(day, 4_000, 11)
    mnq = _frame(day, 14_000, 22)
    return v34.v33.PairSession(day, mes, mnq, 0.0, 0.0)


def _breakout(session: v34.v33.PairSession, position: int, price: float = 14_000.5) -> None:
    session.mnq.loc[position, ["open", "high", "close"]] = price


def _summary(year: int, passes: bool) -> dict:
    count = 80 if passes else 10
    net = 800.0 if passes else -100.0
    average = 10.0 if passes else -10.0
    pf = 1.2 if passes else 0.5
    views = {}
    for name, _ in v34.v33.COST_CASES:
        views[name] = {
            "trade_count": count, "net_dollars": net, "average_trade": average,
            "gross_profit": max(net, 0), "gross_loss": 1.0,
            "profit_factor": pf, "profit_factor_infinite": False,
            "maximum_drawdown": 100.0, "monthly_pnl": {},
        }
    return {"year": year, "fill_convention": "test", "cost_views": views}


def test_signal_bar_is_excluded_from_preceding_30_bar_high():
    session = _session()
    _breakout(session, 30)

    trades = v34.generate_trades([session], 2023)
    assert len(trades) == 1
    assert trades[0]["prior_mnq_high"] == 14_000.25
    assert trades[0]["mnq_signal_close"] == 14_000.5
    assert trades[0]["side"] == 1


def test_entry_uses_next_mes_minute_open():
    session = _session()
    _breakout(session, 30)
    session.mes.loc[31, "open"] = 4_001.25
    session.mes.loc[31, "high"] = 4_001.25
    session.mes.loc[31, "close"] = 4_001.25

    trade = v34.generate_trades([session], 2023)[0]
    assert trade["decision_time"] == session.mes.timestamp.iloc[31].isoformat()
    assert trade["entry_time"] == session.mes.timestamp.iloc[31].isoformat()
    assert trade["entry_price"] == 4_001.25


def test_preclose_truncation_uses_last_completed_bar_without_future_leakage():
    session = _session()
    _breakout(session, 380)
    session.mes.loc[384, "close"] = 4_002.0
    session.mes.loc[384, "high"] = 4_002.0
    session.mes.loc[385:, ["open", "high", "low", "close"]] = 9_999.0

    trade = v34.generate_trades([session], 2023)[0]
    _, _, flat = v34.v33.cash.session(session.date)
    assert trade["exit_reason"] == "v8_preclose"
    assert trade["actual_hold_minutes"] == 4
    assert trade["exit_time"] == pd.Timestamp(flat).tz_convert("UTC").isoformat()
    assert trade["exit_price"] == 4_002.0


def test_non_overlap_allows_exact_exit_reentry_and_skips_bad_paths():
    session = _session()
    _breakout(session, 30)
    session.mnq.loc[31:269, ["open", "high", "low", "close"]] = [14_000.5, 14_000.75, 14_000.25, 14_000.5]
    _breakout(session, 270, 14_001.0)
    trades = v34.generate_trades([session], 2023)
    assert len(trades) == 2
    assert trades[1]["entry_time"] == trades[0]["exit_time"]

    contract_switch = _session()
    _breakout(contract_switch, 30)
    contract_switch.mes.loc[100:, "instrument_id"] = 12
    assert v34.generate_trades([contract_switch], 2023) == []

    minute_gap = _session()
    _breakout(minute_gap, 30)
    minute_gap.mnq.loc[29, "timestamp"] += pd.Timedelta(seconds=30)
    assert v34.generate_trades([minute_gap], 2023) == []


def test_cost_views_charge_fee_and_both_sides_and_report_drawdown():
    trades = [
        {"date": "2023-01-03", "gross_dollars": 20.0},
        {"date": "2023-01-04", "gross_dollars": -10.0},
        {"date": "2023-02-01", "gross_dollars": 5.0},
    ]
    for trade in trades:
        for name, ticks in v34.v33.COST_CASES[1:]:
            trade[name] = v34.v33._cost(trade["gross_dollars"], ticks)

    summary = v34.v33.summarize_cell(trades, 2023)
    two = summary["cost_views"]["selection_2t"]
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

    def summarize(trades, year):
        return _summary(year, next(outcome_iter))

    monkeypatch.setattr(v34.v33, "build_pair_sessions", lambda *args, **kwargs: [])
    monkeypatch.setattr(v34, "generate_trades", generate)
    monkeypatch.setattr(v34.v33, "summarize_cell", summarize)

    result, _ = v34.run_study(loader)
    assert result["verdict"] == expected_verdict
    assert result["years_loaded"] == expected_years
    assert evaluated == expected_years
    unopened = set(v34.ALLOWED_YEARS).difference(expected_years)
    assert all((symbol, year) not in loaded for year in unopened for symbol in ("MES", "MNQ"))
