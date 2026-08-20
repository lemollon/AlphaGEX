"""Walk-forward on the gamma sizing gate.

THE CONTROL IS THE POINT. Every fold reports the SAME test days traded flat -
sell the spread every session - so the question is never "did the gated version
make money" (VRP does that on its own, t=+3.36) but "did gating beat not
gating, on days it had never seen".

The claim is RISK-ADJUSTED, so the fit maximises EV/sd, not EV. 'no gate' is in
the grid, so a fold is free to decide gating is worthless.
"""
import pandas as pd, numpy as np, duckdb
exec(open('money.py').read().split("t['q']=")[0])       # builds `t`
t['yr']=pd.to_datetime(t.trade_date).dt.year
t=t.sort_values('trade_date').reset_index(drop=True)

# Threshold grid in $bn of net gamma in the +-5% band. -99 == no gate.
GRID=[-99,-2,0,1,2,3,4,5,6,8]

def sharpe(s):
    return s.mean()/s.std(ddof=1) if len(s)>2 and s.std(ddof=1)>0 else -9e9

print(f"{'test':>5} {'picked':>8} | {'n flat':>6} {'EV flat':>8} {'sd':>6} {'S':>6} | "
      f"{'n gate':>6} {'EV gate':>8} {'sd':>6} {'S':>6} | {'dEV':>7} {'dS':>6}")
print("-"*104)
oz_g, oz_f = [], []
for ty in [2024,2025,2026]:
    tr,te=t[t.yr<ty],t[t.yr==ty]
    if len(tr)<80: continue
    best,bs=None,-9e9
    for th in GRID:
        s=tr[tr.netband>=th]
        if len(s)<40: continue
        v=sharpe(s.pnl)
        if v>bs: bs,best=v,th
    if best is None: continue
    gate=te[te.netband>=best]
    print(f"{ty:>5} {('none' if best==-99 else f'>={best}'):>8} | "
          f"{len(te):6d} {te.pnl.mean():+7.2f} {te.pnl.std():6.1f} {sharpe(te.pnl):6.3f} | "
          f"{len(gate):6d} {gate.pnl.mean():+7.2f} {gate.pnl.std():6.1f} {sharpe(gate.pnl):6.3f} | "
          f"{gate.pnl.mean()-te.pnl.mean():+6.2f} {sharpe(gate.pnl)-sharpe(te.pnl):+6.3f}")
    oz_g+=list(gate.pnl); oz_f+=list(te.pnl)

g,fl=np.array(oz_g),np.array(oz_f)
print("-"*104)
print(f"\nBLIND TOTALS")
print(f"  flat : n={len(fl):3d}  EV {fl.mean():+.2f}  sd {fl.std(ddof=1):.1f}  "
      f"Sharpe/trade {fl.mean()/fl.std(ddof=1):.3f}  total ${fl.sum():+.0f}")
print(f"  gated: n={len(g):3d}  EV {g.mean():+.2f}  sd {g.std(ddof=1):.1f}  "
      f"Sharpe/trade {g.mean()/g.std(ddof=1):.3f}  total ${g.sum():+.0f}")
print(f"  delta: EV {g.mean()-fl.mean():+.2f}/trade   "
      f"Sharpe {g.mean()/g.std(ddof=1)-fl.mean()/fl.std(ddof=1):+.3f}")
se=np.sqrt(g.var(ddof=1)/len(g)+fl.var(ddof=1)/len(fl))
print(f"  EV difference t = {(g.mean()-fl.mean())/se:+.2f}")
print(f"  worst trade: flat {fl.min():+.0f}  gated {g.min():+.0f}")
print(f"  worst 5% mean: flat {np.percentile(fl,5):+.0f}  gated {np.percentile(g,5):+.0f}")
