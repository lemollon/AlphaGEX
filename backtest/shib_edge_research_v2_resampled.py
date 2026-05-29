"""
SHIB edge research v2 — resample to a TRUE 1-minute grid (last price in each minute)
before computing autocorr and strategies. The raw feed is irregular (2s bursts +
gaps up to minutes), which inflates lag-1 autocorr via bid/ask bounce and makes
'minute' lookbacks ambiguous. A clean 1-min grid is the honest bar.

Research only.
"""
import math
import os
import sys
import statistics as st
from datetime import timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_adapter import get_connection

SLIP_PER_SIDE = 0.001
ROUND_TRIP = 2 * SLIP_PER_SIDE
FUNDING_PER_8H = 0.0001
FUNDING_PER_MIN = FUNDING_PER_8H / (8 * 60.0)

conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT timestamp, shib_price FROM agape_shib_futures_scan_activity
    WHERE shib_price IS NOT NULL AND shib_price > 0 ORDER BY timestamp ASC
""")
rows = cur.fetchall()
cur.close(); conn.close()

# Resample: last price per minute bucket. Forward-fill gaps (carry last price) so
# we have a contiguous grid; mark which minutes are real vs filled.
buckets = {}
for t, p in rows:
    key = int(t.replace(second=0, microsecond=0, tzinfo=timezone.utc).timestamp() // 60)
    buckets[key] = float(p)  # last wins (rows sorted asc)

kmin, kmax = min(buckets), max(buckets)
grid = []
real = []
last = None
for k in range(kmin, kmax + 1):
    if k in buckets:
        last = buckets[k]; r = True
    else:
        r = False
    if last is not None:
        grid.append(last); real.append(r)
px = grid
realf = real
n = len(px)
filled = sum(1 for x in realf if not x)

print("=" * 78)
print("SHIB EDGE RESEARCH v2 — 1-MINUTE RESAMPLED GRID")
print("=" * 78)
print(f"minute bars = {n}  (~{n/60/24:.2f} days)   forward-filled gaps = {filled} ({filled/n*100:.1f}%)")

ret = [math.log(px[i+1]/px[i]) for i in range(n-1)]
mean_r = st.mean(ret); std_r = st.pstdev(ret)
ann_vol = std_r * math.sqrt(365.25*24*60)
print(f"1-min mean ret={mean_r:+.3e}  std={std_r:.3e}  ann_vol~{ann_vol*100:.0f}%")
print(f"buy&hold gross = {(px[-1]/px[0]-1)*100:+.2f}%")

def autocorr(x, lag):
    m = st.mean(x)
    num = sum((x[i]-m)*(x[i-lag]-m) for i in range(lag, len(x)))
    den = sum((v-m)**2 for v in x)
    return num/den if den else float('nan')

print("\n--- 1-MIN RETURN AUTOCORRELATION ---")
print("lag(min)  autocorr")
for lag in (1,2,3,5,10,15,30,60,240):
    print(f"{lag:8d}  {autocorr(ret,lag):+.4f}")

# also autocorr on returns computed only from real (non-filled) consecutive bars,
# to make sure forward-fill (zero returns) isn't biasing toward negative
real_ret = [(math.log(px[i+1]/px[i]), realf[i] and realf[i+1]) for i in range(n-1)]
rr = [r for r,ok in real_ret if ok]
print(f"\nautocorr on REAL-only consecutive 1-min returns (n={len(rr)}):")
for lag in (1,2,3,5,10):
    print(f"  lag{lag}: {autocorr(rr,lag):+.4f}")

# ---- strategy core on minute grid ----
sec_per_bar = 60.0
def trade_pnl(i, j, d):
    gross = d*(px[j]/px[i]-1.0)
    funding = FUNDING_PER_MIN*(j-i)
    return gross - ROUND_TRIP - funding

def summarize(name, pnls):
    if not pnls:
        print(f"{name:36s} NO TRADES"); return None
    nt=len(pnls); wins=[p for p in pnls if p>0]; los=[p for p in pnls if p<=0]
    wr=len(wins)/nt; aw=st.mean(wins) if wins else 0; al=st.mean(los) if los else 0
    pay=(aw/abs(al)) if al else float('inf'); tot=sum(pnls)
    mu=st.mean(pnls); sd=st.pstdev(pnls) if nt>1 else 0; sh=mu/sd if sd else 0
    print(f"{name:36s} n={nt:5d} wr={wr*100:5.1f}% pay={pay:4.2f} tot={tot*100:+7.2f}% shrp={sh:+.3f}")
    return dict(name=name,n=nt,wr=wr,payoff=pay,total=tot,sharpe=sh)

results=[]
print("\n--- MOMENTUM (minute grid, non-overlapping) ---")
for L in (15,60,240):
    for H in (15,60,240):
        pnls=[]; i=L
        while i+H<n:
            mom=px[i]/px[i-L]-1
            d=1 if mom>0 else (-1 if mom<0 else 0)
            if d==0: i+=H; continue
            pnls.append(trade_pnl(i,i+H,d)); i+=H
        results.append(summarize(f"mom L={L} H={H}",pnls))

print("\n--- MEAN-REVERSION (minute grid) ---")
def roll_ms(p,W):
    m=[None]*len(p); s_=[None]*len(p); s=0.0; s2=0.0
    for i in range(len(p)):
        s+=p[i]; s2+=p[i]*p[i]
        if i>=W: o=p[i-W]; s-=o; s2-=o*o
        if i>=W-1:
            mu=s/W; var=max(0.0,s2/W-mu*mu); m[i]=mu; s_[i]=math.sqrt(var)
    return m,s_
for W in (30,120):
    for k in (1.5,2.0,2.5):
        m,sd=roll_ms(px,W); pnls=[]; i=W
        while i<n-1:
            if m[i] is None or not sd[i]: i+=1; continue
            z=(px[i]-m[i])/sd[i]; d=-1 if z>=k else (1 if z<=-k else 0)
            if d==0: i+=1; continue
            j=i+1
            while j<n-1 and j-i<W:
                zj=(px[j]-m[j])/sd[j] if (m[j] and sd[j]) else 0
                if (d==-1 and zj<=0) or (d==1 and zj>=0): break
                j+=1
            pnls.append(trade_pnl(i,j,d)); i=j+1
        results.append(summarize(f"meanrev W={W} k={k}",pnls))

# Contrarian micro: exploit the negative lag-1 autocorr directly.
# After a down 1-min bar go long for 1 bar; after up bar go short. (the bounce trade)
print("\n--- MICRO CONTRARIAN (1-bar bounce, tests neg autocorr) ---")
for hold in (1,2,5):
    pnls=[]; i=hold
    while i+hold<n:
        prev=px[i]/px[i-hold]-1
        d=-1 if prev>0 else (1 if prev<0 else 0)
        if d==0: i+=hold; continue
        pnls.append(trade_pnl(i,i+hold,d)); i+=hold
    results.append(summarize(f"contrarian {hold}min",pnls))
# and the same with ZERO cost to see if the raw signal has any sign edge
print("  (same, gross/zero-cost — does the signal even point right?)")
for hold in (1,2,5):
    pnls=[]; i=hold
    while i+hold<n:
        prev=px[i]/px[i-hold]-1
        d=-1 if prev>0 else (1 if prev<0 else 0)
        if d==0: i+=hold; continue
        pnls.append(d*(px[i+hold]/px[i]-1)); i+=hold
    summarize(f"contrarian {hold}min GROSS",pnls)

print("\n"+"="*78); print("RANKED BY AFTER-COST TOTAL RETURN"); print("="*78)
clean=[r for r in results if r]; clean.sort(key=lambda r:r['total'],reverse=True)
for r in clean:
    print(f"{r['name']:36s} n={r['n']:5d} wr={r['wr']*100:5.1f}% pay={r['payoff']:4.2f} tot={r['total']*100:+7.2f}% shrp={r['sharpe']:+.3f}")
print("\nDONE.")
