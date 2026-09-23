"""Read-only intraday Spark/Flame research using the private ThetaData service.

This module never places orders and never writes IronForge customer tables.
It persists only research runs/trades in AlphaGEX research tables.
"""
from __future__ import annotations
import csv, io, json, math, os, threading, uuid
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any
import requests
from fastapi import APIRouter, HTTPException, Query
from database_adapter import get_connection

router = APIRouter(prefix="/api/spark-flame/research", tags=["spark-flame-research"])
THETA = os.getenv("THETADATA_BASE_URL", "").strip().rstrip("/")
BOT = {
    "spark": {"entry_et":"11:05:00","otm":2.0,"width":5.0,"vix":0.90,"min_credit":0.10},
    "flame": {"entry_et":"14:05:00","otm":1.0,"width":2.0,"vix":0.80,"min_credit":0.10},
}
_guard_times = ("15:57:00","15:58:00","15:59:00")
_guard_buffer = 0.50
_running = False
_lock = threading.Lock()

def _csv(path:str, params:dict[str,str], timeout:int=90)->list[dict[str,str]]:
    if not THETA: raise RuntimeError("THETADATA_BASE_URL not configured")
    r=requests.get(THETA+path,params=params,timeout=timeout); r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))

def _snap(d:date, hms:str)->list[dict[str,str]]:
    y=d.strftime("%Y%m%d")
    return _csv("/v3/option/history/quote",{"symbol":"SPY","expiration":y,"strike":"*","right":"both","date":y,"interval":"1m","start_time":hms,"end_time":hms})

def _n(v:Any)->float|None:
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception:return None

def _right(v:str)->str:
    x=(v or "").strip().lower()
    return "put" if x in ("p","put") else "call" if x in ("c","call") else x

def _parity(rows):
    q={}
    for r in rows:
        k,b,a=_n(r.get("strike")),_n(r.get("bid")),_n(r.get("ask"))
        if k is None or b is None or a is None or b<=0 or a<=0: continue
        q.setdefault(k,{})[_right(r.get("right",""))]=(b+a)/2
    xs=[k+v["call"]-v["put"] for k,v in q.items() if "call" in v and "put" in v]
    return median(xs) if xs else None

def _put(rows,strike):
    for r in rows:
        if _right(r.get("right",""))!="put": continue
        k=_n(r.get("strike"))
        if k is not None and abs(k-strike)<0.01:
            b,a=_n(r.get("bid")),_n(r.get("ask"))
            if b is not None and a is not None and a>0: return b,a
    return None

def _js_round(x:float)->int:return math.floor(x+0.5)

def _tables(conn):
    c=conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS spark_flame_intraday_research_runs(
      run_id TEXT PRIMARY KEY, started_at TIMESTAMPTZ DEFAULT NOW(), finished_at TIMESTAMPTZ,
      start_date DATE, end_date DATE, status TEXT NOT NULL, detail TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS spark_flame_intraday_research_trades(
      run_id TEXT NOT NULL, bot TEXT NOT NULL, trade_date DATE NOT NULL, status TEXT NOT NULL,
      reason TEXT, entry_spot NUMERIC, short_strike NUMERIC, long_strike NUMERIC,
      short_bid NUMERIC, long_ask NUMERIC, entry_credit NUMERIC, vix_ratio NUMERIC,
      guard_time TEXT, guard_spot NUMERIC, close_debit NUMERIC, settle_spot NUMERIC,
      pnl_per_lot NUMERIC, created_at TIMESTAMPTZ DEFAULT NOW(),
      PRIMARY KEY(run_id,bot,trade_date))""")
    conn.commit()

def _vix_series(conn)->dict[date,float]:
    c=conn.cursor(); c.execute("SELECT trade_date,vix FROM sw_vix_daily ORDER BY trade_date")
    return {r[0]:float(r[1]) for r in c.fetchall()}

def _vix_ratio(series:dict[date,float], d:date)->float|None:
    ds=sorted(k for k in series if k<d)
    if len(ds)<21:return None
    prior=series[ds[-1]]
    mx=max(series[x] for x in ds[-21:-1])
    return prior/mx if mx>0 else None

def _one_day(d:date, bot:str, vixs)->dict:
    cfg=BOT[bot]; ratio=_vix_ratio(vixs,d)
    base={"bot":bot,"trade_date":d,"status":"skip","vix_ratio":ratio}
    if ratio is None:return {**base,"reason":"vix_unknown"}
    if ratio>cfg["vix"]:return {**base,"reason":"vix_elevated"}
    entry=_snap(d,cfg["entry_et"]); spot=_parity(entry)
    if spot is None:return {**base,"reason":"missing_entry_spot"}
    short=_js_round(spot-cfg["otm"]); long=short-cfg["width"]
    sq,lq=_put(entry,short),_put(entry,long)
    if not sq or not lq:return {**base,"reason":"missing_leg_quote","entry_spot":spot,"short_strike":short,"long_strike":long}
    credit=sq[0]-lq[1]
    row={**base,"entry_spot":spot,"short_strike":short,"long_strike":long,"short_bid":sq[0],"long_ask":lq[1],"entry_credit":credit}
    if credit<cfg["min_credit"]:return {**row,"reason":"credit_low"}
    for gt in _guard_times:
        g=_snap(d,gt); gspot=_parity(g)
        if gspot is None: continue
        if gspot<=short+_guard_buffer:
            qs,ql=_put(g,short),_put(g,long)
            if qs and ql:
                debit=max(0.0,qs[1]-ql[0])
                return {**row,"status":"trade","reason":"assignment_guard","guard_time":gt,"guard_spot":gspot,"close_debit":debit,"settle_spot":None,"pnl_per_lot":(credit-debit)*100}
    final=_snap(d,"15:59:00"); settle=_parity(final)
    if settle is None:return {**row,"reason":"missing_settle_spot"}
    value=min(max(short-settle,0.0),cfg["width"])
    return {**row,"status":"trade","reason":"settled","settle_spot":settle,"pnl_per_lot":(credit-value)*100}

def _run(start:date,end:date):
    global _running
    run_id="sf-"+uuid.uuid4().hex[:12]
    conn=get_connection()
    try:
        _tables(conn); c=conn.cursor()
        c.execute("INSERT INTO spark_flame_intraday_research_runs(run_id,start_date,end_date,status,detail) VALUES(%s,%s,%s,'running','1m NBBO, production-matched entry/VIX/assignment guard')",(run_id,start,end)); conn.commit()
        vixs=_vix_series(conn); d=start
        while d<=end:
            if d.weekday()<5:
                # One failed market/holiday day is recorded as a skip, not fatal.
                for bot in ("spark","flame"):
                    try: rec=_one_day(d,bot,vixs)
                    except Exception as e:
                        rec={"bot":bot,"trade_date":d,"status":"error","reason":type(e).__name__}
                    c.execute("""INSERT INTO spark_flame_intraday_research_trades
                    (run_id,bot,trade_date,status,reason,entry_spot,short_strike,long_strike,short_bid,long_ask,entry_credit,vix_ratio,guard_time,guard_spot,close_debit,settle_spot,pnl_per_lot)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(run_id,bot,trade_date) DO NOTHING""",
                    (run_id,bot,d,rec.get("status"),rec.get("reason"),rec.get("entry_spot"),rec.get("short_strike"),rec.get("long_strike"),rec.get("short_bid"),rec.get("long_ask"),rec.get("entry_credit"),rec.get("vix_ratio"),rec.get("guard_time"),rec.get("guard_spot"),rec.get("close_debit"),rec.get("settle_spot"),rec.get("pnl_per_lot")))
                    conn.commit()
            d+=timedelta(days=1)
        c.execute("UPDATE spark_flame_intraday_research_runs SET finished_at=NOW(),status='completed',detail='completed' WHERE run_id=%s",(run_id,)); conn.commit()
    except Exception as e:
        try:
            c=conn.cursor(); c.execute("UPDATE spark_flame_intraday_research_runs SET finished_at=NOW(),status='failed',detail=%s WHERE run_id=%s",(repr(e),run_id)); conn.commit()
        except Exception: pass
    finally:
        conn.close()
        with _lock:_running=False

@router.post("/start")
def start(start:str=Query("2025-01-01"),end:str=Query("2025-12-31")):
    global _running
    s,e=date.fromisoformat(start),date.fromisoformat(end)
    with _lock:
        if _running:return {"started":False,"reason":"already_running"}
        _running=True
    threading.Thread(target=_run,args=(s,e),daemon=True,name="spark-flame-intraday").start()
    return {"started":True,"start":start,"end":end,"research_only":True}

@router.get("/status")
def status():
    conn=get_connection()
    try:
        _tables(conn); c=conn.cursor()
        c.execute("SELECT run_id,started_at,finished_at,start_date,end_date,status,detail FROM spark_flame_intraday_research_runs ORDER BY started_at DESC LIMIT 1")
        row=c.fetchone()
        if not row:return {"running":_running,"latest":None}
        run_id=row[0]
        c.execute("""SELECT bot,COUNT(*) FILTER(WHERE status='trade'),ROUND(COALESCE(SUM(pnl_per_lot) FILTER(WHERE status='trade'),0)::numeric,2),
        ROUND(COALESCE(AVG(pnl_per_lot) FILTER(WHERE status='trade'),0)::numeric,2),
        ROUND(COALESCE(100*AVG((pnl_per_lot>0)::int) FILTER(WHERE status='trade'),0)::numeric,1),
        ROUND(MIN(pnl_per_lot) FILTER(WHERE status='trade')::numeric,2)
        FROM spark_flame_intraday_research_trades WHERE run_id=%s GROUP BY bot ORDER BY bot""",(run_id,))
        sums=[{"bot":x[0],"trades":x[1],"pnl":float(x[2]),"avg":float(x[3]),"win_rate":float(x[4]),"worst":float(x[5]) if x[5] is not None else None} for x in c.fetchall()]
        return {"running":_running,"latest":{"run_id":row[0],"started_at":str(row[1]),"finished_at":str(row[2]) if row[2] else None,"start":str(row[3]),"end":str(row[4]),"status":row[5],"detail":row[6],"summary":sums}}
    finally:conn.close()
