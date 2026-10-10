"""MES CHOPGuard v12: freeze the portable guard, isolate the surviving long edge.

V11 found a portable toxic cluster with late15 + directional-location confirmation:
the blocked bucket lost in both 2023 and 2024 under stressed costs, while the
remaining long side was positive in both years and the remaining short side was
negative in both years.

V12 therefore freezes that guard and tests only the surviving LONG setups across
a small predeclared exit-horizon set. Development/selection uses 2023+2024 only.
2025 is evaluated only after a candidate passes and is NOT a blind holdout.

No broker calls, vendor downloads, sizing changes, or production rule changes.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, logging, os, subprocess, sys

STUDY = "valor-mes-chopguard-v12-20260924"
LOCK = 652202609
HASHES = {
    2023: "2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
    2024: "6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
    2025: "629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}
# 09:00 CT entries; fixed exit times, not an optimized sweep.
EXITS = {
    "long_exit_1000": 600,
    "long_exit_1030": 630,
    "long_exit_1100": 660,
    "long_exit_1130": 690,
    "long_exit_1200": 720,
}


def guarded_longs(d):
    from scripts import valor_mes_session_v6 as base
    from scripts import valor_mes_chopguard_v11 as v11
    raw, skipped = base.orders(d, "morning_continuation")
    kept, blocked_guard, blocked_shorts = [], [], []
    incomplete = 0
    cfg = {"late15": True, "dirloc_min": 0.65}
    for o in raw:
        x = v11.enrich(d, o)
        if x is None:
            incomplete += 1
            continue
        if not v11.passes(x, cfg):
            blocked_guard.append(x)
        elif x["side"] != 1:
            blocked_shorts.append(x)
        else:
            kept.append(x)
    skipped = dict(skipped)
    if incomplete:
        skipped["v12_feature_context_incomplete"] = incomplete
    return kept, blocked_guard, blocked_shorts, skipped, len(raw)


def replay_exit(d, schedule, exit_minute):
    from scripts import valor_mes_session_v6 as base
    adjusted = [dict(o, exit_minute=exit_minute) for o in schedule]
    return base.replay(d, adjusted, "signal")


def evaluate(frame, year, only=None):
    from scripts import valor_mes_session_v6 as base
    d = base.prepare(frame)
    longs, blocked_guard, blocked_shorts, skipped, raw_n = guarded_longs(d)
    rows = []
    for name, exit_minute in EXITS.items():
        if only is not None and name != only:
            continue
        trades, unresolved = replay_exit(d, longs, exit_minute)
        for ticks in (2, 4):
            r = base.summarize(trades, unresolved, year, ticks)
            # Diagnostics use the original noon exit so cluster attribution remains
            # directly comparable to V11.
            bg_t, bg_u = replay_exit(d, blocked_guard, 720) if blocked_guard else ([], [])
            bs_t, bs_u = replay_exit(d, blocked_shorts, 720) if blocked_shorts else ([], [])
            bg = base.summarize(bg_t, bg_u, year, ticks) if blocked_guard else None
            bs = base.summarize(bs_t, bs_u, year, ticks) if blocked_shorts else None
            r.update(
                candidate=name,
                year=year,
                exit_minute_ct=exit_minute,
                raw_valid_decisions=raw_n,
                guard_kept_long_decisions=len(longs),
                blocked_by_chopguard=len(blocked_guard),
                blocked_by_long_only=len(blocked_shorts),
                chopguard_blocked_net=(bg["net_dollars"] if bg else 0.0),
                chopguard_blocked_pf=(bg["profit_factor"] if bg else None),
                rejected_short_net=(bs["net_dollars"] if bs else 0.0),
                rejected_short_pf=(bs["profit_factor"] if bs else None),
                base_signal_skips=skipped,
                research_only=True,
                production_changed=False,
                live_ready=False,
            )
            rows.append(r)
    manifest = dict(
        study=STUDY,
        year=year,
        base_engine="valor_mes_session_v6.morning_continuation",
        frozen_chopguard="late15_confirm + directional_location>=0.65",
        direction="long_only",
        exits=EXITS,
        decision_time_ct="09:00",
        selection_cost_ticks_each_side=4,
        round_trip_fee_assumed=3.0,
        new_vendor_downloads=0,
        broker_calls=0,
        production_changed=False,
        live_ready=False,
        validation="2023/2024 development; 2025 already seen chronological check only",
    )
    return manifest, rows


def choose(dev):
    picks = []
    for name in EXITS:
        rs = [
            r for y in (2023, 2024) for r in dev.get(y, [])
            if r["candidate"] == name and r["cost_ticks_each_side"] == 4
        ]
        if len(rs) != 2:
            continue
        if not all(
            r["trades"] >= 50
            and r["net_dollars"] > 0
            and r["profit_factor"] is not None
            and r["profit_factor"] >= 1.05
            and r["unresolved_fraction"] <= 0.03
            for r in rs
        ):
            continue
        worst = min(
            r["net_dollars"] / max(1.0, r["closed_trade_max_drawdown"]) for r in rs
        )
        picks.append((worst, sum(r["net_dollars"] for r in rs), name))
    return sorted(picks, key=lambda z: (-z[0], -z[1], z[2]))[0][2] if picks else None


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
            """INSERT INTO valor_mes_chopguard_v12_state(study_id,status,detail)
               VALUES(%s,%s,%s)
               ON CONFLICT(study_id) DO UPDATE
               SET status=excluded.status,detail=excluded.detail,updated_at=now()""",
            (STUDY, status, Json(dict(
                detail,
                source_sha256=source_hash,
                research_only=True,
                production_changed=False,
                new_vendor_downloads=0,
            ))),
        )

    def cached(year):
        cur.execute(
            "SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",
            (f"GLBX.MDP3:ohlcv-1m:MES.v.0:{year}",),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("cache absent; vendor download prohibited")
        body = bytes(row[1])
        digest = hashlib.sha256(body).hexdigest()
        if digest != row[0] or digest != HASHES[year]:
            raise ValueError("cache checksum mismatch")
        return pd.read_parquet(io.BytesIO(body))

    def store(year, manifest, rows):
        manifest.update(source_sha256=source_hash, cache_sha256=HASHES[year])
        summary = [
            {k: v for k, v in r.items() if k not in ("ledger", "unresolved_ledger")}
            for r in rows
        ]
        evidence = gzip.compress(json.dumps(rows, allow_nan=False).encode(), mtime=0)
        cur.execute(
            """INSERT INTO valor_mes_chopguard_v12_results
               (study_id,year,manifest,summary,evidence_gzip)
               VALUES(%s,%s,%s,%s,%s)
               ON CONFLICT(study_id,year) DO NOTHING""",
            (STUDY, year, Json(manifest), Json(summary), psycopg2.Binary(evidence)),
        )
        return summary

    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v12_state(
                 study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,
                 updated_at timestamptz DEFAULT now());
               CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v12_results(
                 study_id text,year integer,manifest jsonb NOT NULL,summary jsonb NOT NULL,
                 evidence_gzip bytea NOT NULL,created_at timestamptz DEFAULT now(),
                 PRIMARY KEY(study_id,year));"""
        )
        cur.execute(
            "SELECT status FROM valor_mes_chopguard_v12_state WHERE study_id=%s",
            (STUDY,),
        )
        if cur.fetchone() == ("completed",):
            return

        dev = {}
        for year in (2023, 2024):
            state("evaluating_development", year=year)
            manifest, rows = evaluate(cached(year), year)
            manifest["phase"] = "development"
            dev[year] = store(year, manifest, rows)

        selected = choose(dev)
        if selected:
            state("evaluating_chronological_check", year=2025, selected=selected)
            manifest, rows = evaluate(cached(2025), 2025, selected)
            manifest.update(
                phase="chronological_check",
                selection_frozen=selected,
                selected_from_years=[2023, 2024],
                blind_holdout=False,
            )
            store(2025, manifest, rows)
        else:
            store(
                2025,
                dict(
                    phase="not_tested",
                    reason="no_v12_long_candidate_passed_2023_2024_stress_gate",
                    source_sha256=source_hash,
                    cache_sha256=HASHES[2025],
                    production_changed=False,
                    live_ready=False,
                ),
                [],
            )

        state(
            "completed",
            selected=selected,
            test_2025="chronological_check" if selected else "not_tested",
            selection_gate={
                "positive_stress_net_each_year": True,
                "profit_factor_min_each_year": 1.05,
                "trades_min_each_year": 50,
                "unresolved_fraction_max_each_year": 0.03,
            },
        )
    except Exception as exc:
        try:
            state("failed", error_type=type(exc).__name__, message=str(exc)[:500])
        except Exception:
            pass
        logging.getLogger(__name__).exception("MES CHOPGuard v12 failed")
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))
        finally:
            conn.close()


def launch_if_enabled():
    flag = os.getenv(
        "VALOR_MES_CHOPGUARD_V12_AUTORUN",
        os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN", "false"),
    )
    if flag.lower() not in {"1", "true", "yes", "on"}:
        return False
    env = dict(
        os.environ,
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    subprocess.Popen(
        [sys.executable, "-m", "scripts.valor_mes_chopguard_v12"],
        env=env,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
    return True


if __name__ == "__main__":
    run()
