from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from scripts import valor_mes_v33_crossmarket as v33


def _market_frame(day: str, base: float, instrument_id: int = 1) -> pd.DataFrame:
    opening, closing, _ = v33.cash.session(day)
    timestamps = pd.date_range(
        pd.Timestamp(opening).tz_convert("UTC"),
        pd.Timestamp(closing).tz_convert("UTC") - pd.Timedelta(minutes=1),
        freq="1min",
    )
    price = base + (np.arange(len(timestamps)) % 8) * 0.25
    return pd.DataFrame({
        "timestamp": timestamps,
        "instrument_id": instrument_id,
        "open": price,
        "high": price + 0.25,
        "low": price - 0.25,
        "close": price,
        "volume": np.full(len(timestamps), 100),
    })


def _pair(day: str, mes_close: np.ndarray, mnq_close: np.ndarray,
          mes_daily: float, mnq_daily: float) -> v33.PairSession:
    timestamp = pd.date_range(f"{day} 14:30:00+00:00", periods=len(mes_close), freq="1min")
    mes = pd.DataFrame({
        "timestamp": timestamp, "instrument_id": 11,
        "open": mes_close, "high": mes_close + 0.25,
        "low": mes_close - 0.25, "close": mes_close, "volume": 100,
    })
    mnq = pd.DataFrame({
        "timestamp": timestamp, "instrument_id": 22,
        "open": mnq_close, "high": mnq_close + 0.25,
        "low": mnq_close - 0.25, "close": mnq_close, "volume": 100,
    })
    return v33.PairSession(day, mes, mnq, mes_daily, mnq_daily)


def _summary(year: int, trades: int, net: float, average: float,
             profit_factor: float, drawdown: float, four_tick_net: float | None = None) -> dict:
    def metrics(value: float, avg: float) -> dict:
        return {
            "trade_count": trades, "net_dollars": value, "average_trade": avg,
            "gross_profit": max(value, 0), "gross_loss": 1.0,
            "profit_factor": profit_factor, "profit_factor_infinite": False,
            "maximum_drawdown": drawdown, "monthly_pnl": {},
        }

    views = {name: metrics(net, average) for name, _ in v33.COST_CASES}
    if four_tick_net is not None:
        views["stress_4t"] = metrics(four_tick_net, four_tick_net / max(trades, 1))
    return {"year": year, "fill_convention": "test", "cost_views": views}


def test_beta_and_scale_use_prior_dates_only(monkeypatch):
    monkeypatch.setattr(v33, "MIN_BETA_SESSIONS", 2)
    monkeypatch.setattr(v33, "BETA_SESSIONS", 3)
    monkeypatch.setattr(v33, "SCALE_SESSIONS", 2)
    monkeypatch.setattr(v33, "MIN_SCALE_OBSERVATIONS", 20)
    sessions = []
    for index, day in enumerate(("2023-01-03", "2023-01-04", "2023-01-05",
                                 "2023-01-06", "2023-01-09")):
        x = np.arange(80, dtype=float)
        mnq = 12_000 + x * (0.25 + index * 0.01) + np.sin(x) * 0.25
        mes = 4_000 + x * (0.25 + index * 0.005) + np.cos(x) * 0.25
        sessions.append(_pair(day, mes, mnq, 10 + index, 20 + index))

    before = v33.build_feature_rows(sessions)[5]
    current_before = [row for row in before if row["date"] == "2023-01-09"]
    changed_mes = sessions[-1].mes.copy()
    changed_mnq = sessions[-1].mnq.copy()
    changed_mes["close"] += np.arange(len(changed_mes)) * 10
    changed_mnq["close"] -= np.arange(len(changed_mnq)) * 5
    changed = sessions[:-1] + [replace(
        sessions[-1], mes=changed_mes, mnq=changed_mnq,
        mes_return_bps=9_999, mnq_return_bps=-9_999,
    )]
    after = v33.build_feature_rows(changed)[5]
    current_after = [row for row in after if row["date"] == "2023-01-09"]

    assert current_before and current_after
    assert current_before[0]["beta_prior"] == current_after[0]["beta_prior"]
    assert current_before[0]["scale_prior_bps"] == current_after[0]["scale_prior_bps"]
    assert current_before[0]["residual_bps"] != current_after[0]["residual_bps"]


def test_entry_is_next_minute_and_exit_is_exact_hold_close():
    frame = _market_frame("2023-06-01", 4_000)
    session = v33.PairSession("2023-06-01", frame, frame, 1.0, 1.0)
    position = 20
    feature = {
        "date": "2023-06-01", "year": 2023, "position": position,
        "session": session, "beta_prior": 0.5, "scale_prior_bps": 2.0,
        "residual_bps": 4.0, "z_score": 2.0,
        "signal_bar_start": frame.timestamp.iloc[position],
        "decision_time": frame.timestamp.iloc[position] + pd.Timedelta(minutes=1),
    }

    trade = v33.generate_trades([feature], 2023, 5, 1.5, 5)[0]
    assert trade["entry_time"] == frame.timestamp.iloc[position + 1].isoformat()
    assert trade["exit_time"] == (frame.timestamp.iloc[position + 5] + pd.Timedelta(minutes=1)).isoformat()
    assert trade["entry_price"] == frame.open.iloc[position + 1]
    assert trade["exit_price"] == frame.close.iloc[position + 5]


def test_non_overlap_allows_reentry_at_exact_prior_exit_timestamp():
    frame = _market_frame("2023-06-01", 4_000)
    session = v33.PairSession("2023-06-01", frame, frame, 1.0, 1.0)

    def feature(position: int) -> dict:
        return {
            "date": "2023-06-01", "year": 2023, "position": position,
            "session": session, "beta_prior": 0.5, "scale_prior_bps": 2.0,
            "residual_bps": 4.0, "z_score": 2.0,
            "signal_bar_start": frame.timestamp.iloc[position],
            "decision_time": frame.timestamp.iloc[position] + pd.Timedelta(minutes=1),
        }

    trades = v33.generate_trades([feature(20), feature(25)], 2023, 5, 1.5, 5)
    assert len(trades) == 2
    assert trades[1]["entry_time"] == trades[0]["exit_time"]


def test_contract_switches_and_minute_gaps_are_excluded():
    good_day, gap_day, roll_day = "2023-06-01", "2023-06-02", "2023-06-05"
    mes = pd.concat([
        _market_frame(good_day, 4_000, 1),
        _market_frame(gap_day, 4_010, 1).drop(index=50),
        _market_frame(roll_day, 4_020, 1),
    ], ignore_index=True)
    mnq_roll = _market_frame(roll_day, 14_020, 2)
    mnq_roll.loc[len(mnq_roll) // 2:, "instrument_id"] = 3
    mnq = pd.concat([
        _market_frame(good_day, 14_000, 2),
        _market_frame(gap_day, 14_010, 2),
        mnq_roll,
    ], ignore_index=True)

    sessions = v33.build_pair_sessions([mes], [mnq])
    assert [session.date for session in sessions] == [good_day]


def test_costs_and_closed_trade_maximum_drawdown():
    trades = [
        {"date": "2023-01-03", "gross_dollars": 20.0},
        {"date": "2023-01-04", "gross_dollars": -10.0},
        {"date": "2023-02-01", "gross_dollars": 5.0},
    ]
    for trade in trades:
        for name, ticks in v33.COST_CASES[1:]:
            trade[name] = v33._cost(trade["gross_dollars"], ticks)

    summary = v33.summarize_cell(trades, 2023)
    two_tick = summary["cost_views"]["selection_2t"]
    assert [trade["selection_2t"] for trade in trades] == [12.0, -18.0, -3.0]
    assert two_tick["net_dollars"] == -9.0
    assert two_tick["maximum_drawdown"] == 21.0
    assert two_tick["monthly_pnl"]["2023-01"] == -6.0
    assert two_tick["monthly_pnl"]["2023-02"] == -3.0


def test_discovery_ties_select_first_frozen_cell(monkeypatch):
    tied = _summary(2023, trades=80, net=800.0, average=10.0,
                    profit_factor=1.2, drawdown=100.0)
    monkeypatch.setattr(v33, "generate_trades", lambda *args, **kwargs: [])
    monkeypatch.setattr(v33, "summarize_cell", lambda *args, **kwargs: tied)

    _, selected, _ = v33.evaluate_discovery({lookback: [] for lookback in v33.LOOKBACKS})
    assert selected["parameters"] == {
        "lookback_minutes": 5, "threshold_z": 1.5, "hold_minutes": 5,
    }


def test_2025_is_not_loaded_or_evaluated_when_2024_fails(monkeypatch):
    loaded: list[tuple[str, int]] = []
    evaluated: list[int] = []
    selected = {
        "parameters": {"lookback_minutes": 5, "threshold_z": 1.5, "hold_minutes": 5},
        "eligible": True,
        "metrics": _summary(2023, 80, 800, 10, 1.2, 100),
    }

    def loader(symbol: str, year: int):
        loaded.append((symbol, year))
        return pd.DataFrame()

    def evaluate(features, year, parameters):
        evaluated.append(year)
        return _summary(year, 10, -100, -10, 0.5, 100, four_tick_net=-120), []

    monkeypatch.setattr(v33, "build_pair_sessions", lambda *args, **kwargs: [])
    monkeypatch.setattr(v33, "build_feature_rows", lambda sessions: {key: [] for key in v33.LOOKBACKS})
    monkeypatch.setattr(v33, "evaluate_discovery", lambda features: ([], selected, []))
    monkeypatch.setattr(v33, "evaluate_selected", evaluate)

    result, _ = v33.run_study(loader)
    assert result["verdict"] == "FAILED_2024_VALIDATION"
    assert result["years_loaded"] == [2023, 2024]
    assert evaluated == [2024]
    assert ("MES", 2025) not in loaded and ("MNQ", 2025) not in loaded
