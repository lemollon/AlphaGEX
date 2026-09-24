"""MES CHOPGuard v14: adaptive volatility-regime gate.

Frozen architecture from portable research:
- corrected MES morning-continuation engine
- causal CHOPGuard: last 15 minutes confirm direction AND directional location >= 0.65
- LONG ONLY
- 09:00 CT entry / 12:00 CT exit
- existing fixed opening-range stop logic

V13 passed 2023-2024 but failed the already-seen 2025 chronological check.
The remaining hypothesis is volatility expansion: base risk grows directly with
the 30-minute opening range. V14 tests only causal, rolling volatility gates
using PRIOR 20 completed sessions. 2023-2025 are now development/robustness
years; 2026 remains untouched.

No broker calls, vendor downloads, sizing changes, or production rule changes.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, logging, os, subprocess, sys

STUDY="valor-mes-chopguard-v14-20260924"
LOCK=654202609
YEARS=(2023,2024,2025)
HASHES={
  2023:"2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
  2024:"6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
  2025:"629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}
GATES={
  "portable_base":{},
  "width_le_125_med20":{"max_med_ratio":1.25},
  "width_le_150_med20":{"max_med_ratio":1.50},
  "width_le_175_med20":{"max_med_ratio":1.75},
  "width_le_p80_20":{"max_quantile":0.80},
  "width_le_p90_20":{"max_quantile":0.90},
}

def trailing_opening_stats(d):
    import numpy as np
    widths={}
    for day,p in d[d.rth & d.minute.ge(510) & d.minute.lt(540)].groupby("date",sort=True):
        if len(p)==30 and p.segment.nunique()==1:
            widths[day]=float(p.high.max()-p.low.min())
    days=sorted(widths)
    out={}
    for k,day in enumerate(days):
        hist=[widths[x] for x in days[max(0,k-20):k]]
        if len(hist)<10:
            out[day]=None
            continue
        a=np.array(hist,float)
        out[day]={
          "width":widths[day],
          "median20":float(np.median(a)),
          "p80_20":float(np.quantile(a,.80)),
          "p90_20":float(np.quantile(a,.90)),
        }
    return out

def frozen_longs(d):
    from scripts import valor_mes_session_v6 as base
    from scripts import valor_mes_chopguard_v11 as v11
    raw,skipped=base.orders(d,"morning_continuation")
    stats=trailing_opening_stats(d)
    out=[]; incomplete=0; blocked_guard=0; blocked_short=0
    cfg={"late15":True,"dirloc_min":0.65}
    for o in raw:
        x=v11.enrich(d,o)
        st=stats.get(o["date"])
        if x is None or st is None or not st["median20"]:
            incomplete+=1; continue
        if not v11.passes(x,cfg):
            blocked_guard+=1; continue
        if int(x["side"])!=1:
            blocked_short+=1; continue
        x=dict(x)
        x.update(
          opening_width=st["width"],
          trailing_median20=st["median20"],
          trailing_p80_20=st["p80_20"],
          trailing_p90_20=st["p90_20"],
          width_med_ratio=st["width"]/st["median20"],
        )
        out.append(x)
    skipped=dict(skipped)
    skipped.update(v14_history_incomplete=incomplete,v14_chopguard_blocked=blocked_guard,
                   v14_short_blocked=blocked_short)
    return out,skipped,len(raw)

def gate_pass(o,cfg):
    if cfg.get("max_med_ratio") is not None and o["width_med_ratio"]>cfg["max_med_ratio"]:
        return False
    q=cfg.get("max_quantile")
    if q==.80 and o["opening_width"]>o["trailing_p80_20"]:
        return False
    if q==.90 and o["opening_width"]>o["trailing_p90_20"]:
        return False
    return True

def evaluate(frame,year):
    from scripts import valor_mes_session_v6 as base
    d=base.prepare(frame); frozen,skipped,raw_n=frozen_longs(d); rows=[]
    for name,cfg in GATES.items():
        kept=[o for o in frozen if gate_pass(o,cfg)]
        rejected=[o for o in frozen if not gate_pass(o,cfg)]
        kt,ku=base.replay(d,kept,"signal")
        rt,ru=base.replay(d,rejected,"signal") if rejected else ([],[])
        for ticks in (2,4):
            r=base.summarize(kt,ku,year,ticks)
            rr=base.summarize(rt,ru,year,ticks) if rejected else None
            r.update(candidate=name,year=year,raw_valid_decisions=raw_n,
                     frozen_long_decisions=len(frozen),kept_decisions=len(kept),
                     volatility_rejected=len(rejected),
                     volatility_rejected_net=(rr["net_dollars"] if rr else 0.0),
                     volatility_rejected_pf=(rr["profit_factor"] if rr else None),
                     base_signal_skips=skipped,research_only=True,
                     production_changed=False,live_ready=False)
            rows.append(r)
    return dict(study=STUDY,year=year,
                frozen_chopguard="late15_confirm + directional_location>=0.65",
                direction="long_only",entry_minute_ct=540,exit_minute_ct=720,
                trailing_volatility_window_sessions=20,gates=GATES,
                selection_cost_ticks_each_side=4,round_trip_fee_assumed=3.0,
                years_role="2023-2025 development/robustness; 2026 untouched",
                new_vendor_downloads=0,broker_calls=0,production_changed=False,
                live_ready=False),rows

def choose(dev):
    picks=[]
    for name in GATES:
        if name=="portable_base": continue
        rs=[r for y in YEARS for r in dev.get(y,[])
            if r["candidate"]==name and r["cost_ticks_each_side"]==4]
        if len(rs)!=3: continue
        if not all(r["trades"]>=40 and r["net_dollars"]>0 and
                   r["profit_factor"] is not None and r["profit_factor"]>=1.05 and
                   r["unresolved_fraction"]<=.04 for r in rs):
            continue
        worst=min(r["net_dollars"]/max(1.0,r["closed_trade_max_drawdown"]) for r in rs)
        picks.append((worst,sum(r["net_dollars"] for r in rs),name))
    return sorted(picks,key=lambda z:(-z[0],-z[1],z[2]))[0][2] if picks else None

def run():
    import pandas as pd, psycopg2
    from psycopg2.extras import Json
    if hasattr(os,"nice"): os.nice(10)
    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=15); conn.autocommit=True
    cur=conn.cursor(); cur.execute("SELECT pg_try_advisory_lock(%s)",(LOCK,))
    if not cur.fetchone()[0]: conn.close(); return
    sh=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def state(status,**detail):
        cur.execute("""INSERT INTO valor_mes_chopguard_v14_state(study_id,status,detail)
          VALUES(%s,%s,%s) ON CONFLICT(study_id) DO UPDATE
          SET status=excluded.status,detail=excluded.detail,updated_at=now()""",
          (STUDY,status,Json(dict(detail,source_sha256=sh,research_only=True,
                                 production_changed=False,new_vendor_downloads=0))))
    def cached(y):
        cur.execute("SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",
                    (f"GLBX.MDP3:ohlcv-1m:MES.v.0:{y}",))
        row=cur.fetchone()
        if not row: raise ValueError("cache absent; vendor download prohibited")
        body=bytes(row[1]); dig=hashlib.sha256(body).hexdigest()
        if dig!=row[0] or dig!=HASHES[y]: raise ValueError("cache checksum mismatch")
        return pd.read_parquet(io.BytesIO(body))
    def store(y,m,rows):
        m.update(source_sha256=sh,cache_sha256=HASHES[y])
        summary=[{k:v for k,v in r.items() if k not in ("ledger","unresolved_ledger")} for r in rows]
        evidence=gzip.compress(json.dumps(rows,allow_nan=False).encode(),mtime=0)
        cur.execute("""INSERT INTO valor_mes_chopguard_v14_results
          (study_id,year,manifest,summary,evidence_gzip) VALUES(%s,%s,%s,%s,%s)
          ON CONFLICT(study_id,year) DO NOTHING""",
          (STUDY,y,Json(m),Json(summary),psycopg2.Binary(evidence)))
        return summary
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v14_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v14_results(
          study_id text,year int,manifest jsonb NOT NULL,summary jsonb NOT NULL,evidence_gzip bytea NOT NULL,
          created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,year));""")
        cur.execute("SELECT status FROM valor_mes_chopguard_v14_state WHERE study_id=%s",(STUDY,))
        if cur.fetchone()==("completed",): return
        dev={}
        for y in YEARS:
            state("evaluating",year=y)
            m,rows=evaluate(cached(y),y); dev[y]=store(y,m,rows)
        selected=choose(dev)
        state("completed",selected=selected,
              selection_gate={"positive_stress_net_each_year":True,
                              "profit_factor_min_each_year":1.05,
                              "trades_min_each_year":40,
                              "unresolved_fraction_max_each_year":.04},
              untouched_next_year=2026)
    except Exception as e:
        try: state("failed",error_type=type(e).__name__,message=str(e)[:500])
        except Exception: pass
        logging.getLogger(__name__).exception("MES CHOPGuard v14 failed")
    finally:
        try: cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally: conn.close()

def launch_if_enabled():
    flag=os.getenv("VALOR_MES_CHOPGUARD_V14_AUTORUN",
                   os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false"))
    if flag.lower() not in {"1","true","yes","on"}: return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_chopguard_v14"],
                     env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True

if __name__=="__main__": run()
