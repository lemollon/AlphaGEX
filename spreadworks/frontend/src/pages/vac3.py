import duckdb, pandas as pd, numpy as np
C=duckdb.connect(r'C:\Users\lemol\dev\ironforge-data\warehouse\ironforge.duckdb', read_only=True)
px=C.execute("""select trade_date, max(spot) filter (where minute_of_day=959) as close,
                min(spot) as low from bt_spy group by 1 order by 1""").fetchdf().dropna().reset_index(drop=True)
px['nxt_low']=px.low.shift(-1); px['nxt_close']=px.close.shift(-1)
px['dn_pct']=100*(px.nxt_low-px.close)/px.close
px['ret_pct']=100*(px.nxt_close-px.close)/px.close
gk=C.execute("""select trade_date, strike, sum(gamma*(call_oi-put_oi))*100 as gex_raw
                from spy_options_eod where dte between 1 and 90 and gamma is not null
                group by 1,2""").fetchdf()
cur={d:(x.strike.values,x.gex_raw.values) for d,x in gk.groupby('trade_date')}
rows=[]
for _,r in px.iterrows():
    c=cur.get(r.trade_date)
    if c is None or not np.isfinite(r.dn_pct): continue
    k,v=c; s=r.close; gex=v*s*s*0.01/1e9
    band=(k>=s*0.95)&(k<=s*1.05)
    if band.sum()<20: continue
    mx=np.abs(gex[band]).max(); tot=np.abs(gex[band]).sum()
    if mx<=0 or tot<=0: continue
    shelf=(k>=s)&(k<=s*1.005); hole=(k>=s*0.99)&(k<s)
    rows.append({'trade_date':r.trade_date,
                 'shelf':(gex[shelf].max() if shelf.any() else 0)/mx,
                 'hole':np.abs(gex[hole]).sum()/tot,
                 'netband':gex[band].sum(),
                 'dn_pct':r.dn_pct,'ret_pct':r.ret_pct})
df=pd.DataFrame(rows); df['yr']=pd.to_datetime(df.trade_date).dt.year
df.to_parquet('vac3.parquet')

def blk(nm,col,asc=False):
    d=df.copy(); d['q']=pd.qcut(d[col].rank(method='first'),5,labels=False)
    out=[]
    for q,g in d.groupby('q'):
        out.append(f"q{q} n={len(g):>3} dn {g.dn_pct.mean():+.3f}% tail {100*(g.dn_pct<=-1).mean():5.1f}%")
    a,b=d[d.q==4],d[d.q==0]
    t=(a.dn_pct.mean()-b.dn_pct.mean())/np.sqrt(a.dn_pct.var()/len(a)+b.dn_pct.var()/len(b))
    print(f"{nm}\n   " + " | ".join(out) + f"\n   top-vs-bottom t={t:+.2f}\n")

print(f"n = {len(df)} sessions\n")
blk("SHELF ALONE (how big the strike you sit on)", 'shelf')
blk("HOLE ALONE (gamma in the 1% below)", 'hole')
blk("NET GAMMA IN BAND (the plain aggregate)", 'netband')
print("weight sensitivity on shelf - w*hole  (is w=3 special?)")
for w in [0,1,2,3,5,8]:
    d=df.copy(); d['s']=d.shelf-w*d.hole
    d['q']=pd.qcut(d.s.rank(method='first'),5,labels=False)
    a,b=d[d.q==4],d[d.q==0]
    t=(a.dn_pct.mean()-b.dn_pct.mean())/np.sqrt(a.dn_pct.var()/len(a)+b.dn_pct.var()/len(b))
    print(f"   w={w}: top tail {100*(a.dn_pct<=-1).mean():5.1f}%  bottom tail {100*(b.dn_pct<=-1).mean():5.1f}%  t={t:+.2f}")
