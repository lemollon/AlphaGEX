#!/usr/bin/env python3
"""Coin-specific perpetual strategy profile search using free Hyperliquid data.

Searches a compact, interpretable set of profiles per coin rather than a giant
parameter grid. The objective is robustness across 30/90/180 day windows after
fees, funding, slippage and risk sizing.

No CoinGlass or paid data required.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple

_BASE = Path(__file__).with_name("external_perp_reconstruction.py")
_spec = importlib.util.spec_from_file_location("external_perp_reconstruction", _BASE)
_ext = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _ext
_spec.loader.exec_module(_ext)

Bar = _ext.Bar
COINS = _ext.COINS
Result = _ext.Result
Position = _ext.Position
TAKER_FEE_BPS = _ext.TAKER_FEE_BPS
load_bars = _ext.load_bars
ema = _ext.ema
rolling_std = _ext.rolling_std
adverse_fill = _ext.adverse_fill


@dataclass(frozen=True)
class Profile:
    name: str
    family: str
    risk_pct: float
    score_threshold: float
    cooldown_hours: int
    max_hold_hours: int
    stop_pct: float
    target_pct: float
    trail_activation_pct: float
    trail_pct: float
    breakout_hours: int = 24
    volume_ratio: float = 1.0
    require_ema50_alignment: bool = False
    require_ema200_alignment: bool = False


def rolling_mean(values, period):
    out=[None]*len(values); s=0.0
    for i,x in enumerate(values):
        s += x
        if i >= period: s -= values[i-period]
        if i >= period-1: out[i]=s/period
    return out


def rolling_max(values, period):
    out=[None]*len(values)
    for i in range(period,len(values)):
        out[i]=max(values[i-period:i])
    return out


def rolling_min(values, period):
    out=[None]*len(values)
    for i in range(period,len(values)):
        out[i]=min(values[i-period:i])
    return out


def profiles_for(coin: str) -> List[Profile]:
    if coin in ("BTC","ETH"):
        return [
            Profile("breakout24_strict","breakout",0.50,0.20,12,24,1.50,3.00,1.25,0.75,24,1.20,True,False),
            Profile("breakout48_trend","breakout",0.50,0.20,18,30,1.50,3.50,1.50,0.80,48,1.15,True,False),
            Profile("breakout72_trend","breakout",0.40,0.20,24,36,1.75,4.00,1.75,1.00,72,1.10,True,False),
            Profile("breakout48_macro","breakout",0.40,0.25,24,36,1.50,4.00,1.50,0.80,48,1.20,True,True),
            Profile("trend_pullback","trend_pullback",0.50,0.22,12,24,1.50,3.00,1.25,0.75,24,1.0,True,False),
            Profile("slow_trend_strict","slow_trend",0.50,0.25,12,30,1.75,3.50,1.50,0.85,24,1.0,True,False),
        ]
    if coin in ("SOL","AVAX","XRP"):
        return [
            Profile("fast_strict","fast_trend",0.60,0.20,6,12,1.50,2.50,0.75,0.45,24,1.0,True,False),
            Profile("fast_stricter","fast_trend",0.50,0.30,12,16,1.50,3.00,0.85,0.50,24,1.0,True,False),
            Profile("fast_macro","fast_trend",0.50,0.25,12,18,1.75,3.50,1.00,0.60,24,1.0,True,True),
            Profile("breakout24","breakout",0.60,0.20,8,18,1.50,3.00,0.80,0.50,24,1.10,True,False),
            Profile("breakout48","breakout",0.50,0.20,12,24,1.75,3.50,1.00,0.60,48,1.10,True,False),
            Profile("trend_pullback","trend_pullback",0.50,0.22,8,18,1.50,3.00,0.85,0.50,24,1.0,True,False),
        ]
    return [
        Profile("slow_baseline","slow_trend",0.80,0.08,1,12,0.75 if coin=="DOGE" else 0.50,1.50,0.20 if coin=="DOGE" else 0.15,0.10 if coin=="DOGE" else 0.05),
        Profile("slow_cooldown2","slow_trend",0.70,0.12,2,12,0.75,1.75,0.25,0.12),
        Profile("slow_cooldown4","slow_trend",0.60,0.16,4,16,1.00,2.00,0.30,0.15),
        Profile("slow_strict","slow_trend",0.50,0.22,6,18,1.00,2.50,0.40,0.20,24,1.0,True,False),
        Profile("breakout24","breakout",0.50,0.18,6,18,1.00,2.50,0.40,0.20,24,1.10,True,False),
        Profile("breakout48","breakout",0.40,0.18,8,24,1.25,3.00,0.50,0.25,48,1.05,True,False),
    ]


def signals(bars: List[Bar], p: Profile) -> List[Tuple[int,float]]:
    closes=[b.c for b in bars]; highs=[b.h for b in bars]; lows=[b.l for b in bars]; vols=[b.v for b in bars]
    n=len(bars)
    out=[(0,0.0)]*n
    e8,e20,e21,e50,e200=ema(closes,8),ema(closes,20),ema(closes,21),ema(closes,50),ema(closes,200)
    rets=[0.0]+[math.log(closes[i]/closes[i-1]) for i in range(1,n)]
    vol24=rolling_std(rets,24)
    vmean=rolling_mean(vols,24)
    hi=rolling_max(highs,p.breakout_hours)
    lo=rolling_min(lows,p.breakout_hours)

    for i in range(n):
        if i < max(200,p.breakout_hours,72): continue
        hv=max((vol24[i] or 0)*math.sqrt(24),1e-6)
        direction=0; score=0.0

        if p.family=="breakout":
            vr=vols[i]/max(vmean[i] or 0,1e-9)
            if hi[i] and closes[i] > hi[i] and vr >= p.volume_ratio:
                direction=1
                score=((closes[i]/hi[i])-1)/hv + 0.35*(vr-1)
            elif lo[i] and closes[i] < lo[i] and vr >= p.volume_ratio:
                direction=-1
                score=-(((lo[i]/closes[i])-1)/hv + 0.35*(vr-1))
            else:
                continue

        elif p.family=="fast_trend":
            r6=closes[i]/closes[i-6]-1
            r24=closes[i]/closes[i-24]-1
            trend=e8[i]/e21[i]-1
            score=0.50*(trend/hv)+0.30*(r6/max(hv/2,1e-6))+0.20*(r24/hv)
            direction=1 if score>p.score_threshold else -1 if score<-p.score_threshold else 0

        elif p.family=="slow_trend":
            r24=closes[i]/closes[i-24]-1
            r72=closes[i]/closes[i-72]-1
            trend=e20[i]/e50[i]-1
            score=0.50*(trend/hv)+0.30*(r24/hv)+0.20*(r72/max(hv*math.sqrt(3),1e-6))
            direction=1 if score>p.score_threshold else -1 if score<-p.score_threshold else 0

        elif p.family=="trend_pullback":
            trend=e20[i]/e50[i]-1
            r24=closes[i]/closes[i-24]-1
            distance=(closes[i]/e20[i]-1)
            base=0.6*(trend/hv)+0.4*(r24/hv)
            # enter only on a modest pullback toward EMA20 within an established trend
            if base > p.score_threshold and -0.5*hv <= distance <= 0.15*hv:
                direction=1; score=base
            elif base < -p.score_threshold and -0.15*hv <= distance <= 0.5*hv:
                direction=-1; score=base
            else:
                continue

        if direction==0: continue
        if p.require_ema50_alignment:
            if direction==1 and closes[i] <= e50[i]: continue
            if direction==-1 and closes[i] >= e50[i]: continue
        if p.require_ema200_alignment:
            if e200[i] is None: continue
            if direction==1 and closes[i] <= e200[i]: continue
            if direction==-1 and closes[i] >= e200[i]: continue
        if abs(score) < p.score_threshold and p.family=="breakout":
            continue
        out[i]=(direction,score)
    return out


def run_profile(coin: str, bars: List[Bar], p: Profile) -> Result:
    cfg=COINS[coin]; start=cfg["capital"]; equity=start; peak=start; maxdd=0.0
    sig=signals(bars,p); pos: Optional[Position]=None
    trades=[]; fees=funding=gross_total=0.0; next_entry_idx=0

    for i,b in enumerate(bars):
        if pos:
            pos.funding_cash += -pos.side*pos.notional*b.funding
            fav=((b.h/pos.entry_price)-1)*100 if pos.side==1 else ((pos.entry_price/b.l)-1)*100
            pos.mfe_pct=max(pos.mfe_pct,fav); pos.hwm=max(pos.hwm,b.h); pos.lwm=min(pos.lwm,b.l)
            hold=i-pos.entry_idx
            adverse=((b.l/pos.entry_price)-1)*100 if pos.side==1 else ((pos.entry_price/b.h)-1)*100
            pnl_pct=((b.c/pos.entry_price)-1)*100*pos.side
            exit_price=None
            if adverse <= -p.stop_pct:
                raw=pos.entry_price*(1-p.stop_pct/100) if pos.side==1 else pos.entry_price*(1+p.stop_pct/100)
                exit_price=adverse_fill(raw,pos.side,False)
            elif pnl_pct >= p.target_pct:
                raw=pos.entry_price*(1+p.target_pct/100) if pos.side==1 else pos.entry_price*(1-p.target_pct/100)
                exit_price=adverse_fill(raw,pos.side,False)
            else:
                if not pos.trailing_active and pos.mfe_pct >= p.trail_activation_pct:
                    pos.trailing_active=True
                    d=pos.entry_price*p.trail_pct/100
                    pos.trail_stop=max(pos.entry_price,pos.hwm-d) if pos.side==1 else min(pos.entry_price,pos.lwm+d)
                if pos.trailing_active:
                    d=pos.entry_price*p.trail_pct/100
                    if pos.side==1:
                        pos.trail_stop=max(pos.trail_stop or pos.entry_price,pos.hwm-d,pos.entry_price)
                        if b.l <= pos.trail_stop: exit_price=adverse_fill(pos.trail_stop,pos.side,False)
                    else:
                        pos.trail_stop=min(pos.trail_stop or pos.entry_price,pos.lwm+d,pos.entry_price)
                        if b.h >= pos.trail_stop: exit_price=adverse_fill(pos.trail_stop,pos.side,False)
                if exit_price is None and hold >= p.max_hold_hours:
                    exit_price=adverse_fill(b.c,pos.side,False)
            if exit_price is not None:
                gross=(exit_price-pos.entry_price)*pos.qty*pos.side
                exit_fee=abs(exit_price*pos.qty)*TAKER_FEE_BPS/10000
                net=gross-pos.entry_fee-exit_fee+pos.funding_cash
                equity+=net; gross_total+=gross; fees+=pos.entry_fee+exit_fee; funding+=pos.funding_cash
                trades.append({"net":net,"hold":hold})
                peak=max(peak,equity)
                if peak>0: maxdd=max(maxdd,(peak-equity)/peak*100)
                next_entry_idx=i+p.cooldown_hours
                pos=None

        if pos is None and i >= next_entry_idx:
            direction,score=sig[i]
            if direction==0: continue
            entry=adverse_fill(b.c,direction,True)
            risk_budget=max(equity,0)*p.risk_pct/100
            notional=min(risk_budget/max(p.stop_pct/100,1e-6),max(equity,0)*cfg["max_leverage"])
            if notional<=0: continue
            qty=notional/entry; fee=notional*TAKER_FEE_BPS/10000
            pos=Position(direction,i,entry,qty,notional,fee,entry,entry)

    if pos:
        b=bars[-1]; ep=adverse_fill(b.c,pos.side,False)
        gross=(ep-pos.entry_price)*pos.qty*pos.side
        ef=abs(ep*pos.qty)*TAKER_FEE_BPS/10000
        net=gross-pos.entry_fee-ef+pos.funding_cash
        equity+=net; gross_total+=gross; fees+=pos.entry_fee+ef; funding+=pos.funding_cash
        trades.append({"net":net,"hold":len(bars)-1-pos.entry_idx})

    wins=[t for t in trades if t["net"]>0]; losses=[t for t in trades if t["net"]<=0]
    sw=sum(t["net"] for t in wins); sl=abs(sum(t["net"] for t in losses))
    pf=sw/sl if sl>0 else (999 if sw>0 else 0)
    net=equity-start
    return Result(
        coin=coin,strategy=p.name,start_equity=round(start,2),end_equity=round(equity,2),
        return_pct=round((equity/start-1)*100,2),max_drawdown_pct=round(maxdd,2),
        trades=len(trades),wins=len(wins),losses=len(losses),
        win_rate_pct=round(len(wins)/len(trades)*100,2) if trades else 0.0,
        profit_factor=round(pf,3),expectancy_usd=round(net/len(trades),2) if trades else 0.0,
        avg_trade_pct=round(net/start*100/len(trades),4) if trades else 0.0,
        avg_hold_hours=round(sum(t["hold"] for t in trades)/len(trades),2) if trades else 0.0,
        fees_usd=round(fees,2),funding_usd=round(funding,2),gross_pnl_usd=round(gross_total,2),net_pnl_usd=round(net,2)
    )


def score(rows: List[Result]) -> float:
    if not rows: return -999
    positive=sum(1 for r in rows if r.return_pct>0 and r.profit_factor>1)
    s=sum(r.return_pct*0.35 + (min(r.profit_factor,2)-1)*30 - r.max_drawdown_pct*0.25 for r in rows)/len(rows)
    s += positive*12
    if positive<2: s -= 15
    return round(s,3)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--windows",default="30,90,180,365"); ap.add_argument("--out",default="artifacts/perp_coin_profile_search")
    args=ap.parse_args(); windows=sorted(int(x) for x in args.windows.split(",")); maxd=max(windows)
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    allrows=[]; winners=[]
    for coin,cfg in COINS.items():
        print("FETCH",coin)
        bars=load_bars(cfg["hl"],maxd)
        ranked=[]
        for p in profiles_for(coin):
            rows=[]
            for d in windows:
                cutoff=bars[-1].ts-d*24*60*60*1000
                sub=[b for b in bars if b.ts>=cutoff]
                r=run_profile(coin,sub,p); rows.append(r)
                row=asdict(r); row["window_days"]=d; allrows.append(row)
                print(coin,p.name,d,r.return_pct,r.profit_factor,r.max_drawdown_pct,r.trades)
            ranked.append((score(rows),p,rows))
        ranked.sort(key=lambda x:x[0],reverse=True)
        sc,p,rows=ranked[0]
        winners.append({
            "coin":coin,"profile":p.name,"family":p.family,"score":sc,
            "positive_windows":sum(1 for r in rows if r.return_pct>0 and r.profit_factor>1),
            "return_30d":next(r.return_pct for r,d in zip(rows,windows) if d==30),
            "return_90d":next(r.return_pct for r,d in zip(rows,windows) if d==90),
            "return_180d":next(r.return_pct for r,d in zip(rows,windows) if d==180),
            "return_365d":next((r.return_pct for r,d in zip(rows,windows) if d==365),None),
            "pf_180d":next(r.profit_factor for r,d in zip(rows,windows) if d==180),
            "pf_365d":next((r.profit_factor for r,d in zip(rows,windows) if d==365),None),
            "dd_180d":next(r.max_drawdown_pct for r,d in zip(rows,windows) if d==180),
            "dd_365d":next((r.max_drawdown_pct for r,d in zip(rows,windows) if d==365),None),
            "trades_180d":next(r.trades for r,d in zip(rows,windows) if d==180),
            "trades_365d":next((r.trades for r,d in zip(rows,windows) if d==365),None),
            "runner_up":ranked[1][1].name,
        })
    with (out/"all_results.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(allrows[0].keys())); w.writeheader(); w.writerows(allrows)
    with (out/"winners.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(winners[0].keys())); w.writeheader(); w.writerows(winners)
    (out/"winners.json").write_text(json.dumps(winners,indent=2))
    lines=["# Coin-Specific Selective Strategy Search","",
           "| Coin | Profile | Family | +Windows | 30d | 90d | 180d | 365d | PF 365d | DD 365d | Trades 365d |",
           "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for x in winners:
        lines.append(f"| {x['coin']} | {x['profile']} | {x['family']} | {x['positive_windows']}/{len(windows)} | {x['return_30d']}% | {x['return_90d']}% | {x['return_180d']}% | {x['return_365d']}% | {x['pf_365d']:.2f} | {x['dd_365d']}% | {x['trades_365d']} |")
    (out/"report.md").write_text("\n".join(lines))


if __name__=="__main__":
    main()
