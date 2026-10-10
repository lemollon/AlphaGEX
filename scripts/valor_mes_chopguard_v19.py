"""MES CHOPGuard v19: multi-engine session portfolio research.

Purpose:
- preserve the profitable CHOPGuard morning continuation subset
- test whether historically poor afternoon/closing continuation signals contain
  a robust contrarian (fade) edge
- combine only non-overlapping session engines
- optimize portfolio economics, not one setup

All tests use cached 2023-2025 MES minute bars. 2026 remains untouched.
Research only: no broker calls, vendor downloads, sizing changes, or production changes.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, logging, os, subprocess, sys

STUDY="valor-mes-chopguard-v19-20260924"
LOCK=659202609
YEARS=(2023,2024,2025)
HASHES={
  2023:"2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
  2024:"6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
  2025:"629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}

PORTFOLIOS={
 "morning_chopguard":("morning_chopguard",),
 "afternoon_fade":("afternoon_fade",),
 "closing_fade":("closing_fade",),
 "morning_plus_afternoon_fade":("morning_chopguard","afternoon_fade"),
 "morning_plus_closing_fade":("morning_chopguard","closing_fade"),
}

def engine_schedules(d):
    from scripts import valor_mes_session_v6 as base
    from scripts import valor_mes_chopguard_v17 as v17

    morning, morning_skips, raw_n = v17.prepare_orders(d)

    aft_raw, aft_skips = base.orders(d,"afternoon_continuation")
    afternoon=[]
    for o in aft_raw:
        x=dict(o)
        x["side"]=-int(x["side"])
        x["engine"]="afternoon_fade"
        afternoon.append(x)

    close_raw, close_skips = base.orders(d,"closing_continuation")
    closing=[]
    for o in close_raw:
        x=dict(o)
        x["side"]=-int(x["side"])
        x["engine"]="closing_fade"
        closing.append(x)

    m=[]
    for o in morning:
        x=dict(o); x["engine"]="morning_chopguard"; m.append(x)

    return {
      "morning_chopguard":m,
      "afternoon_fade":afternoon,
      "closing_fade":closing,
    },{
      "morning_chopguard":dict(morning_skips,raw_valid_decisions=raw_n),
      "afternoon_fade":aft_skips,
      "closing_fade":close_skips,
    }

def replay_portfolio(d, schedules, engines):
    from scripts import valor_mes_session_v6 as base
    trades=[]; unresolved=[]; counts={}
    for name in engines:
        t,u=base.replay(d,schedules[name],"signal")
        trades.extend(t); unresolved.extend(u)
        counts[name]={"scheduled":len(schedules[name]),"resolved":len(t),"unresolved":len(u)}
    trades.sort(key=lambda x:x["entry"])
    unresolved.sort(key=lambda x:x.get("signal_time",""))
    return trades,unresolved,counts

def evaluate(frame,year):
    from scripts import valor_mes_session_v6 as base
    d=base.prepare(frame)
    schedules, skips=engine_schedules(d)
    rows=[]
    for name,engines in PORTFOLIOS.items():
        trades,unresolved,counts=replay_portfolio(d,schedules,engines)
        for ticks in (2,4):
            r=base.summarize(trades,unresolved,year,ticks)
            r.update(candidate=name,engines=list(engines),engine_counts=counts,
                     engine_skips={k:skips[k] for k in engines},
                     year=year,research_only=True,production_changed=False,
                     live_ready=False)
            rows.append(r)
    return dict(
        study=STUDY,year=year,
        architecture="CHOPGuard morning continuation + inverse afternoon/closing continuation fades",
        portfolios={k:list(v) for k,v in PORTFOLIOS.items()},
        selection_cost_ticks_each_side=4,round_trip_fee_assumed=3.0,
        years_role="2023-2025 development/robustness; 2026 untouched",
        one_position_per_engine_per_day=True,
        overlapping_portfolios_prohibited=True,
        new_vendor_downloads=0,broker_calls=0,production_changed=False,live_ready=False
    ),rows

def choose(dev):
    picks=[]
    for name in PORTFOLIOS:
        rs=[r for y in YEARS for r in dev.get(y,[])
            if r["candidate"]==name and r["cost_ticks_each_side"]==4]
        if len(rs)!=3: continue
        if not all(r["trades"]>=40 and r["net_dollars"]>0 and
                   r["profit_factor"] is not None and r["profit_factor"]>=1.10 and
                   r["avg_trade"] is not None and r["avg_trade"]>=5.0 and
                   r["unresolved_fraction"]<=.04 for r in rs):
            continue
        worst=min(r["net_dollars"]/max(1.,r["closed_trade_max_drawdown"]) for r in rs)
        annual=sum(r["net_dollars"] for r in rs)
        picks.append((worst,annual,name))
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
        cur.execute("""INSERT INTO valor_mes_chopguard_v19_state(study_id,status,detail)
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
        cur.execute("""INSERT INTO valor_mes_chopguard_v19_results
          (study_id,year,manifest,summary,evidence_gzip) VALUES(%s,%s,%s,%s,%s)
          ON CONFLICT(study_id,year) DO NOTHING""",
          (STUDY,y,Json(m),Json(summary),psycopg2.Binary(evidence)))
        return summary
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v19_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v19_results(
          study_id text,year int,manifest jsonb NOT NULL,summary jsonb NOT NULL,evidence_gzip bytea NOT NULL,
          created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,year));""")
        cur.execute("SELECT status FROM valor_mes_chopguard_v19_state WHERE study_id=%s",(STUDY,))
        if cur.fetchone()==("completed",): return
        dev={}
        for y in YEARS:
            state("evaluating",year=y)
            m,rows=evaluate(cached(y),y); dev[y]=store(y,m,rows)
        selected=choose(dev)
        state("completed",selected=selected,
              selection_gate={"positive_stress_net_each_year":True,
                              "profit_factor_min_each_year":1.10,
                              "avg_trade_min_each_year":5.0,
                              "trades_min_each_year":40,
                              "unresolved_fraction_max_each_year":.04},
              untouched_next_year=2026)
    except Exception as e:
        try: state("failed",error_type=type(e).__name__,message=str(e)[:500])
        except Exception: pass
        logging.getLogger(__name__).exception("MES CHOPGuard v19 failed")
    finally:
        try: cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally: conn.close()

def launch_if_enabled():
    flag=os.getenv("VALOR_MES_CHOPGUARD_V19_AUTORUN",
                   os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false"))
    if flag.lower() not in {"1","true","yes","on"}: return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_chopguard_v19"],
                     env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True

if __name__=="__main__": run()
