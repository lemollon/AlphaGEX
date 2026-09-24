"""MES CHOPGuard v11: causal late-confirmation / structure gates.

Goal: isolate portable MES morning-continuation loss clusters after v9/v10 showed
that generic chop and short-only opening filters do not transfer across years.

Development/selection: 2023 + 2024 only.
Stress hurdle: 4 adverse ticks/side + $3 round-trip fee.
2025 is evaluated only after a candidate passes both development years and is
explicitly NOT a blind holdout because it has already been inspected elsewhere.

No broker calls, vendor downloads, sizing changes, or production strategy changes.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, logging, os, subprocess, sys

STUDY = "valor-mes-chopguard-v11-20260924"
LOCK = 651202609
HASHES = {
    2023: "2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
    2024: "6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
    2025: "629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}

# Small frozen hypothesis set. These are structural confirmations, not an optimizer grid.
GUARDS = {
    "baseline": {},
    "late10_confirm": {"late10": True},
    "late15_confirm": {"late15": True},
    "dirloc65": {"dirloc_min": 0.65},
    "vwap_sep10": {"vwap_sep_min": 0.10},
    "late15_dirloc65": {"late15": True, "dirloc_min": 0.65},
    "late15_vwap10": {"late15": True, "vwap_sep_min": 0.10},
    "short_late15": {"short_late15": True},
}


def enrich(d, order):
    """All features use only 08:30-08:59 CT bars, known at the 09:00 decision."""
    p = d[(d.date == order["date"]) & d.rth & d.minute.ge(510) & d.minute.lt(540)]
    if len(p) != 30 or p.index[-1] != order["index"] or p.segment.nunique() != 1:
        return None
    width = float(p.high.max() - p.low.min())
    if width <= 0 or float(p.volume.sum()) <= 0:
        return None
    side = int(order["side"])
    ref = float(p.close.iloc[-1])
    hi, lo = float(p.high.max()), float(p.low.min())
    vwap = float((p.volume * (p.high + p.low + p.close) / 3).sum() / p.volume.sum())
    late10 = side * (ref - float(p.open.iloc[-10]))
    late15 = side * (ref - float(p.open.iloc[-15]))
    dirloc = (ref - lo) / width if side == 1 else (hi - ref) / width
    vwap_sep = side * (ref - vwap) / width
    x = dict(order)
    x.update(
        late10_move=float(late10),
        late15_move=float(late15),
        directional_location=float(dirloc),
        vwap_separation_ratio=float(vwap_sep),
        opening_width=float(width),
    )
    return x


def build_schedule(d):
    from scripts import valor_mes_session_v6 as base
    raw, skipped = base.orders(d, "morning_continuation")
    out, incomplete = [], 0
    for o in raw:
        x = enrich(d, o)
        if x is None:
            incomplete += 1
        else:
            out.append(x)
    skipped = dict(skipped)
    if incomplete:
        skipped["v11_feature_context_incomplete"] = incomplete
    return out, skipped


def passes(o, cfg):
    side = int(o["side"])
    if cfg.get("late10") and o["late10_move"] <= 0:
        return False
    if cfg.get("late15") and o["late15_move"] <= 0:
        return False
    if cfg.get("dirloc_min") is not None and o["directional_location"] < cfg["dirloc_min"]:
        return False
    if cfg.get("vwap_sep_min") is not None and o["vwap_separation_ratio"] < cfg["vwap_sep_min"]:
        return False
    if cfg.get("short_late15") and side == -1 and o["late15_move"] <= 0:
        return False
    return True


def compact_summary(r):
    return {k: v for k, v in r.items() if k not in ("ledger", "unresolved_ledger")}


def evaluate(frame, year, only=None):
    from scripts import valor_mes_session_v6 as base
    d = base.prepare(frame)
    raw, skipped = build_schedule(d)
    rows = []
    for name, cfg in GUARDS.items():
        if only is not None and name != only:
            continue
        kept = [o for o in raw if passes(o, cfg)]
        blocked = [o for o in raw if not passes(o, cfg)]
        kt, ku = base.replay(d, kept, "signal")
        bt, bu = base.replay(d, blocked, "signal") if blocked else ([], [])
        for ticks in (2, 4):
            r = base.summarize(kt, ku, year, ticks)
            br = base.summarize(bt, bu, year, ticks) if blocked else None
            r.update(
                guard=name,
                year=year,
                raw_valid_decisions=len(raw),
                kept_decisions=len(kept),
                blocked_decisions=len(blocked),
                blocked_net=(br["net_dollars"] if br else 0.0),
                blocked_pf=(br["profit_factor"] if br else None),
                blocked_win_rate=(br["win_rate"] if br else None),
                blocked_long_net=(br["long_net"] if br else 0.0),
                blocked_short_net=(br["short_net"] if br else 0.0),
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
        guards=GUARDS,
        feature_window_ct="08:30-08:59",
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


def select_candidate(dev):
    picks = []
    for name in GUARDS:
        if name == "baseline":
            continue
        rs = [
            r for y in (2023, 2024) for r in dev.get(y, [])
            if r["guard"] == name and r["cost_ticks_each_side"] == 4
        ]
        if len(rs) != 2:
            continue
        if not all(
            r["trades"] >= 80
            and r["net_dollars"] > 0
            and r["profit_factor"] is not None
            and r["profit_factor"] >= 1.05
            and r["unresolved_fraction"] <= 0.03
            for r in rs
        ):
            continue
        # Prefer the candidate with the strongest worst-year return-to-DD ratio.
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
            """INSERT INTO valor_mes_chopguard_v11_state(study_id,status,detail)
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
        key = f"GLBX.MDP3:ohlcv-1m:MES.v.0:{year}"
        cur.execute(
            "SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",
            (key,),
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
        summary = [compact_summary(r) for r in rows]
        evidence = gzip.compress(json.dumps(rows, allow_nan=False).encode(), mtime=0)
        cur.execute(
            """INSERT INTO valor_mes_chopguard_v11_results
               (study_id,year,manifest,summary,evidence_gzip)
               VALUES(%s,%s,%s,%s,%s)
               ON CONFLICT(study_id,year) DO NOTHING""",
            (STUDY, year, Json(manifest), Json(summary), psycopg2.Binary(evidence)),
        )
        return summary

    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v11_state(
                 study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,
                 updated_at timestamptz DEFAULT now());
               CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v11_results(
                 study_id text,year integer,manifest jsonb NOT NULL,summary jsonb NOT NULL,
                 evidence_gzip bytea NOT NULL,created_at timestamptz DEFAULT now(),
                 PRIMARY KEY(study_id,year));"""
        )
        cur.execute(
            "SELECT status FROM valor_mes_chopguard_v11_state WHERE study_id=%s",
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

        selected = select_candidate(dev)
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
                    reason="no_v11_guard_passed_2023_2024_stress_gate",
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
                "trades_min_each_year": 80,
                "unresolved_fraction_max_each_year": 0.03,
            },
        )
    except Exception as exc:
        try:
            state("failed", error_type=type(exc).__name__, message=str(exc)[:500])
        except Exception:
            pass
        logging.getLogger(__name__).exception("MES CHOPGuard v11 failed")
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))
        finally:
            conn.close()


def launch_if_enabled():
    flag = os.getenv(
        "VALOR_MES_CHOPGUARD_V11_AUTORUN",
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
        [sys.executable, "-m", "scripts.valor_mes_chopguard_v11"],
        env=env,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
    return True


if __name__ == "__main__":
    run()
