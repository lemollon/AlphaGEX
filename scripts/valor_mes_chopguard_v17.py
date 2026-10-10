"""MES CHOPGuard v17: delayed reconfirmation only on disturbed-regime mornings.

Frozen architecture:
- corrected morning_continuation
- portable CHOPGuard: late15 confirmation + directional location >= .65
- LONG ONLY
- normal days enter 09:00 CT and exit 12:00 CT
- original stop geometry

V16 identified shock125_reg110 as a 2025 toxic bucket, but those same days were
profitable in 2024. V17 does NOT delete those days. It delays only those flagged
days to 09:15 or 09:30 CT and requires price to still confirm the long thesis
using data available at the delayed decision time.

2023-2025 are development/robustness years. 2026 remains untouched.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, logging, os, subprocess, sys

STUDY="valor-mes-chopguard-v17-20260924"
LOCK=657202609
YEARS=(2023,2024,2025)
HASHES={
  2023:"2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
  2024:"6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
  2025:"629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}
MODES={
 "portable_base":{"delay":None,"vwap":False},
 "delay15_hold":{"delay":555,"vwap":False},
 "delay15_hold_vwap":{"delay":555,"vwap":True},
 "delay30_hold":{"delay":570,"vwap":False},
 "delay30_hold_vwap":{"delay":570,"vwap":True},
}

def disturbed(o):
    return o["width_med_ratio"]>1.25 and o["regime_ratio"]>1.10

def prepare_orders(d):
    from scripts import valor_mes_session_v6 as base
    from scripts import valor_mes_chopguard_v11 as v11
    from scripts import valor_mes_chopguard_v16 as v16
    raw,skipped=base.orders(d,"morning_continuation")
    stats=v16.trailing_stats(d)
    out=[]; incomplete=guard_blocked=short_blocked=0
    guard={"late15":True,"dirloc_min":.65}
    for o in raw:
        x=v11.enrich(d,o); st=stats.get(o["date"])
        if x is None or st is None or not st["med20"]:
            incomplete+=1; continue
        if not v11.passes(x,guard):
            guard_blocked+=1; continue
        if int(x["side"])!=1:
            short_blocked+=1; continue
        x=dict(x)
        x.update(width_med_ratio=st["width"]/st["med20"],
                 regime_ratio=st["regime_ratio"])
        out.append(x)
    skipped=dict(skipped)
    skipped.update(v17_history_incomplete=incomplete,
                   v17_chopguard_blocked=guard_blocked,
                   v17_short_blocked=short_blocked)
    return out,skipped,len(raw)

def adapt(d,o,cfg):
    """Return (adapted_order, status). No forward info beyond delayed decision."""
    if cfg["delay"] is None or not disturbed(o):
        return dict(o),"normal_0900"
    target=int(cfg["delay"])
    p=d[(d.date==o["date"]) & d.rth & d.minute.ge(540) & d.minute.lt(target)]
    if len(p)!=(target-540) or p.segment.nunique()!=1:
        return None,"missing_delay_context"
    last=p.iloc[-1]
    # Long thesis must still be intact relative to the original 08:59 reference.
    if float(last.close)<=float(o["reference"]):
        return None,"failed_hold"
    if cfg.get("vwap"):
        q=d[(d.date==o["date"]) & d.rth & d.minute.ge(510) & d.minute.lt(target)]
        if len(q)!=(target-510) or float(q.volume.sum())<=0:
            return None,"missing_vwap_context"
        vwap=float((q.volume*(q.high+q.low+q.close)/3).sum()/q.volume.sum())
        if float(last.close)<=vwap:
            return None,"failed_vwap"
    x=dict(o)
    # replay enters on the bar immediately after order[index].
    x["index"]=int(p.index[-1])
    x["delayed_decision_minute"]=target
    # Keep original reference/risk/stop geometry frozen.
    return x,"delayed_confirmed"

def evaluate(frame,year):
    from collections import Counter
    from scripts import valor_mes_session_v6 as base
    d=base.prepare(frame); frozen,skipped,raw_n=prepare_orders(d); rows=[]
    for name,cfg in MODES.items():
        sched=[]; states=Counter()
        disturbed_n=0
        for o in frozen:
            if disturbed(o): disturbed_n+=1
            x,state=adapt(d,o,cfg); states[state]+=1
            if x is not None:sched.append(x)
        trades,unresolved=base.replay(d,sched,"signal")
        for ticks in (2,4):
            r=base.summarize(trades,unresolved,year,ticks)
            r.update(candidate=name,year=year,raw_valid_decisions=raw_n,
                     frozen_long_decisions=len(frozen),disturbed_decisions=disturbed_n,
                     kept_decisions=len(sched),adapt_states=dict(states),
                     base_signal_skips=skipped,research_only=True,
                     production_changed=False,live_ready=False)
            rows.append(r)
    return dict(study=STUDY,year=year,
                frozen_chopguard="late15_confirm + directional_location>=0.65",
                disturbed_rule="opening_width/prior20_median>1.25 AND prior20_median/prior60_median>1.10",
                normal_entry_minute_ct=540,delayed_modes=MODES,exit_minute_ct=720,
                direction="long_only",original_stop_geometry=True,
                selection_cost_ticks_each_side=4,round_trip_fee_assumed=3.0,
                years_role="2023-2025 development/robustness; 2026 untouched",
                new_vendor_downloads=0,broker_calls=0,production_changed=False,
                live_ready=False),rows

def choose(dev):
    picks=[]
    for name in MODES:
        if name=="portable_base":continue
        rs=[r for y in YEARS for r in dev.get(y,[])
            if r["candidate"]==name and r["cost_ticks_each_side"]==4]
        if len(rs)!=3:continue
        if not all(r["trades"]>=40 and r["net_dollars"]>0 and
                   r["profit_factor"] is not None and r["profit_factor"]>=1.05 and
                   r["unresolved_fraction"]<=.04 for r in rs):
            continue
        worst=min(r["net_dollars"]/max(1.,r["closed_trade_max_drawdown"]) for r in rs)
        picks.append((worst,sum(r["net_dollars"] for r in rs),name))
    return sorted(picks,key=lambda z:(-z[0],-z[1],z[2]))[0][2] if picks else None

def run():
    import pandas as pd, psycopg2
    from psycopg2.extras import Json
    if hasattr(os,"nice"):os.nice(10)
    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=15);conn.autocommit=True
    cur=conn.cursor();cur.execute("SELECT pg_try_advisory_lock(%s)",(LOCK,))
    if not cur.fetchone()[0]:conn.close();return
    sh=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def state(status,**detail):
        cur.execute("""INSERT INTO valor_mes_chopguard_v17_state(study_id,status,detail)
          VALUES(%s,%s,%s) ON CONFLICT(study_id) DO UPDATE
          SET status=excluded.status,detail=excluded.detail,updated_at=now()""",
          (STUDY,status,Json(dict(detail,source_sha256=sh,research_only=True,
                                 production_changed=False,new_vendor_downloads=0))))
    def cached(y):
        cur.execute("SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",
                    (f"GLBX.MDP3:ohlcv-1m:MES.v.0:{y}",))
        row=cur.fetchone()
        if not row:raise ValueError("cache absent; vendor download prohibited")
        body=bytes(row[1]);dig=hashlib.sha256(body).hexdigest()
        if dig!=row[0] or dig!=HASHES[y]:raise ValueError("cache checksum mismatch")
        return pd.read_parquet(io.BytesIO(body))
    def store(y,m,rows):
        m.update(source_sha256=sh,cache_sha256=HASHES[y])
        summary=[{k:v for k,v in r.items() if k not in ("ledger","unresolved_ledger")} for r in rows]
        evidence=gzip.compress(json.dumps(rows,allow_nan=False).encode(),mtime=0)
        cur.execute("""INSERT INTO valor_mes_chopguard_v17_results
          (study_id,year,manifest,summary,evidence_gzip) VALUES(%s,%s,%s,%s,%s)
          ON CONFLICT(study_id,year) DO NOTHING""",
          (STUDY,y,Json(m),Json(summary),psycopg2.Binary(evidence)))
        return summary
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v17_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v17_results(
          study_id text,year int,manifest jsonb NOT NULL,summary jsonb NOT NULL,evidence_gzip bytea NOT NULL,
          created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,year));""")
        cur.execute("SELECT status FROM valor_mes_chopguard_v17_state WHERE study_id=%s",(STUDY,))
        if cur.fetchone()==("completed",):return
        dev={}
        for y in YEARS:
            state("evaluating",year=y)
            m,rows=evaluate(cached(y),y);dev[y]=store(y,m,rows)
        selected=choose(dev)
        state("completed",selected=selected,
              selection_gate={"positive_stress_net_each_year":True,
                              "profit_factor_min_each_year":1.05,
                              "trades_min_each_year":40,
                              "unresolved_fraction_max_each_year":.04},
              untouched_next_year=2026)
    except Exception as e:
        try:state("failed",error_type=type(e).__name__,message=str(e)[:500])
        except Exception:pass
        logging.getLogger(__name__).exception("MES CHOPGuard v17 failed")
    finally:
        try:cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally:conn.close()

def launch_if_enabled():
    flag=os.getenv("VALOR_MES_CHOPGUARD_V17_AUTORUN",
                   os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false"))
    if flag.lower() not in {"1","true","yes","on"}:return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_chopguard_v17"],
                     env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True

if __name__=="__main__":run()
