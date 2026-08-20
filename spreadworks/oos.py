"""OUT-OF-SAMPLE test per PREREG.md. Run once. Report whatever comes out."""
import duckdb, numpy as np, pandas as pd
C=duckdb.connect(r'C:\Users\lemol\dev\ironforge-data\warehouse\ironforge.duckdb', read_only=True)

def build(ticker, lo, hi):
    px=C.execute(f"""select trade_date, spot from gex_daily_orat
                     where ticker='{ticker}' and trade_date between '{lo}' and '{hi}'
                     and spot is not null order by trade_date""").fetchdf()
    px['nxt']=px.spot.shift(-1)
    px['ret']=100*(px.nxt-px.spot)/px.spot
    oi=C.execute(f"""select trade_date, strike, sum(call_oi) coi, sum(put_oi) poi,
                            avg(gamma) g
                     from orat_options_eod
                     where ticker='{ticker}' and dte between 1 and 90 and gamma is not null
                       and trade_date between '{lo}' and '{hi}'
                     group by 1,2 order by 1,2""").fetchdf()
    spot={r.trade_date:r.spot for r in px.itertuples()}
    prev=None; rows=[]
    for d,g in oi.groupby('trade_date'):
        cur=g.set_index('strike')
        s=spot.get(d)
        if prev is not None and s and np.isfinite(s):
            j=cur.join(prev[['coi','poi']],rsuffix='_p',how='inner').dropna()
            band=j[(j.index>=s*0.95)&(j.index<s)]
            if len(band)>=10:
                v=float((band.g*((band.coi-band.coi_p)-(band.poi-band.poi_p))).sum())
                rows.append({'trade_date':d,'dgex_dn':v*100*s*s*0.01/1e9})
        prev=cur
    f=pd.DataFrame(rows).merge(px[['trade_date','ret']],on='trade_date').dropna()
    return f

def report(name, f):
    if len(f)<100:
        print(f"{name}: only {len(f)} sessions — cannot test"); return None
    f=f.copy(); f['q']=pd.qcut(f.dgex_dn.rank(method='first'),5,labels=False)
    top=f[f.q==4]; allm=f.ret.mean()
    edge=top.ret.mean()-allm
    t=(top.ret.mean()-allm)/np.sqrt(top.ret.var()/len(top)+f.ret.var()/len(f))
    print(f"\n=== {name}   n={len(f)}  {f.trade_date.min()} .. {f.trade_date.max()}")
    print(f"    all days      mean {allm:+.4f}%   P(up) {100*(f.ret>0).mean():.1f}%")
    print(f"    top quintile  mean {top.ret.mean():+.4f}%   P(up) {100*(top.ret>0).mean():.1f}%   n={len(top)}")
    print(f"    EDGE          {edge:+.4f}%/day   t={t:+.2f}   -> {'PASS' if edge>0 else 'FAIL'}")
    print(f"    quintile means: {[round(f[f.q==i].ret.mean(),4) for i in range(5)]}")
    return edge

print("PRE-REGISTERED OUT-OF-SAMPLE TEST")
print("pass bar: top-quintile mean > all-days mean on BOTH sets\n")
e1=report("SPX 2020-2026 (different instrument)", build('SPX','2020-01-02','2026-08-11'))
e2=report("SPY 2020-2022 (untouched years)",      build('SPY','2020-01-02','2022-12-31'))
print("\n" + "="*62)
if e1 is not None and e2 is not None:
    print(f"VERDICT: {'PASS' if (e1>0 and e2>0) else 'FAIL'}  (SPX {e1:+.4f}%, SPY20-22 {e2:+.4f}%)")
