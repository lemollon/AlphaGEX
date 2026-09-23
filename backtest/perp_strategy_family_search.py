#!/usr/bin/env python3
"""Search strategy families per perpetual coin using public Hyperliquid data.

Families:
- slow_trend: 20/50 EMA + 24h/72h momentum
- fast_trend: 8/21 EMA + 6h/24h momentum
- breakout: 24h channel breakout + volume confirmation
- mean_reversion: 20h z-score fade with trend veto
- funding_reversion: extreme funding fade with momentum confirmation
- hybrid_meme: fast momentum + funding pressure, designed for DOGE/SHIB-like behavior

The goal is robustness, not maximum in-sample return. We evaluate 30/90/180 day
windows and report a robustness score that rewards positive expectancy and PF
across windows while penalizing drawdown and sign instability.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import importlib.util
import sys

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
SLIPPAGE_BPS = _ext.SLIPPAGE_BPS
MAX_HOLD_HOURS = _ext.MAX_HOLD_HOURS
load_bars = _ext.load_bars
ema = _ext.ema
rolling_std = _ext.rolling_std
adverse_fill = _ext.adverse_fill

FAMILIES = (
    "slow_trend",
    "fast_trend",
    "breakout",
    "mean_reversion",
    "funding_reversion",
    "hybrid_meme",
)

FAMILY_RISK = {
    "slow_trend": 1.0,
    "fast_trend": 0.8,
    "breakout": 1.0,
    "mean_reversion": 0.7,
    "funding_reversion": 0.5,
    "hybrid_meme": 0.8,
}

FAMILY_HOLD = {
    "slow_trend": 24,
    "fast_trend": 12,
    "breakout": 18,
    "mean_reversion": 8,
    "funding_reversion": 8,
    "hybrid_meme": 10,
}


def rolling_mean(values: List[float], period: int) -> List[Optional[float]]:
    out = [None] * len(values)
    if period <= 0:
        return out
    s = 0.0
    for i, x in enumerate(values):
        s += x
        if i >= period:
            s -= values[i-period]
        if i >= period - 1:
            out[i] = s / period
    return out


def rolling_max(values: List[float], period: int) -> List[Optional[float]]:
    out = [None] * len(values)
    for i in range(period, len(values)):
        out[i] = max(values[i-period:i])
    return out


def rolling_min(values: List[float], period: int) -> List[Optional[float]]:
    out = [None] * len(values)
    for i in range(period, len(values)):
        out[i] = min(values[i-period:i])
    return out


def signal_family(bars: List[Bar], family: str) -> List[Tuple[int, str, float]]:
    closes = [b.c for b in bars]
    volumes = [b.v for b in bars]
    n = len(bars)
    out = [(0, "LOW", 0.0)] * n

    e8, e20, e21, e50 = ema(closes, 8), ema(closes, 20), ema(closes, 21), ema(closes, 50)
    rets = [0.0]
    for i in range(1, n):
        rets.append(math.log(closes[i] / closes[i-1]))
    vol24 = rolling_std(rets, 24)
    mean20 = rolling_mean(closes, 20)
    std20 = rolling_std(closes, 20)
    vol_mean24 = rolling_mean(volumes, 24)
    high24 = rolling_max([b.h for b in bars], 24)
    low24 = rolling_min([b.l for b in bars], 24)

    for i in range(n):
        if i < 72:
            continue
        vol = max((vol24[i] or 0) * math.sqrt(24), 1e-6)
        funding = bars[i].funding
        score = 0.0
        direction = 0

        if family == "slow_trend":
            if e20[i] is None or e50[i] is None:
                continue
            r24 = closes[i] / closes[i-24] - 1.0
            r72 = closes[i] / closes[i-72] - 1.0
            trend = e20[i] / e50[i] - 1.0
            score = 0.45*(trend/vol) + 0.35*(r24/vol) + 0.20*(r72/(vol*math.sqrt(3)))
            score -= max(-0.5, min(0.5, funding*2500.0))*0.20
            direction = 1 if score > 0.08 else -1 if score < -0.08 else 0

        elif family == "fast_trend":
            if e8[i] is None or e21[i] is None:
                continue
            r6 = closes[i] / closes[i-6] - 1.0
            r24 = closes[i] / closes[i-24] - 1.0
            trend = e8[i] / e21[i] - 1.0
            score = 0.50*(trend/vol) + 0.30*(r6/max(vol/math.sqrt(4),1e-6)) + 0.20*(r24/vol)
            direction = 1 if score > 0.10 else -1 if score < -0.10 else 0

        elif family == "breakout":
            if high24[i] is None or low24[i] is None or vol_mean24[i] is None:
                continue
            volume_ratio = volumes[i] / max(vol_mean24[i], 1e-9)
            if closes[i] > high24[i] and volume_ratio >= 1.05:
                direction = 1
                score = min(2.0, ((closes[i]/high24[i]-1.0)/vol) + 0.5*(volume_ratio-1.0))
            elif closes[i] < low24[i] and volume_ratio >= 1.05:
                direction = -1
                score = -min(2.0, ((low24[i]/closes[i]-1.0)/vol) + 0.5*(volume_ratio-1.0))
            else:
                continue

        elif family == "mean_reversion":
            if mean20[i] is None or std20[i] is None or std20[i] <= 0 or e20[i] is None or e50[i] is None:
                continue
            z = (closes[i] - mean20[i]) / std20[i]
            trend_strength = abs(e20[i]/e50[i]-1.0) / vol
            # Only fade when the higher-timeframe trend is weak.
            if trend_strength > 0.35:
                continue
            if z <= -1.5:
                direction = 1
                score = min(2.0, abs(z)/2.0)
            elif z >= 1.5:
                direction = -1
                score = -min(2.0, abs(z)/2.0)
            else:
                continue

        elif family == "funding_reversion":
            r6 = closes[i]/closes[i-6]-1.0
            if funding >= 0.00012 and r6 <= 0.0:
                direction = -1
                score = -min(2.0, abs(funding)/0.00012)
            elif funding <= -0.00012 and r6 >= 0.0:
                direction = 1
                score = min(2.0, abs(funding)/0.00012)
            else:
                continue

        elif family == "hybrid_meme":
            if e8[i] is None or e21[i] is None:
                continue
            r3 = closes[i]/closes[i-3]-1.0
            r12 = closes[i]/closes[i-12]-1.0
            trend = e8[i]/e21[i]-1.0
            momentum = 0.45*(trend/vol) + 0.35*(r3/max(vol/math.sqrt(8),1e-6)) + 0.20*(r12/max(vol/math.sqrt(2),1e-6))
            funding_pressure = max(-0.6, min(0.6, funding*3000.0))
            score = momentum - 0.15*funding_pressure
            direction = 1 if score > 0.12 else -1 if score < -0.12 else 0

        a = abs(score)
        conf = "HIGH" if a >= 0.75 else "MEDIUM" if a >= 0.35 else "LOW"
        out[i] = (direction, conf, score)

    return out


def run_family(coin: str, bars: List[Bar], family: str) -> Result:
    cfg = COINS[coin]
    start_equity = cfg["capital"]
    equity = start_equity
    peak = equity
    max_dd = 0.0
    sigs = signal_family(bars, family)
    risk_pct = FAMILY_RISK[family]
    max_hold = FAMILY_HOLD[family]

    # exits adapted to family behavior
    activation = cfg["activation"]
    trail = cfg["trail"]
    max_loss = cfg["max_loss"]
    if family == "mean_reversion":
        activation = max(0.25, activation * 0.65)
        trail = max(0.15, trail * 0.75)
        max_loss = min(max_loss, 1.5)
    elif family == "fast_trend":
        activation = max(0.25, activation * 0.75)
        trail = max(0.15, trail * 0.75)
        max_loss = min(max_loss, 2.0)
    elif family == "breakout":
        activation = max(0.4, activation)
        trail = max(0.25, trail)
    elif family == "funding_reversion":
        activation = max(0.2, activation * 0.5)
        trail = max(0.15, trail * 0.6)
        max_loss = min(max_loss, 1.25)
    elif family == "hybrid_meme":
        activation = max(0.15, activation)
        trail = max(0.08, trail)
        max_loss = min(max_loss, 1.25)

    pos: Optional[Position] = None
    trades = []
    fees_total = funding_total = gross_total = 0.0

    for i, bar in enumerate(bars):
        if pos is not None:
            fc = -pos.side * pos.notional * bar.funding
            pos.funding_cash += fc
            fav = ((bar.h/pos.entry_price)-1)*100 if pos.side == 1 else ((pos.entry_price/bar.l)-1)*100
            pos.mfe_pct = max(pos.mfe_pct, fav)
            pos.hwm = max(pos.hwm, bar.h)
            pos.lwm = min(pos.lwm, bar.l)
            hold = i - pos.entry_idx
            adverse = ((bar.l/pos.entry_price)-1)*100 if pos.side == 1 else ((pos.entry_price/bar.h)-1)*100
            exit_price = None
            reason = None

            if adverse <= -max_loss:
                raw = pos.entry_price*(1-max_loss/100) if pos.side == 1 else pos.entry_price*(1+max_loss/100)
                exit_price = adverse_fill(raw, pos.side, opening=False)
                reason = "MAX_LOSS"
            else:
                if not pos.trailing_active and pos.mfe_pct >= activation:
                    pos.trailing_active = True
                    dist = pos.entry_price*trail/100
                    pos.trail_stop = max(pos.entry_price, pos.hwm-dist) if pos.side == 1 else min(pos.entry_price, pos.lwm+dist)
                if pos.trailing_active:
                    dist = pos.entry_price*trail/100
                    if pos.side == 1:
                        pos.trail_stop = max(pos.trail_stop or pos.entry_price, pos.hwm-dist, pos.entry_price)
                        if bar.l <= pos.trail_stop:
                            exit_price = adverse_fill(pos.trail_stop, pos.side, opening=False)
                            reason = "TRAIL"
                    else:
                        pos.trail_stop = min(pos.trail_stop or pos.entry_price, pos.lwm+dist, pos.entry_price)
                        if bar.h >= pos.trail_stop:
                            exit_price = adverse_fill(pos.trail_stop, pos.side, opening=False)
                            reason = "TRAIL"
                if exit_price is None and hold >= max_hold:
                    exit_price = adverse_fill(bar.c, pos.side, opening=False)
                    reason = "MAX_HOLD"

            if exit_price is not None:
                gross = (exit_price-pos.entry_price)*pos.qty*pos.side
                exit_fee = abs(exit_price*pos.qty)*TAKER_FEE_BPS/10000.0
                net = gross-pos.entry_fee-exit_fee+pos.funding_cash
                equity += net
                gross_total += gross
                fees_total += pos.entry_fee+exit_fee
                funding_total += pos.funding_cash
                trades.append({"net":net,"hold":hold})
                peak = max(peak,equity)
                if peak > 0:
                    max_dd = max(max_dd,(peak-equity)/peak*100)
                pos = None

        if pos is None and i >= 72:
            direction, conf, score = sigs[i]
            if direction == 0 or conf == "LOW":
                continue
            entry = adverse_fill(bar.c,direction,opening=True)
            risk_budget = max(equity,0)*risk_pct/100
            stop_fraction = max_loss/100
            desired_notional = risk_budget/max(stop_fraction,1e-6)
            max_notional = max(equity,0)*cfg["max_leverage"]
            notional = min(desired_notional,max_notional)
            if notional <= 0:
                continue
            qty = notional/entry
            fee = notional*TAKER_FEE_BPS/10000
            pos = Position(direction,i,entry,qty,notional,fee,entry,entry)

    if pos is not None:
        bar = bars[-1]
        exit_price=adverse_fill(bar.c,pos.side,opening=False)
        gross=(exit_price-pos.entry_price)*pos.qty*pos.side
        exit_fee=abs(exit_price*pos.qty)*TAKER_FEE_BPS/10000
        net=gross-pos.entry_fee-exit_fee+pos.funding_cash
        equity+=net
        gross_total+=gross
        fees_total+=pos.entry_fee+exit_fee
        funding_total+=pos.funding_cash
        trades.append({"net":net,"hold":len(bars)-1-pos.entry_idx})

    wins=[t for t in trades if t["net"]>0]
    losses=[t for t in trades if t["net"]<=0]
    sw=sum(t["net"] for t in wins)
    sl=abs(sum(t["net"] for t in losses))
    pf=sw/sl if sl>0 else (999.0 if sw>0 else 0.0)
    net=equity-start_equity
    return Result(
        coin=coin,strategy=family,start_equity=round(start_equity,2),end_equity=round(equity,2),
        return_pct=round((equity/start_equity-1)*100,2),max_drawdown_pct=round(max_dd,2),
        trades=len(trades),wins=len(wins),losses=len(losses),
        win_rate_pct=round(len(wins)/len(trades)*100,2) if trades else 0.0,
        profit_factor=round(pf,3),
        expectancy_usd=round(net/len(trades),2) if trades else 0.0,
        avg_trade_pct=round(net/start_equity*100/len(trades),4) if trades else 0.0,
        avg_hold_hours=round(sum(t["hold"] for t in trades)/len(trades),2) if trades else 0.0,
        fees_usd=round(fees_total,2),funding_usd=round(funding_total,2),
        gross_pnl_usd=round(gross_total,2),net_pnl_usd=round(net,2),
    )


def robustness(rows: List[Result]) -> float:
    if not rows:
        return -999.0
    # reward positive return + PF across windows; punish DD and sign instability
    score = 0.0
    pos_windows = 0
    for r in rows:
        score += r.return_pct * 0.35
        score += (min(r.profit_factor, 2.0)-1.0)*25.0
        score -= r.max_drawdown_pct * 0.20
        if r.return_pct > 0 and r.profit_factor > 1:
            pos_windows += 1
    score += pos_windows * 10.0
    if pos_windows == 0:
        score -= 20.0
    return round(score/len(rows),3)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--max-days",type=int,default=180)
    ap.add_argument("--windows",default="30,90,180")
    ap.add_argument("--out",default="artifacts/perp_strategy_family_search")
    args=ap.parse_args()
    windows=sorted(set(int(x) for x in args.windows.split(",") if x.strip()))
    max_days=max(max(windows),args.max_days)
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)

    all_rows=[]
    summary=[]
    for coin,cfg in COINS.items():
        print(f"fetch {coin} {max_days}d")
        bars=load_bars(cfg["hl"],max_days)
        if len(bars)<200:
            print(" insufficient"); continue
        by_family={}
        for family in FAMILIES:
            family_rows=[]
            for days in windows:
                cutoff=bars[-1].ts-days*24*60*60*1000
                sub=[b for b in bars if b.ts>=cutoff]
                r=run_family(coin,sub,family)
                d=asdict(r); d["window_days"]=days
                all_rows.append(d)
                family_rows.append(r)
                print(f" {family:18s} {days:3d}d ret={r.return_pct:+7.2f}% PF={r.profit_factor:5.2f} DD={r.max_drawdown_pct:5.1f}% n={r.trades}")
            by_family[family]=(robustness(family_rows),family_rows)

        ranked=sorted(by_family.items(), key=lambda kv: kv[1][0], reverse=True)
        best_name,(best_score,best_rows)=ranked[0]
        second_name,(second_score,second_rows)=ranked[1]
        summary.append({
            "coin":coin,
            "best_family":best_name,
            "robustness_score":best_score,
            "second_family":second_name,
            "second_score":second_score,
            "positive_windows":sum(1 for r in best_rows if r.return_pct>0 and r.profit_factor>1),
            "return_30d":next((r.return_pct for r in best_rows if len(best_rows) and windows[best_rows.index(r)]==30),None) if 30 in windows else None,
            "return_90d":next((r.return_pct for r in best_rows if len(best_rows) and windows[best_rows.index(r)]==90),None) if 90 in windows else None,
            "return_180d":next((r.return_pct for r in best_rows if len(best_rows) and windows[best_rows.index(r)]==180),None) if 180 in windows else None,
        })

    if all_rows:
        with (out/"all_results.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(all_rows[0].keys())); w.writeheader(); w.writerows(all_rows)
        (out/"all_results.json").write_text(json.dumps(all_rows,indent=2))
    if summary:
        with (out/"coin_winners.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(summary[0].keys())); w.writeheader(); w.writerows(summary)
        (out/"coin_winners.json").write_text(json.dumps(summary,indent=2))

        lines=[
            "# Per-Coin Strategy Family Search","",
            "| Coin | Best Family | Robustness | Positive Windows | 30d | 90d | 180d | Runner-up |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
        for s in summary:
            lines.append(
                f"| {s['coin']} | {s['best_family']} | {s['robustness_score']:.2f} | "
                f"{s['positive_windows']}/3 | {s['return_30d']}% | {s['return_90d']}% | {s['return_180d']}% | {s['second_family']} |"
            )
        (out/"report.md").write_text("\n".join(lines))


if __name__=="__main__":
    main()
