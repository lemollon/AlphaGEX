"""MES CHOPGuard v20: causal profit-cluster detector.

Goal:
Find the market-state features that distinguish the profitable MES morning
clusters from the dead/loss periods without hard-coding calendar months.

Frozen base setup:
- morning_continuation
- late15 confirmation
- directional location >= .65
- long only
- 09:00 CT decision / 12:00 CT exit
- original stop geometry

New causal features:
- opening directional quality (dirloc, late15 strength, VWAP separation)
- opening shock / background volatility regime
- prior 5 / prior 10 SHADOW trade stressed expectancy

The shadow ledger evaluates every frozen base signal at 4 adverse ticks/side
plus $3 round-trip fee. Today's eligibility can use only completed PRIOR signal
outcomes. 2026 remains untouched.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, logging, os, subprocess, sys
from collections import deque

STUDY="valor-mes-chopguard-v20-20260924"
LOCK=660202609
YEARS=(2023,2024,2025)
HASHES={
  2023:"2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
  2024:"6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
  2025:"629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}

RULES={
 "portable_base":{},
 "quality_dir75_late10":{"dirloc":.75,"late_strength":.10},
 "quality_vwap15_late10":{"vwap":.15,"late_strength":.10},
 "edge5_positive":{"edge5":0.0},
 "edge10_positive":{"edge10":0.0},
 "edge5_10_positive":{"edge5":0.0,"edge10":0.0},
 "quality_dir75_edge5":{"dirloc":.75,"edge5":0.0},
 "quality_late10_edge5":{"late_strength":.10,"edge5":0.0},
 "quality_vwap10_edge5":{"vwap":.10,"edge5":0.0},
 "quality_dir75_late10_edge5":{"dirloc":.75,"late_strength":.10,"edge5":0.0},
 "quality_dir75_late10_edge10":{"dirloc":.75,"late_strength":.10,"edge10":0.0},
 "quality_dir75_late10_edge5_10":{"dirloc":.75,"late_strength":.10,"edge5":0.0,"edge10":0.0},
}

def frozen_orders(d):
    from scripts import valor_mes_chopguard_v17 as v17
    rows, skipped, raw_n=v17.prepare_orders(d)
    out=[]
    for o in rows:
        x=dict(o)
        width=float(x["opening_width"])
        x["late15_strength"]=float(x["late15_move"])/width if width>0 else 0.0
        out.append(x)
    return out,skipped,raw_n

def shadow_features(d, orders, year):
    """Attach prior completed shadow expectancy only; no same-day/future outcome."""
    from scripts import valor_mes_session_v6 as base
    trades, unresolved=base.replay(d,orders,"signal")
    s=base.summarize(trades,unresolved,year,4)
    outcome={x["date"]:float(x["net"]) for x in s["ledger"]}
    unresolved_dates={x["date"] for x in s["unresolved_ledger"]}
    h5=deque(maxlen=5); h10=deque(maxlen=10)
    out=[]
    for o in sorted(orders,key=lambda z:z["date"]):
        x=dict(o)
        x["prior5_n"]=len(h5)
        x["prior10_n"]=len(h10)
        x["prior5_expectancy"]=sum(h5)/len(h5) if h5 else None
        x["prior10_expectancy"]=sum(h10)/len(h10) if h10 else None
        out.append(x)
        day=o["date"]
        if day in outcome and day not in unresolved_dates:
            p=float(outcome[day]); h5.append(p); h10.append(p)
    return out

def passes(o,cfg):
    if cfg.get("dirloc") is not None and float(o["directional_location"])<cfg["dirloc"]:
        return False
    if cfg.get("late_strength") is not None and float(o["late15_strength"])<cfg["late_strength"]:
        return False
    if cfg.get("vwap") is not None and float(o["vwap_separation_ratio"])<cfg["vwap"]:
        return False
    if cfg.get("edge5") is not None:
        if int(o["prior5_n"])<5 or float(o["prior5_expectancy"])<=cfg["edge5"]: return False
    if cfg.get("edge10") is not None:
        if int(o["prior10_n"])<10 or float(o["prior10_expectancy"])<=cfg["edge10"]: return False
    return True

def feature_diagnostics(schedule, outcomes):
    """Compact winner/loser feature summaries for interpretation, not selection."""
    import numpy as np
    rows=[]
    for o in schedule:
        p=outcomes.get(o["date"])
        if p is None: continue
        rows.append((p,o))
    def stats(items):
        if not items:return {}
        def m(k):
            a=[float(o[k]) for _,o in items if o.get(k) is not None]
            return round(float(np.mean(a)),6) if a else None
        return dict(n=len(items),avg_net=round(float(np.mean([p for p,_ in items])),6),
                    dirloc=m("directional_location"),late_strength=m("late15_strength"),
                    vwap_sep=m("vwap_separation_ratio"),width_med=m("width_med_ratio"),
                    regime_ratio=m("regime_ratio"))
    return {"winners":stats([(p,o) for p,o in rows if p>0]),
            "losers":stats([(p,o) for p,o in rows if p<0])}

def evaluate(frame,year):
    from scripts import valor_mes_session_v6 as base
    d=base.prepare(frame)
    frozen,skipped,raw_n=frozen_orders(d)
    enriched=shadow_features(d,frozen,year)
    all_trades,all_un=base.replay(d,frozen,"signal")
    all_sum=base.summarize(all_trades,all_un,year,4)
    outcomes={x["date"]:float(x["net"]) for x in all_sum["ledger"]}
    diag=feature_diagnostics(enriched,outcomes)
    rows=[]
    for name,cfg in RULES.items():
        sched=[o for o in enriched if passes(o,cfg)]
        trades,unresolved=base.replay(d,sched,"signal")
        for ticks in (2,4):
            r=base.summarize(trades,unresolved,year,ticks)
            r.update(candidate=name,year=year,raw_valid_decisions=raw_n,
                     frozen_long_decisions=len(frozen),kept_decisions=len(sched),
                     rejected_decisions=len(frozen)-len(sched),
                     feature_diagnostics=diag,base_signal_skips=skipped,
                     research_only=True,production_changed=False,live_ready=False)
            rows.append(r)
    return dict(study=STUDY,year=year,
                architecture="profit-cluster selector on frozen morning CHOPGuard",
                rules=RULES,
                shadow_cost_ticks_each_side=4,
                selection_cost_ticks_each_side=4,
                round_trip_fee_assumed=3.0,
                minimum_promotion_bar={
                  "net_dollars_each_year":750,
                  "profit_factor_each_year":1.20,
                  "avg_trade_each_year":12,
                  "trades_each_year":25,
                  "unresolved_fraction_max":.04
                },
                years_role="2023-2025 development/robustness; 2026 untouched",
                new_vendor_downloads=0,broker_calls=0,
                production_changed=False,live_ready=False),rows

def choose(dev):
    picks=[]
    for name in RULES:
        if name=="portable_base": continue
        rs=[r for y in YEARS for r in dev.get(y,[])
            if r["candidate"]==name and r["cost_ticks_each_side"]==4]
        if len(rs)!=3: continue
        if not all(r["trades"]>=25 and r["net_dollars"]>=750 and
                   r["profit_factor"] is not None and r["profit_factor"]>=1.20 and
                   r["avg_trade"] is not None and r["avg_trade"]>=12 and
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
        cur.execute("""INSERT INTO valor_mes_chopguard_v20_state(study_id,status,detail)
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
        cur.execute("""INSERT INTO valor_mes_chopguard_v20_results
          (study_id,year,manifest,summary,evidence_gzip) VALUES(%s,%s,%s,%s,%s)
          ON CONFLICT(study_id,year) DO NOTHING""",
          (STUDY,y,Json(m),Json(summary),psycopg2.Binary(evidence)))
        return summary
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v20_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v20_results(
          study_id text,year int,manifest jsonb NOT NULL,summary jsonb NOT NULL,evidence_gzip bytea NOT NULL,
          created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,year));""")
        cur.execute("SELECT status FROM valor_mes_chopguard_v20_state WHERE study_id=%s",(STUDY,))
        if cur.fetchone()==("completed",):return
        dev={}
        for y in YEARS:
            state("evaluating",year=y)
            m,rows=evaluate(cached(y),y);dev[y]=store(y,m,rows)
        selected=choose(dev)
        state("completed",selected=selected,
              promotion_bar={"net_each_year_min":750,"pf_each_year_min":1.20,
                             "avg_trade_each_year_min":12,"trades_each_year_min":25,
                             "unresolved_fraction_max":.04},
              untouched_next_year=2026)
    except Exception as e:
        try:state("failed",error_type=type(e).__name__,message=str(e)[:500])
        except Exception:pass
        logging.getLogger(__name__).exception("MES CHOPGuard v20 failed")
    finally:
        try:cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally:conn.close()

def launch_if_enabled():
    flag=os.getenv("VALOR_MES_CHOPGUARD_V20_AUTORUN",
                   os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false"))
    if flag.lower() not in {"1","true","yes","on"}:return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_chopguard_v20"],
                     env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True

if __name__=="__main__":run()
