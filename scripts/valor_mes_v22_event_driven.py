"""MES v22 event-driven structure research.

Clean-slate event engine; no fixed clock-time entry requirement beyond RTH scope.

Hypotheses:
1) OR breakout + retest acceptance
2) Failed OR breakout fade
3) VWAP reclaim/rejection after meaningful extension
4) Compression breakout with directional confirmation

Signals are built from completed 5-minute bars; entry is next minute open.
One trade/day/spec. Cached 2023-2025 only. 2026 remains untouched.
Research only: no broker calls, no vendor downloads, no production changes.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, logging, math, os, subprocess, sys

STUDY="valor-mes-v22-event-driven-20260924"
LOCK=662202609
YEARS=(2023,2024,2025)
HASHES={
  2023:"2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
  2024:"6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
  2025:"629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}
SPECS={
 "or_breakout_retest":180,
 "failed_or_breakout":120,
 "vwap_reclaim":150,
 "compression_breakout":180,
}

def add(found,name,row,side,stop,target):
    import numpy as np
    from scripts import valor_mes_rebuild_v4 as core
    if not all(np.isfinite(z) for z in (row.atr,stop,target)): return
    ref=float(row.close); side=int(side)
    stop=core.quantize(float(stop),side); target=core.quantize(float(target),side)
    risk=side*(ref-stop); reward=side*(target-ref)
    cost=core.FEE/core.PV+4*core.TICK
    if risk < 2*cost or risk > 2.25*float(row.atr): return
    if reward < 1.8*risk or reward < 5*cost: return
    found[name].append(dict(index=int(row.raw_index),side=side,reference=ref,
        stop=stop,target=target,risk=risk,
        signal_time=(row.bar_start+__import__("pandas").Timedelta(minutes=5)).isoformat()))

def candidates(d):
    import numpy as np
    from scripts import valor_mes_rebuild_v4 as core
    b,_=core.context(d)
    found={k:[] for k in SPECS}

    for _,g in b[b.rth].groupby(["date","instrument_id"],sort=False):
        rows=list(g.itertuples(index=False))
        if not rows or rows[0].minute!=core.START: continue
        used={k:False for k in SPECS}
        outside={1:0,-1:0}
        last=None
        # Track whether price has made a meaningful extension from VWAP.
        extended={1:False,-1:False}

        for idx,row in enumerate(rows):
            if not (core.START+30 <= row.minute < core.END-90):
                last=row; continue
            a=float(row.atr)
            if not np.isfinite(a) or a<=0 or not np.isfinite(row.or_high) or not np.isfinite(row.vwap):
                last=row; continue

            # 1) OR breakout acceptance + retest.
            for side in (1,-1):
                level=float(row.or_high if side>0 else row.or_low)
                beyond=side*(float(row.close)-level)
                if beyond >= .20*a and side*(float(row.close)-float(row.vwap))>0:
                    outside[side]+=1
                elif beyond < 0:
                    outside[side]=0

                if (not used["or_breakout_retest"] and last is not None and
                    outside[side]>=2):
                    touched=(float(row.low)<=level+.15*a) if side>0 else (float(row.high)>=level-.15*a)
                    held=side*(float(row.close)-level)>=.10*a
                    candle=side*(float(row.close)-float(row.open))>0
                    if touched and held and candle:
                        extreme=min(float(row.low),float(last.low)) if side>0 else max(float(row.high),float(last.high))
                        stop=extreme-side*.20*a
                        risk=side*(float(row.close)-stop)
                        target=float(row.close)+side*2.5*risk
                        add(found,"or_breakout_retest",row,side,stop,target)
                        if found["or_breakout_retest"]: used["or_breakout_retest"]=True

            # 2) Failed OR breakout: excursion outside, close back inside, reversal candle.
            if not used["failed_or_breakout"]:
                for breakout_side in (1,-1):
                    level=float(row.or_high if breakout_side>0 else row.or_low)
                    excursion=(float(row.high)-level) if breakout_side>0 else (level-float(row.low))
                    back_inside=breakout_side*(float(row.close)-level)<0
                    reversal=breakout_side*(float(row.close)-float(row.open))<0
                    if excursion>=.30*a and back_inside and reversal:
                        side=-breakout_side
                        stop=(float(row.high)+.20*a) if side<0 else (float(row.low)-.20*a)
                        midpoint=(float(row.or_high)+float(row.or_low))/2
                        target=midpoint
                        add(found,"failed_or_breakout",row,side,stop,target)
                        if found["failed_or_breakout"]: used["failed_or_breakout"]=True
                        break

            # 3) VWAP reclaim/rejection after extension.
            for side in (1,-1):
                if side*(float(row.close)-float(row.vwap))>=.65*a:
                    extended[side]=True
            if not used["vwap_reclaim"] and last is not None:
                # Long reclaim after downside extension; short rejection after upside extension.
                if extended[-1] and float(last.close)<float(last.vwap) and float(row.close)>float(row.vwap) and float(row.close)>float(row.open):
                    stop=float(row.low)-.25*a
                    risk=float(row.close)-stop
                    add(found,"vwap_reclaim",row,1,stop,float(row.close)+2.25*risk)
                    if found["vwap_reclaim"]: used["vwap_reclaim"]=True
                elif extended[1] and float(last.close)>float(last.vwap) and float(row.close)<float(row.vwap) and float(row.close)<float(row.open):
                    stop=float(row.high)+.25*a
                    risk=stop-float(row.close)
                    add(found,"vwap_reclaim",row,-1,stop,float(row.close)-2.25*risk)
                    if found["vwap_reclaim"]: used["vwap_reclaim"]=True

            # 4) Four-bar compression -> directional breakout.
            if not used["compression_breakout"] and idx>=4:
                prev=rows[idx-4:idx]
                if all(np.isfinite(float(z.atr)) for z in prev):
                    ph=max(float(z.high) for z in prev); pl=min(float(z.low) for z in prev)
                    cr=ph-pl
                    if cr<=1.35*a:
                        for side in (1,-1):
                            break_level=ph if side>0 else pl
                            breakout=side*(float(row.close)-break_level)>=.20*a
                            aligned=side*(float(row.close)-float(row.vwap))>0
                            candle=side*(float(row.close)-float(row.open))>0
                            if breakout and aligned and candle:
                                stop=(pl-.20*a) if side>0 else (ph+.20*a)
                                risk=side*(float(row.close)-stop)
                                target=float(row.close)+side*2.5*risk
                                add(found,"compression_breakout",row,side,stop,target)
                                if found["compression_breakout"]: used["compression_breakout"]=True
                                break
            last=row
    return found

def evaluate(frame,year):
    from scripts import valor_mes_rebuild_v4 as core
    d=core.prepare(frame); signals=candidates(d); rows=[]
    for name,horizon in SPECS.items():
        trades,censored,rejected=core.replay(d,signals[name],horizon)
        for ticks in (2,4):
            r=core.summarize(trades,censored,rejected,name,ticks)
            r.update(candidate=name,year=year,raw_candidates=len(signals[name]),
                     research_only=True,production_changed=False,live_ready=False)
            rows.append(r)
    return dict(study=STUDY,year=year,specs=SPECS,
        execution="completed 5m event signal; next minute open; bracket + horizon",
        selection_cost_ticks_each_side=4,round_trip_fee_assumed=3.0,
        selection_bar={"net_each_year_min":1000,"pf_each_year_min":1.25,
                       "avg_trade_each_year_min":15,"trades_each_year_min":25,
                       "max_drawdown_each_year":1500,"censored_fraction_max":.02},
        years_role="2023-2025 development/robustness; 2026 untouched",
        new_vendor_downloads=0,broker_calls=0,production_changed=False,live_ready=False),rows

def choose(dev):
    picks=[]
    for name in SPECS:
        rs=[r for y in YEARS for r in dev.get(y,[])
            if r["candidate"]==name and r["cost_ticks_each_side"]==4]
        if len(rs)!=3: continue
        if not all(r["trades"]>=25 and r["net_dollars"]>=1000 and
                   r["profit_factor"] is not None and r["profit_factor"]>=1.25 and
                   r["avg_trade"] is not None and r["avg_trade"]>=15 and
                   r["closed_trade_max_drawdown"]<=1500 and
                   r["censored_fraction"]<=.02 for r in rs):
            continue
        worst=min(r["net_dollars"]/max(1.,r["closed_trade_max_drawdown"]) for r in rs)
        total=sum(r["net_dollars"] for r in rs)
        picks.append((worst,total,name))
    return sorted(picks,key=lambda z:(-z[0],-z[1],z[2]))[0][2] if picks else None

def run():
    import pandas as pd, psycopg2
    from psycopg2.extras import Json
    if hasattr(os,"nice"): os.nice(10)
    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=15);conn.autocommit=True
    cur=conn.cursor();cur.execute("SELECT pg_try_advisory_lock(%s)",(LOCK,))
    if not cur.fetchone()[0]:conn.close();return
    sh=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def state(status,**detail):
        cur.execute("""INSERT INTO valor_mes_v22_state(study_id,status,detail)
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
        summary=[{k:v for k,v in r.items() if k not in ("trade_ledger","censored_ledger")} for r in rows]
        evidence=gzip.compress(json.dumps(rows,allow_nan=False).encode(),mtime=0)
        cur.execute("""INSERT INTO valor_mes_v22_results
          (study_id,year,manifest,summary,evidence_gzip) VALUES(%s,%s,%s,%s,%s)
          ON CONFLICT(study_id,year) DO NOTHING""",
          (STUDY,y,Json(m),Json(summary),psycopg2.Binary(evidence)))
        return summary
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_v22_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_v22_results(
          study_id text,year int,manifest jsonb NOT NULL,summary jsonb NOT NULL,evidence_gzip bytea NOT NULL,
          created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,year));""")
        cur.execute("SELECT status FROM valor_mes_v22_state WHERE study_id=%s",(STUDY,))
        if cur.fetchone()==("completed",):return
        dev={}
        for y in YEARS:
            state("evaluating",year=y)
            m,rows=evaluate(cached(y),y);dev[y]=store(y,m,rows)
        selected=choose(dev)
        state("completed",selected=selected,
              selection_bar={"net_each_year_min":1000,"pf_each_year_min":1.25,
                             "avg_trade_each_year_min":15,"trades_each_year_min":25,
                             "max_drawdown_each_year":1500,"censored_fraction_max":.02},
              untouched_next_year=2026)
    except Exception as e:
        try:state("failed",error_type=type(e).__name__,message=str(e)[:500])
        except Exception:pass
        logging.getLogger(__name__).exception("MES v22 event-driven failed")
    finally:
        try:cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally:conn.close()

def launch_if_enabled():
    flag=os.getenv("VALOR_MES_V22_AUTORUN",
                   os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false"))
    if flag.lower() not in {"1","true","yes","on"}:return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_v22_event_driven"],
                     env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True

if __name__=="__main__":run()
