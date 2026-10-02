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
        cur.execute("SELECT status FROM valor_mes_v28_state WHERE study_id=%s",(STUDY,))
        existing=cur.fetchone()
        if existing and existing[0]=="completed":
            return
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
        cur.execute("SELECT status FROM valor_mes_v29_state WHERE study_id=%s",(V29_STUDY,))
        existing=cur.fetchone()
        if existing and existing[0]=="completed":
            return
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


V30_STUDY="valor-mes-v30-grid-direction-20260925"
V30_LOCK=670202609
V30_THRESHOLDS=(0.54,0.56,0.58)
V30_HOLD=60
V30_COOLDOWN=75
V30_MAX_DAY=3

def _v30_load_opportunities(cur):
    """15-minute RTH decision grid with a fixed 60-minute forward label."""
    import io
    import numpy as np
    import pandas as pd
    from scripts import valor_mes_rebuild_v4 as core
    from scripts import valor_mes_v22_event_driven as v22

    opps=[]
    for year in YEARS:
        cur.execute("SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",
                    (f"GLBX.MDP3:ohlcv-1m:MES.v.0:{year}",))
        row=cur.fetchone()
        if not row:
            raise ValueError(f"missing MES cache {year}")
        body=bytes(row[1]); dig=hashlib.sha256(body).hexdigest()
        if dig!=row[0] or dig!=v22.HASHES[year]:
            raise ValueError(f"cache checksum mismatch {year}")

        d=core.prepare(pd.read_parquet(io.BytesIO(body)))
        b,previous=core.context(d)
        closes=d.close.to_numpy(float)
        opens=d.open.to_numpy(float)
        seg=d.segment.to_numpy()
        dates=d.date.to_numpy()

        for _,g in b[b.rth].groupby(["date","instrument_id"],sort=False):
            rows=list(g.itertuples(index=False))
            hist=[]
            for r in rows:
                hist.append(r)
                # completed 5m bar decisions every 15m from 09:00 CT through 13:45 CT.
                if r.minute < core.START+30 or r.minute > core.END-V30_HOLD-15:
                    continue
                if (r.minute-(core.START+30)) % 15 != 0:
                    continue
                if len(hist)<7 or not np.isfinite(float(r.atr)) or float(r.atr)<=0:
                    continue
                if not np.isfinite(float(r.vwap)) or not np.isfinite(float(r.or_high)):
                    continue

                e=int(r.raw_index)+1
                x=e+V30_HOLD-1
                if x>=len(d) or seg[e]!=seg[int(r.raw_index)] or seg[x]!=seg[e] or dates[x]!=dates[e]:
                    continue

                atr=float(r.atr)
                ref=float(r.close)
                c5=float(hist[-2].close) if len(hist)>=2 else ref
                c15=float(hist[-4].close) if len(hist)>=4 else ref
                c30=float(hist[-7].close)
                recent=hist[-7:]
                path=sum(abs(float(recent[j].close)-float(recent[j-1].close)) for j in range(1,len(recent)))
                efficiency=abs(ref-c30)/path if path>0 else 0.0
                width=float(r.or_high)-float(r.or_low)
                loc=(ref-float(r.or_low))/width if width>0 else .5
                bar_range=(max(float(z.high) for z in hist[-4:])-min(float(z.low) for z in hist[-4:]))/atr

                prior=previous.get(r.date)
                prior_range_atr=0.0
                prior_close_loc=.5
                if prior and float(prior.get("atr20") or 0)>0:
                    prior_range_atr=(float(prior["high"])-float(prior["low"]))/float(prior["atr20"])
                    pr=float(prior["high"])-float(prior["low"])
                    if pr>0:
                        prior_close_loc=(float(prior["close"])-float(prior["low"]))/pr

                entry=float(opens[e]); exit_raw=float(closes[x])
                raw_move=exit_raw-entry
                opps.append(dict(
                    year=year,date=str(dates[e]),
                    entry_time=d.timestamp.iloc[e].isoformat(),
                    exit_time=(d.timestamp.iloc[x]+pd.Timedelta(minutes=1)).isoformat(),
                    entry_raw=entry,exit_raw=exit_raw,
                    features=[
                        (ref-c5)/atr,
                        (ref-c15)/atr,
                        (ref-c30)/atr,
                        (ref-float(r.vwap))/atr,
                        width/atr if width>0 else 0.0,
                        loc,
                        efficiency,
                        bar_range,
                        (r.minute-core.START)/(core.END-core.START),
                        prior_range_atr,
                        prior_close_loc,
                    ],
                    label=1 if raw_move>0 else 0,
                    raw_move=raw_move
                ))
    opps.sort(key=lambda z:(z["date"],z["entry_time"]))
    return opps

def _v30_net(o,side,ticks=4):
    from scripts import valor_mes_rebuild_v4 as core
    ent=core.fill(float(o["entry_raw"]),int(side),ticks)
    ex=core.fill(float(o["exit_raw"]),-int(side),ticks)
    return round(int(side)*(ex-ent)*core.PV-core.FEE,6)

def _v30_walkforward(opps,threshold):
    import numpy as np
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression

    by_day=defaultdict(list)
    for o in opps: by_day[o["date"]].append(o)

    train=[]
    taken=[]
    for day in sorted(by_day):
        todays=by_day[day]
        if len(train)>=400 and len({z["label"] for z in train[-1800:]})==2:
            tr=train[-1800:]
            X=np.asarray([z["features"] for z in tr],float)
            y=np.asarray([z["label"] for z in tr],int)
            model=make_pipeline(StandardScaler(),
                LogisticRegression(C=.25,max_iter=500,class_weight="balanced",random_state=17))
            model.fit(X,y)
            probs=model.predict_proba(np.asarray([z["features"] for z in todays],float))[:,1]

            scored=[]
            for p,o in zip(probs,todays):
                p=float(p)
                if p>=threshold:
                    q=dict(o);q["side"]=1;q["confidence"]=p;q["net"]=_v30_net(q,1,4);scored.append(q)
                elif p<=1-threshold:
                    q=dict(o);q["side"]=-1;q["confidence"]=1-p;q["net"]=_v30_net(q,-1,4);scored.append(q)

            scored.sort(key=lambda z:z["entry_time"])
            chosen=[]
            last=None
            for q in scored:
                if last is not None and _minutes_between(last,q["entry_time"])<V30_COOLDOWN:
                    continue
                chosen.append(q);last=q["entry_time"]
                if len(chosen)>=V30_MAX_DAY:
                    break
            taken.extend(chosen)
        train.extend(todays)
    return taken

def _v30_rule(opps,mode):
    """Dense causal baselines: 30m momentum or 30m fade."""
    taken=[]
    by_day=defaultdict(list)
    for o in opps: by_day[o["date"]].append(o)
    for day in sorted(by_day):
        last=None;n=0
        for o in by_day[day]:
            m=float(o["features"][2])
            if abs(m)<.15:
                continue
            side=1 if m>0 else -1
            if mode=="fade":
                side=-side
            if last is not None and _minutes_between(last,o["entry_time"])<V30_COOLDOWN:
                continue
            q=dict(o);q["side"]=side;q["confidence"]=abs(m);q["net"]=_v30_net(q,side,4)
            taken.append(q);last=q["entry_time"];n+=1
            if n>=V30_MAX_DAY:
                break
    return taken

def _v30_summary(rows,year,label):
    import numpy as np
    xs=[z for z in rows if int(z["year"])==year]
    p=np.asarray([float(z["net"]) for z in xs],float)
    wins=float(p[p>0].sum()) if len(p) else 0.0
    losses=float(-p[p<0].sum()) if len(p) else 0.0
    eq=np.r_[0.,p.cumsum()] if len(p) else np.asarray([0.])
    days=len(set(z["date"] for z in xs))
    return dict(candidate=label,year=year,trades=len(xs),trading_days=days,
        avg_trades_per_active_day=round(len(xs)/days,4) if days else None,
        net_dollars=round(float(p.sum()),6),
        avg_trade=round(float(p.mean()),6) if len(p) else None,
        win_rate=round(float((p>0).mean()*100),4) if len(p) else None,
        profit_factor=round(wins/losses,6) if losses else None,
        closed_trade_max_drawdown=round(float((np.maximum.accumulate(eq)-eq).max()),6),
        research_only=True,production_changed=False,live_ready=False)

def run_grid_direction():
    import psycopg2
    from psycopg2.extras import Json
    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=15);conn.autocommit=True
    cur=conn.cursor();cur.execute("SELECT pg_try_advisory_lock(%s)",(V30_LOCK,))
    if not cur.fetchone()[0]:
        conn.close();return
    sh=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_v30_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_v30_results(
          study_id text PRIMARY KEY,summary jsonb NOT NULL,created_at timestamptz DEFAULT now());""")
        cur.execute("""INSERT INTO valor_mes_v30_state(study_id,status,detail) VALUES(%s,'running',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='running',detail=excluded.detail,updated_at=now()""",
          (V30_STUDY,Json(dict(source_sha256=sh,research_only=True,production_changed=False))))
        opps=_v30_load_opportunities(cur)
        out=[]
        variants={"momentum30":_v30_rule(opps,"momentum"),"fade30":_v30_rule(opps,"fade")}
        for th in V30_THRESHOLDS:
            variants[f"wf_grid_p{int(th*100)}"]=_v30_walkforward(opps,th)
        for name,rows in variants.items():
            for y in YEARS:
                out.append(_v30_summary(rows,y,name))

        viable=[]
        for name in variants:
            rs=[r for r in out if r["candidate"]==name]
            if len(rs)==3 and all(r["trades"]>=180 and r["net_dollars"]>0 and
                r["profit_factor"] is not None and r["profit_factor"]>=1.10 and
                r["avg_trade"] is not None and r["avg_trade"]>=4 for r in rs):
                viable.append(dict(candidate=name,total_net=round(sum(r["net_dollars"] for r in rs),6),
                    min_trades=min(r["trades"] for r in rs),worst_pf=min(r["profit_factor"] for r in rs)))
        cur.execute("""INSERT INTO valor_mes_v30_results(study_id,summary) VALUES(%s,%s)
          ON CONFLICT(study_id) DO UPDATE SET summary=excluded.summary,created_at=now()""",
          (V30_STUDY,Json(out)))
        cur.execute("""UPDATE valor_mes_v30_state SET status='completed',detail=%s,updated_at=now()
          WHERE study_id=%s""",
          (Json(dict(source_sha256=sh,research_only=True,production_changed=False,
                     opportunity_count=len(opps),grid_minutes=15,hold_minutes=V30_HOLD,
                     cooldown_minutes=V30_COOLDOWN,max_trades_per_day=V30_MAX_DAY,
                     minimum_activity_rule=">=180 trades/year",
                     viable=viable,untouched_next_year=2026)),V30_STUDY))
    except Exception as e:
        cur.execute("""INSERT INTO valor_mes_v30_state(study_id,status,detail) VALUES(%s,'failed',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='failed',detail=excluded.detail,updated_at=now()""",
          (V30_STUDY,Json(dict(source_sha256=sh,error_type=type(e).__name__,
                              message=str(e)[:500],research_only=True,production_changed=False))))
        raise
    finally:
        try:cur.execute("SELECT pg_advisory_unlock(%s)",(V30_LOCK,))
        finally:conn.close()

if __name__=="__main__":
    run()
    run_inverse_events()
    run_grid_direction()
