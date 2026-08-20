"""FOLLOW THE MONEY: change in dealer positioning, not its level.

Everything tested so far used OI *levels* - the state of the board. This uses
the DELTA: which strikes gained open interest yesterday, i.e. where new dealer
gamma was actually created. That is a different variable and it has not been
looked at.

Known at t's close, evaluated on t+1. Nothing here sees the future.
"""
import duckdb, numpy as np, pandas as pd
C=duckdb.connect(r'C:\Users\lemol\dev\ironforge-data\warehouse\ironforge.duckdb', read_only=True)

px=C.execute("""select trade_date, max(spot) filter (where minute_of_day=959) as close,
                min(spot) as low, max(spot) as high
                from bt_spy group by 1 order by 1""").fetchdf().dropna().reset_index(drop=True)
px['nxt_ret']=100*(px.close.shift(-1)-px.close)/px.close
px['nxt_dn']=100*(px.low.shift(-1)-px.close)/px.close
px['nxt_up']=100*(px.high.shift(-1)-px.close)/px.close

# Per strike per day: gamma and OI, dte 1-90.
oi=C.execute("""
  select trade_date, strike,
         sum(call_oi) as coi, sum(put_oi) as poi,
         sum(gamma*call_oi) as cg, sum(gamma*put_oi) as pg,
         avg(gamma) as g
  from spy_options_eod where dte between 1 and 90 and gamma is not null
  group by 1,2 order by 1,2
""").fetchdf()

prev={}
rows=[]
for d, g in oi.groupby('trade_date'):
    cur=g.set_index('strike')
    if prev:
        pd_, pk = prev['d'], prev['t']
        j=cur.join(pk[['coi','poi']], rsuffix='_p', how='inner').dropna()
        if len(j) > 30:
            j['dcoi']=j.coi-j.coi_p
            j['dpoi']=j.poi-j.poi_p
            rows.append({'trade_date': d, 'prev': pd_, 'tbl': j})
    prev={'d': d, 't': cur}

feat=[]
for r in rows:
    s=px.loc[px.trade_date==r['trade_date'],'close']
    if not len(s): continue
    s=float(s.iloc[0])
    j=r['tbl']
    near=j[(j.index>=s*0.95)&(j.index<=s*1.05)]
    if len(near)<15: continue
    scale=100*s*s*0.01/1e9
    # NEW dealer gamma created yesterday (calls +, puts -)
    dgex=float((near.g*(near.dcoi-near.dpoi)).sum())*scale
    # WHERE it was created, relative to spot
    up=near[near.index>s]; dn=near[near.index<s]
    dgex_up=float((up.g*(up.dcoi-up.dpoi)).sum())*scale
    dgex_dn=float((dn.g*(dn.dcoi-dn.dpoi)).sum())*scale
    # Raw contract flow, unweighted by gamma - the crude "who bought what"
    dcall=float(near.dcoi.sum()); dput=float(near.dpoi.sum())
    feat.append({'trade_date':r['trade_date'],'spot':s,'dgex':dgex,
                 'dgex_up':dgex_up,'dgex_dn':dgex_dn,
                 'dcall':dcall,'dput':dput,
                 'pc_flow':(dput-dcall)/(abs(dput)+abs(dcall)+1)})
f=pd.DataFrame(feat).merge(px[['trade_date','nxt_ret','nxt_dn','nxt_up']],on='trade_date').dropna()
f['yr']=pd.to_datetime(f.trade_date).dt.year
f.to_parquet('doi.parquet')
print(f"sessions with a usable OI change: {len(f)}  {f.trade_date.min().date()} .. {f.trade_date.max().date()}")
