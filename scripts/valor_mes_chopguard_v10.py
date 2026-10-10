"""MES CHOPGuard v10: direction-aware, cache-only research.

v9 showed generic opening-efficiency filtering was not portable: ER>=.20 nearly
rescued 2024 but harmed 2023. v10 therefore tests a small frozen set of
SHORT-only quality gates while leaving qualifying long setups unchanged.

Selection is based only on 2023+2024 at 4 adverse ticks/side + $3 RT fee.
2025 is checked only if a candidate passes both development years.
No broker calls, vendor downloads, sizing changes, or production rule changes.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, logging, os, subprocess, sys

STUDY="valor-mes-chopguard-v10-20260924"
LOCK=650202609
HASHES={
  2023:"2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
  2024:"6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
  2025:"629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}
# Frozen hypotheses, not an optimizer grid.
GUARDS={
 "baseline":{"short_min_er":None,"short_max_close_loc":None,"short_min_disp":None},
 "short_er20":{"short_min_er":.20,"short_max_close_loc":None,"short_min_disp":None},
 "short_close35":{"short_min_er":None,"short_max_close_loc":.35,"short_min_disp":None},
 "short_disp50":{"short_min_er":None,"short_max_close_loc":None,"short_min_disp":.50},
 "short_er20_close35":{"short_min_er":.20,"short_max_close_loc":.35,"short_min_disp":None},
 "short_er20_disp50":{"short_min_er":.20,"short_max_close_loc":None,"short_min_disp":.50},
}

def enrich(d, order):
    import numpy as np
    p=d[(d.date==order["date"]) & d.rth & d.minute.ge(510) & d.minute.lt(540)]
    if len(p)!=30 or p.index[-1]!=order["index"] or p.segment.nunique()!=1:
        return None
    path=np.r_[float(p.open.iloc[0]),p.close.to_numpy(float)]
    travel=float(np.abs(np.diff(path)).sum())
    er=abs(float(path[-1]-path[0]))/travel if travel else 0.
    hi,lo=float(p.high.max()),float(p.low.min())
    width=hi-lo
    if width<=0:return None
    close=float(p.close.iloc[-1]); opening=float(p.open.iloc[0])
    return dict(order,opening_efficiency=er,
                opening_close_location=(close-lo)/width,
                opening_displacement_ratio=abs(close-opening)/width)

def schedule(d):
    from scripts import valor_mes_session_v6 as base
    raw,skipped=base.orders(d,"morning_continuation")
    out=[]; bad=0
    for o in raw:
        x=enrich(d,o)
        if x is None: bad+=1
        else: out.append(x)
    skipped=dict(skipped)
    if bad: skipped["v10_feature_context_incomplete"]=bad
    return out,skipped

def passes(o,cfg):
    if o["side"]!= -1:return True
    if cfg["short_min_er"] is not None and o["opening_efficiency"]<cfg["short_min_er"]:return False
    if cfg["short_max_close_loc"] is not None and o["opening_close_location"]>cfg["short_max_close_loc"]:return False
    if cfg["short_min_disp"] is not None and o["opening_displacement_ratio"]<cfg["short_min_disp"]:return False
    return True

def evaluate(frame,year,only=None):
    from scripts import valor_mes_session_v6 as base
    d=base.prepare(frame); raw,skipped=schedule(d); rows=[]
    for name,cfg in GUARDS.items():
        if only is not None and name!=only:continue
        kept=[o for o in raw if passes(o,cfg)]
        blocked=[o for o in raw if not passes(o,cfg)]
        bt,un=base.replay(d,kept,"signal")
        for ticks in (2,4):
            r=base.summarize(bt,un,year,ticks)
            r.update(guard=name,year=year,raw_valid_decisions=len(raw),
                     kept_decisions=len(kept),blocked_short_setups=len(blocked),
                     blocked_short_er=sum(o["side"]==-1 and cfg["short_min_er"] is not None and o["opening_efficiency"]<cfg["short_min_er"] for o in raw),
                     blocked_short_close=sum(o["side"]==-1 and cfg["short_max_close_loc"] is not None and o["opening_close_location"]>cfg["short_max_close_loc"] for o in raw),
                     blocked_short_disp=sum(o["side"]==-1 and cfg["short_min_disp"] is not None and o["opening_displacement_ratio"]<cfg["short_min_disp"] for o in raw),
                     base_signal_skips=skipped,research_only=True,
                     production_changed=False,live_ready=False)
            rows.append(r)
    manifest=dict(study=STUDY,year=year,base_engine="valor_mes_session_v6.morning_continuation",
                  guards=GUARDS,selection_cost_ticks_each_side=4,round_trip_fee_assumed=3.,
                  new_vendor_downloads=0,broker_calls=0,production_changed=False,live_ready=False,
                  validation="2023/2024 development; 2025 already seen chronological check only")
    return manifest,rows

def select(dev):
    picks=[]
    for name in GUARDS:
        if name=="baseline":continue
        rs=[r for y in (2023,2024) for r in dev.get(y,[])
            if r["guard"]==name and r["cost_ticks_each_side"]==4]
        if len(rs)!=2:continue
        if not all(r["trades"]>=80 and r["net_dollars"]>0 and
                   r["profit_factor"] is not None and r["profit_factor"]>=1.05 and
                   r["unresolved_fraction"]<=.03 for r in rs):continue
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
        cur.execute("""INSERT INTO valor_mes_chopguard_v10_state(study_id,status,detail) VALUES(%s,%s,%s)
          ON CONFLICT(study_id) DO UPDATE SET status=excluded.status,detail=excluded.detail,updated_at=now()""",
          (STUDY,status,Json(dict(detail,source_sha256=sh,research_only=True,production_changed=False,new_vendor_downloads=0))))
    def cached(y):
        cur.execute("SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",(f"GLBX.MDP3:ohlcv-1m:MES.v.0:{y}",))
        row=cur.fetchone()
        if not row:raise ValueError("cache absent; vendor download prohibited")
        body=bytes(row[1]);dig=hashlib.sha256(body).hexdigest()
        if dig!=row[0] or dig!=HASHES[y]:raise ValueError("cache checksum mismatch")
        return pd.read_parquet(io.BytesIO(body))
    def store(y,m,rows):
        m.update(source_sha256=sh,cache_sha256=HASHES[y])
        summary=[{k:v for k,v in r.items() if k not in ("ledger","unresolved_ledger")} for r in rows]
        evidence=gzip.compress(json.dumps(rows,allow_nan=False).encode(),mtime=0)
        cur.execute("""INSERT INTO valor_mes_chopguard_v10_results(study_id,year,manifest,summary,evidence_gzip)
          VALUES(%s,%s,%s,%s,%s) ON CONFLICT(study_id,year) DO NOTHING""",
          (STUDY,y,Json(m),Json(summary),psycopg2.Binary(evidence)))
        return summary
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v10_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v10_results(
          study_id text,year int,manifest jsonb NOT NULL,summary jsonb NOT NULL,evidence_gzip bytea NOT NULL,
          created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,year));""")
        dev={}
        for y in (2023,2024):
            state("evaluating_development",year=y)
            m,rs=evaluate(cached(y),y);m["phase"]="development";dev[y]=store(y,m,rs)
        chosen=select(dev)
        if chosen:
            state("evaluating_chronological_check",year=2025,selected=chosen)
            m,rs=evaluate(cached(2025),2025,chosen)
            m.update(phase="chronological_check",selection_frozen=chosen,blind_holdout=False)
            store(2025,m,rs)
        else:
            store(2025,dict(phase="not_tested",reason="no_directional_guard_passed_2023_2024_stress_gate",
                            source_sha256=sh,cache_sha256=HASHES[2025],production_changed=False,live_ready=False),[])
        state("completed",selected=chosen,test_2025="chronological_check" if chosen else "not_tested",
              selection_gate={"positive_stress_net_each_year":True,"profit_factor_min_each_year":1.05,
                              "trades_min_each_year":80,"unresolved_fraction_max_each_year":.03})
    except Exception as e:
        try:state("failed",error_type=type(e).__name__,message=str(e)[:400])
        except Exception:pass
        logging.getLogger(__name__).exception("MES CHOPGuard v10 failed")
    finally:
        try:cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally:conn.close()

def launch_if_enabled():
    if os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false").lower() not in {"1","true","yes","on"}:return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_chopguard_v10"],env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True

if __name__=="__main__":run()
