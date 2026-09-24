"""MES v21 clean-slate regime research.

This is intentionally NOT a CHOPGuard derivative. It rebuilds MES around a
small set of causal, interpretable intraday hypotheses and a regime router.

Candidate engines:
1) trend_60: strong first-hour directional auction, 09:30 CT -> 12:00 CT
2) trend_90: stronger 90-minute directional auction, 10:00 CT -> 13:00 CT
3) pullback_trend: strong morning trend followed by a controlled 15m pullback,
   09:45 CT -> 12:00 CT
4) opening_fade: inefficient opening excursion with 15m reversal confirmation,
   09:00 CT -> 10:30 CT
5) regime_router: one trade/day, selecting trend_60 or opening_fade from opening
   efficiency / reversal structure.

All features use only bars completed before the decision. Cached 2023-2025 MES
minute data only. 2026 remains untouched. Research only.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, logging, math, os, subprocess, sys

STUDY="valor-mes-v21-clean-slate-20260924"
LOCK=661202609
YEARS=(2023,2024,2025)
HASHES={
  2023:"2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
  2024:"6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
  2025:"629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}
PV,TICK,FEE=5.0,.25,3.0
SPECS=("trend_60","trend_90","pullback_trend","opening_fade","regime_router")

def context(d, day, end_minute):
    import numpy as np
    p=d[(d.date==day)&d.rth&d.minute.ge(510)&d.minute.lt(end_minute)]
    need=end_minute-510
    if len(p)!=need or p.empty or p.minute.iloc[0]!=510 or p.minute.iloc[-1]!=end_minute-1 or p.segment.nunique()!=1:
        return None
    hi=float(p.high.max()); lo=float(p.low.min()); width=hi-lo
    if width<=0 or float(p.volume.sum())<=0:return None
    op=float(p.open.iloc[0]); cl=float(p.close.iloc[-1])
    vwap=float((p.volume*(p.high+p.low+p.close)/3).sum()/p.volume.sum())
    move=cl-op
    side=int(np.sign(move))
    loc_up=(cl-lo)/width
    loc_dn=(hi-cl)/width
    efficiency=abs(move)/width
    late15=float(cl-p.open.iloc[-15]) if len(p)>=15 else 0.0
    late30=float(cl-p.open.iloc[-30]) if len(p)>=30 else 0.0
    return dict(p=p,index=int(p.index[-1]),reference=cl,open=op,high=hi,low=lo,width=width,
                vwap=vwap,move=move,side=side,efficiency=efficiency,
                loc_up=loc_up,loc_dn=loc_dn,late15=late15,late30=late30)

def mk_order(c, day, side, exit_minute, risk_mult=.75):
    risk=math.ceil(max(4.0,c["width"]*risk_mult)/TICK)*TICK
    return dict(index=c["index"],date=day,side=int(side),
                reference=float(c["reference"]),risk=float(risk),
                exit_minute=int(exit_minute))

def trend_order(c, day, exit_minute, min_eff=.55, min_loc=.75):
    if c is None or c["side"]==0:return None
    s=c["side"]; loc=c["loc_up"] if s>0 else c["loc_dn"]
    if c["efficiency"]<min_eff or loc<min_loc:return None
    if s*(c["reference"]-c["vwap"])<=0:return None
    if s*c["late15"]<=0:return None
    return mk_order(c,day,s,exit_minute,.70)

def pullback_order(c,day):
    if c is None or c["side"]==0:return None
    s=c["side"]; loc=c["loc_up"] if s>0 else c["loc_dn"]
    if c["efficiency"]<.45 or loc<.62:return None
    if s*(c["reference"]-c["vwap"])<=0:return None
    # overall trend intact, but last 15m is a controlled counter-move
    if s*c["late15"]>=0:return None
    if abs(c["late15"])>.35*c["width"]:return None
    return mk_order(c,day,s,720,.60)

def fade_order(c,day):
    import numpy as np
    if c is None:return None
    opening_side=int(np.sign(c["move"]))
    if opening_side==0:return None
    # Inefficient opening: large travel, weak net displacement, reversal in last 15m.
    if c["efficiency"]>.38:return None
    fade=-opening_side
    if fade*c["late15"]<=0:return None
    # Still require price to be meaningfully displaced from VWAP before fading.
    if abs(c["reference"]-c["vwap"])<.12*c["width"]:return None
    return mk_order(c,day,fade,630,.55)

def schedules(d):
    days=sorted(d[d.rth].date.unique())
    out={k:[] for k in SPECS}
    skipped={k:0 for k in SPECS}
    for day in days:
        c540=context(d,day,540)
        c570=context(d,day,570)
        c585=context(d,day,585)
        c600=context(d,day,600)

        a=trend_order(c570,day,720,.55,.75)
        if a: out["trend_60"].append(a)
        else: skipped["trend_60"]+=1

        a=trend_order(c600,day,780,.58,.78)
        if a: out["trend_90"].append(a)
        else: skipped["trend_90"]+=1

        a=pullback_order(c585,day)
        if a: out["pullback_trend"].append(a)
        else: skipped["pullback_trend"]+=1

        a=fade_order(c540,day)
        if a: out["opening_fade"].append(a)
        else: skipped["opening_fade"]+=1

        # Router is deliberately deterministic and mutually exclusive.
        routed=None
        if c570 is not None:
            routed=trend_order(c570,day,720,.55,.75)
        if routed is None:
            routed=fade_order(c540,day)
        if routed:
            out["regime_router"].append(routed)
        else:
            skipped["regime_router"]+=1
    return out,skipped

def evaluate(frame,year):
    from scripts import valor_mes_session_v6 as base
    d=base.prepare(frame); scheds,skips=schedules(d); rows=[]
    for spec in SPECS:
        trades,unresolved=base.replay(d,scheds[spec],"signal")
        for ticks in (2,4):
            r=base.summarize(trades,unresolved,year,ticks)
            r.update(candidate=spec,year=year,decisions=len(scheds[spec]),
                     skipped_days=skips[spec],research_only=True,
                     production_changed=False,live_ready=False)
            rows.append(r)
    return dict(study=STUDY,year=year,specs=list(SPECS),
                architecture="clean-slate causal MES intraday regimes",
                costs={"selection_ticks_each_side":4,"round_trip_fee":FEE},
                selection_bar={"net_each_year_min":1000,"profit_factor_each_year_min":1.20,
                               "avg_trade_each_year_min":12,"trades_each_year_min":30,
                               "max_closed_trade_drawdown_each_year":1500,
                               "unresolved_fraction_max":.04},
                years_role="2023-2025 development/robustness; 2026 untouched",
                new_vendor_downloads=0,broker_calls=0,
                production_changed=False,live_ready=False),rows

def choose(dev):
    picks=[]
    for name in SPECS:
        rs=[r for y in YEARS for r in dev.get(y,[])
            if r["candidate"]==name and r["cost_ticks_each_side"]==4]
        if len(rs)!=3:continue
        if not all(r["trades"]>=30 and r["net_dollars"]>=1000 and
                   r["profit_factor"] is not None and r["profit_factor"]>=1.20 and
                   r["avg_trade"] is not None and r["avg_trade"]>=12 and
                   r["closed_trade_max_drawdown"]<=1500 and
                   r["unresolved_fraction"]<=.04 for r in rs):
            continue
        worst=min(r["net_dollars"]/max(1.,r["closed_trade_max_drawdown"]) for r in rs)
        total=sum(r["net_dollars"] for r in rs)
        picks.append((worst,total,name))
    return sorted(picks,key=lambda x:(-x[0],-x[1],x[2]))[0][2] if picks else None

def run():
    import pandas as pd, psycopg2
    from psycopg2.extras import Json
    if hasattr(os,"nice"):os.nice(10)
    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=15);conn.autocommit=True
    cur=conn.cursor();cur.execute("SELECT pg_try_advisory_lock(%s)",(LOCK,))
    if not cur.fetchone()[0]:conn.close();return
    sh=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def state(status,**detail):
        cur.execute("""INSERT INTO valor_mes_v21_state(study_id,status,detail)
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
        cur.execute("""INSERT INTO valor_mes_v21_results
          (study_id,year,manifest,summary,evidence_gzip) VALUES(%s,%s,%s,%s,%s)
          ON CONFLICT(study_id,year) DO NOTHING""",
          (STUDY,y,Json(m),Json(summary),psycopg2.Binary(evidence)))
        return summary
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_v21_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_mes_v21_results(
          study_id text,year int,manifest jsonb NOT NULL,summary jsonb NOT NULL,evidence_gzip bytea NOT NULL,
          created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,year));""")
        cur.execute("SELECT status FROM valor_mes_v21_state WHERE study_id=%s",(STUDY,))
        if cur.fetchone()==("completed",):return
        dev={}
        for y in YEARS:
            state("evaluating",year=y)
            m,rows=evaluate(cached(y),y);dev[y]=store(y,m,rows)
        selected=choose(dev)
        state("completed",selected=selected,
              selection_bar={"net_each_year_min":1000,"pf_each_year_min":1.20,
                             "avg_trade_each_year_min":12,"trades_each_year_min":30,
                             "max_drawdown_each_year":1500,
                             "unresolved_fraction_max":.04},
              untouched_next_year=2026)
    except Exception as e:
        try:state("failed",error_type=type(e).__name__,message=str(e)[:500])
        except Exception:pass
        logging.getLogger(__name__).exception("MES v21 clean-slate failed")
    finally:
        try:cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally:conn.close()

def launch_if_enabled():
    flag=os.getenv("VALOR_MES_V21_AUTORUN",
                   os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false"))
    if flag.lower() not in {"1","true","yes","on"}:return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_v21_clean_slate"],
                     env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True

if __name__=="__main__":run()
