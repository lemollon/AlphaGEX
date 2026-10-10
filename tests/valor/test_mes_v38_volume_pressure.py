from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from scripts import valor_mes_v38_volume_pressure as v38


def _cash(day: str = "2023-06-01", instrument_id: int = 11) -> pd.DataFrame:
    opening, closing, _ = v38.v33.cash.session(day)
    timestamp = pd.date_range(
        pd.Timestamp(opening).tz_convert("UTC"),
        pd.Timestamp(closing).tz_convert("UTC") - pd.Timedelta(minutes=1),
        freq="1min",
    )
    price = 4_000 + (np.arange(len(timestamp)) % 8) * 0.25
    return pd.DataFrame({
        "timestamp": timestamp, "instrument_id": instrument_id,
        "open": price, "high": price + 0.25, "low": price - 0.25,
        "close": price, "volume": np.full(len(timestamp), 100),
    })


def _feature(day: str = "2023-06-01", **changes) -> v38.VolumeFeature:
    base = v38.VolumeFeature(
        date=day, cash=_cash(day), instrument_id=11,
        signed_volume_proxy=0.5, opening_price_response=1.0,
        observation_volume=3_000.0, prior_60_abs_median=0.4,
    )
    return replace(base, **changes)


def _summary(year: int, trades: int, net: float, average: float,
             profit_factor: float, drawdown: float, four_tick: float | None = None) -> dict:
    views = {}
    for name, _ in v38.v33.COST_CASES:
        value = four_tick if name == "stress_4t" and four_tick is not None else net
        views[name] = {
            "trade_count": trades, "net_dollars": value, "average_trade": average,
            "gross_profit": max(value, 0), "gross_loss": 1.0,
            "profit_factor": profit_factor, "profit_factor_infinite": False,
            "maximum_drawdown": drawdown, "monthly_pnl": {},
        }
    return {"year": year, "fill_convention": "test", "cost_views": views}


def test_clv_includes_extremes_midpoint_and_exact_zero_range():
    frame = pd.DataFrame({
        "high": [10.0, 10.0, 10.0, 7.0],
        "low": [8.0, 8.0, 8.0, 7.0],
        "close": [10.0, 8.0, 9.0, 7.0],
    })
    assert v38.bar_clv(frame).tolist() == [1.0, -1.0, 0.0, 0.0]


def test_prior_60_median_excludes_current_session():
    days = v38.v36._calendar_days(2023)[:61]
    features = [
        _feature(day, signed_volume_proxy=float(index + 1))
        for index, day in enumerate(days)
    ]
    assigned = v38.assign_prior_medians(features)
    assert all(feature.prior_60_abs_median is None for feature in assigned[:60])
    assert assigned[60].prior_60_abs_median == 30.5

    features[-1] = replace(features[-1], signed_volume_proxy=999.0)
    assert v38.assign_prior_medians(features)[60].prior_60_abs_median == 30.5


def test_modes_and_directions_are_frozen():
    assert v38.signal_side(_feature(), "flow_follow") == 1
    assert v38.signal_side(
        _feature(signed_volume_proxy=-0.5, opening_price_response=-1),
        "flow_follow",
    ) == -1
    assert v38.signal_side(
        _feature(signed_volume_proxy=0.5, opening_price_response=-1),
        "absorption_reversal",
    ) == -1
    assert v38.signal_side(_feature(), "absorption_reversal") == 0


def test_entry_is_0900_open_and_exit_is_exact_hold_close():
    feature = _feature()
    feature.cash.loc[30, ["open", "high", "close"]] = 4_003.0
    feature.cash.loc[59, ["high", "close"]] = 4_005.0

    trade = v38.generate_trades([feature], 2023, "flow_follow", "all", 30)[0]
    assert trade["decision_time"] == (feature.cash.timestamp.iloc[29] + pd.Timedelta(minutes=1)).isoformat()
    assert trade["entry_time"] == feature.cash.timestamp.iloc[30].isoformat()
    assert trade["entry_price"] == 4_003.0
    assert trade["exit_time"] == (feature.cash.timestamp.iloc[59] + pd.Timedelta(minutes=1)).isoformat()
    assert trade["exit_price"] == 4_005.0


def test_causal_high_is_inclusive_and_requires_prior_60_value():
    equal = _feature(signed_volume_proxy=0.4, prior_60_abs_median=0.4)
    assert len(v38.generate_trades(
        [equal], 2023, "flow_follow", "causal_high", 30,
    )) == 1
    assert v38.generate_trades(
        [replace(equal, prior_60_abs_median=None)],
        2023, "flow_follow", "causal_high", 30,
    ) == []


def test_costs_and_deterministic_cell_selection(monkeypatch):
    trades = [
        {"date": "2023-01-03", "gross_dollars": 20.0},
        {"date": "2023-01-04", "gross_dollars": -10.0},
        {"date": "2023-02-01", "gross_dollars": 5.0},
    ]
    for trade in trades:
        for name, ticks in v38.v33.COST_CASES[1:]:
            trade[name] = v38.v33._cost(trade["gross_dollars"], ticks)
    two = v38.v33.summarize_cell(trades, 2023)["cost_views"]["selection_2t"]
    assert two["net_dollars"] == -9.0 and two["maximum_drawdown"] == 21.0

    tied = _summary(2023, 60, 600.0, 10.0, 1.2, 100.0, four_tick=100.0)
    monkeypatch.setattr(v38, "generate_trades", lambda *args, **kwargs: [])
    monkeypatch.setattr(v38.v33, "summarize_cell", lambda *args, **kwargs: tied)
    cells, selected, _ = v38.evaluate_discovery([])
    assert len(cells) == 16
    assert selected["parameters"] == {
        "mode": "flow_follow", "pressure_regime": "all", "hold_minutes": 30,
    }


def test_later_years_remain_sealed_after_2023_failure(monkeypatch):
    loaded = []

    def loader(symbol: str, year: int) -> pd.DataFrame:
        loaded.append((symbol, year))
        return pd.DataFrame()

    monkeypatch.setattr(v38, "build_features", lambda frames: ([], {}))
    monkeypatch.setattr(v38, "evaluate_discovery", lambda features: ([], None, []))
    result, _ = v38.run_study(loader)
    assert result["verdict"] == "FAMILY_FAIL_DISCOVERY"
    assert result["years_loaded"] == [2023]
    assert loaded == [("MES", 2023)]


def test_v8_input_validation_rejects_negative_volume_and_off_grid_prices():
    negative = _cash()
    negative.loc[0, "volume"] = -1
    with pytest.raises(ValueError, match="Invalid OHLCV"):
        v38.build_features([negative])

    off_grid = _cash()
    off_grid.loc[0, "close"] = 4_000.1
    with pytest.raises(ValueError, match="Off-grid"):
        v38.build_features([off_grid])
