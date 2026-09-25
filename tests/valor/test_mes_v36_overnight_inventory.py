from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from scripts import valor_mes_v36_overnight_inventory as v36


def _bars(timestamp: pd.DatetimeIndex, base: float = 4_000.0,
          instrument_id: int = 11) -> pd.DataFrame:
    price = base + (np.arange(len(timestamp)) % 8) * 0.25
    return pd.DataFrame({
        "timestamp": timestamp, "instrument_id": instrument_id,
        "open": price, "high": price + 0.25, "low": price - 0.25,
        "close": price, "volume": 100,
    })


def _raw_session(day: str = "2023-06-01", include_maintenance_edge: bool = False) -> pd.DataFrame:
    cash_day = date.fromisoformat(day)
    previous = cash_day - timedelta(days=1)
    start = pd.Timestamp(datetime.combine(previous, time(17, 0), tzinfo=v36.CT)).tz_convert("UTC")
    _, cash_close, _ = v36.v33.cash.session(day)
    end = pd.Timestamp(cash_close).tz_convert("UTC") - pd.Timedelta(minutes=1)
    timestamp = pd.date_range(start, end, freq="1min")
    if include_maintenance_edge:
        timestamp = timestamp.insert(0, start - pd.Timedelta(minutes=1))
    return _bars(timestamp)


def _cash_frame(day: str, contract: int = 11, width: float = 2.0) -> pd.DataFrame:
    opening, closing, _ = v36.v33.cash.session(day)
    timestamp = pd.date_range(
        pd.Timestamp(opening).tz_convert("UTC"),
        pd.Timestamp(closing).tz_convert("UTC") - pd.Timedelta(minutes=1),
        freq="1min",
    )
    frame = _bars(timestamp, instrument_id=contract)
    frame["high"] = 4_000 + width
    frame["low"] = 4_000.0
    frame["close"] = 4_001.0
    return frame


def _feature(day: str = "2023-06-01", **changes) -> v36.FeatureSession:
    cash = _cash_frame(day)
    base = v36.FeatureSession(
        date=day, cash=cash, instrument_id=11, atr_prior=4.0,
        overnight_move=2.0, overnight_efficiency=0.5,
        last_hour_return=1.0, opening_response=1.0,
        overnight_first=pd.Timestamp(cash.timestamp.iloc[0]) - pd.Timedelta(hours=15, minutes=30),
        overnight_last=pd.Timestamp(cash.timestamp.iloc[0]) - pd.Timedelta(minutes=1),
    )
    return replace(base, **changes)


def _summary(year: int, trades: int, net: float, average: float,
             profit_factor: float, drawdown: float, four_tick: float | None = None) -> dict:
    views = {}
    for name, _ in v36.v33.COST_CASES:
        value = four_tick if name == "stress_4t" and four_tick is not None else net
        views[name] = {
            "trade_count": trades, "net_dollars": value, "average_trade": average,
            "gross_profit": max(value, 0), "gross_loss": 1.0,
            "profit_factor": profit_factor, "profit_factor_infinite": False,
            "maximum_drawdown": drawdown, "monthly_pnl": {},
        }
    return {"year": year, "fill_convention": "test", "cost_views": views}


def test_overnight_coverage_and_final_hour_requirements():
    day = "2023-06-01"
    prepared = v36.prepare_raw([_raw_session(day)])
    window, reason = v36.overnight_window(prepared, day, 11)
    assert reason is None and len(window) == 930

    start, end = v36._overnight_bounds(day)
    observed_only = prepared.drop(
        prepared[(prepared.timestamp >= start) & (prepared.timestamp <= end)].index[10:20]
    )
    observed_window, reason = v36.overnight_window(observed_only, day, 11)
    assert reason is None and len(observed_window) == 920

    sparse = prepared.drop(prepared[(prepared.timestamp >= start)
                                    & (prepared.timestamp <= end)].index[10:41])
    assert v36.overnight_window(sparse, day, 11)[1] == "overnight_under_900_minutes"

    final_sparse = prepared.drop(
        prepared[(prepared.timestamp >= end - pd.Timedelta(minutes=59))
                 & (prepared.timestamp < end)].index[:6]
    )
    assert v36.overnight_window(final_sparse, day, 11)[1] == "overnight_final_hour_under_55"


def test_maintenance_boundary_is_not_part_of_overnight_path():
    day = "2023-06-01"
    raw = _raw_session(day, include_maintenance_edge=True)
    raw.loc[0, ["open", "high", "low", "close"]] = 9_999.0
    prepared = v36.prepare_raw([raw])
    window, reason = v36.overnight_window(prepared, day, 11)
    start, _ = v36._overnight_bounds(day)
    assert reason is None
    assert window.timestamp.iloc[0] == start
    assert window.open.iloc[0] != 9_999.0


def test_roll_transition_resets_twenty_true_range_history():
    days = v36._calendar_days(2023)[:45]
    sessions = {
        day: _cash_frame(day, contract=11 if index < 22 else 12)
        for index, day in enumerate(days)
    }
    atr = v36.prior_atr(sessions)
    assert days[20] not in atr
    assert days[21] in atr
    assert all(days[index] not in atr for index in range(22, 43))
    assert days[43] in atr


def test_current_cash_day_is_excluded_from_its_atr():
    days = v36._calendar_days(2023)[:22]
    sessions = {day: _cash_frame(day) for day in days}
    baseline = v36.prior_atr(sessions)[days[21]]
    sessions[days[21]] = _cash_frame(days[21], width=100.0)
    assert v36.prior_atr(sessions)[days[21]] == baseline


def test_mode_signs_are_frozen():
    assert v36.signal_side(_feature(), "confirmed_continuation") == 1
    assert v36.signal_side(
        _feature(overnight_move=-2, last_hour_return=-1, opening_response=-1),
        "confirmed_continuation",
    ) == -1
    assert v36.signal_side(_feature(opening_response=-1), "opening_rejection") == -1
    assert v36.signal_side(_feature(last_hour_return=-1), "confirmed_continuation") == 0
    assert v36.signal_side(_feature(opening_response=1), "opening_rejection") == 0


def test_entry_is_next_0835_open_and_exit_is_exact_hold_close():
    feature = _feature()
    feature.cash.loc[5, ["open", "high", "close"]] = 4_003.0
    feature.cash.loc[34, ["high", "close"]] = 4_005.0

    trade = v36.generate_trades(
        [feature], 2023, "confirmed_continuation", 0.25, 0.05, 30,
    )[0]
    assert trade["decision_time"] == (feature.cash.timestamp.iloc[4] + pd.Timedelta(minutes=1)).isoformat()
    assert trade["entry_time"] == feature.cash.timestamp.iloc[5].isoformat()
    assert trade["entry_price"] == 4_003.0
    assert trade["exit_time"] == (feature.cash.timestamp.iloc[34] + pd.Timedelta(minutes=1)).isoformat()
    assert trade["exit_price"] == 4_005.0


def test_costs_and_deterministic_written_order_selection(monkeypatch):
    trades = [
        {"date": "2023-01-03", "gross_dollars": 20.0},
        {"date": "2023-01-04", "gross_dollars": -10.0},
        {"date": "2023-02-01", "gross_dollars": 5.0},
    ]
    for trade in trades:
        for name, ticks in v36.v33.COST_CASES[1:]:
            trade[name] = v36.v33._cost(trade["gross_dollars"], ticks)
    two = v36.v33.summarize_cell(trades, 2023)["cost_views"]["selection_2t"]
    assert two["net_dollars"] == -9.0 and two["maximum_drawdown"] == 21.0

    tied = _summary(2023, 80, 800.0, 10.0, 1.2, 100.0, four_tick=100.0)
    monkeypatch.setattr(v36, "generate_trades", lambda *args, **kwargs: [])
    monkeypatch.setattr(v36.v33, "summarize_cell", lambda *args, **kwargs: tied)
    _, selected, _ = v36.evaluate_discovery([])
    assert selected["parameters"] == {
        "mode": "confirmed_continuation", "magnitude_atr": 0.25,
        "efficiency": 0.05, "hold_minutes": 30,
    }


def test_2025_stays_unopened_when_2024_fails(monkeypatch):
    loaded, evaluated = [], []
    selected = {
        "parameters": {"mode": "confirmed_continuation", "magnitude_atr": 0.25,
                       "efficiency": 0.05, "hold_minutes": 30},
        "eligible": True,
    }

    def loader(symbol: str, year: int) -> pd.DataFrame:
        loaded.append((symbol, year))
        return pd.DataFrame()

    def evaluate(features, year, parameters):
        evaluated.append(year)
        return _summary(year, 10, -100, -10, 0.5, 100, four_tick=-120), []

    monkeypatch.setattr(v36, "build_features", lambda frames: ([], {}))
    monkeypatch.setattr(v36, "evaluate_discovery", lambda features: ([], selected, []))
    monkeypatch.setattr(v36, "evaluate_selected", evaluate)

    result, _ = v36.run_study(loader)
    assert result["verdict"] == "FAILED_2024_VALIDATION"
    assert result["years_loaded"] == [2023, 2024]
    assert evaluated == [2024]
    assert ("MES", 2025) not in loaded
