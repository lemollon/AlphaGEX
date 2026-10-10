"""Does the market already PAY you for the tail difference?

Net gamma near spot separates the next-day drawdown tail hard (27.4% vs 5.0%).
That is only tradeable if the credit does NOT already price it. So: sell a real
put spread off the real chain and compare P&L by gamma quintile.

🚨 dte=1 IS NOT ENOUGH - 41% of "1DTE" rows settle at the SAME close. The filter
must be expiration_date > trade_date.
"""
import duckdb, pandas as pd, numpy as np
C=duckdb.connect(r'C:\Users\lemol\dev\ironforge-data\warehouse\ironforge.duckdb', read_only=True)
feat=pd.read_parquet('vac3.parquet')[['trade_date','netband','dn_pct','ret_pct']]

px=C.execute("""select trade_date, max(spot) filter (where minute_of_day=959) as close
                from bt_spy group by 1 order by 1""").fetchdf().dropna().reset_index(drop=True)
px['nxt_close']=px.close.shift(-1); px['nxt_date']=px.trade_date.shift(-1)

ch=C.execute("""
  select trade_date, expiration_date, strike, put_mid
  from spy_options_eod
  where expiration_date > trade_date and dte <= 3
    and put_mid is not null and put_mid > 0
""").fetchdf()

rows=[]
for _,r in px.iterrows():
    if not np.isfinite(r.nxt_close): continue
    g=ch[(ch.trade_date==r.trade_date) & (ch.expiration_date==r.nxt_date)]
    if len(g)<10: continue
    s=r.close
    ks=g.set_index('strike').put_mid.sort_index()
    short_k=ks.index[np.argmin(np.abs(ks.index.values-s*0.995))]   # ~0.5% OTM
    long_k=short_k-2.0
    if long_k not in ks.index: continue
    credit=ks[short_k]-ks[long_k]
    if not (0.01 < credit < 2.0): continue
    settle=max(0.0,short_k-r.nxt_close)-max(0.0,long_k-r.nxt_close)   # cost to close
    rows.append({'trade_date':r.trade_date,'credit':credit,'pnl':100*(credit-settle),
                 'maxloss':100*(2.0-credit)})
t=pd.DataFrame(rows).merge(feat,on='trade_date')
t['q']=pd.qcut(t.netband.rank(method='first'),5,labels=False)
print(f"real short put spreads priced off the chain: n={len(t)}   "
      f"{t.trade_date.min().date()} .. {t.trade_date.max().date()}\n")
print(f"{'q':>2} {'net gamma $bn':>18} {'n':>4} {'credit':>7} {'P&L/trade':>10} {'win%':>6} {'worst':>8} {'tail dn':>8}")
for q,g in t.groupby('q'):
    print(f"{q:>2} {g.netband.min():+8.2f}..{g.netband.max():+7.2f} {len(g):>4} "
          f"${g.credit.mean():.3f} {g.pnl.mean():+9.2f} {100*(g.pnl>0).mean():5.1f}% "
          f"{g.pnl.min():+8.0f} {100*(g.dn_pct<=-1).mean():7.1f}%")
a,b=t[t.q==4],t[t.q==0]
d=a.pnl.mean()-b.pnl.mean(); se=np.sqrt(a.pnl.var()/len(a)+b.pnl.var()/len(b))
print(f"\n  high-gamma minus low-gamma P&L: {d:+.2f}/trade, t={d/se:+.2f}")
print(f"  credit received:  high {a.credit.mean():.3f}  low {b.credit.mean():.3f}  "
      f"-> the market {'DOES' if b.credit.mean()>a.credit.mean()*1.05 else 'does NOT'} pay more for the risky bucket")
print("\nper-year P&L/trade, top quintile:")
a2=a.copy(); a2['yr']=pd.to_datetime(a2.trade_date).dt.year
for y,g in a2.groupby('yr'): print(f"   {y} n={len(g):>3} {g.pnl.mean():+.2f}")
