"""MES v31 raw-edge map over the frozen 2023-2025 development window.

Research only. Reads checksummed cached Databento MES one-minute OHLCV from
Postgres, never calls a vendor or broker, and never reads 2026. The study uses
one fixed signal definition (the sign of the completed trailing 15-minute
return) and maps momentum versus mean reversion across predefined time buckets
and 15/30/60/120-minute holding horizons.

Fills are trade-print proxies: next-minute open to the close of the final hold
minute. Gross results are shown without costs; fee/slippage cases charge $3 per
round trip and 0/1/2/4 adverse ticks on both entry and exit. The 1-tick case is
an unverified planning proxy, not calibrated live execution.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import hashlib
import io
import math
import os
import statistics
import subprocess
import sys


STUDY = "valor-mes-v31-edge-map-20260925"
LOCK = 671202609
YEARS = (2023, 2024, 2025)
HORIZONS = (15, 30, 60, 120)
SIGNAL_LOOKBACK_MINUTES = 15
GRID_MINUTES = 15
FEE = 3.0
TICK = 0.25
POINT_VALUE = 5.0

TIME_BUCKETS = (
    ("opening_morning", 525, 630),   # 08:45 <= entry < 10:30 CT
    ("late_morning", 630, 690),      # 10:30 <= entry < 11:30 CT
    ("midday", 690, 750),            # 11:30 <= entry < 12:30 CT
    ("afternoon", 750, 840),         # 12:30 <= entry < 14:00 CT
    ("late_session", 840, 900),      # 14:00 <= entry < 15:00 CT
)

COST_CASES = (
    ("raw_gross", None, 0.0),
    ("fee_only_0t", 0, FEE),
    ("planning_1t_unverified", 1, FEE),
    ("stress_2t", 2, FEE),
    ("severe_4t", 4, FEE),
)
CLUSTER_COSTS = {"planning_1t_unverified", "severe_4t"}
FEATURES = (
    "atr_bps",
    "directional_efficiency_15",
    "signal_strength_atr",
    "vwap_distance_atr",
    "or_width_atr",
    "or_location",
    "recent_range_atr",
    "volume_ratio_60m",
    "overnight_gap_atr",
    "prior_range_atr",
    "prior_close_location",
)


class StudyVersionConflict(RuntimeError):
    """A completed fixed-ID study cannot be replaced by different source."""


def time_bucket(entry_minute: int) -> str | None:
    """Return the preregistered CT entry bucket for a minute-of-day."""
    for name, start, end in TIME_BUCKETS:
        if start <= entry_minute < end:
            return name
    return None


def net_dollars(raw_move: float, side: int, adverse_ticks_each_side: int | None,
                round_trip_fee: float) -> float:
    """Price a one-contract MES trade under one explicit execution case."""
    if side not in (-1, 1):
        raise ValueError("side must be -1 or 1")
    slippage = 0.0 if adverse_ticks_each_side is None else (
        2 * adverse_ticks_each_side * TICK * POINT_VALUE
    )
    return round(side * raw_move * POINT_VALUE - slippage - round_trip_fee, 6)


def select_non_overlapping(rows: list[dict]) -> list[dict]:
    """Accept chronological entries only after the preceding position exits."""
    selected: list[dict] = []
    last_exit = -1
    for row in sorted(rows, key=lambda z: (z["entry_index"], z["exit_index"])):
        if int(row["entry_index"]) <= last_exit:
            continue
        selected.append(row)
        last_exit = int(row["exit_index"])
    return selected


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 6) if values else None


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 6) if values else None


def _five_minute_volume(frame, raw_index: int) -> float | None:
    if raw_index < 4:
        return None
    window = frame.iloc[raw_index - 4:raw_index + 1]
    if len(window) != 5 or window.segment.nunique() != 1:
        return None
    return float(window.volume.sum())


def _build_year_opportunities(cur, year: int) -> tuple[list[dict], int]:
    import numpy as np
    import pandas as pd
    from scripts import valor_mes_rebuild_v4 as core

    cur.execute(
        "SELECT sha256, parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",
        (f"GLBX.MDP3:ohlcv-1m:MES.v.0:{year}",),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"missing MES cache {year}")
    body = bytes(row[1])
    digest = hashlib.sha256(body).hexdigest()
    expected = core.CACHE_HASHES[year]
    if digest != row[0] or digest != expected:
        raise ValueError(f"cache checksum mismatch {year}")

    data = core.prepare(pd.read_parquet(io.BytesIO(body)))
    bars, previous = core.context(data)
    opens = data.open.to_numpy(float)
    closes = data.close.to_numpy(float)
    segments = data.segment.to_numpy()
    dates = data.date.to_numpy()
    timestamps = data.timestamp
    opportunities: list[dict] = []
    full_groups = []
    for _, group in bars[bars.rth].groupby(["date", "instrument_id"], sort=False):
        rows = list(group.itertuples(index=False))
        contiguous = all(
            rows[index].bar_start - rows[index - 1].bar_start == pd.Timedelta(minutes=5)
            for index in range(1, len(rows))
        )
        if (len(rows) != 78 or not contiguous or rows[0].minute != core.START or
                rows[-1].minute != core.END - 5):
            continue
        full_groups.append(rows)
    sessions = len({rows[0].date for rows in full_groups})

    for rows in full_groups:
        history = []
        volumes: list[float | None] = []
        session_open = float(rows[0].open)
        for current in rows:
            history.append(current)
            volumes.append(_five_minute_volume(data, int(current.raw_index)))
            if len(history) < 3:
                continue
            if current.bar_start - history[-3].bar_start != pd.Timedelta(minutes=10):
                continue

            entry_index = int(current.raw_index) + 1
            if entry_index >= len(data) or segments[entry_index] != segments[int(current.raw_index)]:
                continue
            if timestamps.iloc[entry_index] - timestamps.iloc[int(current.raw_index)] != pd.Timedelta(minutes=1):
                continue
            entry_minute = int(data.minute.iloc[entry_index])
            bucket = time_bucket(entry_minute)
            if bucket is None or (entry_minute - (core.START + 15)) % GRID_MINUTES != 0:
                continue

            atr = _finite(current.atr)
            reference = float(current.close)
            signal_move = reference - float(history[-3].open)
            if atr is None or atr <= 0 or signal_move == 0:
                continue
            recent = history[-3:]
            path_points = [float(recent[0].open)] + [float(z.close) for z in recent]
            path = sum(abs(path_points[j] - path_points[j - 1]) for j in range(1, len(path_points)))
            recent_range = max(float(z.high) for z in recent) - min(float(z.low) for z in recent)
            prior = previous.get(current.date)
            if prior is not None and prior.get("instrument_id") != current.instrument_id:
                prior = None

            prior_range_atr = prior_close_location = overnight_gap_atr = None
            if prior is not None:
                prior_atr = _finite(prior.get("atr20"))
                prior_range = float(prior["high"]) - float(prior["low"])
                if prior_atr is not None and prior_atr > 0:
                    prior_range_atr = prior_range / prior_atr
                    overnight_gap_atr = (session_open - float(prior["close"])) / prior_atr
                if prior_range > 0:
                    prior_close_location = (float(prior["close"]) - float(prior["low"])) / prior_range

            or_high = _finite(current.or_high)
            or_low = _finite(current.or_low)
            or_width = None if or_high is None or or_low is None else or_high - or_low
            vwap = _finite(current.vwap)
            prior_volumes = [float(v) for v in volumes[-13:-1] if v is not None]
            current_volume = volumes[-1]
            volume_ratio = None
            if current_volume is not None and len(prior_volumes) == 12:
                baseline = statistics.fmean(prior_volumes)
                if baseline > 0:
                    volume_ratio = current_volume / baseline

            common_features = {
                "atr_bps": atr / reference * 10_000 if reference > 0 else None,
                "directional_efficiency_15": abs(signal_move) / path if path > 0 else 0.0,
                "signal_strength_atr": abs(signal_move) / atr,
                "vwap_distance_atr": None if vwap is None else (reference - vwap) / atr,
                "or_width_atr": None if or_width is None or or_width <= 0 else or_width / atr,
                "or_location": None if or_width is None or or_width <= 0 else (reference - or_low) / or_width,
                "recent_range_atr": recent_range / atr,
                "volume_ratio_60m": volume_ratio,
                "overnight_gap_atr": overnight_gap_atr,
                "prior_range_atr": prior_range_atr,
                "prior_close_location": prior_close_location,
            }

            signal_side = 1 if signal_move > 0 else -1
            for horizon in HORIZONS:
                exit_index = entry_index + horizon - 1
                if exit_index >= len(data):
                    continue
                if (segments[exit_index] != segments[entry_index] or
                        dates[exit_index] != dates[entry_index] or
                        int(data.minute.iloc[exit_index]) >= core.END):
                    continue
                raw_move = float(closes[exit_index] - opens[entry_index])
                for direction, side in (("momentum", signal_side),
                                        ("mean_reversion", -signal_side)):
                    features = dict(common_features)
                    # Positive means price is on the trade's side of VWAP.
                    if features["vwap_distance_atr"] is not None:
                        features["vwap_distance_atr"] *= side
                    opportunities.append({
                        "year": year,
                        "date": str(dates[entry_index]),
                        "entry_time": timestamps.iloc[entry_index].isoformat(),
                        "exit_time": (timestamps.iloc[exit_index] + pd.Timedelta(minutes=1)).isoformat(),
                        "entry_index": entry_index,
                        "exit_index": exit_index,
                        "horizon": horizon,
                        "time_bucket": bucket,
                        "direction": direction,
                        "side": side,
                        "raw_move": raw_move,
                        "features": features,
                    })
    return opportunities, sessions


def _cell_metrics(rows: list[dict], sessions: int, ticks: int | None,
                  fee: float) -> dict:
    import numpy as np

    pnl = np.asarray(
        [net_dollars(r["raw_move"], r["side"], ticks, fee) for r in rows],
        dtype=float,
    )
    wins = float(pnl[pnl > 0].sum()) if len(pnl) else 0.0
    losses = float(-pnl[pnl < 0].sum()) if len(pnl) else 0.0
    equity = np.r_[0.0, pnl.cumsum()] if len(pnl) else np.asarray([0.0])
    active_days = len({r["date"] for r in rows})
    return {
        "trades": len(rows),
        "sessions": sessions,
        "active_days": active_days,
        "trades_per_session": round(len(rows) / sessions, 6) if sessions else None,
        "net_dollars": round(float(pnl.sum()), 6),
        "avg_trade": round(float(pnl.mean()), 6) if len(pnl) else None,
        "profit_factor": round(wins / losses, 6) if losses else None,
        "win_rate": round(float((pnl > 0).mean() * 100), 6) if len(pnl) else None,
        "closed_trade_max_drawdown": round(
            float((np.maximum.accumulate(equity) - equity).max()), 6
        ),
        "fill_convention": "next-minute open to final hold-minute close; trade-print proxy",
    }


def _loss_clusters(rows: list[dict], ticks: int, fee: float) -> tuple[list[list[dict]], set[int]]:
    clusters: list[list[dict]] = []
    current: list[dict] = []
    clustered_ids: set[int] = set()
    for row in rows:
        pnl = net_dollars(row["raw_move"], row["side"], ticks, fee)
        item = dict(row, net=pnl)
        if pnl < 0:
            current.append(item)
        else:
            if len(current) >= 2:
                clusters.append(current)
                clustered_ids.update(id(z["_source"]) for z in current)
            current = []
    if len(current) >= 2:
        clusters.append(current)
        clustered_ids.update(id(z["_source"]) for z in current)
    return clusters, clustered_ids


def _cluster_and_diagnostics(rows: list[dict], ticks: int, fee: float) -> tuple[list[dict], list[dict]]:
    wrapped = [dict(row, _source=row) for row in rows]
    clusters, clustered_ids = _loss_clusters(wrapped, ticks, fee)
    records = []
    for cluster in sorted(clusters, key=lambda g: sum(z["net"] for z in g))[:5]:
        means = {}
        for feature in FEATURES:
            values = [_finite(z["features"].get(feature)) for z in cluster]
            means[feature] = _mean([z for z in values if z is not None])
        records.append({
            "trades": len(cluster),
            "start": cluster[0]["entry_time"],
            "end": cluster[-1]["exit_time"],
            "net_dollars": round(sum(z["net"] for z in cluster), 6),
            "dates": [z["date"] for z in cluster],
            "feature_means": means,
        })

    diagnostics = []
    clustered = [r for r in rows if id(r) in clustered_ids]
    other = [r for r in rows if id(r) not in clustered_ids]
    for feature in FEATURES:
        a = [_finite(r["features"].get(feature)) for r in clustered]
        b = [_finite(r["features"].get(feature)) for r in other]
        a = [x for x in a if x is not None]
        b = [x for x in b if x is not None]
        pooled = a + b
        scale = statistics.pstdev(pooled) if len(pooled) >= 2 else 0.0
        mean_a, mean_b = _mean(a), _mean(b)
        diagnostics.append({
            "feature": feature,
            "clustered_n": len(a),
            "noncluster_n": len(b),
            "clustered_mean": mean_a,
            "clustered_median": _median(a),
            "noncluster_mean": mean_b,
            "noncluster_median": _median(b),
            "standardized_mean_difference": (
                round((mean_a - mean_b) / scale, 6)
                if mean_a is not None and mean_b is not None and scale > 0 else None
            ),
        })
    return records, diagnostics


def _calibration_evidence(cur) -> dict:
    cur.execute("SELECT to_regclass('public.valor_execution_calibration')")
    if cur.fetchone()[0] is None:
        return {"available": False, "reason": "calibration table absent"}
    cur.execute(
        """SELECT run_id, created_at, summary
           FROM valor_execution_calibration ORDER BY created_at DESC LIMIT 1"""
    )
    row = cur.fetchone()
    if not row:
        return {"available": False, "reason": "calibration table empty"}
    summary = row[2] or {}
    return {
        "available": True,
        "run_id": row[0],
        "created_at": row[1].isoformat(),
        "history_rows": summary.get("history_rows"),
        "quote_events": summary.get("quote_events"),
        "broker_slippage_calibrated": summary.get("broker_slippage_calibrated", False),
        "fee_analysis": summary.get("fee_analysis"),
        "conclusion": "insufficient to calibrate realistic fills; 1 tick/side remains an unverified planning proxy",
    }


def _create_tables(cur) -> None:
    cur.execute(
        """CREATE TABLE IF NOT EXISTS valor_mes_v31_state(
             study_id TEXT PRIMARY KEY, status TEXT NOT NULL, detail JSONB NOT NULL,
             updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
           CREATE TABLE IF NOT EXISTS valor_mes_v31_cells(
             study_id TEXT NOT NULL, year INTEGER NOT NULL, horizon_minutes INTEGER NOT NULL,
             time_bucket TEXT NOT NULL, direction TEXT NOT NULL, cost_model TEXT NOT NULL,
             adverse_ticks_each_side INTEGER, round_trip_fee NUMERIC NOT NULL,
             metrics JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
             PRIMARY KEY(study_id,year,horizon_minutes,time_bucket,direction,cost_model));
           CREATE TABLE IF NOT EXISTS valor_mes_v31_clusters(
             study_id TEXT NOT NULL, year INTEGER NOT NULL, horizon_minutes INTEGER NOT NULL,
             time_bucket TEXT NOT NULL, direction TEXT NOT NULL, cost_model TEXT NOT NULL,
             cluster_rank INTEGER NOT NULL, cluster JSONB NOT NULL,
             created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
             PRIMARY KEY(study_id,year,horizon_minutes,time_bucket,direction,cost_model,cluster_rank));
           CREATE TABLE IF NOT EXISTS valor_mes_v31_diagnostics(
             study_id TEXT NOT NULL, year INTEGER NOT NULL, horizon_minutes INTEGER NOT NULL,
             time_bucket TEXT NOT NULL, direction TEXT NOT NULL, cost_model TEXT NOT NULL,
             feature TEXT NOT NULL, summary JSONB NOT NULL,
             created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
             PRIMARY KEY(study_id,year,horizon_minutes,time_bucket,direction,cost_model,feature));"""
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
    source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        _create_tables(cur)
        cur.execute(
            "SELECT status,detail FROM valor_mes_v31_state WHERE study_id=%s",
            (STUDY,),
        )
        existing = cur.fetchone()
        if existing and existing[0] == "completed":
            previous_hash = (existing[1] or {}).get("source_sha256")
            if previous_hash == source_hash:
                return
            raise StudyVersionConflict(
                "completed v31 has a different source hash; use a new study id"
            )
        calibration = _calibration_evidence(cur)
        cur.execute(
            """INSERT INTO valor_mes_v31_state(study_id,status,detail)
               VALUES(%s,'running',%s)
               ON CONFLICT(study_id) DO UPDATE SET status='running',
                 detail=EXCLUDED.detail,updated_at=NOW()""",
            (STUDY, Json({
                "current_version": "v31",
                "current_stage": "mapping raw edge",
                "source_sha256": source_hash,
                "research_only": True,
                "production_changed": False,
                "untouched_next_year": 2026,
                "current_blocker": calibration["conclusion"] if calibration.get("available") else calibration["reason"],
                "next_action": "finish v31 cells and evaluate whether any regimes justify v32",
            })),
        )

        cell_rows = cluster_rows = diagnostic_rows = 0
        survivors = defaultdict(list)
        pending_cells = []
        pending_clusters = []
        pending_diagnostics = []

        for year in YEARS:
            opportunities, sessions = _build_year_opportunities(cur, year)
            grouped: dict[tuple, list[dict]] = defaultdict(list)
            for opportunity in opportunities:
                key = (
                    opportunity["horizon"], opportunity["time_bucket"],
                    opportunity["direction"],
                )
                grouped[key].append(opportunity)

            for (horizon, bucket, direction), candidates in sorted(grouped.items()):
                selected = select_non_overlapping(candidates)
                for cost_model, ticks, fee in COST_CASES:
                    metrics = _cell_metrics(selected, sessions, ticks, fee)
                    pending_cells.append(
                        (STUDY, year, horizon, bucket, direction, cost_model,
                         ticks, fee, Json(metrics))
                    )
                    cell_rows += 1
                    if metrics["net_dollars"] > 0:
                        survivors[(horizon, bucket, direction, cost_model)].append(year)

                    if cost_model not in CLUSTER_COSTS:
                        continue
                    clusters, diagnostics = _cluster_and_diagnostics(selected, int(ticks), fee)
                    for rank, cluster in enumerate(clusters, 1):
                        pending_clusters.append(
                            (STUDY, year, horizon, bucket, direction, cost_model,
                             rank, Json(cluster))
                        )
                        cluster_rows += 1
                    for diagnostic in diagnostics:
                        feature = diagnostic.pop("feature")
                        pending_diagnostics.append(
                            (STUDY, year, horizon, bucket, direction, cost_model,
                             feature, Json(diagnostic))
                        )
                        diagnostic_rows += 1

        all_year_survivors = [
            {"horizon_minutes": key[0], "time_bucket": key[1], "direction": key[2],
             "cost_model": key[3]}
            for key, years in sorted(survivors.items()) if sorted(years) == list(YEARS)
        ]
        detail = {
            "current_version": "v31",
            "current_stage": "completed raw-edge map",
            "latest_results": {
                "cell_rows": cell_rows,
                "cluster_rows": cluster_rows,
                "diagnostic_rows": diagnostic_rows,
                "positive_all_three_years": all_year_survivors,
            },
            "source_sha256": source_hash,
            "research_only": True,
            "production_changed": False,
            "live_ready": False,
            "untouched_next_year": 2026,
            "signal": "sign of completed trailing 15-minute return",
            "grid_minutes": GRID_MINUTES,
            "horizons_minutes": list(HORIZONS),
            "time_buckets_ct": [
                {"name": name, "start_minute": start, "end_minute_exclusive": end}
                for name, start, end in TIME_BUCKETS
            ],
            "one_position_rule": "enforced independently inside every horizon/time/direction cell",
            "fill_convention": "next-minute open to final hold-minute close; trade-print proxy, not executable BBO",
            "cost_cases": [
                {"name": name, "adverse_ticks_each_side": ticks, "round_trip_fee": fee}
                for name, ticks, fee in COST_CASES
            ],
            "execution_calibration": calibration,
            "current_blocker": "realistic broker slippage and fees remain uncalibrated",
            "next_action": "build v32 only from cells positive in all development years with usable activity",
        }
        connection.autocommit = False
        cur.execute("DELETE FROM valor_mes_v31_cells WHERE study_id=%s", (STUDY,))
        cur.execute("DELETE FROM valor_mes_v31_clusters WHERE study_id=%s", (STUDY,))
        cur.execute("DELETE FROM valor_mes_v31_diagnostics WHERE study_id=%s", (STUDY,))
        if pending_cells:
            execute_values(
                cur,
                """INSERT INTO valor_mes_v31_cells(
                     study_id,year,horizon_minutes,time_bucket,direction,cost_model,
                     adverse_ticks_each_side,round_trip_fee,metrics) VALUES %s""",
                pending_cells,
                page_size=500,
            )
        if pending_clusters:
            execute_values(
                cur,
                """INSERT INTO valor_mes_v31_clusters(
                     study_id,year,horizon_minutes,time_bucket,direction,cost_model,
                     cluster_rank,cluster) VALUES %s""",
                pending_clusters,
                page_size=500,
            )
        if pending_diagnostics:
            execute_values(
                cur,
                """INSERT INTO valor_mes_v31_diagnostics(
                     study_id,year,horizon_minutes,time_bucket,direction,cost_model,
                     feature,summary) VALUES %s""",
                pending_diagnostics,
                page_size=500,
            )
        cur.execute(
            """UPDATE valor_mes_v31_state SET status='completed',detail=%s,updated_at=NOW()
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
            """INSERT INTO valor_mes_v31_state(study_id,status,detail)
               VALUES(%s,'failed',%s)
               ON CONFLICT(study_id) DO UPDATE SET status='failed',
                 detail=EXCLUDED.detail,updated_at=NOW()""",
            (STUDY, Json({
                "current_version": "v31",
                "current_stage": "failed",
                "source_sha256": source_hash,
                "error_type": type(exc).__name__,
                "message": str(exc)[:500],
                "research_only": True,
                "production_changed": False,
                "untouched_next_year": 2026,
                "next_action": "repair the recorded failure without changing the preregistered matrix",
            })),
        )
        raise
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))
        finally:
            connection.close()


def launch_if_enabled() -> bool:
    """Launch once on the research-enabled Render runtime, never in-process."""
    flag = os.getenv("VALOR_MES_V31_AUTORUN", "false")
    if flag.lower() not in {"1", "true", "yes", "on"}:
        return False
    environment = dict(
        os.environ,
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    subprocess.Popen(
        [sys.executable, "-m", "scripts.valor_mes_v31_edge_map"],
        env=environment,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
    return True


if __name__ == "__main__":
    run()
