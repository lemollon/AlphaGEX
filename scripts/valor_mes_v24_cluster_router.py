"""MES v24: causal loss-cluster circuit breakers for v22 event engines.

Uses completed v22 stressed 4-tick/side ledgers as shadow truth.
Each engine runs its own causal state machine:
- ACTIVE: take trades
- after N consecutive completed losses -> SHADOW
- SHADOW: do not take trades, but continue observing the engine's hypothetical outcome
- after M consecutive shadow wins -> ACTIVE

No future outcome is used to decide the current trade.
Research-only. 2026 untouched.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, json, os, subprocess, sys

STUDY="valor-mes-v24-cluster-router-20260924"
LOCK=664202609
V22="valor-mes-v22-event-driven-20260924"
YEARS=(2023,2024,2025)
ENGINES=("or_breakout_retest","failed_or_breakout","vwap_reclaim","compression_breakout")
MODES={
 "pause2_resume1":(2,1),
 "pause2_resume2":(2,2),
 "pause3_resume1":(3,1),
 "pause3_resume2":(3,2),
}

def apply(ledger, lose_n, win_n):
    active=True; loss_streak=0; shadow_wins=0
    taken=[]; shadow=[]; transitions=[]
    for t in sorted(ledger,key=lambda x:x["entry"]):
        net=float(t["net"])
        if active:
            taken.append(t)
            if net<0:
                loss_streak+=1
                if loss_streak>=lose_n:
                    active=False; shadow_wins=0
                    transitions.append(dict(date=t["date"],to="shadow",reason=f"{lose_n}_losses"))
            else:
                loss_streak=0
        else:
            shadow.append(t)
            if net>0:
                shadow_wins+=1
                if shadow_wins>=win_n:
                    active=True; loss_streak=0
                    transitions.append(dict(date=t["date"],to="active",reason=f"{win_n}_shadow_wins"))
            else:
                shadow_wins=0
    return taken,shadow,transitions

def summarize(taken,shadow,transitions,year,engine,mode):
    import numpy as np
    p=np.array([float(t["net"]) for t in taken],float)
    wins=float(p[p>0].sum()) if len(p) else 0.0
    losses=float(-p[p<0].sum()) if len(p) else 0.0
    eq=np.r_[0.,p.cumsum()] if len(p) else np.array([0.])
    monthly={f"{year}-{m:02d}":0.0 for m in range(1,13)}
    for t in taken: monthly[t["date"][:7]]+=float(t["net"])
    shadow_p=np.array([float(t["net"]) for t in shadow],float)
    return dict(
      candidate=f"{engine}:{mode}",engine=engine,mode=mode,year=year,
      trades=len(taken),shadow_trades=len(shadow),
      net_dollars=round(float(p.sum()),6),
      avg_trade=round(float(p.mean()),6) if len(p) else None,
      win_rate=round(float((p>0).mean()*100),4) if len(p) else None,
      profit_factor=round(wins/losses,6) if losses else None,
      closed_trade_max_drawdown=round(float((np.maximum.accumulate(eq)-eq).max()),6),
      shadow_net=round(float(shadow_p.sum()),6),
      transitions=len(transitions),monthly={k:round(v,6) for k,v in monthly.items()},
      research_only=True,production_changed=False,live_ready=False)

def run():
    import psycopg2
    from psycopg2.extras import Json
    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=15);conn.autocommit=True
    cur=conn.cursor();cur.execute("SELECT pg_try_advisory_lock(%s)",(LOCK,))
    if not cur.fetchone()[0]:conn.close();return
    sh=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_v24_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_v24_results(
          study_id text,year int,summary jsonb NOT NULL,created_at timestamptz DEFAULT now(),
          PRIMARY KEY(study_id,year));""")
        cur.execute("""INSERT INTO valor_mes_v24_state(study_id,status,detail) VALUES(%s,'running',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='running',detail=excluded.detail,updated_at=now()""",
          (STUDY,Json(dict(source_sha256=sh,research_only=True,production_changed=False))))
        allrows={}
        for y in YEARS:
            cur.execute("SELECT evidence_gzip FROM valor_mes_v22_results WHERE study_id=%s AND year=%s",(V22,y))
            rr=cur.fetchone()
            if not rr:raise ValueError(f"missing v22 evidence {y}")
            rows=json.loads(gzip.decompress(bytes(rr[0])))
            base={r["candidate"]:r for r in rows if int(r["cost_ticks_each_side"])==4}
            out=[]
            for eng in ENGINES:
                ledger=base[eng]["trade_ledger"]
                for mode,(ln,wn) in MODES.items():
                    taken,shadow,trans=apply(ledger,ln,wn)
                    out.append(summarize(taken,shadow,trans,y,eng,mode))
            allrows[y]=out
            cur.execute("""INSERT INTO valor_mes_v24_results(study_id,year,summary)
              VALUES(%s,%s,%s) ON CONFLICT(study_id,year)
              DO UPDATE SET summary=excluded.summary,created_at=now()""",(STUDY,y,Json(out)))
        viable=[]
        for eng in ENGINES:
            for mode in MODES:
                rs=[r for y in YEARS for r in allrows[y] if r["engine"]==eng and r["mode"]==mode]
                if all(r["net_dollars"]>0 and r["profit_factor"] is not None and r["profit_factor"]>=1.05 and r["trades"]>=8 for r in rs):
                    viable.append(dict(engine=eng,mode=mode,total_net=sum(r["net_dollars"] for r in rs),
                                       worst_pf=min(r["profit_factor"] for r in rs)))
        cur.execute("""UPDATE valor_mes_v24_state SET status='completed',detail=%s,updated_at=now()
          WHERE study_id=%s""",(Json(dict(source_sha256=sh,research_only=True,production_changed=False,
            viable=viable,years=list(YEARS),untouched_next_year=2026)),STUDY))
    finally:
        try:cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally:conn.close()

def launch_if_enabled():
    flag=os.getenv("VALOR_MES_V24_AUTORUN",os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false"))
    if flag.lower() not in {"1","true","yes","on"}:return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_v24_cluster_router"],
                     env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True

if __name__=="__main__":run()
