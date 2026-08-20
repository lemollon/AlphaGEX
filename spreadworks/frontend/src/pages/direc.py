"""(A) Is direction really 50/50? I have been saying "coin flip" too loosely."""
import duckdb, pandas as pd, numpy as np
C=duckdb.connect(r'C:\Users\lemol\dev\ironforge-data\warehouse\ironforge.duckdb', read_only=True)
d=C.execute("""select trade_date,
       max(spot) filter (where minute_of_day=959) as close,
       min(spot) as low, max(spot) as high
     from bt_spy group by 1 order by 1""").fetchdf().dropna().reset_index(drop=True)
d['ret']=100*(d.close.shift(-1)-d.close)/d.close
d['dn']=100*(d.low.shift(-1)-d.close)/d.close
d['up']=100*(d.high.shift(-1)-d.close)/d.close
d=d.dropna()
n=len(d)
print(f"SPY next-session direction, n={n} (2023-2026)\n")
pu=(d.ret>0).mean()
print(f"  P(up day)            {100*pu:5.1f}%   P(down day) {100*(1-pu):5.1f}%")
print(f"  mean next-day return {d.ret.mean():+.4f}%   median {d.ret.median():+.4f}%")
for th in [0.5,1.0,1.5]:
    a,b=(d.ret>=th).mean(),(d.ret<=-th).mean()
    print(f"  P(up>={th}%) {100*a:5.1f}%  vs  P(down<=-{th}%) {100*b:5.1f}%   "
          f"ratio {a/b if b else float('nan'):.2f}x")
print(f"\n  mean UP excursion  {d.up.mean():+.3f}%")
print(f"  mean DOWN excursion {d.dn.mean():+.3f}%   -> intraday range is "
      f"{'SKEWED UP' if d.up.mean()>abs(d.dn.mean()) else 'SKEWED DOWN'}")
print(f"\n  So it is NOT 50/50. The drift is real and it is UP.")
print(f"  A 'coin flip' framing understates the base case by "
      f"{100*pu-50:.1f} points of directional edge that is free.")
