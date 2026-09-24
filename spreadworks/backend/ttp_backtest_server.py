"""Preliminary TTP multi-engine backtest using Yahoo 5-minute bars.

Runs on Render (internet access), fetches 60 trading days of 5-minute RTH bars,
uses next-bar-open entries to avoid lookahead, conservative same-bar stop priority,
2R target, 15:45 ET force-flat, 3 trades/day portfolio cap, $50 planned risk.
This is a screening backtest, not the final 1-minute/1-year validation.
"""
from __future__ import annotations

import asyncio
import json
import math
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
UNIVERSE = ["AAPL","AMD","AMZN","BAC","COIN","HOOD","META","MSFT","MU","NVDA","PLTR","RIVN","SOFI","TSLA","UBER"]
RISK_DOLLARS = 50.0
MAX_POSITION_VALUE = 10000.0
MAX_STOP_PCT = 1.5
MAX_TRADES_DAY = 3
SLIPPAGE_PCT = 0.0003  # 3 bps each side
FEE_PER_SHARE_ROUNDTRIP = 0.01

app = FastAPI(title="TTP Multi-Engine Backtest")
RESULT: dict[str, Any] = {"status":"pending"}
task = None

@dataclass(frozen=True)
class Bar:
    ts: datetime
    o: float
    h: float
    l: float
    c: float
    v: float

@dataclass
class Trade:
    symbol: str
    day: str
    engine: str
    quality: float
    signal_time: str
    entry_time: str
    entry: float
    stop: float
    target: float
    shares: int
    exit_time: str
    exit_price: float
    exit_reason: str
    gross_pnl: float
    net_pnl: float
    r_multiple: float

async def fetch(client: httpx.AsyncClient, symbol: str) -> list[Bar]:
    r = await client.get(
        YAHOO.format(symbol=symbol),
        params={"interval":"5m","range":"60d","includePrePost":"false","events":"div,splits"},
        headers={"User-Agent":"Mozilla/5.0 AlphaGEX-TTP-Backtest/1.0"},
        timeout=30,
    )
    r.raise_for_status()
    root = ((r.json().get("chart") or {}).get("result") or [None])[0]
    if not root:
        return []
    q = (((root.get("indicators") or {}).get("quote") or [{}])[0])
    stamps = root.get("timestamp") or []
    arr = [q.get(k) or [] for k in ("open","high","low","close","volume")]
    out=[]
    for i,s in enumerate(stamps):
        try: vals=[a[i] for a in arr]
        except IndexError: continue
        if any(x is None for x in vals[:4]): continue
        ts=datetime.fromtimestamp(float(s),UTC).astimezone(ET)
        if ts.weekday()<5 and time(9,30)<=ts.time()<time(16,0):
            out.append(Bar(ts,*(float(x or 0) for x in vals)))
    return out

def signal_for(prefix:list[Bar], prevclose:float|None) -> tuple[str,float,float]|None:
    if len(prefix)<7: return None
    opening=prefix[0]
    last,prev=prefix[-1],prefix[-2]
    cumv=sum(x.v for x in prefix)
    if last.c<2 or cumv<100000: return None
    vwap=sum(x.c*x.v for x in prefix)/cumv if cumv else last.c
    orh=opening.h
    prior_high=max(x.h for x in prefix[:-1])
    vols=[x.v for x in prefix[-21:-1] if x.v>0]
    med=statistics.median(vols) if vols else 0
    rvol=last.v/med if med else 1.0
    dc=((last.c/prevclose)-1)*100 if prevclose else 0
    gap=((opening.o/prevclose)-1)*100 if prevclose else 0
    stop=min(x.l for x in prefix[-5:])

    if gap>=2 and last.c>orh and prev.c<=orh and last.c>vwap:
        q=min(9.5,7.0+min(gap,5)*.3+min(rvol,3)*.35)
        return "GAP_GO",q,stop
    if last.c>orh and prev.c<=orh and last.c>vwap:
        q=min(9.2,6.8+min(rvol,3)*.5+min(max(dc,0),4)*.25)
        return "ORB",q,stop
    if last.c>prior_high and prev.c<=prior_high and last.c>vwap and rvol>=1.2:
        q=min(9.3,7.0+min(rvol,3)*.55+min(max(dc,0),4)*.2)
        return "HOD_BREAKOUT",q,stop
    if prev.c<=vwap*1.001 and last.c>vwap and last.c>prev.c and rvol>=1.15:
        q=min(8.8,6.6+min(rvol,3)*.55+min(max(dc,0),4)*.2)
        return "VWAP_RECLAIM",q,stop
    if len(prefix)>=4:
        c=[x.c for x in prefix[-4:]]
        if c[0]<c[1]<c[2]<c[3] and last.c>vwap and rvol>=1.5 and dc>=1:
            q=min(9.0,6.8+min(rvol,3.5)*.5+min(dc,5)*.2)
            return "MOMENTUM_RVOL",q,stop
    return None

def symbol_trades(symbol:str,bars:list[Bar]) -> list[Trade]:
    byday=defaultdict(list)
    for b in bars: byday[b.ts.date()].append(b)
    days=sorted(byday)
    out=[]
    prev_close=None
    for d in days:
        day=sorted(byday[d],key=lambda x:x.ts)
        if prev_close is None:
            prev_close=day[0].o
        fired=False
        for i in range(6,len(day)-1):
            b=day[i]
            if not (time(9,35)<=b.ts.time()<=time(15,30)): continue
            sig=signal_for(day[:i+1],prev_close)
            if not sig: continue
            engine,q,stop=sig
            if q<7.2: continue
            nxt=day[i+1]
            entry=nxt.o*(1+SLIPPAGE_PCT)
            dist=entry-stop
            if dist<=0 or dist/entry*100>MAX_STOP_PCT: continue
            shares=min(math.floor(RISK_DOLLARS/dist),math.floor(MAX_POSITION_VALUE/entry))
            if shares<1: continue
            target=entry+2*dist
            exitp=day[-1].c*(1-SLIPPAGE_PCT); reason="EOD"; exitts=day[-1].ts
            for x in day[i+1:]:
                if x.ts.time()>time(15,45):
                    break
                stop_hit=x.l<=stop
                target_hit=x.h>=target
                if stop_hit:
                    exitp=stop*(1-SLIPPAGE_PCT); reason="STOP"; exitts=x.ts; break
                if target_hit:
                    exitp=target*(1-SLIPPAGE_PCT); reason="TARGET_2R"; exitts=x.ts; break
                exitp=x.c*(1-SLIPPAGE_PCT); exitts=x.ts
            gross=(exitp-entry)*shares
            fees=shares*FEE_PER_SHARE_ROUNDTRIP
            net=gross-fees
            out.append(Trade(
                symbol=symbol,day=d.isoformat(),engine=engine,quality=round(q,2),
                signal_time=b.ts.isoformat(),entry_time=nxt.ts.isoformat(),
                entry=round(entry,4),stop=round(stop,4),target=round(target,4),
                shares=shares,exit_time=exitts.isoformat(),exit_price=round(exitp,4),
                exit_reason=reason,gross_pnl=round(gross,2),net_pnl=round(net,2),
                r_multiple=round(net/RISK_DOLLARS,3),
            ))
            fired=True
            break
        prev_close=day[-1].c
    return out

def stats(trades:list[Trade]) -> dict[str,Any]:
    if not trades:
        return {"trades":0}
    pnl=[t.net_pnl for t in trades]
    wins=[x for x in pnl if x>0]; losses=[x for x in pnl if x<=0]
    gross_win=sum(wins); gross_loss=-sum(losses)
    equity=0; peak=0; maxdd=0
    for t in sorted(trades,key=lambda z:z.entry_time):
        equity+=t.net_pnl; peak=max(peak,equity); maxdd=max(maxdd,peak-equity)
    return {
        "trades":len(trades),
        "wins":len(wins),
        "losses":len(losses),
        "win_rate_pct":round(100*len(wins)/len(trades),1),
        "net_pnl":round(sum(pnl),2),
        "avg_pnl":round(statistics.mean(pnl),2),
        "expectancy_R":round(statistics.mean(t.r_multiple for t in trades),3),
        "profit_factor":round(gross_win/gross_loss,2) if gross_loss>0 else None,
        "max_drawdown":round(maxdd,2),
        "targets":sum(t.exit_reason=="TARGET_2R" for t in trades),
        "stops":sum(t.exit_reason=="STOP" for t in trades),
        "eod":sum(t.exit_reason=="EOD" for t in trades),
    }


def cluster_analysis(trades:list[Trade]) -> dict[str,Any]:
    if not trades:
        return {}
    def hour_bucket(t:Trade)->str:
        dt=datetime.fromisoformat(t.entry_time)
        h=dt.hour
        m=dt.minute
        mins=h*60+m
        if mins < 10*60: return "09:35-09:59"
        if mins < 11*60: return "10:00-10:59"
        if mins < 12*60: return "11:00-11:59"
        if mins < 13*60: return "12:00-12:59"
        if mins < 14*60: return "13:00-13:59"
        if mins < 15*60: return "14:00-14:59"
        return "15:00-15:30"

    def stop_pct(t:Trade)->float:
        return ((t.entry-t.stop)/t.entry)*100 if t.entry else 0

    time_stats={}
    for b in ["09:35-09:59","10:00-10:59","11:00-11:59","12:00-12:59","13:00-13:59","14:00-14:59","15:00-15:30"]:
        ts=[t for t in trades if hour_bucket(t)==b]
        if ts: time_stats[b]=stats(ts)

    engine_symbol={}
    keys=sorted({(t.engine,t.symbol) for t in trades})
    for e,s in keys:
        ts=[t for t in trades if t.engine==e and t.symbol==s]
        if len(ts)>=3:
            engine_symbol[f"{e}:{s}"]=stats(ts)

    stop_buckets={"<=0.4%":[],"0.4-0.8%":[],"0.8-1.2%":[],">1.2%":[]}
    for t in trades:
        p=stop_pct(t)
        if p<=0.4: stop_buckets["<=0.4%"].append(t)
        elif p<=0.8: stop_buckets["0.4-0.8%"].append(t)
        elif p<=1.2: stop_buckets["0.8-1.2%"].append(t)
        else: stop_buckets[">1.2%"].append(t)
    stop_stats={k:stats(v) for k,v in stop_buckets.items() if v}

    # Consecutive loss streaks in portfolio order.
    ordered=sorted(trades,key=lambda t:t.entry_time)
    streaks=[]; cur=[]
    for t in ordered:
        if t.net_pnl<=0:
            cur.append(t)
        else:
            if cur: streaks.append(cur); cur=[]
    if cur: streaks.append(cur)
    streaks.sort(key=len,reverse=True)
    worst_streaks=[]
    for st in streaks[:10]:
        worst_streaks.append({
            "length":len(st),
            "net_pnl":round(sum(t.net_pnl for t in st),2),
            "start":st[0].entry_time,
            "end":st[-1].entry_time,
            "symbols":[t.symbol for t in st],
            "engines":[t.engine for t in st],
        })

    weekday={}
    for n in range(5):
        ts=[t for t in trades if datetime.fromisoformat(t.entry_time).weekday()==n]
        if ts: weekday[["Mon","Tue","Wed","Thu","Fri"][n]]=stats(ts)

    winners=[t for t in trades if t.net_pnl>0]
    losers=[t for t in trades if t.net_pnl<=0]
    return {
        "by_time_of_day":time_stats,
        "by_stop_width":stop_stats,
        "by_weekday":weekday,
        "engine_symbol_combos":engine_symbol,
        "worst_loss_streaks":worst_streaks,
        "avg_quality_winners":round(statistics.mean(t.quality for t in winners),2) if winners else None,
        "avg_quality_losers":round(statistics.mean(t.quality for t in losers),2) if losers else None,
    }

async def run_backtest():
    global RESULT
    RESULT={"status":"running","started_at":datetime.now(UTC).isoformat()}
    print("[ttp-backtest] START",flush=True)
    all_trades=[]
    async with httpx.AsyncClient() as client:
        sem=asyncio.Semaphore(4)
        async def one(sym):
            async with sem:
                try:
                    bars=await fetch(client,sym)
                    ts=symbol_trades(sym,bars)
                    print(f"[ttp-backtest] {sym} bars={len(bars)} trades={len(ts)}",flush=True)
                    return ts
                except Exception as e:
                    print(f"[ttp-backtest] {sym} ERROR {type(e).__name__}: {e}",flush=True)
                    return []
        groups=await asyncio.gather(*(one(s) for s in UNIVERSE))
    raw=[t for g in groups for t in g]

    # Portfolio cap: at most 3 entries/day; rank simultaneous choices by quality.
    byday=defaultdict(list)
    for t in raw: byday[t.day].append(t)
    selected=[]
    for d,ts in byday.items():
        ts=sorted(ts,key=lambda x:(x.entry_time,-x.quality))
        chosen=[]
        for t in ts:
            if len(chosen)>=MAX_TRADES_DAY: break
            chosen.append(t)
        selected.extend(chosen)
    selected.sort(key=lambda x:x.entry_time)

    engine_stats={e:stats([t for t in selected if t.engine==e]) for e in
        ["MOMENTUM_RVOL","GAP_GO","ORB","VWAP_RECLAIM","HOD_BREAKOUT"]}
    symbol_stats={s:stats([t for t in selected if t.symbol==s]) for s in UNIVERSE}
    RESULT={
        "status":"complete",
        "completed_at":datetime.now(UTC).isoformat(),
        "period":"Yahoo 5m / 60d available history",
        "assumptions":{
            "next_bar_entry":True,"target_R":2.0,"planned_risk":RISK_DOLLARS,
            "max_trades_day":MAX_TRADES_DAY,"max_position_value":MAX_POSITION_VALUE,
            "slippage_each_side_pct":SLIPPAGE_PCT*100,
            "roundtrip_fee_per_share":FEE_PER_SHARE_ROUNDTRIP,
            "same_bar_stop_priority":True,
        },
        "overall":stats(selected),
        "by_engine":engine_stats,
        "by_symbol":symbol_stats,
        "clusters":cluster_analysis(selected),
        "sample_trades":[asdict(t) for t in selected[-20:]],
    }
    print("[ttp-backtest] RESULT "+json.dumps(RESULT,separators=(",",":")),flush=True)

@app.on_event("startup")
async def startup():
    global task
    task=asyncio.create_task(run_backtest())

@app.get("/health")
async def health():
    return {"status":"ok","backtest_status":RESULT.get("status")}

@app.get("/result")
async def result():
    return RESULT
