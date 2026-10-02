"""
Seeds flame-v2 CALM-measure history for FLAME (14:05 ET entry) and SPARK
(11:05 ET entry) from the local vix_minute.duckdb warehouse, from 2022-09
through the latest date in the warehouse. Writes two committed JSON files
under ironforge/webapp/src/lib/flame-v2/seed/ (flame_calm_seed.json,
spark_calm_seed.json) so a fresh deploy does not need ~20 real trading
sessions to accumulate before CALM can ever fire for either bot (see
signal-store.ts's own header comment on why this seed exists).

CALM measure definition — matches flame-v2/math.ts's calmMeasure() /
the frozen research script signal_on_flame_spark.py's calm_measure_series
EXACTLY: sample standard deviation (ddof=1, numpy.std(..., ddof=1)) of
1-minute log(VIX close) changes over the minutes STRICTLY BEFORE the entry
minute on that calendar day, back up to 120 minutes before entry (fewer
minutes on a day where less history exists before entry — e.g. SPARK's
11:05 ET entry is only ~93 minutes after the 09:31 ET open, so its window
is naturally shorter than FLAME's). A day is skipped entirely (no row
written) if fewer than 5 closes are available in that window — the same
floor calmMeasure() itself enforces, so a seeded row and a live-computed
row are never computed differently.

What this script does NOT seed:
  - Percentile thresholds / is_calm flags. Those are an EXPANDING window
    over all PRIOR days (this seed's days plus every later real trading
    day) — computed live, at decision time, by priorCalmMeasures() +
    isCalmFromHistory() (signal-store.ts / math.ts). This script supplies
    only the raw per-day measure those functions consume.
  - D1 (SPARK trailing-60-winner) / D2 (FLAME depth-2 regime-brain)
    training rows — per-day VIX-decay ratio, prior_spy_up, r0_pnl..r3_pnl,
    and D2's 7 features. signal_on_flame_spark.py computes these INSIDE
    run_d1()/run_d2() purely in-memory and never persists a per-day dump;
    reproducing that dump (re-deriving every band-eligible day's
    hypothetical R0/R1/R2/R3 P&L from raw option-chain fills) was out of
    scope for this seed pass. D1/D2 therefore start with ZERO prior
    history on a fresh deploy and accumulate purely from live trading
    days going forward (minHist=20 for D1, minSamples=40 for D2) — both
    already fail closed to today's existing admission rule until enough
    history accumulates (see flame-v2/engine.ts
    flameRegimeBrainDecision / sparkTrailingBandDecision), so this is a
    safe, explicitly-flagged gap, not a silent one.

Run manually, once, from a machine with vix_minute.duckdb (Leron's laptop —
this file is NOT reachable from Render, see signal-store.ts):

    python ironforge/scripts/seed_flame_v2_signal_history.py

Then commit the two JSON files it writes. The idempotent loader in
signal-store.ts (loadSeedIfEmpty) inserts any seed row missing from
flame_v2_signal_history on first use in each environment — safe to run
this script again later (e.g. to extend the seed) and recommit.
"""
import json
import math
import statistics
from pathlib import Path

import duckdb

WAREHOUSE = r"C:\Users\lemol\dev\ironforge-data\warehouse\vix_minute.duckdb"
OUT_DIR = Path(__file__).resolve().parents[1] / "webapp" / "src" / "lib" / "flame-v2" / "seed"
START_DATE = "2022-09-01"

ENTRY_HHMMSS = {"flame": "14:05:00", "spark": "11:05:00"}
WINDOW_MINUTES = 120
MIN_CLOSES = 5


def calm_measure(closes: list) -> float | None:
    """Exact port of flame-v2/math.ts calmMeasure()."""
    if len(closes) < MIN_CLOSES:
        return None
    logrets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    if len(logrets) < 2:
        return None
    return statistics.stdev(logrets)  # ddof=1 sample std


def main() -> None:
    con = duckdb.connect(WAREHOUSE, read_only=True)
    dates = [
        r[0]
        for r in con.execute(
            f"select distinct ts::date as d from vix_minute where ts::date >= '{START_DATE}' order by d"
        ).fetchall()
    ]
    if not dates:
        print("No trading days found >= START_DATE — nothing to seed.")
        return
    print(f"{len(dates)} trading days from {dates[0]} to {dates[-1]}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    window_sql = (
        "select close from vix_minute "
        "where ts >= (?::TIMESTAMP - interval '{m} minutes') and ts < ?::TIMESTAMP "
        "order by ts"
    ).format(m=WINDOW_MINUTES)

    for bot, entry_hhmmss in ENTRY_HHMMSS.items():
        rows = []
        skipped = 0
        for d in dates:
            d_str = str(d)
            entry_ts = f"{d_str} {entry_hhmmss}"
            result = con.execute(window_sql, [entry_ts, entry_ts]).fetchall()
            closes = [r[0] for r in result if r[0] is not None]
            measure = calm_measure(closes)
            if measure is None:
                skipped += 1
                continue
            rows.append({"trade_date": d_str, "calm_measure": round(measure, 10)})

        out_path = OUT_DIR / f"{bot}_calm_seed.json"
        out_path.write_text(json.dumps(rows), encoding="utf-8")
        print(f"{bot}: wrote {len(rows)} rows ({skipped} days skipped, <{MIN_CLOSES} closes) -> {out_path}")

    con.close()


if __name__ == "__main__":
    main()
