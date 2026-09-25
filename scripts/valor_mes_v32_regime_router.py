"""MES v32 compact ATR regime-router study over 2023-2025 only.

Research only. The opportunity set is rebuilt through the causal, checksummed
MES cache reader from v31, then restricted to four frozen raw-gross survivor
cells. Fills remain trade-print proxies (next-minute open to final hold-minute
close), not executable BBO. The one-tick case is an unverified planning proxy;
the execution calibration contains no historical fill/fee rows.

All expanding ATR thresholds and shadow-route performance use prior dates only.
Rows from one date are evaluated as a batch and enter history only after every
decision for that date has been made. No query or loop includes 2026.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import groupby
from pathlib import Path
import hashlib
import math
import os
import subprocess
import sys

from scripts import valor_mes_v31_edge_map as v31


STUDY = "valor-mes-v32-regime-router-20260925"
LOCK = 672202609
YEARS = (2023, 2024, 2025)
FEE = 3.0
MIN_PRIOR_OBSERVATIONS = 60

BASE_CELLS = (
    (30, "afternoon", "momentum"),
    (60, "afternoon", "momentum"),
    (120, "late_morning", "momentum"),
    (120, "opening_morning", "mean_reversion"),
)
BASE_CELL_PRIORITY = {cell: rank for rank, cell in enumerate(BASE_CELLS)}
ATR_EXCLUSION_CELLS = {
    (30, "afternoon", "momentum"),
    (120, "opening_morning", "mean_reversion"),
}
VARIANTS = (
    "combined_baseline",
    "atr_low_tercile_exclusion",
    "atr_tercile_shadow_router",
)
COST_CASES = (
    ("raw_gross", None, 0.0),
    ("fee_only_0t", 0, FEE),
    ("planning_1t_unverified", 1, FEE),
    ("severe_4t", 4, FEE),
)


class StudyVersionConflict(RuntimeError):
    """A completed fixed-ID study cannot be replaced by different source."""


def cell_key(row: dict) -> tuple[int, str, str]:
    return (int(row["horizon"]), row["time_bucket"], row["direction"])


def linear_quantile(values: list[float], probability: float) -> float:
    """Return the deterministic linear (R-7 / NumPy default) quantile."""
    if not values:
        raise ValueError("quantile requires at least one value")
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between zero and one")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def atr_bin(value: float, lower: float, upper: float) -> str:
    """Classify ATR with stable inclusive boundaries."""
    if value < lower:
        return "low"
    if value < upper:
        return "mid"
    return "high"


def planning_net(row: dict) -> float:
    """Price one shadow observation at the explicitly unverified 1t case."""
    return v31.net_dollars(row["raw_move"], row["side"], 1, FEE)


def performance_metrics(values: list[float]) -> dict:
    wins = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    total = sum(values)
    return {
        "observations": len(values),
        "net_dollars": round(total, 6),
        "gross_profit": round(wins, 6),
        "gross_loss": round(losses, 6),
        "profit_factor": round(wins / losses, 6) if losses else None,
        "avg_net_trade": round(total / len(values), 6) if values else None,
    }


def route_is_eligible(metrics: dict) -> bool:
    """Apply the frozen v32 prior-shadow promotion gate."""
    profit_factor = metrics["profit_factor"]
    profit_factor_passes = (
        profit_factor is not None and profit_factor >= 1.10
    ) or (
        metrics["observations"] > 0
        and metrics["gross_profit"] > 0
        and metrics["gross_loss"] == 0
    )
    return (
        metrics["observations"] >= MIN_PRIOR_OBSERVATIONS
        and metrics["net_dollars"] > 0
        and profit_factor_passes
        and metrics["avg_net_trade"] is not None
        and metrics["avg_net_trade"] > 0
    )


def _chronological_groups(rows: list[dict]):
    ordered = sorted(
        rows,
        key=lambda row: (
            int(row["year"]), row["date"], int(row["entry_index"]),
            BASE_CELL_PRIORITY[cell_key(row)],
        ),
    )
    return groupby(ordered, key=lambda row: (int(row["year"]), row["date"]))


def select_global_non_overlapping(rows: list[dict], rank_by_route: bool = False) -> list[dict]:
    """Select at most one global MES position, including simultaneous entries."""
    selected: list[dict] = []
    last_exit_by_year: dict[int, str] = {}
    ordered = sorted(
        rows,
        key=lambda row: (
            int(row["year"]), row["entry_time"],
            -float(row.get("route_prior_avg_net") or 0.0) if rank_by_route else 0.0,
            BASE_CELL_PRIORITY[cell_key(row)],
            int(row["exit_index"]),
        ),
    )
    for (year, entry_time), simultaneous in groupby(
        ordered, key=lambda row: (int(row["year"]), row["entry_time"])
    ):
        if year in last_exit_by_year and entry_time < last_exit_by_year[year]:
            continue
        candidates = list(simultaneous)
        chosen = candidates[0]
        selected.append(chosen)
        last_exit_by_year[year] = chosen["exit_time"]
    return selected


def combined_baseline(rows: list[dict]) -> list[dict]:
    annotated = []
    for row in rows:
        item = dict(row)
        item.update({
            "variant": "combined_baseline",
            "atr_bin": None,
            "route_prior_observations": None,
            "route_prior_avg_net": None,
            "route_reason": "frozen base cell",
        })
        annotated.append(item)
    return select_global_non_overlapping(annotated)


def atr_low_tercile_exclusion(rows: list[dict]) -> list[dict]:
    """Apply the two-cell ATR exclusion with prior-date-only thresholds."""
    atr_history: dict[tuple, list[float]] = defaultdict(list)
    candidates: list[dict] = []
    for _, date_rows_iter in _chronological_groups(rows):
        date_rows = list(date_rows_iter)
        thresholds: dict[tuple, float] = {}
        for key in ATR_EXCLUSION_CELLS:
            if len(atr_history[key]) >= MIN_PRIOR_OBSERVATIONS:
                thresholds[key] = linear_quantile(atr_history[key], 1 / 3)

        for row in date_rows:
            key = cell_key(row)
            value = float(row["features"]["atr_bps"])
            threshold = thresholds.get(key)
            excluded = threshold is not None and value < threshold
            if excluded:
                continue
            item = dict(row)
            item.update({
                "variant": "atr_low_tercile_exclusion",
                "atr_bin": "low" if excluded else None,
                "route_prior_observations": len(atr_history[key]),
                "route_prior_avg_net": None,
                "route_reason": (
                    "warmup baseline behavior" if key in ATR_EXCLUSION_CELLS and threshold is None
                    else "at-or-above prior exact-cell ATR 33rd percentile"
                    if key in ATR_EXCLUSION_CELLS
                    else "cell unchanged by ATR exclusion"
                ),
                "atr_q33_prior": None if threshold is None else round(threshold, 9),
            })
            candidates.append(item)

        # Same-date ATR observations become available only after all decisions.
        for row in date_rows:
            atr_history[cell_key(row)].append(float(row["features"]["atr_bps"]))
    return select_global_non_overlapping(candidates)


def atr_tercile_shadow_router(rows: list[dict]) -> list[dict]:
    """Route only causally profitable cell/ATR bins, then globally deconflict."""
    atr_history: dict[tuple, list[float]] = defaultdict(list)
    shadow_history: dict[tuple, list[float]] = defaultdict(list)
    eligible_candidates: list[dict] = []

    for _, date_rows_iter in _chronological_groups(rows):
        date_rows = list(date_rows_iter)
        thresholds: dict[tuple, tuple[float, float]] = {}
        for key in BASE_CELLS:
            if len(atr_history[key]) >= MIN_PRIOR_OBSERVATIONS:
                thresholds[key] = (
                    linear_quantile(atr_history[key], 1 / 3),
                    linear_quantile(atr_history[key], 2 / 3),
                )

        classified: list[tuple[dict, tuple, str]] = []
        for row in date_rows:
            key = cell_key(row)
            cutoffs = thresholds.get(key)
            if cutoffs is None:
                continue
            bin_name = atr_bin(float(row["features"]["atr_bps"]), *cutoffs)
            route_key = (key, bin_name)
            prior = performance_metrics(shadow_history[route_key])
            classified.append((row, route_key, bin_name))
            if not route_is_eligible(prior):
                continue
            item = dict(row)
            item.update({
                "variant": "atr_tercile_shadow_router",
                "atr_bin": bin_name,
                "route_prior_observations": prior["observations"],
                "route_prior_avg_net": prior["avg_net_trade"],
                "route_reason": "prior-date shadow route passed frozen planning gate",
                "route_prior_metrics": prior,
                "atr_q33_prior": round(cutoffs[0], 9),
                "atr_q67_prior": round(cutoffs[1], 9),
            })
            eligible_candidates.append(item)

        # Current-date ATR and outcomes are withheld until all decisions are frozen.
        for row in date_rows:
            atr_history[cell_key(row)].append(float(row["features"]["atr_bps"]))
        for row, route_key, _ in classified:
            shadow_history[route_key].append(planning_net(row))

    return select_global_non_overlapping(eligible_candidates, rank_by_route=True)


def annual_metrics(rows: list[dict], ticks: int | None, fee: float) -> dict:
    pnl = [v31.net_dollars(row["raw_move"], row["side"], ticks, fee) for row in rows]
    wins = sum(value for value in pnl if value > 0)
    losses = -sum(value for value in pnl if value < 0)
    equity = peak = max_drawdown = 0.0
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return {
        "trades": len(rows),
        "active_days": len({row["date"] for row in rows}),
        "net_dollars": round(sum(pnl), 6),
        "gross_profit": round(wins, 6),
        "gross_loss": round(losses, 6),
        "avg_trade": round(sum(pnl) / len(pnl), 6) if pnl else None,
        "profit_factor": round(wins / losses, 6) if losses else None,
        "win_rate": round(100 * sum(value > 0 for value in pnl) / len(pnl), 6) if pnl else None,
        "closed_trade_max_drawdown": round(max_drawdown, 6),
        "fill_convention": "next-minute open to final hold-minute close; trade-print proxy, not executable BBO",
    }


def promotion_audit(annual_by_variant: dict[str, dict[int, dict]]) -> dict:
    audit = {}
    for variant, years in annual_by_variant.items():
        complete = all(year in years for year in YEARS)
        audit[variant] = {
            "basis": "planning_1t_unverified",
            "planning_case_is_realistic": False,
            "yearly": {str(year): years.get(year) for year in YEARS},
            "preferred_180_trades_each_year": complete and all(
                years[year]["trades"] >= 180 for year in YEARS
            ),
            "positive_net_every_year": complete and all(
                years[year]["net_dollars"] > 0 for year in YEARS
            ),
            "preferred_pf_1_20_each_year": complete and all(
                (
                    years[year]["profit_factor"] is not None
                    and years[year]["profit_factor"] >= 1.20
                ) or (
                    years[year]["trades"] > 0
                    and years[year]["gross_profit"] > 0
                    and years[year]["gross_loss"] == 0
                )
                for year in YEARS
            ),
            "preferred_avg_net_at_least_8_each_year": complete and all(
                years[year]["avg_trade"] is not None
                and years[year]["avg_trade"] >= 8.0
                for year in YEARS
            ),
            "automatic_promotion": False,
        }
    return audit


def _build_opportunities(cur) -> tuple[list[dict], dict[int, int]]:
    rows: list[dict] = []
    sessions: dict[int, int] = {}
    for year in YEARS:
        year_rows, session_count = v31._build_year_opportunities(cur, year)
        sessions[year] = session_count
        rows.extend(row for row in year_rows if cell_key(row) in BASE_CELL_PRIORITY)
    return rows, sessions


def _create_tables(cur) -> None:
    cur.execute(
        """CREATE TABLE IF NOT EXISTS valor_mes_v32_state(
             study_id TEXT PRIMARY KEY, status TEXT NOT NULL, detail JSONB NOT NULL,
             updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
           CREATE TABLE IF NOT EXISTS valor_mes_v32_annual(
             study_id TEXT NOT NULL, variant TEXT NOT NULL, year INTEGER NOT NULL,
             cost_model TEXT NOT NULL, adverse_ticks_each_side INTEGER,
             round_trip_fee NUMERIC NOT NULL, metrics JSONB NOT NULL,
             created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
             PRIMARY KEY(study_id,variant,year,cost_model));
           CREATE TABLE IF NOT EXISTS valor_mes_v32_trades(
             study_id TEXT NOT NULL, variant TEXT NOT NULL, year INTEGER NOT NULL,
             trade_date DATE NOT NULL, entry_time TIMESTAMPTZ NOT NULL,
             exit_time TIMESTAMPTZ NOT NULL, horizon_minutes INTEGER NOT NULL,
             time_bucket TEXT NOT NULL, direction TEXT NOT NULL, side INTEGER NOT NULL,
             atr_bin TEXT, raw_move NUMERIC NOT NULL, route JSONB NOT NULL,
             cost_results JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
             PRIMARY KEY(study_id,variant,entry_time));"""
    )


def run() -> None:
    import psycopg2
    from psycopg2.extras import Json, execute_values

    connection = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15)
    connection.autocommit = True
    cur = connection.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,))
    if not cur.fetchone()[0]:
        connection.close()
        return

    own_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    v31_hash = hashlib.sha256(Path(v31.__file__).read_bytes()).hexdigest()
    source_hash = hashlib.sha256(f"{own_hash}:{v31_hash}".encode()).hexdigest()
    try:
        _create_tables(cur)
        cur.execute(
            "SELECT status,detail FROM valor_mes_v32_state WHERE study_id=%s",
            (STUDY,),
        )
        existing = cur.fetchone()
        if existing and existing[0] == "completed":
            if (existing[1] or {}).get("source_sha256") == source_hash:
                return
            raise StudyVersionConflict(
                "completed v32 has a different source/dependency hash; use a new study id"
            )

        cur.execute(
            """INSERT INTO valor_mes_v32_state(study_id,status,detail)
               VALUES(%s,'running',%s)
               ON CONFLICT(study_id) DO UPDATE SET status='running',
                 detail=EXCLUDED.detail,updated_at=NOW()""",
            (STUDY, Json({
                "current_version": "v32",
                "current_stage": "evaluating frozen ATR router",
                "source_sha256": source_hash,
                "v31_dependency_sha256": v31_hash,
                "research_only": True,
                "production_changed": False,
                "untouched_next_year": 2026,
                "current_blocker": "planning 1t execution case is unverified",
                "next_action": "finish preregistered variants and audit promotion criteria",
            })),
        )

        opportunities, sessions = _build_opportunities(cur)
        variant_rows = {
            "combined_baseline": combined_baseline(opportunities),
            "atr_low_tercile_exclusion": atr_low_tercile_exclusion(opportunities),
            "atr_tercile_shadow_router": atr_tercile_shadow_router(opportunities),
        }

        annual_rows = []
        trade_rows = []
        planning_annual: dict[str, dict[int, dict]] = defaultdict(dict)
        for variant in VARIANTS:
            selected = variant_rows[variant]
            for year in YEARS:
                year_rows = [row for row in selected if int(row["year"]) == year]
                for cost_model, ticks, fee in COST_CASES:
                    metrics = annual_metrics(year_rows, ticks, fee)
                    metrics["available_sessions"] = sessions[year]
                    metrics["trades_per_session"] = (
                        round(metrics["trades"] / sessions[year], 6)
                        if sessions[year] else None
                    )
                    annual_rows.append(
                        (STUDY, variant, year, cost_model, ticks, fee, Json(metrics))
                    )
                    if cost_model == "planning_1t_unverified":
                        planning_annual[variant][year] = metrics

            for row in selected:
                route = {
                    key: row.get(key)
                    for key in (
                        "route_reason", "route_prior_observations",
                        "route_prior_avg_net", "route_prior_metrics",
                        "atr_q33_prior", "atr_q67_prior",
                    )
                    if key in row
                }
                costs = {
                    name: v31.net_dollars(row["raw_move"], row["side"], ticks, fee)
                    for name, ticks, fee in COST_CASES
                }
                trade_rows.append((
                    STUDY, variant, int(row["year"]), row["date"],
                    row["entry_time"], row["exit_time"], int(row["horizon"]),
                    row["time_bucket"], row["direction"], int(row["side"]),
                    row.get("atr_bin"), float(row["raw_move"]), Json(route), Json(costs),
                ))

        audit = promotion_audit(planning_annual)
        detail = {
            "current_version": "v32",
            "current_stage": "completed compact ATR router audit",
            "source_sha256": source_hash,
            "v31_dependency_sha256": v31_hash,
            "research_only": True,
            "production_changed": False,
            "live_ready": False,
            "untouched_next_year": 2026,
            "years": list(YEARS),
            "base_cells": [
                {"horizon_minutes": cell[0], "time_bucket": cell[1], "direction": cell[2]}
                for cell in BASE_CELLS
            ],
            "variants": list(VARIANTS),
            "atr_evidence_cells": [
                {"horizon_minutes": cell[0], "time_bucket": cell[1], "direction": cell[2]}
                for cell in BASE_CELLS if cell in ATR_EXCLUSION_CELLS
            ],
            "causality": "exact-cell ATR thresholds and shadow outcomes use prior dates only; date batches update afterward",
            "global_position_rule": "one MES position at a time; router ranks simultaneous routes by prior planning average net",
            "fill_convention": "next-minute open to final hold-minute close; trade-print proxy, not executable BBO",
            "execution_calibration": {
                "historical_fill_fee_rows": 0,
                "planning_1t_unverified_is_realistic": False,
                "severe_case_adverse_ticks_each_side": 4,
            },
            "selected_trades": {name: len(rows) for name, rows in variant_rows.items()},
            "promotion_audit": audit,
            "current_blocker": "no executable BBO or broker-fill calibration; planning cost is unverified",
            "next_action": "do not touch 2026 or production; independently review the frozen annual audit",
        }

        connection.autocommit = False
        cur.execute("DELETE FROM valor_mes_v32_annual WHERE study_id=%s", (STUDY,))
        cur.execute("DELETE FROM valor_mes_v32_trades WHERE study_id=%s", (STUDY,))
        if annual_rows:
            execute_values(
                cur,
                """INSERT INTO valor_mes_v32_annual(
                     study_id,variant,year,cost_model,adverse_ticks_each_side,
                     round_trip_fee,metrics) VALUES %s""",
                annual_rows,
                page_size=200,
            )
        if trade_rows:
            execute_values(
                cur,
                """INSERT INTO valor_mes_v32_trades(
                     study_id,variant,year,trade_date,entry_time,exit_time,
                     horizon_minutes,time_bucket,direction,side,atr_bin,raw_move,
                     route,cost_results) VALUES %s""",
                trade_rows,
                page_size=500,
            )
        cur.execute(
            """UPDATE valor_mes_v32_state SET status='completed',detail=%s,updated_at=NOW()
               WHERE study_id=%s""",
            (Json(detail), STUDY),
        )
        connection.commit()
        connection.autocommit = True
    except StudyVersionConflict:
        raise
    except Exception as exc:
        if not connection.autocommit:
            connection.rollback()
            connection.autocommit = True
        cur.execute(
            """INSERT INTO valor_mes_v32_state(study_id,status,detail)
               VALUES(%s,'failed',%s)
               ON CONFLICT(study_id) DO UPDATE SET status='failed',
                 detail=EXCLUDED.detail,updated_at=NOW()""",
            (STUDY, Json({
                "current_version": "v32",
                "current_stage": "failed",
                "source_sha256": source_hash,
                "v31_dependency_sha256": v31_hash,
                "error_type": type(exc).__name__,
                "message": str(exc)[:500],
                "research_only": True,
                "production_changed": False,
                "untouched_next_year": 2026,
                "next_action": "repair the recorded failure without changing preregistered variants",
            })),
        )
        raise
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))
        finally:
            connection.close()


def launch_if_enabled() -> bool:
    """Launch v32 only through its own explicit research flag."""
    flag = os.getenv("VALOR_MES_V32_AUTORUN", "false")
    if flag.lower() not in {"1", "true", "yes", "on"}:
        return False
    environment = dict(
        os.environ,
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    subprocess.Popen(
        [sys.executable, "-m", "scripts.valor_mes_v32_regime_router"],
        env=environment,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
    return True


if __name__ == "__main__":
    run()
