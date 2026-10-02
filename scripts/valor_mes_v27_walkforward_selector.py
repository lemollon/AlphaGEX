"""MES v27 high-frequency walk-forward event selector.

Shared feature/build helpers used by v28.
Research only; 2026 untouched.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, math, os, subprocess, sys
from collections import defaultdict, deque

STUDY="valor-mes-v27-walkforward-selector-20260925"
LOCK=667202609
V22="valor-mes-v22-event-driven-20260924"
YEARS=(2023,2024,2025)
HASHES={
  2023:"2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
  2024:"6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
  2025:"629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}
ENGINES=("or_breakout_retest","failed_or_breakout","vwap_reclaim","compression_breakout")

def load_bars(cur):
    import pandas as pd
    from scripts import valor_mes_rebuild_v4 as core
    contexts={}
    for y in YEARS:
        cur.execute("SELECT sha256, parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",
                    (f"GLBX.MDP3:ohlcv-1m:MES.v.0:{y}",))
        row=cur.fetchone()
        if not row: raise ValueError(f"missing MES cache {y}")
        body=bytes(row[1]); dig=hashlib.sha256(body).hexdigest()
        if dig!=row[0] or dig!=HASHES[y]: raise ValueError(f"cache checksum mismatch {y}")
        d=core.prepare(pd.read_parquet(io.BytesIO(body)))
        b,_=core.context(d)
        for r in b.itertuples(index=False):
            contexts[(y,int(r.raw_index))]=r
    return contexts

def load_events(cur, contexts):
    out=[]
    hist={e:deque(maxlen=10) for e in ENGINES}
    global_hist=deque(maxlen=20)
    raw=[]
    for y in YEARS:
        cur.execute("SELECT evidence_gzip FROM valor_mes_v22_results WHERE study_id=%s AND year=%s",(V22,y))
        rr=cur.fetchone()
        if not rr: raise ValueError(f"missing v22 evidence {y}")
        rows=json.loads(gzip.decompress(bytes(rr[0])))
        base={r["candidate"]:r for r in rows if int(r["cost_ticks_each_side"])==4}
        for e in ENGINES:
            for t in base[e]["trade_ledger"]:
                x=dict(t); x["engine"]=e; x["year"]=y
                raw.append(x)
    raw.sort(key=lambda z:(z["date"],z["entry"],z["engine"]))

    by_day=defaultdict(list)
    for x in raw: by_day[x["date"]].append(x)

    for day in sorted(by_day):
        todays=by_day[day]
        for t in todays:
            r=contexts.get((int(t["year"]),int(t["index"])))
            if r is None: continue
            atr=float(r.atr) if getattr(r,"atr",None) is not None and math.isfinite(float(r.atr)) else None
            if not atr or atr<=0: continue
            orh=float(r.or_high); orl=float(r.or_low); vw=float(r.vwap)
            width=orh-orl
            if not (math.isfinite(width) and width>0 and math.isfinite(vw)): continue
            side=int(t["side"]); ref=float(t["reference"])
            eng_hist=list(hist[t["engine"]]); gh=list(global_hist)
            edge5=sum(eng_hist[-5:])/len(eng_hist[-5:]) if len(eng_hist)>=5 else 0.0
            edge10=sum(eng_hist[-10:])/len(eng_hist[-10:]) if len(eng_hist)>=10 else 0.0
            g10=sum(gh[-10:])/len(gh[-10:]) if len(gh)>=10 else 0.0
            loc=((ref-orl)/width) if side>0 else ((orh-ref)/width)
            dist_edge=(side*(ref-(orh if side>0 else orl)))/atr
            risk=float(t["risk"]) if t.get("risk") is not None else abs(ref-float(t["stop"]))
            reward=abs(float(t["target"])-ref) if t.get("target") is not None else 0.0
            feat=dict(
                minute=float(r.minute)/390.0,
                side=float(side),
                atr=atr,
                or_width_atr=width/atr,
                vwap_dist_atr=side*(ref-vw)/atr,
                or_location=loc,
                edge_dist_atr=dist_edge,
                risk_atr=risk/atr,
                rr=(reward/risk if risk>0 else 0.0),
                edge5=edge5/25.0,
                edge10=edge10/25.0,
                global10=g10/25.0,
                engine=t["engine"],
            )
            out.append(dict(event=t,features=feat,label=1 if float(t["net"])>0 else 0,
                            net=float(t["net"]),date=day,year=int(t["year"])))
        for t in todays:
            pnl=float(t["net"])
            hist[t["engine"]].append(pnl)
            global_hist.append(pnl)
    return out

def matrix(items):
    import numpy as np
    names=["minute","side","atr","or_width_atr","vwap_dist_atr","or_location",
           "edge_dist_atr","risk_atr","rr","edge5","edge10","global10"]
    X=[]
    for z in items:
        f=z["features"]
        row=[float(f[k]) for k in names]
        row += [1.0 if f["engine"]==e else 0.0 for e in ENGINES]
        X.append(row)
    return np.asarray(X,float)

def launch_if_enabled():
    return False

if __name__=="__main__":
    pass
