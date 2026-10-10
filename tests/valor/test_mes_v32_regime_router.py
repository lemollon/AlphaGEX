from datetime import date, timedelta

from scripts.valor_mes_v32_regime_router import (
    FEE,
    atr_low_tercile_exclusion,
    atr_tercile_shadow_router,
    annual_metrics,
    launch_if_enabled,
    linear_quantile,
    select_global_non_overlapping,
)


def _row(
    sequence: int,
    *,
    atr: float = 10.0,
    raw_move: float = 2.0,
    horizon: int = 30,
    bucket: str = "afternoon",
    direction: str = "momentum",
    trade_date: str | None = None,
    entry_index: int | None = None,
    entry_clock: str = "13:00:00",
    exit_clock: str = "13:30:00",
) -> dict:
    day = trade_date or (date(2023, 1, 1) + timedelta(days=sequence)).isoformat()
    entry = sequence * 200 if entry_index is None else entry_index
    return {
        "year": 2023,
        "date": day,
        "entry_time": f"{day}T{entry_clock}-05:00",
        "exit_time": f"{day}T{exit_clock}-05:00",
        "entry_index": entry,
        "exit_index": entry + horizon - 1,
        "horizon": horizon,
        "time_bucket": bucket,
        "direction": direction,
        "side": 1,
        "raw_move": raw_move,
        "features": {"atr_bps": atr},
    }


def test_prior_date_threshold_and_same_day_batch_are_causal():
    prior = [_row(index, atr=float(index + 1)) for index in range(60)]
    current_date = date(2023, 4, 1).isoformat()
    below = _row(60, atr=20.0, trade_date=current_date, entry_index=12_000)
    above = _row(
        61, atr=21.0, trade_date=current_date, entry_index=12_050,
        entry_clock="14:00:00", exit_clock="14:30:00",
    )

    selected = atr_low_tercile_exclusion(prior + [below, above])

    assert linear_quantile([float(index + 1) for index in range(60)], 1 / 3) == 20.666666666666664
    assert not any(row["entry_index"] == 12_000 for row in selected)
    accepted = next(row for row in selected if row["entry_index"] == 12_050)
    assert accepted["route_prior_observations"] == 60
    assert accepted["atr_q33_prior"] == 20.666666667


def test_exclusion_warmup_allows_baseline_but_router_waits():
    rows = [_row(index, atr=5.0) for index in range(10)]

    assert len(atr_low_tercile_exclusion(rows)) == 10
    assert atr_tercile_shadow_router(rows) == []


def test_shadow_router_batches_same_day_outcomes_without_leakage():
    rows = [_row(index, atr=10.0) for index in range(60)]
    for index in range(60, 120):
        # 50 wins and 10 losses create an eligible high-ATR shadow route.
        move = 2.0 if index < 110 else -1.0
        rows.append(_row(index, atr=10.0, raw_move=move))

    current_date = date(2023, 8, 1).isoformat()
    first = _row(120, atr=10.0, raw_move=-20.0, trade_date=current_date, entry_index=24_000)
    second = _row(
        121, atr=10.0, raw_move=2.0, trade_date=current_date, entry_index=24_050,
        entry_clock="14:00:00", exit_clock="14:30:00",
    )

    selected = atr_tercile_shadow_router(rows + [first, second])
    same_day = [row for row in selected if row["date"] == current_date]

    assert len(same_day) == 2
    assert {row["route_prior_observations"] for row in same_day} == {60}
    assert {row["route_prior_avg_net"] for row in same_day} == {2.0}


def test_global_non_overlap_ranks_simultaneous_routes_then_respects_exit():
    lower = _row(0, horizon=30, entry_index=100)
    lower["route_prior_avg_net"] = 1.0
    higher = _row(0, horizon=60, entry_index=100, exit_clock="14:00:00")
    higher["route_prior_avg_net"] = 3.0
    overlaps = _row(
        0, horizon=30, entry_index=150,
        entry_clock="13:30:00", exit_clock="14:00:00",
    )
    overlaps["route_prior_avg_net"] = 9.0
    starts_after_exit = _row(
        0, horizon=30, entry_index=160,
        entry_clock="14:00:00", exit_clock="14:30:00",
    )
    starts_after_exit["route_prior_avg_net"] = 2.0

    selected = select_global_non_overlapping(
        [lower, higher, overlaps, starts_after_exit], rank_by_route=True
    )

    assert [(row["horizon"], row["entry_index"]) for row in selected] == [
        (60, 100),
        (30, 160),
    ]


def test_cost_accounting_charges_fee_and_both_sides():
    row = _row(0, raw_move=1.0)

    planning = annual_metrics([row], 1, FEE)
    severe = annual_metrics([row], 4, FEE)

    assert planning["net_dollars"] == -0.5
    assert severe["net_dollars"] == -8.0


def test_annual_metrics_reports_frequency_inputs():
    first = _row(0, trade_date="2023-01-03")
    second = _row(1, trade_date="2023-01-03", entry_clock="14:00:00", exit_clock="14:30:00")

    metrics = annual_metrics([first, second], 1, FEE)

    assert metrics["trades"] == 2
    assert metrics["active_days"] == 1


def test_v32_autorun_is_isolated_from_all_older_flags(monkeypatch):
    monkeypatch.delenv("VALOR_MES_V32_AUTORUN", raising=False)
    monkeypatch.setenv("VALOR_MES_V31_AUTORUN", "true")
    monkeypatch.setenv("VALOR_MES_CHOPGUARD_V10_AUTORUN", "true")

    assert launch_if_enabled() is False
