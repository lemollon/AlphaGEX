"""MES v28 multi-entry walk-forward selector.

Builds on v27 feature construction but removes the one-trade/day ceiling.

Goals:
- target roughly 1+ quality MES trade/session on average
- allow up to 3 independent entries/day
- require 45-minute cooldown between entries
- score all event families with a walk-forward model trained only on prior dates
- reject low-score events instead of forcing a trade
- minimum acceptance activity: 180 trades/year
- 2026 untouched
"""
from __future__ import annotations
from pathlib import Path
import hashlib, json, os, subprocess, sys
from collections import defaultdict
from datetime import datetime

STUDY="valor-mes-v28-multientry-selector-20260925"
LOCK=668202609
YEARS=(2023,2024,2025)
THRESHOLDS=(0.50,0.52,0.54)
MIN_TRAIN=120
TRAILING_TRAIN=700
MAX_TRADES_DAY=3
COOLDOWN_MIN=45

def _minutes_between(a,b):
    try:
        x=datetime.fromisoformat(a.replace("Z","+00:00"))
        y=datetime.fromisoformat(b.replace("Z","+00:00"))
        return (y-x).total_seconds()/60.0
    except Exception:
        return 9999.0

def walkforward_multi(events,threshold):
    import numpy as np
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from scripts.valor_mes_v27_walkforward_selector import matrix

    train=[]
    taken=[]
    by_day=defaultdict(list)
    for e in events:
        by_day[e["date"]].append(e)

    for day in sorted(by_day):
        todays=by_day[day]
        if len(train)>=MIN_TRAIN and len({z["label"] for z in train[-TRAILING_TRAIN:]})==2:
            tr=train[-TRAILING_TRAIN:]
            X=matrix(tr)
            y=np.asarray([z["label"] for z in tr],int)
            model=make_pipeline(
                StandardScaler(),
                LogisticRegression(C=.5,max_iter=500,class_weight="balanced",random_state=11)
            )
            model.fit(X,y)
            probs=model.predict_proba(matrix(todays))[:,1]

            scored=[]
            for p,z in zip(probs,todays):
                if float(p) >= threshold:
                    q=dict(z)
                    q["prob"]=float(p)
                    scored.append(q)

            # Chronological execution: choose highest-score eligible signal at each
            # opportunity, max 3/day, with a 45m cooldown after each accepted entry.
            scored.sort(key=lambda z:(z["event"]["entry"],-z["prob"]))
            chosen=[]
            last_entry=None
            for z in scored:
                entry=z["event"]["entry"]
                if last_entry is not None and _minutes_between(last_entry,entry) < COOLDOWN_MIN:
                    continue
                chosen.append(z)
                last_entry=entry
                if len(chosen)>=MAX_TRADES_DAY:
                    break
            taken.extend(chosen)

        # Train only after today's decisions are fully frozen.
        train.extend(todays)
    return taken

def summarize(taken,year,label):
    import numpy as np
    rows=[z for z in taken if z["year"]==year]
    p=np.asarray([z["net"] for z in rows],float)
    wins=float(p[p>0].sum()) if len(p) else 0.0
    losses=float(-p[p<0].sum()) if len(p) else 0.0
    eq=np.r_[0.,p.cumsum()] if len(p) else np.asarray([0.])
    by_day=defaultdict(int)
    for z in rows: by_day[z["date"]]+=1
    return dict(
        candidate=label,year=year,trades=len(rows),
        trading_days=len(by_day),
        avg_trades_per_active_day=round(len(rows)/len(by_day),4) if by_day else None,
        net_dollars=round(float(p.sum()),6),
        avg_trade=round(float(p.mean()),6) if len(p) else None,
        win_rate=round(float((p>0).mean()*100),4) if len(p) else None,
        profit_factor=round(wins/losses,6) if losses else None,
        closed_trade_max_drawdown=round(float((np.maximum.accumulate(eq)-eq).max()),6),
        avg_probability=round(sum(z["prob"] for z in rows)/len(rows),6) if rows else None,
        research_only=True,production_changed=False,live_ready=False
    )

def run():
    import psycopg2
    from psycopg2.extras import Json
    from scripts.valor_mes_v27_walkforward_selector import load_bars, load_events

    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=15); conn.autocommit=True
    cur=conn.cursor(); cur.execute("SELECT pg_try_advisory_lock(%s)",(LOCK,))
    if not cur.fetchone()[0]:
        conn.close(); return

    sh=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_v28_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_v28_results(
          study_id text PRIMARY KEY,summary jsonb NOT NULL,created_at timestamptz DEFAULT now());""")
        cur.execute("""INSERT INTO valor_mes_v28_state(study_id,status,detail) VALUES(%s,'running',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='running',detail=excluded.detail,updated_at=now()""",
          (STUDY,Json(dict(source_sha256=sh,research_only=True,production_changed=False))))

        contexts=load_bars(cur)
        events=load_events(cur,contexts)
        rows=[]
        for th in THRESHOLDS:
            taken=walkforward_multi(events,th)
            for y in YEARS:
                rows.append(summarize(taken,y,f"wf_multi_p{int(th*100)}"))

        cur.execute("""INSERT INTO valor_mes_v28_results(study_id,summary) VALUES(%s,%s)
          ON CONFLICT(study_id) DO UPDATE SET summary=excluded.summary,created_at=now()""",
          (STUDY,Json(rows)))

        viable=[]
        for c in sorted(set(r["candidate"] for r in rows)):
            rs=[r for r in rows if r["candidate"]==c]
            if len(rs)==3 and all(
                r["trades"]>=180 and
                r["net_dollars"]>0 and
                r["profit_factor"] is not None and r["profit_factor"]>=1.10 and
                r["avg_trade"] is not None and r["avg_trade"]>=4
                for r in rs
            ):
                viable.append(dict(
                    candidate=c,
                    total_net=round(sum(r["net_dollars"] for r in rs),6),
                    worst_pf=min(r["profit_factor"] for r in rs),
                    min_trades=min(r["trades"] for r in rs)
                ))

        cur.execute("""UPDATE valor_mes_v28_state SET status='completed',detail=%s,updated_at=now()
          WHERE study_id=%s""",
          (Json(dict(source_sha256=sh,research_only=True,production_changed=False,
                     viable=viable,max_trades_per_day=MAX_TRADES_DAY,
                     cooldown_minutes=COOLDOWN_MIN,
                     minimum_activity_rule=">=180 trades per year",
                     untouched_next_year=2026)),STUDY))
    except Exception as e:
        cur.execute("""INSERT INTO valor_mes_v28_state(study_id,status,detail) VALUES(%s,'failed',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='failed',detail=excluded.detail,updated_at=now()""",
          (STUDY,Json(dict(source_sha256=sh,error_type=type(e).__name__,message=str(e)[:500]))))
        raise
    finally:
        try: cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally: conn.close()

def launch_if_enabled():
    flag=os.getenv("VALOR_MES_V28_AUTORUN",os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false"))
    if flag.lower() not in {"1","true","yes","on"}:
        return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_v28_multientry_selector"],
        env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True


V29_STUDY="valor-mes-v29-inverse-events-20260925"
V29_LOCK=669202609

def run_inverse_events():
    """Test whether v22 event timing has edge with the opposite direction."""
    import io
    import pandas as pd
    import psycopg2
    from psycopg2.extras import Json
    from scripts import valor_mes_rebuild_v4 as core
    from scripts import valor_mes_v22_event_driven as v22

    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=15)
    conn.autocommit=True
    cur=conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)",(V29_LOCK,))
    if not cur.fetchone()[0]:
        conn.close()
        return

    sh=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_v29_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_v29_results(
          study_id text PRIMARY KEY,summary jsonb NOT NULL,created_at timestamptz DEFAULT now());""")
        cur.execute("""INSERT INTO valor_mes_v29_state(study_id,status,detail) VALUES(%s,'running',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='running',detail=excluded.detail,updated_at=now()""",
          (V29_STUDY,Json(dict(source_sha256=sh,research_only=True,production_changed=False))))

        out=[]
        for year in YEARS:
            cur.execute("SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",
                        (f"GLBX.MDP3:ohlcv-1m:MES.v.0:{year}",))
            row=cur.fetchone()
            if not row:
                raise ValueError(f"missing MES cache {year}")
            body=bytes(row[1])
            dig=hashlib.sha256(body).hexdigest()
            expected=v22.HASHES[year]
            if dig!=row[0] or dig!=expected:
                raise ValueError(f"cache checksum mismatch {year}")

            d=core.prepare(pd.read_parquet(io.BytesIO(body)))
            signals=v22.candidates(d)

            for name,horizon in v22.SPECS.items():
                inv=[]
                for o in signals[name]:
                    x=dict(o)
                    ref=float(x["reference"])
                    side=-int(x["side"])
                    risk=float(x["risk"])
                    reward=abs(float(x["target"])-ref)
                    x["side"]=side
                    x["stop"]=ref-side*risk
                    x["target"]=ref+side*reward
                    x["risk"]=risk
                    inv.append(x)

                trades,censored,rejected=core.replay(d,inv,horizon)
                for ticks in (2,4):
                    r=core.summarize(trades,censored,rejected,f"inverse_{name}",ticks)
                    r={k:v for k,v in r.items() if k not in ("trade_ledger","censored_ledger")}
                    r.update(candidate=f"inverse_{name}",year=year,
                             raw_candidates=len(inv),research_only=True,
                             production_changed=False,live_ready=False)
                    out.append(r)

        viable=[]
        for name in ("or_breakout_retest","vwap_reclaim","compression_breakout"):
            label=f"inverse_{name}"
            rs=[r for r in out if r["candidate"]==label and r["cost_ticks_each_side"]==4]
            if len(rs)==3 and all(
                r["trades"]>=100 and r["net_dollars"]>0 and
                r["profit_factor"] is not None and r["profit_factor"]>=1.10 and
                r["avg_trade"] is not None and r["avg_trade"]>=5 and
                r["censored_fraction"]<=.02
                for r in rs
            ):
                viable.append(dict(
                    candidate=label,
                    total_net=round(sum(r["net_dollars"] for r in rs),6),
                    min_trades=min(r["trades"] for r in rs),
                    worst_pf=min(r["profit_factor"] for r in rs),
                    worst_net=min(r["net_dollars"] for r in rs)
                ))

        cur.execute("""INSERT INTO valor_mes_v29_results(study_id,summary) VALUES(%s,%s)
          ON CONFLICT(study_id) DO UPDATE SET summary=excluded.summary,created_at=now()""",
          (V29_STUDY,Json(out)))
        cur.execute("""UPDATE valor_mes_v29_state SET status='completed',detail=%s,updated_at=now()
          WHERE study_id=%s""",
          (Json(dict(source_sha256=sh,research_only=True,production_changed=False,
                     test="exact opposite direction of v22 event families",
                     minimum_activity_rule=">=100 trades/year for broad engines",
                     viable=viable,untouched_next_year=2026)),V29_STUDY))
    except Exception as e:
        cur.execute("""INSERT INTO valor_mes_v29_state(study_id,status,detail) VALUES(%s,'failed',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='failed',detail=excluded.detail,updated_at=now()""",
          (V29_STUDY,Json(dict(source_sha256=sh,error_type=type(e).__name__,
                              message=str(e)[:500],research_only=True,
                              production_changed=False))))
        raise
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)",(V29_LOCK,))
        finally:
            conn.close()

if __name__=="__main__":
    run()
    run_inverse_events()
