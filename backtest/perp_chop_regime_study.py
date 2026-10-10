#!/usr/bin/env python3
"""365-day chop/regime study for AlphaGEX perpetuals using public Hyperliquid data."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import List, Optional

_BASE = Path(__file__).with_name("perp_coin_profile_search.py")
_spec = importlib.util.spec_from_file_location("perp_coin_profile_search", _BASE)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

Bar=_mod.Bar
COINS=_mod.COINS
Position=_mod.Position
TAKER_FEE_BPS=_mod.TAKER_FEE_BPS
load_bars=_mod.load_bars
ema=_mod.ema
rolling_std=_mod.rolling_std
adverse_fill=_mod.adverse_fill
profiles_for=_mod.profiles_for
signals=_mod.signals

BEST_PROFILE = {
    "BTC": "breakout48_macro",
    "ETH": "breakout24_strict",
    "SOL": "breakout24",
    "AVAX": "breakout48",
    "XRP": "fast_macro",
    "DOGE": "slow_strict",
    "SHIB": "breakout24",
}

def get_profile(coin):
    for p in profiles_for(coin):
        if p.name == BEST_PROFILE[coin]:
            return p
    raise KeyError((coin, BEST_PROFILE[coin]))

def rolling_mean(values, period):
    out=[None]*len(values); s=0.0
    for i,x in enumerate(values):
        s += x
        if i>=period: s -= values[i-period]
        if i>=period-1: out[i]=s/period
    return out

def rolling_percentile_rank(values, lookback):
    out=[None]*len(values)
    for i,v in enumerate(values):
        if i < lookback or v is None:
            continue
        hist=[x for x in values[i-lookback:i] if x is not None]
        if not hist:
            continue
        out[i]=sum(1 for x in hist if x <= v)/len(hist)
    return out

def classify_regimes(bars: List[Bar]):
    closes=[b.c for b in bars]
    highs=[b.h for b in bars]
    lows=[b.l for b in bars]
    vols=[b.v for b in bars]
    rets=[0.0]+[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))]
    rv24=rolling_std(rets,24)
    rv72=rolling_std(rets,72)
    e20=ema(closes,20)
    e50=ema(closes,50)
    vmean24=rolling_mean(vols,24)

    range24=[None]*len(bars)
    ema_spread=[None]*len(bars)
    vol_ratio=[None]*len(bars)
    for i in range(len(bars)):
        if i>=24:
            range24[i]=(max(highs[i-23:i+1])-min(lows[i-23:i+1]))/closes[i]
        if e20[i] and e50[i]:
            ema_spread[i]=abs(e20[i]/e50[i]-1)
        if rv24[i] and rv72[i] and rv72[i]>0:
            vol_ratio[i]=rv24[i]/rv72[i]

    rv_rank=rolling_percentile_rank(rv24,24*30)
    range_rank=rolling_percentile_rank(range24,24*30)
    spread_rank=rolling_percentile_rank(ema_spread,24*30)

    regimes=["UNKNOWN"]*len(bars)
    last_comp_start=None

    for i in range(len(bars)):
        if i < 24*30 or rv_rank[i] is None or range_rank[i] is None or spread_rank[i] is None:
            continue

        compression = rv_rank[i] <= 0.25 and range_rank[i] <= 0.30 and spread_rank[i] <= 0.35
        chop = rv_rank[i] <= 0.55 and spread_rank[i] <= 0.50 and (vol_ratio[i] or 1.0) <= 1.10
        expansion = (vol_ratio[i] or 0) >= 1.15

        if compression:
            regimes[i]="COMPRESSION"
            if last_comp_start is None:
                last_comp_start=i
        else:
            if last_comp_start is not None and i-last_comp_start >= 4:
                hi=max(highs[last_comp_start:i])
                lo=min(lows[last_comp_start:i])
                if closes[i] > hi and expansion and vols[i] >= (vmean24[i] or vols[i]):
                    regimes[i]="BREAKOUT_UP"
                elif closes[i] < lo and expansion and vols[i] >= (vmean24[i] or vols[i]):
                    regimes[i]="BREAKOUT_DOWN"
                elif expansion and abs((e20[i]/e50[i]-1) if e20[i] and e50[i] else 0) > 0.002:
                    regimes[i]="TREND"
                elif chop:
                    regimes[i]="CHOP"
                else:
                    regimes[i]="NEUTRAL"
                last_comp_start=None
            elif expansion and abs((e20[i]/e50[i]-1) if e20[i] and e50[i] else 0) > 0.002:
                regimes[i]="TREND"
            elif chop:
                regimes[i]="CHOP"
            else:
                regimes[i]="NEUTRAL"
    return regimes

def mean_revert_signal(bars, i):
    if i < 20:
        return 0
    closes=[b.c for b in bars]
    m=sum(closes[i-19:i+1])/20
    var=sum((x-m)**2 for x in closes[i-19:i+1])/20
    sd=math.sqrt(var)
    if sd<=0:
        return 0
    z=(closes[i]-m)/sd
    if z <= -1.6:
        return 1
    if z >= 1.6:
        return -1
    return 0

def run_mode(coin,bars,mode):
    p=get_profile(coin)
    cfg=COINS[coin]
    regimes=classify_regimes(bars)
    base_sig=signals(bars,p)

    start=cfg["capital"]
    equity=start
    peak=start
    maxdd=0.0
    pos: Optional[Position]=None
    next_entry=0
    trades=[]
    fees=funding=gross_total=0.0

    for i,b in enumerate(bars):
        if pos:
            pos.funding_cash += -pos.side*pos.notional*b.funding
            fav=((b.h/pos.entry_price)-1)*100 if pos.side==1 else ((pos.entry_price/b.l)-1)*100
            pos.mfe_pct=max(pos.mfe_pct,fav)
            pos.hwm=max(pos.hwm,b.h)
            pos.lwm=min(pos.lwm,b.l)
            hold=i-pos.entry_idx
            adverse=((b.l/pos.entry_price)-1)*100 if pos.side==1 else ((pos.entry_price/b.h)-1)*100
            pnlpct=((b.c/pos.entry_price)-1)*100*pos.side
            ep=None
            reason=None

            stop_pct=p.stop_pct
            target_pct=p.target_pct
            trail_activation=p.trail_activation_pct
            trail_pct=p.trail_pct

            if mode=="dynamic_regime":
                if regimes[i]=="TREND":
                    target_pct *= 1.5
                    trail_pct *= 1.25
                elif regimes[i] in ("CHOP","NEUTRAL"):
                    target_pct *= 0.75

            if adverse <= -stop_pct:
                raw=pos.entry_price*(1-stop_pct/100) if pos.side==1 else pos.entry_price*(1+stop_pct/100)
                ep=adverse_fill(raw,pos.side,False)
                reason="STOP"
            elif pnlpct >= target_pct:
                raw=pos.entry_price*(1+target_pct/100) if pos.side==1 else pos.entry_price*(1-target_pct/100)
                ep=adverse_fill(raw,pos.side,False)
                reason="TARGET"
            else:
                if not pos.trailing_active and pos.mfe_pct>=trail_activation:
                    pos.trailing_active=True
                    d=pos.entry_price*trail_pct/100
                    pos.trail_stop=max(pos.entry_price,pos.hwm-d) if pos.side==1 else min(pos.entry_price,pos.lwm+d)
                if pos.trailing_active:
                    d=pos.entry_price*trail_pct/100
                    if pos.side==1:
                        pos.trail_stop=max(pos.trail_stop or pos.entry_price,pos.hwm-d,pos.entry_price)
                        if b.l<=pos.trail_stop:
                            ep=adverse_fill(pos.trail_stop,pos.side,False)
                            reason="TRAIL"
                    else:
                        pos.trail_stop=min(pos.trail_stop or pos.entry_price,pos.lwm+d,pos.entry_price)
                        if b.h>=pos.trail_stop:
                            ep=adverse_fill(pos.trail_stop,pos.side,False)
                            reason="TRAIL"
                if mode=="dynamic_regime" and regimes[i]=="CHOP" and hold>=3 and ep is None:
                    ep=adverse_fill(b.c,pos.side,False)
                    reason="CHOP_EXIT"
                if ep is None and hold>=p.max_hold_hours:
                    ep=adverse_fill(b.c,pos.side,False)
                    reason="MAX_HOLD"

            if ep is not None:
                gross=(ep-pos.entry_price)*pos.qty*pos.side
                ef=abs(ep*pos.qty)*TAKER_FEE_BPS/10000
                net=gross-pos.entry_fee-ef+pos.funding_cash
                equity+=net
                gross_total+=gross
                fees+=pos.entry_fee+ef
                funding+=pos.funding_cash
                entry_regime=getattr(pos,"entry_regime","UNKNOWN")
                trades.append({"net":net,"hold":hold,"entry_regime":entry_regime,"reason":reason})
                peak=max(peak,equity)
                if peak>0:
                    maxdd=max(maxdd,(peak-equity)/peak*100)
                next_entry=i+p.cooldown_hours
                if mode=="dynamic_regime" and reason in ("STOP","CHOP_EXIT"):
                    next_entry=max(next_entry,i+8)
                pos=None

        if pos is None and i>=next_entry:
            regime=regimes[i]
            direction=0
            risk_mult=1.0

            if mode=="always_on":
                direction,_=base_sig[i]
            elif mode=="cash_in_chop":
                if regime not in ("CHOP","COMPRESSION"):
                    direction,_=base_sig[i]
            elif mode=="mean_revert_chop":
                if regime=="CHOP":
                    direction=mean_revert_signal(bars,i)
                    risk_mult=0.4
                elif regime!="COMPRESSION":
                    direction,_=base_sig[i]
            elif mode=="dynamic_regime":
                if regime=="BREAKOUT_UP":
                    direction=1
                    risk_mult=0.8
                elif regime=="BREAKOUT_DOWN":
                    direction=-1
                    risk_mult=0.8
                elif regime=="TREND":
                    direction,_=base_sig[i]
                    risk_mult=0.6

            if direction==0:
                continue

            entry=adverse_fill(b.c,direction,True)
            risk_budget=max(equity,0)*p.risk_pct/100*risk_mult
            notional=min(risk_budget/max(p.stop_pct/100,1e-6),max(equity,0)*cfg["max_leverage"])
            if notional<=0:
                continue
            qty=notional/entry
            fee=notional*TAKER_FEE_BPS/10000
            pos=Position(direction,i,entry,qty,notional,fee,entry,entry)
            setattr(pos,"entry_regime",regime)

    if pos:
        b=bars[-1]
        ep=adverse_fill(b.c,pos.side,False)
        gross=(ep-pos.entry_price)*pos.qty*pos.side
        ef=abs(ep*pos.qty)*TAKER_FEE_BPS/10000
        net=gross-pos.entry_fee-ef+pos.funding_cash
        equity+=net
        gross_total+=gross
        fees+=pos.entry_fee+ef
        funding+=pos.funding_cash
        trades.append({"net":net,"hold":len(bars)-1-pos.entry_idx,"entry_regime":getattr(pos,"entry_regime","UNKNOWN"),"reason":"END"})

    wins=[t for t in trades if t["net"]>0]
    losses=[t for t in trades if t["net"]<=0]
    sw=sum(t["net"] for t in wins)
    sl=abs(sum(t["net"] for t in losses))
    pf=sw/sl if sl else (999 if sw>0 else 0)
    net=equity-start

    chop_trades=[t for t in trades if t["entry_regime"]=="CHOP"]
    chop_net=sum(t["net"] for t in chop_trades)

    stats={
        "coin":coin,
        "mode":mode,
        "return_pct":round((equity/start-1)*100,2),
        "profit_factor":round(pf,3),
        "max_drawdown_pct":round(maxdd,2),
        "trades":len(trades),
        "win_rate_pct":round(len(wins)/len(trades)*100,2) if trades else 0,
        "fees_usd":round(fees,2),
        "funding_usd":round(funding,2),
        "net_pnl_usd":round(net,2),
        "chop_trades":len(chop_trades),
        "chop_net_pnl_usd":round(chop_net,2),
    }

    counts={}
    for r in regimes:
        counts[r]=counts.get(r,0)+1
    denom=sum(counts.values()) or 1
    for key in ("CHOP","COMPRESSION","BREAKOUT_UP","BREAKOUT_DOWN","TREND","NEUTRAL","UNKNOWN"):
        stats[f"{key.lower()}_pct"]=round(counts.get(key,0)/denom*100,2)
    return stats

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--days",type=int,default=365)
    ap.add_argument("--out",default="artifacts/perp_chop_regime_study")
    a=ap.parse_args()
    out=Path(a.out)
    out.mkdir(parents=True,exist_ok=True)

    rows=[]
    for coin,cfg in COINS.items():
        bars=load_bars(cfg["hl"],a.days)
        print("COIN",coin,"bars",len(bars))
        for mode in ("always_on","cash_in_chop","mean_revert_chop","dynamic_regime"):
            s=run_mode(coin,bars,mode)
            rows.append(s)
            print(coin,mode,s["return_pct"],s["profit_factor"],s["max_drawdown_pct"],s["trades"],"chop",s["chop_pct"])

    with (out/"results.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    (out/"results.json").write_text(json.dumps(rows,indent=2))

    lines=[
        "# 365-Day Chop / Regime Study",
        "",
        "| Coin | Mode | Return | PF | Max DD | Trades | Chop % | Chop trades | Chop P&L |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['coin']} | {row['mode']} | {row['return_pct']}% | {row['profit_factor']:.2f} | "
            f"{row['max_drawdown_pct']}% | {row['trades']} | {row['chop_pct']}% | "
            f"{row['chop_trades']} | \${row['chop_net_pnl_usd']} |"
        )

    (out/"report.md").write_text("\n".join(lines))

if __name__=="__main__":
    main()
