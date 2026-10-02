"""MES CHOPGuard research: cache-only, causal, no broker/vendor calls.

Purpose:
- Keep the corrected MES morning-continuation engine from valor_mes_session_v6.
- Detect opening-session chop using only 08:30-08:59 CT bars known at 09:00.
- Test a small frozen Kaufman-efficiency threshold set.
- Separately test one causal stop-cluster rule: after a true stop-out, skip the
  next otherwise-valid setup.
- Select on 2023+2024 stressed fills only. 2025 is evaluated only for a
  selected development candidate and is NOT claimed as blind OOS.

This module never changes production VALOR rules, balances, sizing, or orders.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import gzip
import hashlib
import io
import json
import logging
import math
import os
import subprocess
import sys

STUDY = "valor-mes-chopguard-v9-20260924"
LOCK = 649202609
YEARS = (2023, 2024, 2025)
HASHES = {
    2023: "2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
    2024: "6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
    2025: "629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}
# Frozen before results. These are not an optimizer grid.
GUARDS = {
    "baseline": {"min_er": None, "skip_after_stop": False},
    "chopguard_er20": {"min_er": 0.20, "skip_after_stop": False},
    "chopguard_er25": {"min_er": 0.25, "skip_after_stop": False},
    "chopguard_er30": {"min_er": 0.30, "skip_after_stop": False},
    "chopguard_er25_stop_standdown": {"min_er": 0.25, "skip_after_stop": True},
}


def opening_efficiency(d, order):
    """Kaufman-style efficiency for 08:30-08:59 CT, known at 09:00."""
    import numpy as np
    i = int(order["index"])
    day = order["date"]
    p = d[(d.date == day) & d.rth & d.minute.ge(510) & d.minute.lt(540)]
    if len(p) != 30 or p.index[-1] != i or p.segment.nunique() != 1:
        return None, None
    path = np.r_[float(p.open.iloc[0]), p.close.to_numpy(float)]
    delta = np.diff(path)
    travel = float(np.abs(delta).sum())
    er = abs(float(path[-1] - path[0])) / travel if travel > 0 else 0.0
    signs = np.sign(delta)
    signs = signs[signs != 0]
    reversals = int(np.sum(signs[1:] != signs[:-1])) if len(signs) > 1 else 0
    return float(er), reversals


def guarded_schedule(d):
    from scripts import valor_mes_session_v6 as base
    raw, skipped = base.orders(d, "morning_continuation")
    enriched = []
    incomplete = 0
    for order in raw:
        er, reversals = opening_efficiency(d, order)
        if er is None:
            incomplete += 1
            continue
        x = dict(order)
        x["opening_efficiency"] = er
        x["opening_reversals"] = reversals
        enriched.append(x)
    skipped = dict(skipped)
    if incomplete:
        skipped["chopguard_incomplete_opening_path"] = incomplete
    return enriched, skipped


def apply_er(schedule, min_er):
    if min_er is None:
        return list(schedule), 0
    kept = [o for o in schedule if o["opening_efficiency"] >= min_er]
    return kept, len(schedule) - len(kept)


def replay_with_optional_standdown(d, schedule, skip_after_stop):
    """Replay chronologically; optionally skip one eligible order after a stop."""
    from scripts import valor_mes_session_v6 as base
    if not skip_after_stop:
        return (*base.replay(d, schedule, "signal"), 0)
    trades, unresolved = [], []
    skip_next = False
    skipped_after_stop = 0
    for order in schedule:
        if skip_next:
            skipped_after_stop += 1
            skip_next = False
            continue
        one_trades, one_unresolved = base.replay(d, [order], "signal")
        trades.extend(one_trades)
        unresolved.extend(one_unresolved)
        if one_trades and one_trades[-1]["reason"] in ("stop", "gap_stop"):
            skip_next = True
    return trades, unresolved, skipped_after_stop


def result_row(d, schedule, skipped_base, year, name, cfg, ticks):
    from scripts import valor_mes_session_v6 as base
    filtered, blocked_chop = apply_er(schedule, cfg["min_er"])
    trades, unresolved, blocked_cluster = replay_with_optional_standdown(
        d, filtered, cfg["skip_after_stop"]
    )
    r = base.summarize(trades, unresolved, year, ticks)
    ers = [o["opening_efficiency"] for o in filtered]
    revs = [o["opening_reversals"] for o in filtered]
    r.update(
        guard=name,
        min_opening_efficiency=cfg["min_er"],
        skip_next_after_stop=cfg["skip_after_stop"],
        raw_valid_decisions=len(schedule),
        guard_decisions=len(filtered) - blocked_cluster,
        blocked_as_chop=blocked_chop,
        blocked_after_stop=blocked_cluster,
        opening_efficiency_mean=(sum(ers) / len(ers)) if ers else None,
        opening_reversals_mean=(sum(revs) / len(revs)) if revs else None,
        base_signal_skips=skipped_base,
        year=year,
        research_only=True,
        production_changed=False,
        live_ready=False,
    )
    return r


def evaluate(frame, year, only_guard=None):
    from scripts import valor_mes_session_v6 as base
    d = base.prepare(frame)
    schedule, skipped = guarded_schedule(d)
    rows = []
    for name, cfg in GUARDS.items():
        if only_guard is not None and name != only_guard:
            continue
        for ticks in (2, 4):
            rows.append(result_row(d, schedule, skipped, year, name, cfg, ticks))
    manifest = {
        "study": STUDY,
        "year": year,
        "base_engine": "valor_mes_session_v6.morning_continuation",
        "decision_time_ct": "09:00",
        "opening_window_ct": "08:30-08:59",
        "guards": GUARDS,
        "selection_cost_ticks_each_side": 4,
        "round_trip_fee_assumed": 3.0,
        "new_vendor_downloads": 0,
        "broker_calls": 0,
        "production_changed": False,
        "live_ready": False,
        "validation": "2023/2024 development; 2025 already seen chronological check only",
    }
    return manifest, rows


def select_candidate(dev):
    """Require robust profitability in BOTH development years under stress."""
    choices = []
    for name in sorted(GUARDS):
        if name == "baseline":
            continue
        rows = []
        for year in (2023, 2024):
            rows.extend(
                r for r in dev.get(year, [])
                if r["guard"] == name and r["cost_ticks_each_side"] == 4
            )
        if len(rows) != 2:
            continue
        if not all(
            r["trades"] >= 80
            and r["net_dollars"] > 0
            and r["profit_factor"] is not None
            and r["profit_factor"] >= 1.05
            and r["unresolved_fraction"] <= 0.03
            for r in rows
        ):
            continue
        score = min(
            r["net_dollars"] / max(1.0, r["closed_trade_max_drawdown"])
            for r in rows
        )
        choices.append((score, sum(r["net_dollars"] for r in rows), name))
    if not choices:
        return None
    return sorted(choices, key=lambda z: (-z[0], -z[1], z[2]))[0][2]


def run():
    import pandas as pd
    import psycopg2
    from psycopg2.extras import Json

    if hasattr(os, "nice"):
        os.nice(10)
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,))
    if not cur.fetchone()[0]:
        conn.close()
        return

    source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def state(status, **detail):
        cur.execute(
            """INSERT INTO valor_mes_chopguard_v9_state(study_id,status,detail)
               VALUES(%s,%s,%s)
               ON CONFLICT(study_id) DO UPDATE
               SET status=excluded.status, detail=excluded.detail, updated_at=now()""",
            (
                STUDY,
                status,
                Json(dict(detail, source_sha256=source_hash,
                          research_only=True, production_changed=False,
                          new_vendor_downloads=0)),
            ),
        )

    def cached(year):
        key = f"GLBX.MDP3:ohlcv-1m:MES.v.0:{year}"
        cur.execute(
            "SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",
            (key,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Required cached MES bars absent; paid download prohibited")
        body = bytes(row[1])
        digest = hashlib.sha256(body).hexdigest()
        if digest != row[0] or digest != HASHES[year]:
            raise ValueError("MES cache checksum mismatch")
        return pd.read_parquet(io.BytesIO(body))

    def store(year, manifest, rows):
        manifest.update(source_sha256=source_hash, cache_sha256=HASHES[year])
        summary = [
            {k: v for k, v in r.items() if k not in ("ledger", "unresolved_ledger")}
            for r in rows
        ]
        evidence = gzip.compress(
            json.dumps(rows, allow_nan=False).encode(), mtime=0
        )
        cur.execute(
            """INSERT INTO valor_mes_chopguard_v9_results
               (study_id,year,manifest,summary,evidence_gzip)
               VALUES(%s,%s,%s,%s,%s)
               ON CONFLICT(study_id,year) DO NOTHING""",
            (STUDY, year, Json(manifest), Json(summary), psycopg2.Binary(evidence)),
        )
        return summary

    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v9_state(
                   study_id text PRIMARY KEY,
                   status text NOT NULL,
                   detail jsonb,
                   updated_at timestamptz DEFAULT now());
               CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v9_results(
                   study_id text,
                   year integer,
                   manifest jsonb NOT NULL,
                   summary jsonb NOT NULL,
                   evidence_gzip bytea NOT NULL,
                   created_at timestamptz DEFAULT now(),
                   PRIMARY KEY(study_id,year));"""
        )
        cur.execute(
            "SELECT status FROM valor_mes_chopguard_v9_state WHERE study_id=%s",
            (STUDY,),
        )
        if cur.fetchone() == ("completed",):
            return
        cur.execute(
            """SELECT COUNT(*) FROM valor_mes_chopguard_v9_results
               WHERE study_id=%s
                 AND manifest->>'source_sha256' IS DISTINCT FROM %s""",
            (STUDY, source_hash),
        )
        if cur.fetchone()[0]:
            state("blocked_source_version")
            return

        dev = {}
        for year in (2023, 2024):
            cur.execute(
                """SELECT summary FROM valor_mes_chopguard_v9_results
                   WHERE study_id=%s AND year=%s""",
                (STUDY, year),
            )
            row = cur.fetchone()
            if row:
                dev[year] = row[0]
                continue
            state("evaluating_development", year=year)
            manifest, rows = evaluate(cached(year), year)
            manifest["phase"] = "development"
            dev[year] = store(year, manifest, rows)

        selected = select_candidate(dev)
        cur.execute(
            "SELECT 1 FROM valor_mes_chopguard_v9_results WHERE study_id=%s AND year=2025",
            (STUDY,),
        )
        if not cur.fetchone():
            if selected:
                state("evaluating_chronological_check", year=2025, selected=selected)
                manifest, rows = evaluate(cached(2025), 2025, selected)
                manifest.update(
                    phase="chronological_check",
                    selected_from_years=[2023, 2024],
                    selection_frozen=selected,
                    blind_holdout=False,
                )
                store(2025, manifest, rows)
            else:
                store(
                    2025,
                    {
                        "phase": "not_tested",
                        "reason": "no_chopguard_passed_2023_2024_stress_gate",
                        "source_sha256": source_hash,
                        "cache_sha256": HASHES[2025],
                        "production_changed": False,
                        "live_ready": False,
                    },
                    [],
                )

        state(
            "completed",
            selected=selected,
            selection_gate={
                "positive_stress_net_each_year": True,
                "profit_factor_min_each_year": 1.05,
                "trades_min_each_year": 80,
                "unresolved_fraction_max_each_year": 0.03,
            },
            test_2025="chronological_check" if selected else "not_tested",
        )
    except Exception as exc:
        try:
            state("failed", error_type=type(exc).__name__, message=str(exc)[:400])
        except Exception:
            pass
        logging.getLogger(__name__).exception("MES CHOPGuard v9 research failed")
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))
        finally:
            conn.close()


def launch_if_enabled():
    flag = os.getenv("VALOR_MES_CHOPGUARD_V9_AUTORUN", "false")
    if flag.lower() not in {"1", "true", "yes", "on"}:
        return False
    env = dict(
        os.environ,
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    subprocess.Popen(
        [sys.executable, "-m", "scripts.valor_mes_chopguard_v9"],
        env=env,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
    return True


if __name__ == "__main__":
    run()
