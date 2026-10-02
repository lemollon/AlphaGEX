"""MES CHOPGuard v18: causal loss-cluster circuit breaker.

Frozen base:
- corrected MES morning-continuation engine
- CHOPGuard late15 confirmation + directional location >= .65
- LONG ONLY
- 09:00 CT entry / 12:00 CT exit
- original stop geometry

Hypothesis:
Losses cluster because the same setup keeps firing after its local edge degrades.
V18 leaves the setup unchanged. It moves to SHADOW mode after N consecutive
4-tick/side stressed losses, continues simulating every valid signal, and resumes
only after M consecutive shadow wins. State transitions use only completed prior
trades, so the gate is causal.

2023-2025 are development/robustness years. 2026 remains untouched.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, logging, os, subprocess, sys

STUDY="valor-mes-chopguard-v18-20260924"
LOCK=658202609
YEARS=(2023,2024,2025)
HASHES={
  2023:"2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
  2024:"6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
  2025:"629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}
MODES={
 "portable_base":None,
 "pause2_resume1":(2,1),
 "pause2_resume2":(2,2),
 "pause3_resume1":(3,1),
 "pause3_resume2":(3,2),
}

def frozen_schedule(d):
    from scripts import valor_mes_chopguard_v17 as v17
    rows, skipped, raw_n = v17.prepare_orders(d)
    return rows, skipped, raw_n

def stressed_outcomes(d, schedule, year):
    from scripts import valor_mes_session_v6 as base
    trades, unresolved = base.replay(d, schedule, "signal")
    s = base.summarize(trades, unresolved, year, 4)
    outcomes = {x["date"]: float(x["net"]) for x in s["ledger"]}
    unresolved_dates = {x["date"] for x in s["unresolved_ledger"]}
    return outcomes, unresolved_dates

def apply_state_machine(schedule, outcomes, unresolved_dates, cfg):
    if cfg is None:
        return list(schedule), {
            "executed":len(schedule),"shadowed":0,"pause_events":0,
            "resume_events":0,"max_shadow_run":0,
        }
    loss_trigger, win_resume = cfg
    live=True; live_loss_streak=0; shadow_win_streak=0
    out=[]; shadowed=0; pause_events=0; resume_events=0; shadow_run=0; max_shadow=0
    for o in sorted(schedule,key=lambda x:x["date"]):
        day=o["date"]
        if live:
            out.append(o)
            shadow_run=0
            if day in unresolved_dates or day not in outcomes:
                continue
            if outcomes[day] < 0:
                live_loss_streak += 1
                if live_loss_streak >= loss_trigger:
                    live=False
                    shadow_win_streak=0
                    pause_events += 1
            elif outcomes[day] > 0:
                live_loss_streak=0
        else:
            shadowed += 1
            shadow_run += 1
            max_shadow=max(max_shadow,shadow_run)
            if day in unresolved_dates or day not in outcomes:
                continue
            if outcomes[day] > 0:
                shadow_win_streak += 1
                if shadow_win_streak >= win_resume:
                    live=True
                    live_loss_streak=0
                    shadow_win_streak=0
                    resume_events += 1
            else:
                shadow_win_streak=0
    return out, {
        "executed":len(out),"shadowed":shadowed,"pause_events":pause_events,
        "resume_events":resume_events,"max_shadow_run":max_shadow,
    }

def evaluate(frame,year):
    from scripts import valor_mes_session_v6 as base
    d=base.prepare(frame)
    frozen, skipped, raw_n=frozen_schedule(d)
    outcomes, unresolved_dates=stressed_outcomes(d,frozen,year)
    rows=[]
    for name,cfg in MODES.items():
        sched,state=apply_state_machine(frozen,outcomes,unresolved_dates,cfg)
        trades,unresolved=base.replay(d,sched,"signal")
        for ticks in (2,4):
            r=base.summarize(trades,unresolved,year,ticks)
            r.update(candidate=name,year=year,raw_valid_decisions=raw_n,
                     frozen_long_decisions=len(frozen),kept_decisions=len(sched),
                     circuit_state=state,base_signal_skips=skipped,
                     gate_outcome_cost_ticks_each_side=4,
                     research_only=True,production_changed=False,live_ready=False)
            rows.append(r)
    return dict(
        study=STUDY,year=year,
        frozen_chopguard="late15_confirm + directional_location>=0.65",
        direction="long_only",entry_minute_ct=540,exit_minute_ct=720,
        circuit_breaker="pause after N consecutive completed stressed losses; resume after M consecutive shadow wins",
        modes=MODES,selection_cost_ticks_each_side=4,round_trip_fee_assumed=3.0,
        years_role="2023-2025 development/robustness; 2026 untouched",
        new_vendor_downloads=0,broker_calls=0,production_changed=False,live_ready=False
    ),rows

def choose(dev):
    picks=[]
    for name in MODES:
        if name=="portable_base": continue
        rs=[r for y in YEARS for r in dev.get(y,[])
            if r["candidate"]==name and r["cost_ticks_each_side"]==4]
        if len(rs)!=3: continue
        if not all(r["trades"]>=35 and r["net_dollars"]>0 and
                   r["profit_factor"] is not None and r["profit_factor"]>=1.05 and
                   r["unresolved_fraction"]<=.04 for r in rs):
            continue
        worst=min(r["net_dollars"]/max(1.,r["closed_trade_max_drawdown"]) for r in rs)
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
        cur.execute("""INSERT INTO valor_mes_chopguard_v18_state(study_id,status,detail)
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
        cur.execute("""INSERT INTO valor_mes_chopguard_v18_results
          (study_id,year,manifest,summary,evidence_gzip) VALUES(%s,%s,%s,%s,%s)
          ON CONFLICT(study_id,year) DO NOTHING""",
          (STUDY,y,Json(m),Json(summary),psycopg2.Binary(evidence)))
        return summary
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v18_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_chopguard_v18_results(
          study_id text,year int,manifest jsonb NOT NULL,summary jsonb NOT NULL,evidence_gzip bytea NOT NULL,
          created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,year));""")
        cur.execute("SELECT status FROM valor_mes_chopguard_v18_state WHERE study_id=%s",(STUDY,))
        if cur.fetchone()==("completed",): return
        dev={}
        for y in YEARS:
            state("evaluating",year=y)
            m,rows=evaluate(cached(y),y); dev[y]=store(y,m,rows)
        selected=choose(dev)
        state("completed",selected=selected,
              selection_gate={"positive_stress_net_each_year":True,
                              "profit_factor_min_each_year":1.05,
                              "trades_min_each_year":35,
                              "unresolved_fraction_max_each_year":.04},
              untouched_next_year=2026)
    except Exception as e:
        try: state("failed",error_type=type(e).__name__,message=str(e)[:500])
        except Exception: pass
        logging.getLogger(__name__).exception("MES CHOPGuard v18 failed")
    finally:
        try: cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally: conn.close()

def launch_if_enabled():
    flag=os.getenv("VALOR_MES_CHOPGUARD_V18_AUTORUN",
                   os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false"))
    if flag.lower() not in {"1","true","yes","on"}: return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_chopguard_v18"],
                     env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True

if __name__=="__main__": run()
