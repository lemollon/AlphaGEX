"""MES CHOPGuard v13: quality layer on the frozen profitable long subset.

V11 found the portable toxic cluster:
  late15 confirmation + directional location >= 0.65.
V12 showed:
  long-only + noon exit is best, but 2023's edge is too thin under 4-tick/side
  stressed fills because friction consumes most of the gross edge.

V13 freezes all prior choices and tests a SMALL causal quality set designed to
remove marginal long entries, not optimize time or calendar effects.

Selection: 2023 + 2024 only, 4 adverse ticks/side + $3 round-trip fee.
2025: chronological check only if a candidate passes; never called blind OOS.
No vendor downloads, broker calls, sizing changes, or production rule changes.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, logging, os, subprocess, sys

STUDY = "valor-mes-chopguard-v13-20260924"
LOCK = 653202609
HASHES = {
    2023: "2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
    2024: "6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
    2025: "629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}

# Frozen, interpretable hypotheses. All use information known at 09:00 CT.
QUALITY = {
    "frozen_base": {},
    "dirloc75": {"dirloc_min": 0.75},
    "dirloc80": {"dirloc_min": 0.80},
    "vwap_sep10": {"vwap_sep_min": 0.10},
    "vwap_sep15": {"vwap_sep_min": 0.15},
    "late15_strength10": {"late15_strength_min": 0.10},
    "late15_strength15": {"late15_strength_min": 0.15},
    "dirloc75_vwap10": {"dirloc_min": 0.75, "vwap_sep_min": 0.10},
    "dirloc75_late10": {"dirloc_min": 0.75, "late15_strength_min": 0.10},
}


def frozen_longs(d):
    from scripts import valor_mes_session_v6 as base
    from scripts import valor_mes_chopguard_v11 as v11
    raw, skipped = base.orders(d, "morning_continuation")
    out = []
    blocked_guard = []
    blocked_short = []
    incomplete = 0
    frozen = {"late15": True, "dirloc_min": 0.65}
    for o in raw:
        x = v11.enrich(d, o)
        if x is None:
            incomplete += 1
            continue
        if not v11.passes(x, frozen):
            blocked_guard.append(x)
            continue
        if int(x["side"]) != 1:
            blocked_short.append(x)
            continue
        width = float(x["opening_width"])
        x = dict(x)
        x["late15_strength"] = float(x["late15_move"]) / width if width > 0 else 0.0
        out.append(x)
    skipped = dict(skipped)
    if incomplete:
        skipped["v13_feature_context_incomplete"] = incomplete
    return out, blocked_guard, blocked_short, skipped, len(raw)


def passes_quality(o, cfg):
    if cfg.get("dirloc_min") is not None and o["directional_location"] < cfg["dirloc_min"]:
        return False
    if cfg.get("vwap_sep_min") is not None and o["vwap_separation_ratio"] < cfg["vwap_sep_min"]:
        return False
    if cfg.get("late15_strength_min") is not None and o["late15_strength"] < cfg["late15_strength_min"]:
        return False
    return True


def evaluate(frame, year, only=None):
    from scripts import valor_mes_session_v6 as base
    d = base.prepare(frame)
    frozen, blocked_guard, blocked_short, skipped, raw_n = frozen_longs(d)
    rows = []
    for name, cfg in QUALITY.items():
        if only is not None and name != only:
            continue
        kept = [o for o in frozen if passes_quality(o, cfg)]
        rejected = [o for o in frozen if not passes_quality(o, cfg)]
        kt, ku = base.replay(d, kept, "signal")
        rt, ru = base.replay(d, rejected, "signal") if rejected else ([], [])
        for ticks in (2, 4):
            r = base.summarize(kt, ku, year, ticks)
            rr = base.summarize(rt, ru, year, ticks) if rejected else None
            r.update(
                candidate=name,
                year=year,
                raw_valid_decisions=raw_n,
                frozen_long_decisions=len(frozen),
                kept_decisions=len(kept),
                quality_rejected=len(rejected),
                quality_rejected_net=(rr["net_dollars"] if rr else 0.0),
                quality_rejected_pf=(rr["profit_factor"] if rr else None),
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
        exit_minute_ct=720,
        quality=QUALITY,
        selection_cost_ticks_each_side=4,
        round_trip_fee_assumed=3.0,
        new_vendor_downloads=0,
        broker_calls=0,
        production_changed=False,
        live_ready=False,
        validation="2023/2024 development; 2025 chronological check only",
    )
    return manifest, rows


def select_candidate(dev):
    picks = []
    for name in QUALITY:
        if name == "frozen_base":
            continue
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
            """INSERT INTO valor_mes_chopguard_v13_state(study_id,status,detail)
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
            """INSERT INTO valor_mes_chopguard_v13_results
               (study_id,year,manifest,summary,evidence_gzip)
               VALUES(%s,%s,%s,%s,%s)
               ON CONFLICT(study_id,year) DO NOTHING""",
            (STUDY, year, Json(manifest), Json(summary), psycopg2.Binary(evidence)),
        )
        return summary

    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v13_state(
                 study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,
                 updated_at timestamptz DEFAULT now());
               CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v13_results(
                 study_id text,year integer,manifest jsonb NOT NULL,summary jsonb NOT NULL,
                 evidence_gzip bytea NOT NULL,created_at timestamptz DEFAULT now(),
                 PRIMARY KEY(study_id,year));"""
        )
        cur.execute("SELECT status FROM valor_mes_chopguard_v13_state WHERE study_id=%s", (STUDY,))
        if cur.fetchone() == ("completed",):
            return

        dev = {}
        for year in (2023, 2024):
            state("evaluating_development", year=year)
            m, rows = evaluate(cached(year), year)
            m["phase"] = "development"
            dev[year] = store(year, m, rows)

        selected = select_candidate(dev)
        if selected:
            state("evaluating_chronological_check", year=2025, selected=selected)
            m, rows = evaluate(cached(2025), 2025, selected)
            m.update(
                phase="chronological_check",
                selection_frozen=selected,
                selected_from_years=[2023, 2024],
                blind_holdout=False,
            )
            store(2025, m, rows)
        else:
            store(
                2025,
                dict(
                    phase="not_tested",
                    reason="no_v13_quality_candidate_passed_2023_2024_stress_gate",
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
        logging.getLogger(__name__).exception("MES CHOPGuard v13 failed")
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))
        finally:
            conn.close()


def launch_if_enabled():
    flag = os.getenv(
        "VALOR_MES_CHOPGUARD_V13_AUTORUN",
        os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN", "false"),
    )
    if flag.lower() not in {"1", "true", "yes", "on"}:
        return False
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    subprocess.Popen(
        [sys.executable, "-m", "scripts.valor_mes_chopguard_v13"],
        env=env,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
    return True


if __name__ == "__main__":
    run()
