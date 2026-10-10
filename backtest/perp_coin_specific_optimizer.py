#!/usr/bin/env python3
"""Coin-specific perp strategy optimizer using public Hyperliquid data only.

This optimizer searches deliberately small, interpretable candidate sets for
BTC/ETH and the alt perps. It is designed to reduce over-trading and improve
payoff asymmetry, not maximize in-sample P&L.

Validation:
- 30d, 90d, 180d windows
- 180d is also split into three sequential 60d blocks
- selection rewards PF > 1 and positive expectancy across windows/blocks
- fees, slippage and funding are included
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
from typing import Optional

_SIBLING = Path(__file__).with_name("external_perp_reconstruction.py")
_spec = importlib.util.spec_from_file_location("external_perp_reconstruction", _SIBLING)
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

MS_DAY = 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class Candidate:
    name: str
    style: str
    fast_ema: int
    slow_ema: int
    lookback: int
    momentum_hours: int
    min_volume_ratio: float
    min_score: float
    stop_pct: float
    target_pct: float
    trail_activation_pct: float
    trail_pct: float
    max_hold_hours: int
    cooldown_hours: int
    risk_pct: float
    long_only: bool = False
    short_only: bool = False


def candidates_for(coin: str):
    if coin == "BTC":
        return [
            Candidate("btc_breakout_48", "breakout", 20, 50, 48, 24, 1.15, 0.20, 1.25, 2.50, 1.25, 0.75, 36, 6, 0.50),
            Candidate("btc_breakout_72", "breakout", 20, 50, 72, 24, 1.20, 0.25, 1.25, 3.00, 1.50, 0.85, 48, 8, 0.50),
            Candidate("btc_trend_pullback", "trend", 20, 50, 24, 12, 1.00, 0.25, 1.50, 3.00, 1.50, 0.85, 36, 6, 0.50),
            Candidate("btc_breakout_long", "breakout", 20, 50, 48, 24, 1.15, 0.20, 1.25, 2.75, 1.25, 0.75, 36, 6, 0.50, long_only=True),
            Candidate("btc_breakout_short", "breakout", 20, 50, 48, 24, 1.15, 0.20, 1.25, 2.75, 1.25, 0.75, 36, 6, 0.50, short_only=True),
        ]
    if coin == "ETH":
        return [
            Candidate("eth_breakout_36", "breakout", 16, 48, 36, 18, 1.15, 0.20, 1.40, 2.80, 1.30, 0.80, 30, 5, 0.50),
            Candidate("eth_breakout_48", "breakout", 20, 50, 48, 24, 1.20, 0.25, 1.40, 3.00, 1.40, 0.85, 36, 6, 0.50),
            Candidate("eth_trend_pullback", "trend", 12, 36, 24, 12, 1.00, 0.25, 1.50, 3.00, 1.40, 0.80, 30, 5, 0.50),
            Candidate("eth_breakout_long", "breakout", 16, 48, 36, 18, 1.15, 0.20, 1.40, 2.80, 1.30, 0.80, 30, 5, 0.50, long_only=True),
            Candidate("eth_breakout_short", "breakout", 16, 48, 36, 18, 1.15, 0.20, 1.40, 2.80, 1.30, 0.80, 30, 5, 0.50, short_only=True),
        ]

    # Alts: improve the best family mainly by throttling and confirmation.
    base = {
        "SOL": (8, 21, 6, 1.05, 0.18, 1.25, 2.25, 0.70, 0.45, 12, 2, 0.60),
        "AVAX": (8, 21, 6, 1.05, 0.18, 1.30, 2.40, 0.75, 0.50, 12, 3, 0.50),
        "XRP": (8, 21, 6, 1.05, 0.18, 1.20, 2.20, 0.65, 0.45, 12, 2, 0.50),
        "DOGE": (20, 50, 12, 1.00, 0.16, 0.75, 1.60, 0.25, 0.15, 10, 1, 0.60),
        "SHIB": (20, 50, 12, 1.00, 0.18, 0.60, 1.30, 0.20, 0.12, 8, 2, 0.35),
    }[coin]
    f, s, mom, vr, ms, st, tgt, act, tr, hold, cd, risk = base
    style = "trend"
    return [
        Candidate(f"{coin.lower()}_selective_a", style, f, s, 24, mom, vr, ms, st, tgt, act, tr, hold, cd, risk),
        Candidate(f"{coin.lower()}_selective_b", style, f, s, 36, mom, max(vr,1.05), ms+0.05, st, tgt+0.30, act, tr, hold+4, cd+1, risk),
        Candidate(f"{coin.lower()}_selective_c", style, f, s, 24, mom, max(vr,1.10), ms+0.10, max(0.5,st*0.85), tgt, act*0.9, max(0.08,tr*0.9), hold, cd+2, risk*0.8),
        Candidate(f"{coin.lower()}_long_only", style, f, s, 24, mom, vr, ms, st, tgt, act, tr, hold, cd, risk, long_only=True),
        Candidate(f"{coin.lower()}_short_only", style, f, s, 24, mom, vr, ms, st, tgt, act, tr, hold, cd, risk, short_only=True),
    ]


def rolling_mean(values, period):
    out=[None]*len(values); s=0.0
    for i,x in enumerate(values):
        s+=x
        if i>=period: s-=values[i-period]
        if i>=period-1: out[i]=s/period
    return out


def signals(bars, c: Candidate):
    closes=[b.c for b in bars]; volumes=[b.v for b in bars]
    efast=ema(closes,c.fast_ema); eslow=ema(closes,c.slow_ema)
    vmean=rolling_mean(volumes,24)
    rets=[0.0]
    for i in range(1,len(closes)):
        rets.append(math.log(closes[i]/closes[i-1]))
    vol24=rolling_std(rets,24)
    out=[0]*len(bars)

    for i in range(max(c.lookback,c.slow_ema,24),len(bars)):
        if efast[i] is None or eslow[i] is None or vmean[i] is None or not vol24[i]:
            continue
        vol=max(vol24[i]*math.sqrt(24),1e-6)
        vol_ratio=volumes[i]/max(vmean[i],1e-9)
        trend=(efast[i]/eslow[i]-1.0)/vol
        mom=(closes[i]/closes[i-c.momentum_hours]-1.0)/max(vol*math.sqrt(c.momentum_hours/24),1e-6)

        d=0
        if c.style=="breakout":
            hi=max(b.h for b in bars[i-c.lookback:i])
            lo=min(b.l for b in bars[i-c.lookback:i])
            if closes[i]>hi and trend>0 and vol_ratio>=c.min_volume_ratio:
                score=0.55*trend+0.45*mom
                if score>=c.min_score: d=1
            elif closes[i]<lo and trend<0 and vol_ratio>=c.min_volume_ratio:
                score=0.55*trend+0.45*mom
                if score<=-c.min_score: d=-1
        else:
            # Trend continuation with pullback tolerance: require aligned EMA
            # and momentum, but not a fresh channel breakout.
            score=0.60*trend+0.40*mom
            if score>=c.min_score and vol_ratio>=c.min_volume_ratio: d=1
            elif score<=-c.min_score and vol_ratio>=c.min_volume_ratio: d=-1

        if c.long_only and d<0: d=0
        if c.short_only and d>0: d=0
        out[i]=d
    return out


def run(coin, bars, c: Candidate):
    cfg=COINS[coin]
    start=cfg["capital"]; equity=start; peak=start; maxdd=0.0
    sig=signals(bars,c)
    pos: Optional[Position]=None; trades=[]; fees=funding=gross_total=0.0
    cooldown_until=-1

    for i,b in enumerate(bars):
        if pos is not None:
            fc=-pos.side*pos.notional*b.funding
            pos.funding_cash+=fc
            pos.hwm=max(pos.hwm,b.h); pos.lwm=min(pos.lwm,b.l)
            fav=((b.h/pos.entry_price)-1)*100 if pos.side==1 else ((pos.entry_price/b.l)-1)*100
            pos.mfe_pct=max(pos.mfe_pct,fav)
            adverse=((b.l/pos.entry_price)-1)*100 if pos.side==1 else ((pos.entry_price/b.h)-1)*100
            hold=i-pos.entry_idx
            exit_px=None; reason=None

            if adverse<=-c.stop_pct:
                raw=pos.entry_price*(1-c.stop_pct/100) if pos.side==1 else pos.entry_price*(1+c.stop_pct/100)
                exit_px=adverse_fill(raw,pos.side,opening=False); reason="STOP"
            else:
                favorable_close=((b.c/pos.entry_price)-1)*100*pos.side
                if favorable_close>=c.target_pct:
                    raw=pos.entry_price*(1+c.target_pct/100) if pos.side==1 else pos.entry_price*(1-c.target_pct/100)
                    exit_px=adverse_fill(raw,pos.side,opening=False); reason="TARGET"
                else:
                    if not pos.trailing_active and pos.mfe_pct>=c.trail_activation_pct:
                        pos.trailing_active=True
                        dist=pos.entry_price*c.trail_pct/100
                        pos.trail_stop=max(pos.entry_price,pos.hwm-dist) if pos.side==1 else min(pos.entry_price,pos.lwm+dist)
                    if pos.trailing_active:
                        dist=pos.entry_price*c.trail_pct/100
                        if pos.side==1:
                            pos.trail_stop=max(pos.trail_stop or pos.entry_price,pos.hwm-dist,pos.entry_price)
                            if b.l<=pos.trail_stop:
                                exit_px=adverse_fill(pos.trail_stop,pos.side,opening=False); reason="TRAIL"
                        else:
                            pos.trail_stop=min(pos.trail_stop or pos.entry_price,pos.lwm+dist,pos.entry_price)
                            if b.h>=pos.trail_stop:
                                exit_px=adverse_fill(pos.trail_stop,pos.side,opening=False); reason="TRAIL"
                if exit_px is None and hold>=c.max_hold_hours:
                    exit_px=adverse_fill(b.c,pos.side,opening=False); reason="HOLD"

            if exit_px is not None:
                gross=(exit_px-pos.entry_price)*pos.qty*pos.side
                exit_fee=abs(exit_px*pos.qty)*TAKER_FEE_BPS/10000
                net=gross-pos.entry_fee-exit_fee+pos.funding_cash
                equity+=net; fees+=pos.entry_fee+exit_fee; funding+=pos.funding_cash; gross_total+=gross
                trades.append((net,hold,reason))
                peak=max(peak,equity)
                if peak>0: maxdd=max(maxdd,(peak-equity)/peak*100)
                pos=None
                cooldown_until=i+c.cooldown_hours

        if pos is None and i>=max(c.lookback,c.slow_ema,24) and i>=cooldown_until:
            d=sig[i]
            if d==0: continue
            entry=adverse_fill(b.c,d,opening=True)
            risk_budget=max(equity,0)*c.risk_pct/100
            notional=min(risk_budget/max(c.stop_pct/100,1e-6),max(equity,0)*cfg["max_leverage"])
            if notional<=0: continue
            qty=notional/entry
            fee=notional*TAKER_FEE_BPS/10000
            pos=Position(d,i,entry,qty,notional,fee,entry,entry)

    if pos is not None:
        b=bars[-1]
        px=adverse_fill(b.c,pos.side,opening=False)
        gross=(px-pos.entry_price)*pos.qty*pos.side
        ef=abs(px*pos.qty)*TAKER_FEE_BPS/10000
        net=gross-pos.entry_fee-ef+pos.funding_cash
        equity+=net; fees+=pos.entry_fee+ef; funding+=pos.funding_cash; gross_total+=gross
        trades.append((net,len(bars)-1-pos.entry_idx,"END"))

    wins=[x for x in trades if x[0]>0]; losses=[x for x in trades if x[0]<=0]
    sw=sum(x[0] for x in wins); sl=abs(sum(x[0] for x in losses))
    pf=sw/sl if sl>0 else (999.0 if sw>0 else 0.0)
    net=equity-start
    return Result(
        coin=coin,strategy=c.name,start_equity=round(start,2),end_equity=round(equity,2),
        return_pct=round((equity/start-1)*100,2),max_drawdown_pct=round(maxdd,2),
        trades=len(trades),wins=len(wins),losses=len(losses),
        win_rate_pct=round(len(wins)/len(trades)*100,2) if trades else 0.0,
        profit_factor=round(pf,3),expectancy_usd=round(net/len(trades),2) if trades else 0.0,
        avg_trade_pct=round(net/start*100/len(trades),4) if trades else 0.0,
        avg_hold_hours=round(sum(x[1] for x in trades)/len(trades),2) if trades else 0.0,
        fees_usd=round(fees,2),funding_usd=round(funding,2),
        gross_pnl_usd=round(gross_total,2),net_pnl_usd=round(net,2),
    )


def score(results, blocks):
    vals=results+blocks
    if not vals: return -999
    good=sum(1 for r in vals if r.return_pct>0 and r.profit_factor>1)
    avg_ret=sum(r.return_pct for r in vals)/len(vals)
    avg_pf=sum(min(r.profit_factor,2.0) for r in vals)/len(vals)
    avg_dd=sum(r.max_drawdown_pct for r in vals)/len(vals)
    # Heavy penalty for zero-trade or negative-PF candidates.
    activity=sum(1 for r in vals if r.trades>=5)
    return round(avg_ret*0.4+(avg_pf-1)*35-avg_dd*0.25+good*5+activity*1.5,3)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default="artifacts/perp_coin_specific_optimizer")
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    detail=[]; winners=[]

    for coin,cfg in COINS.items():
        print(f"\n=== {coin} ===")
        bars=load_bars(cfg["hl"],180)
        if len(bars)<1000:
            print("insufficient history"); continue

        ranked=[]
        for cand in candidates_for(coin):
            windows=[]
            for days in (30,90,180):
                cutoff=bars[-1].ts-days*MS_DAY
                sub=[b for b in bars if b.ts>=cutoff]
                r=run(coin,sub,cand); windows.append(r)
                row=asdict(r); row["period"]=f"{days}d"; detail.append(row)

            # sequential 60d blocks
            blocks=[]
            start_ts=bars[-1].ts-180*MS_DAY
            for bi in range(3):
                lo=start_ts+bi*60*MS_DAY
                hi=lo+60*MS_DAY
                sub=[b for b in bars if lo<=b.ts<hi]
                if len(sub)>200:
                    r=run(coin,sub,cand); blocks.append(r)
                    row=asdict(r); row["period"]=f"block{bi+1}_60d"; detail.append(row)

            sc=score(windows,blocks)
            ranked.append((sc,cand,windows,blocks))
            print(cand.name, "score", sc, "windows", [(r.return_pct,r.profit_factor,r.trades) for r in windows])

        ranked.sort(key=lambda x:x[0],reverse=True)
        sc,cand,windows,blocks=ranked[0]
        winners.append({
            "coin":coin,"candidate":cand.name,"score":sc,
            "return_30d":windows[0].return_pct,"pf_30d":windows[0].profit_factor,
            "return_90d":windows[1].return_pct,"pf_90d":windows[1].profit_factor,
            "return_180d":windows[2].return_pct,"pf_180d":windows[2].profit_factor,
            "dd_180d":windows[2].max_drawdown_pct,"trades_180d":windows[2].trades,
            "positive_blocks":sum(1 for r in blocks if r.return_pct>0 and r.profit_factor>1),
            "blocks_tested":len(blocks),
        })

    if detail:
        with (out/"all_candidates.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(detail[0].keys())); w.writeheader(); w.writerows(detail)
    if winners:
        with (out/"winners.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(winners[0].keys())); w.writeheader(); w.writerows(winners)
        (out/"winners.json").write_text(json.dumps(winners,indent=2))
        lines=["# Coin-Specific Perpetual Optimizer","",
               "| Coin | Candidate | Score | 30d | 90d | 180d | PF 180d | DD 180d | 60d blocks + |",
               "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
        for w in winners:
            lines.append(f"| {w['coin']} | {w['candidate']} | {w['score']} | {w['return_30d']}% | {w['return_90d']}% | {w['return_180d']}% | {w['pf_180d']} | {w['dd_180d']}% | {w['positive_blocks']}/{w['blocks_tested']} |")
        (out/"report.md").write_text("\n".join(lines))


if __name__=="__main__":
    main()
