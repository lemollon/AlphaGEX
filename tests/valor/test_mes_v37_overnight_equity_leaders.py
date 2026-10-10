from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from scripts import valor_mes_v37_overnight_equity_leaders as v37


def _bars(timestamp: pd.DatetimeIndex, base: float, tick: float,
          instrument_id: int) -> pd.DataFrame:
    price = base + (np.arange(len(timestamp)) % 8) * tick
    return pd.DataFrame({
        "timestamp": timestamp, "instrument_id": instrument_id,
        "open": price, "high": price + tick, "low": price - tick,
        "close": price, "volume": 100,
    })


def _overnight(day: str, symbol: str, instrument_id: int) -> pd.DataFrame:
    start, end = v37.v36._overnight_bounds(day)
    tick = v37.v35.TICK_SIZES[symbol]
    base = 14_000.0 if symbol == "MNQ" else 2_000.0
    return _bars(pd.date_range(start, end, freq="1min"), base, tick, instrument_id)


def _cash(day: str = "2023-06-01", instrument_id: int = 11) -> pd.DataFrame:
    opening, closing, _ = v37.v33.cash.session(day)
    timestamp = pd.date_range(
        pd.Timestamp(opening).tz_convert("UTC"),
        pd.Timestamp(closing).tz_convert("UTC") - pd.Timedelta(minutes=1),
        freq="1min",
    )
    return _bars(timestamp, 4_000.0, 0.25, instrument_id)


def _feature(day: str = "2023-06-01", **changes) -> v37.LeaderFeature:
    cash = _cash(day)
    start, end = v37.v36._overnight_bounds(day)
    base = v37.LeaderFeature(
        date=day, mes_cash=cash, mes_instrument_id=11,
        mnq_instrument_id=22, m2k_instrument_id=33,
        mnq_overnight_return=2.0, m2k_overnight_return=1.0,
        opening_response=1.0, mnq_first=start, mnq_last=end,
        m2k_first=start, m2k_last=end,
    )
    return replace(base, **changes)


def _summary(year: int, trades: int, net: float, average: float,
             profit_factor: float, drawdown: float, four_tick: float | None = None) -> dict:
    views = {}
    for name, _ in v37.v33.COST_CASES:
        value = four_tick if name == "stress_4t" and four_tick is not None else net
        views[name] = {
            "trade_count": trades, "net_dollars": value, "average_trade": average,
            "gross_profit": max(value, 0), "gross_loss": 1.0,
            "profit_factor": profit_factor, "profit_factor_infinite": False,
            "maximum_drawdown": drawdown, "monthly_pnl": {},
        }
    return {"year": year, "fill_convention": "test", "cost_views": views}


def test_each_leader_overnight_window_enforces_coverage_and_one_contract():
    day = "2023-06-01"
    prepared = v37.prepare_market([_overnight(day, "MNQ", 22)], "MNQ")
    window, reason = v37.leader_window(prepared, day)
    assert reason is None and len(window) == 930

    changed = prepared.copy()
    changed.loc[500:, "instrument_id"] = 23
    assert v37.leader_window(changed, day)[1] == "overnight_contract_change"

    sparse = prepared.drop(prepared.index[10:41])
    assert v37.leader_window(sparse, day)[1] == "overnight_under_900_minutes"


def test_feature_builder_needs_only_leader_overnights_and_complete_mes_cash():
    day = "2023-06-01"
    features, exclusions = v37.build_features({
        "MES": [_cash(day)],
        "MNQ": [_overnight(day, "MNQ", 22)],
        "M2K": [_overnight(day, "M2K", 33)],
    })
    feature = next(item for item in features if item.date == day)
    assert feature.mnq_overnight_return > 0
    assert feature.m2k_overnight_return > 0
    assert feature.opening_response > 0
    assert exclusions[2023]["usable_sessions"] == 1


def test_modes_require_same_nonzero_leader_sign_and_opening_confirmation_or_rejection():
    assert v37.signal_side(_feature(), "leader_confirmed") == 1
    assert v37.signal_side(_feature(opening_response=-1), "leader_rejected") == -1
    assert v37.signal_side(
        _feature(mnq_overnight_return=-2, m2k_overnight_return=-1,
                 opening_response=-1), "leader_confirmed",
    ) == -1
    assert v37.signal_side(_feature(m2k_overnight_return=-1), "leader_confirmed") == 0
    assert v37.signal_side(_feature(m2k_overnight_return=0), "leader_rejected") == 0
    assert v37.signal_side(_feature(opening_response=0), "leader_confirmed") == 0


def test_entry_is_0835_open_and_240_minute_exit_is_exact_close():
    feature = _feature()
    feature.mes_cash.loc[5, ["open", "high", "close"]] = 4_003.0
    feature.mes_cash.loc[244, ["high", "close"]] = 4_006.0

    trade = v37.generate_trades([feature], 2023, "leader_confirmed", 240)[0]
    assert trade["decision_time"] == (feature.mes_cash.timestamp.iloc[4] + pd.Timedelta(minutes=1)).isoformat()
    assert trade["entry_time"] == feature.mes_cash.timestamp.iloc[5].isoformat()
    assert trade["entry_price"] == 4_003.0
    assert trade["exit_time"] == (feature.mes_cash.timestamp.iloc[244] + pd.Timedelta(minutes=1)).isoformat()
    assert trade["exit_price"] == 4_006.0


def test_missing_or_changed_mes_execution_path_skips_trade():
    gap = _feature()
    gap.mes_cash.loc[100, "timestamp"] += pd.Timedelta(seconds=30)
    assert v37.generate_trades([gap], 2023, "leader_confirmed", 120) == []

    roll = _feature()
    roll.mes_cash.loc[100:, "instrument_id"] = 12
    assert v37.generate_trades([roll], 2023, "leader_confirmed", 120) == []


def test_costs_and_deterministic_cell_selection(monkeypatch):
    trades = [
        {"date": "2023-01-03", "gross_dollars": 20.0},
        {"date": "2023-01-04", "gross_dollars": -10.0},
        {"date": "2023-02-01", "gross_dollars": 5.0},
    ]
    for trade in trades:
        for name, ticks in v37.v33.COST_CASES[1:]:
            trade[name] = v37.v33._cost(trade["gross_dollars"], ticks)
    two = v37.v33.summarize_cell(trades, 2023)["cost_views"]["selection_2t"]
    assert two["net_dollars"] == -9.0 and two["maximum_drawdown"] == 21.0

    tied = _summary(2023, 80, 800.0, 10.0, 1.2, 100.0, four_tick=100.0)
    monkeypatch.setattr(v37, "generate_trades", lambda *args, **kwargs: [])
    monkeypatch.setattr(v37.v33, "summarize_cell", lambda *args, **kwargs: tied)
    cells, selected, _ = v37.evaluate_discovery([])
    assert len(cells) == 8
    assert selected["parameters"] == {"mode": "leader_confirmed", "hold_minutes": 30}


def test_sequential_firewall_keeps_2025_unopened_after_2024_failure(monkeypatch):
    loaded, evaluated = [], []
    selected = {"parameters": {"mode": "leader_confirmed", "hold_minutes": 30},
                "eligible": True}

    def loader(symbol: str, year: int) -> pd.DataFrame:
        loaded.append((symbol, year))
        return pd.DataFrame()

    def evaluate(features, year, parameters):
        evaluated.append(year)
        return _summary(year, 10, -100, -10, 0.5, 100, four_tick=-120), []

    monkeypatch.setattr(v37, "build_features", lambda frames: ([], {}))
    monkeypatch.setattr(v37, "evaluate_discovery", lambda features: ([], selected, []))
    monkeypatch.setattr(v37, "evaluate_selected", evaluate)

    result, _ = v37.run_study(loader)
    assert result["verdict"] == "FAILED_2024_VALIDATION"
    assert result["years_loaded"] == [2023, 2024]
    assert evaluated == [2024]
    assert all((symbol, 2025) not in loaded for symbol in v37.SYMBOLS)
