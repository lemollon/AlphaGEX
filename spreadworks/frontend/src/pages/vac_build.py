"""Continuous downside-gamma-vacuum measure, per session.

WHAT THE FIRST TEST GOT WRONG. It asked "is there a shelf with a vacuum below,
yes or no" - a binary that fired 48% of days, which is close to uninformative by
construction. The tradeable quantity is not WHETHER there is a hole but HOW BIG
it is, so this measures depth continuously and lets the outcome sort it.

Look-ahead discipline:
  * the chain is the EOD chain of day t, so every feature is known at t's close
  * outcomes are measured on t+1, which is the first session you could trade
  * 🚨 spot is the REAL close from bt_spy, never ORAT's underlying_price
    (corr 0.9495 against real closes - it is not a close)
"""
import duckdb, numpy as np, pandas as pd

C = duckdb.connect(r'C:\Users\lemol\dev\ironforge-data\warehouse\ironforge.duckdb', read_only=True)

# Real closes + next-session outcomes.
px = C.execute("""
  select trade_date,
         max(spot) filter (where minute_of_day=959) as close,
         min(spot) as low, max(spot) as high
  from bt_spy group by 1 order by 1
""").fetchdf().dropna().reset_index(drop=True)
px['nxt_low']   = px.low.shift(-1)
px['nxt_high']  = px.high.shift(-1)
px['nxt_close'] = px.close.shift(-1)
px['dn_pct'] = 100*(px.nxt_low  - px.close)/px.close     # worst drawdown next session
px['up_pct'] = 100*(px.nxt_high - px.close)/px.close
px['ret_pct']= 100*(px.nxt_close- px.close)/px.close

# Per-strike net dealer gamma, dte 1-90, standard convention (calls +, puts -).
gk = C.execute("""
  select trade_date, strike,
         sum(gamma * (call_oi - put_oi)) * 100 as gex_raw
  from spy_options_eod
  where dte between 1 and 90 and gamma is not null
  group by 1,2
""").fetchdf()

rows = []
for d, g in gk.groupby('trade_date'):
    rows.append((d, g.strike.values, g.gex_raw.values))
curves = {d: (k, v) for d, k, v in rows}

feat = []
for i, r in px.iterrows():
    d, s = r.trade_date, r.close
    cur = curves.get(d)
    if cur is None or not np.isfinite(s):
        continue
    k, v = cur
    gex = v * s * s * 0.01 / 1e9          # $bn per 1% move
    band = (k >= s*0.95) & (k <= s*1.05)
    if band.sum() < 20:
        continue
    tot = np.abs(gex[band]).sum()
    if tot <= 0:
        continue
    # DOWNSIDE SUPPORT DENSITY: how much gamma sits in the 2% under spot,
    # as a share of everything within +-5%. Low = a hole under the market.
    near = (k >= s*0.98) & (k < s)
    dens = np.abs(gex[near]).sum() / tot
    # AIR POCKET: how far you fall before hitting a strike carrying at least
    # 10% of the largest single-strike concentration in the band.
    thresh = 0.10 * np.abs(gex[band]).max()
    below = np.where((k < s) & (np.abs(gex) >= thresh))[0]
    airpct = 100*(s - k[below].max())/s if len(below) else 5.0
    feat.append({'trade_date': d, 'close': s, 'dens': dens, 'air': airpct,
                 'tot_gex': gex[band].sum(),
                 'dn_pct': r.dn_pct, 'up_pct': r.up_pct, 'ret_pct': r.ret_pct})

f = pd.DataFrame(feat).dropna()
f['yr'] = pd.to_datetime(f.trade_date).dt.year
f.to_parquet('vac.parquet')
print(f"sessions with a usable curve: {len(f)}   {f.trade_date.min()} .. {f.trade_date.max()}")
print(f"\ndownside support density: {f.dens.describe()[['min','25%','50%','75%','max']].round(4).to_dict()}")
print(f"air pocket %:             {f.air.describe()[['min','25%','50%','75%','max']].round(3).to_dict()}")
