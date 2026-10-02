"""MES v26: first-loss circuit breaker.

Direct follow-up to v23/v24:
Loss dollars are concentrated in consecutive streaks, so v24's two-loss trigger
may react one trade too late. V26 pauses an engine immediately after ONE
completed stressed loss and observes all subsequent signals in shadow.

Recovery variants:
- resume after 1 shadow win
- resume after 2 consecutive shadow wins
- resume after 3 consecutive shadow wins

Continuous state across 2023 -> 2024 -> 2025. Research only; 2026 untouched.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, json, os, subprocess, sys
import numpy as np

STUDY="valor-mes-v26-first-loss-breaker-20260924"
LOCK=666202609
V22="valor-mes-v22-event-driven-20260924"
YEARS=(2023,2024,2025)
ENGINES=("or_breakout_retest","failed_or_breakout","vwap_reclaim","compression_breakout")
MODES={"pause1_resume1":1,"pause1_resume2":2,"pause1_resume3":3}

def load(cur):
    by={e:[] for e in ENGINES}
    for y in YEARS:
        cur.execute("SELECT evidence_gzip FROM valor_mes_v22_results WHERE study_id=%s AND year=%s",(V22,y))
        rr=cur.fetchone()
        if not rr: raise ValueError(f"missing v22 {y}")
        rows=json.loads(gzip.decompress(bytes(rr[0])))
        base={r["candidate"]:r for r in rows if int(r["cost_ticks_each_side"])==4}
        for e in ENGINES:
            for t in base[e]["trade_ledger"]:
                x=dict(t); x["engine"]=e; x["year"]=y
                by[e].append(x)
    for e in ENGINES: by[e].sort(key=lambda x:x["entry"])
    return by

def gate(ledger, resume_wins):
    active=True; sw=0; taken=[]; shadow=[]
    for t in ledger:
        pnl=float(t["net"])
        if active:
            taken.append(t)
            if pnl<0:
                active=False; sw=0
        else:
            shadow.append(t)
            if pnl>0:
                sw+=1
                if sw>=resume_wins:
                    active=True; sw=0
            else:
                sw=0
    return taken,shadow

def summarize(rows,year,label):
    x=[t for t in rows if int(t["year"])==year]
    p=np.array([float(t["net"]) for t in x],float)
    wins=float(p[p>0].sum()) if len(p) else 0.
    losses=float(-p[p<0].sum()) if len(p) else 0.
    eq=np.r_[0.,p.cumsum()] if len(p) else np.array([0.])
    return dict(candidate=label,year=year,trades=len(x),
        net_dollars=round(float(p.sum()),6),
        avg_trade=round(float(p.mean()),6) if len(p) else None,
        win_rate=round(float((p>0).mean()*100),4) if len(p) else None,
        profit_factor=round(wins/losses,6) if losses else None,
        closed_trade_max_drawdown=round(float((np.maximum.accumulate(eq)-eq).max()),6),
        research_only=True,production_changed=False,live_ready=False)

def run():
    import psycopg2
    from psycopg2.extras import Json
    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=15); conn.autocommit=True
    cur=conn.cursor(); cur.execute("SELECT pg_try_advisory_lock(%s)",(LOCK,))
    if not cur.fetchone()[0]: conn.close(); return
    sh=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_v26_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_v26_results(
          study_id text PRIMARY KEY,summary jsonb NOT NULL,created_at timestamptz DEFAULT now());""")
        cur.execute("""INSERT INTO valor_mes_v26_state(study_id,status,detail) VALUES(%s,'running',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='running',detail=excluded.detail,updated_at=now()""",
          (STUDY,Json(dict(source_sha256=sh,research_only=True,production_changed=False))))
        by=load(cur); out=[]
        for e,ledger in by.items():
            for mode,n in MODES.items():
                taken,shadow=gate(ledger,n)
                for y in YEARS:
                    r=summarize(taken,y,f"{e}:{mode}")
                    r["shadow_trades"]=sum(1 for t in shadow if int(t["year"])==y)
                    out.append(r)
        # portfolio: union all independently-gated engine trades, max one/day.
        for mode,n in MODES.items():
            allowed=[]
            for e,ledger in by.items():
                taken,_=gate(ledger,n); allowed.extend(taken)
            allowed.sort(key=lambda x:x["entry"])
            chosen=[]; used=set()
            for t in allowed:
                if t["date"] in used: continue
                chosen.append(t); used.add(t["date"])
            for y in YEARS: out.append(summarize(chosen,y,f"portfolio_first:{mode}"))
        cur.execute("""INSERT INTO valor_mes_v26_results(study_id,summary) VALUES(%s,%s)
          ON CONFLICT(study_id) DO UPDATE SET summary=excluded.summary,created_at=now()""",(STUDY,Json(out)))
        viable=[]
        for c in sorted(set(r["candidate"] for r in out)):
            rs=[r for r in out if r["candidate"]==c]
            if len(rs)==3 and all(r["trades"]>=8 and r["net_dollars"]>0 and
                r["profit_factor"] is not None and r["profit_factor"]>=1.05 for r in rs):
                viable.append(dict(candidate=c,total_net=round(sum(r["net_dollars"] for r in rs),6),
                    worst_pf=min(r["profit_factor"] for r in rs),
                    worst_net=min(r["net_dollars"] for r in rs)))
        cur.execute("""UPDATE valor_mes_v26_state SET status='completed',detail=%s,updated_at=now()
          WHERE study_id=%s""",(Json(dict(source_sha256=sh,research_only=True,
             production_changed=False,continuous_state=True,viable=viable,
             years=list(YEARS),untouched_next_year=2026)),STUDY))
    except Exception as e:
        cur.execute("""INSERT INTO valor_mes_v26_state(study_id,status,detail) VALUES(%s,'failed',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='failed',detail=excluded.detail,updated_at=now()""",
          (STUDY,Json(dict(source_sha256=sh,error_type=type(e).__name__,message=str(e)[:500]))))
        raise
    finally:
        try: cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally: conn.close()

def launch_if_enabled():
    flag=os.getenv("VALOR_MES_V26_AUTORUN",os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false"))
    if flag.lower() not in {"1","true","yes","on"}: return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_v26_first_loss_breaker"],
                     env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True

if __name__=="__main__": run()
