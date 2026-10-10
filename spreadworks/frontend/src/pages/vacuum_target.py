"""(B) THE CLAIM I NEVER TESTED.

Not "does a vacuum make a fall more likely" - that was my test, and it failed.
His claim is: GIVEN a fall starts, the vacuum says HOW FAR it runs, and the next
real gamma strike is where it stops. That is conditional magnitude + a target,
and the mechanism only ever implied that.

Everything is known at t-1's close; the outcome is session t.
"""
import duckdb, pandas as pd, numpy as np
C=duckdb.connect(r'C:\Users\lemol\dev\ironforge-data\warehouse\ironforge.duckdb', read_only=True)
px=C.execute("""select trade_date, max(spot) filter (where minute_of_day=959) as close,
                min(spot) as low from bt_spy group by 1 order by 1""").fetchdf().dropna().reset_index(drop=True)
px['nxt_low']=px.low.shift(-1); px['nxt_date']=px.trade_date.shift(-1)
gk=C.execute("""select trade_date, strike, sum(gamma*(call_oi-put_oi))*100 as gex_raw
                from spy_options_eod where dte between 1 and 90 and gamma is not null
                group by 1,2""").fetchdf()
cur={d:(x.strike.values,x.gex_raw.values) for d,x in gk.groupby('trade_date')}

rows=[]
for _,r in px.iterrows():
    c=cur.get(r.trade_date)
    if c is None or not np.isfinite(r.nxt_low): continue
    k,v=c; s=r.close; gex=v*s*s*0.01/1e9
    band=(k>=s*0.94)&(k<=s*1.05)
    if band.sum()<20: continue
    mx=np.abs(gex[band]).max()
    if mx<=0: continue
    below=np.where((k<s)&(k>=s*0.94)&(np.abs(gex)>=0.10*mx))[0]
    if not len(below): continue
    floor_k=k[below].max()                       # the next real structure down
    air=100*(s-floor_k)/s                        # how much space above it
    dn=100*(r.nxt_low-s)/s                       # realised down excursion
    rows.append({'trade_date':r.trade_date,'close':s,'floor_k':floor_k,
                 'air':air,'dn':dn,'nxt_low':r.nxt_low,
                 'gap_to_floor':100*(r.nxt_low-floor_k)/floor_k})
f=pd.DataFrame(rows)
print(f"n={len(f)} sessions with an identifiable floor below\n")

# --- his claim, part 1: GIVEN a break, does air predict depth? ---
for brk in [0.3,0.5]:
    m=f[f.dn<=-brk]
    c=np.corrcoef(m.air,-m.dn)[0,1]
    print(f"GIVEN the low breaks {brk}% below the close (n={len(m)}):")
    print(f"   corr(air pocket, depth of the fall) = {c:+.3f}")
    m2=m.copy(); m2['q']=pd.qcut(m2.air.rank(method='first'),4,labels=False)
    for q,g in m2.groupby('q'):
        print(f"     air {g.air.min():5.2f}-{g.air.max():5.2f}%  n={len(g):>3}  "
              f"mean depth {g.dn.mean():+.3f}%   median {g.dn.median():+.3f}%")
    print()

# --- his claim, part 2: does the fall STOP at the floor? ---
m=f[f.dn<=-0.3]
print(f"DOES THE FALL STOP AT THE FLOOR?  (n={len(m)} breaking days)")
held=(m.nxt_low>=m.floor_k).mean()
print(f"   low held ABOVE the floor strike: {100*held:.1f}% of the time")
near=((m.gap_to_floor>=0)&(m.gap_to_floor<=0.15)).mean()
print(f"   low landed within 0.15% ABOVE the floor: {100*near:.1f}%")
# null: a random strike at the same distance carries no information
rng=np.random.default_rng(11); nulls=[]
for _ in range(2000):
    shuf=m.air.sample(frac=1,random_state=int(rng.integers(1e9))).values
    fake=m.close.values*(1-shuf/100)
    nulls.append(((m.nxt_low.values>=fake)).mean())
nulls=np.array(nulls)
print(f"   null (floor distances shuffled):  {100*nulls.mean():.1f}%  "
      f"[95% {100*np.percentile(nulls,2.5):.1f}-{100*np.percentile(nulls,97.5):.1f}]")
print(f"   -> real {100*held:.1f}% vs null {100*nulls.mean():.1f}%  "
      f"p={(nulls>=held).mean():.3f}")
