"""MES v25: continuous rolling-edge router.

Builds directly on v22 event-engine ledgers and v23/v24 loss-cluster evidence.

Core idea:
- Every engine continues to run in SHADOW on every valid signal.
- A real trade is allowed only when that engine's PRIOR completed shadow
  expectancy is positive.
- State is continuous across 2023 -> 2024 -> 2025; no annual reset.
- Portfolio variants allow at most one taken MES trade per calendar day.

No future/current outcome is used to decide the current trade.
Research only. 2026 remains untouched.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, json, os, subprocess, sys
from collections import deque, defaultdict

STUDY="valor-mes-v25-rolling-edge-router-20260924"
LOCK=665202609
V22="valor-mes-v22-event-driven-20260924"
YEARS=(2023,2024,2025)
ENGINES=("or_breakout_retest","failed_or_breakout","vwap_reclaim","compression_breakout")
MODES=("roll5_pos","roll10_pos","roll5_10_pos")

def load_ledgers(cur):
    by_engine={e:[] for e in ENGINES}
    for y in YEARS:
        cur.execute("SELECT evidence_gzip FROM valor_mes_v22_results WHERE study_id=%s AND year=%s",(V22,y))
        row=cur.fetchone()
        if not row: raise ValueError(f"missing v22 evidence {y}")
        rows=json.loads(gzip.decompress(bytes(row[0])))
        base={r["candidate"]:r for r in rows if int(r["cost_ticks_each_side"])==4}
        for e in ENGINES:
            for t in base[e]["trade_ledger"]:
                x=dict(t); x["engine"]=e; x["year"]=y
                by_engine[e].append(x)
    for e in ENGINES:
        by_engine[e].sort(key=lambda x:x["entry"])
    return by_engine

def annotate(by_engine):
    """Attach scores computed strictly from PRIOR completed shadow outcomes."""
    out=[]
    for e,ledger in by_engine.items():
        h5=deque(maxlen=5); h10=deque(maxlen=10)
        for t in ledger:
            x=dict(t)
            x["prior5_n"]=len(h5); x["prior10_n"]=len(h10)
            x["edge5"]=sum(h5)/len(h5) if h5 else None
            x["edge10"]=sum(h10)/len(h10) if h10 else None
            out.append(x)
            pnl=float(t["net"])
            h5.append(pnl); h10.append(pnl)
    return sorted(out,key=lambda x:x["entry"])

def eligible(t,mode):
    if mode=="roll5_pos":
        return t["prior5_n"]>=5 and float(t["edge5"])>0
    if mode=="roll10_pos":
        return t["prior10_n"]>=10 and float(t["edge10"])>0
    if mode=="roll5_10_pos":
        return (t["prior5_n"]>=5 and t["prior10_n"]>=10 and
                float(t["edge5"])>0 and float(t["edge10"])>0)
    raise ValueError(mode)

def summary(trades,year,label):
    import numpy as np
    rows=[t for t in trades if int(t["year"])==year]
    p=np.array([float(t["net"]) for t in rows],float)
    wins=float(p[p>0].sum()) if len(p) else 0.
    losses=float(-p[p<0].sum()) if len(p) else 0.
    eq=np.r_[0.,p.cumsum()] if len(p) else np.array([0.])
    monthly={f"{year}-{m:02d}":0. for m in range(1,13)}
    for t in rows: monthly[t["date"][:7]]+=float(t["net"])
    return dict(candidate=label,year=year,trades=len(rows),
      net_dollars=round(float(p.sum()),6),
      avg_trade=round(float(p.mean()),6) if len(p) else None,
      win_rate=round(float((p>0).mean()*100),4) if len(p) else None,
      profit_factor=round(wins/losses,6) if losses else None,
      closed_trade_max_drawdown=round(float((np.maximum.accumulate(eq)-eq).max()),6),
      monthly={k:round(v,6) for k,v in monthly.items()},
      research_only=True,production_changed=False,live_ready=False)

def evaluate(all_events):
    results=[]
    for mode in MODES:
        # engine-specific gates
        for e in ENGINES:
            taken=[t for t in all_events if t["engine"]==e and eligible(t,mode)]
            for y in YEARS: results.append(summary(taken,y,f"{e}:{mode}"))

        # portfolio: causal first eligible signal of each day wins capital.
        chosen=[]; used=set()
        for t in all_events:
            day=t["date"]
            if day in used or not eligible(t,mode): continue
            chosen.append(t); used.add(day)
        for y in YEARS: results.append(summary(chosen,y,f"portfolio_first:{mode}"))

        # portfolio quality version: require positive 5 expectancy and select
        # only events whose 5-edge is at least as strong as 10-edge when both
        # histories exist. This is a fixed, causal confirmation rule, not a grid.
        chosen=[]; used=set()
        for t in all_events:
            day=t["date"]
            if day in used or not eligible(t,mode): continue
            if t["prior5_n"]>=5 and t["prior10_n"]>=10 and t["edge5"] is not None and t["edge10"] is not None:
                if float(t["edge5"]) < float(t["edge10"]): continue
            chosen.append(t); used.add(day)
        for y in YEARS: results.append(summary(chosen,y,f"portfolio_accel:{mode}"))
    return results

def run():
    import psycopg2
    from psycopg2.extras import Json
    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=15);conn.autocommit=True
    cur=conn.cursor();cur.execute("SELECT pg_try_advisory_lock(%s)",(LOCK,))
    if not cur.fetchone()[0]:conn.close();return
    sh=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_v25_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_v25_results(
          study_id text PRIMARY KEY,summary jsonb NOT NULL,created_at timestamptz DEFAULT now());""")
        cur.execute("""INSERT INTO valor_mes_v25_state(study_id,status,detail) VALUES(%s,'running',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='running',detail=excluded.detail,updated_at=now()""",
          (STUDY,Json(dict(source_sha256=sh,research_only=True,production_changed=False))))
        events=annotate(load_ledgers(cur))
        rows=evaluate(events)
        cur.execute("""INSERT INTO valor_mes_v25_results(study_id,summary) VALUES(%s,%s)
          ON CONFLICT(study_id) DO UPDATE SET summary=excluded.summary,created_at=now()""",
          (STUDY,Json(rows)))
        candidates=sorted(set(r["candidate"] for r in rows))
        viable=[]
        for c in candidates:
            rs=[r for r in rows if r["candidate"]==c]
            if len(rs)==3 and all(r["trades"]>=8 and r["net_dollars"]>0 and
               r["profit_factor"] is not None and r["profit_factor"]>=1.05 for r in rs):
                viable.append(dict(candidate=c,total_net=round(sum(r["net_dollars"] for r in rs),6),
                    worst_pf=min(r["profit_factor"] for r in rs),
                    worst_net=min(r["net_dollars"] for r in rs)))
        cur.execute("""UPDATE valor_mes_v25_state SET status='completed',detail=%s,updated_at=now()
          WHERE study_id=%s""",(Json(dict(source_sha256=sh,research_only=True,
            production_changed=False,continuous_state=True,viable=viable,
            years=list(YEARS),untouched_next_year=2026)),STUDY))
    except Exception as e:
        cur.execute("""INSERT INTO valor_mes_v25_state(study_id,status,detail) VALUES(%s,'failed',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='failed',detail=excluded.detail,updated_at=now()""",
          (STUDY,Json(dict(source_sha256=sh,error_type=type(e).__name__,message=str(e)[:500]))))
        raise
    finally:
        try:cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally:conn.close()

def launch_if_enabled():
    flag=os.getenv("VALOR_MES_V25_AUTORUN",os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false"))
    if flag.lower() not in {"1","true","yes","on"}:return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_v25_rolling_edge_router"],
                     env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True

if __name__=="__main__":run()
