"""Rebuild backend/data/rolling_flow_baselines.json from the warehouse.

The file was originally generated ad hoc and never committed with a builder,
which meant the only way to add a series to it was to re-derive the whole
convention from a docstring. This is that builder, verified to reproduce the
shipped put/total numbers exactly (minute 696: put_mean 1806823.5873,
put_sd 400623.0430) before the mix series was appended.

WHAT IT ADDS: `pc_mean` / `pc_sd` — the trailing-63 baseline of the CUMULATIVE
put/call VOLUME RATIO, per minute. The rolling watcher previously graded put
volume and total volume as LEVELS only. Those are the two legs that were both
correctly quiet at 10:00 CT on 2026-08-17 (putv +0.58, totv -0.45) while the
ratio printed +2.72 — the highest of the trailing 63. The fixed clocks were
taught to divide them; the every-10-minute watcher was not, so the intraday
tape carried the pre-08/18 metric all day.

Ratio convention MUST match routes_risk._pc: putv / (totv - putv) on
cumulative session volume, ET minute-of-day (571 = 09:31 ET).
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import duckdb

DB = r"C:\Users\lemol\dev\ironforge-data\warehouse\ironforge.duckdb"
OUT = Path(__file__).resolve().parents[1] / "backend" / "data" / "rolling_flow_baselines.json"
LAST_SESSION = "2026-08-11"   # keep the window pinned to the shipped file
SESSIONS = 63
# 2026-08-19: was 696-900 (10:36-14:00 CT), which left 41% of the session with
# no flow reading at all — including 14:00-15:00, when 0DTE gamma peaks and
# EBB settles at the close. That range was never a data limit: bt_spy carries
# ~900 sessions at EVERY minute from 571 to 959. The tape could not see the
# last hour because a file stopped early, and the 08-17 lesson was that a
# session you cannot replay is one you cannot improve.
MIN_LO, MIN_HI = 571, 959     # 08:31-14:59 CT — the whole session

QUERY = f"""
with s as (
    select trade_date, minute_of_day, put_vol, call_vol
    from bt_spy
    where trade_date <= DATE '{LAST_SESSION}' and minute_of_day between 571 and 960
),
d as (select distinct trade_date from s order by trade_date desc limit {SESSIONS}),
j as (select s.* from s join d using(trade_date)),
cum as (
    select trade_date, minute_of_day,
           sum(put_vol)  over (partition by trade_date order by minute_of_day) as cp,
           sum(call_vol) over (partition by trade_date order by minute_of_day) as cc
    from j
)
select minute_of_day, cp, cc
from cum
where minute_of_day between {MIN_LO} and {MIN_HI}
order by minute_of_day
"""


def main() -> None:
    con = duckdb.connect(DB, read_only=True)
    rows = con.execute(QUERY).fetchall()
    con.close()

    by_min: dict[int, list[tuple[float, float]]] = {}
    for m, cp, cc in rows:
        by_min.setdefault(int(m), []).append((float(cp), float(cc)))

    baselines: dict[str, dict] = {}
    for m in sorted(by_min):
        puts = [p for p, _ in by_min[m]]
        tots = [p + c for p, c in by_min[m]]
        # cc is CALL volume here, so the ratio is put/call directly — but the
        # runtime computes it as putv/(totv-putv) from a snapshot that only
        # carries put and total. Same number; do it the runtime's way so a
        # rounding difference can never open a gap between them.
        ratios = [p / (t - p) for p, t in zip(puts, tots) if (t - p) > 0]
        if len(puts) < 2 or len(ratios) < 2:
            continue
        baselines[str(m)] = {
            "put_mean": round(st.mean(puts), 1),
            "put_sd": round(st.stdev(puts), 1),
            "tot_mean": round(st.mean(tots), 1),
            "tot_sd": round(st.stdev(tots), 1),
            "pc_mean": round(st.mean(ratios), 6),
            "pc_sd": round(st.stdev(ratios), 6),
        }

    out = {
        "seeded": "2026-08-13",
        "sessions": SESSIONS,
        "last_session": LAST_SESSION,
        "minute_convention": "ET minute-of-day (571=09:31 ET); window 696-900 = 10:36-14:00 CT",
        "source": "bt_spy cumulative put_vol/tot_vol, trailing 63 sessions",
        "mix_added": "2026-08-19 — pc_mean/pc_sd, cumulative put/call ratio",
        "baselines": baselines,
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {OUT} — {len(baselines)} minutes")


if __name__ == "__main__":
    main()
