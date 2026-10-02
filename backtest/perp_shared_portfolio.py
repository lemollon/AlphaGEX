#!/usr/bin/env python3
"""Shared-capital 365-day portfolio simulation for AlphaGEX perpetuals.

Uses the current best coin-specific strategy/rules:
BTC baseline best profile
ETH baseline best profile (research-only, included for comparison)
SOL cash-in-chop
AVAX baseline best profile
XRP dynamic v2
DOGE dynamic v2
SHIB cash-in-chop

One shared portfolio compounds trade-by-trade and applies portfolio risk caps.
"""

from __future__ import annotations
import argparse, csv, importlib.util, json, sys
from pathlib import Path
from typing import Optional

_BASE = Path(__file__).with_name("perp_dynamic_v2.py")
_spec = importlib.util.spec_from_file_location("perp_dynamic_v2", _BASE)
_mod = importlib.util.module_from_spec(_spec); sys.modules[_spec.name]=_mod; _spec.loader.exec_module(_mod)

Bar=_mod.Bar
COINS=_mod.COINS
Position=_mod.Position
TAKER_FEE_BPS=_mod.TAKER_FEE_BPS
load_bars=_mod.load_bars
adverse_fill=_mod.adverse_fill
get_profile=_mod.get_profile
classify_regimes=_mod.classify_regimes
signals=_mod.signals
PERMISSIONS=_mod.PERMISSIONS
COOLDOWN_AFTER_LOSS=_mod.COOLDOWN_AFTER_LOSS

MODE = {
    "BTC":"baseline",
    "ETH":"baseline",
    "SOL":"cash_in_chop",
    "AVAX":"baseline",
    "XRP":"dynamic_v2",
    "DOGE":"dynamic_v2",
    "SHIB":"cash_in_chop",
}

# Risk as % of shared portfolio equity before coin/regime multipliers.
BASE_RISK = {
    "BTC":0.50, "ETH":0.40, "SOL":0.45, "AVAX":0.40, "XRP":0.40, "DOGE":0.45, "SHIB":0.30
}

# Crude correlation groups for concentration controls.
GROUP = {
    "BTC":"majors","ETH":"majors",
    "SOL":"alts","AVAX":"alts","XRP":"alts",
    "DOGE":"memes","SHIB":"memes",
}

MAX_TOTAL_RISK_PCT = 2.0
MAX_GROUP_RISK_PCT = 1.0
MAX_OPEN_POSITIONS = 4

def permission_mult(coin, mode, regime):
    if mode=="baseline":
        return 1.0
    if mode=="cash_in_chop":
        return 0.0 if regime in ("CHOP","COMPRESSION") else 1.0
    if mode=="dynamic_v2":
        return PERMISSIONS[coin].get(regime,0.0)
    raise ValueError(mode)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--days",type=int,default=365)
    ap.add_argument("--out",default="artifacts/perp_shared_portfolio")
    ap.add_argument("--exclude-eth",action="store_true")
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)

    coins=[c for c in COINS if not (args.exclude_eth and c=="ETH")]
    data={}
    for coin in coins:
        bars=load_bars(COINS[coin]["hl"],args.days)
        p=get_profile(coin)
        data[coin]={
            "bars":bars,
            "profile":p,
            "regimes":classify_regimes(bars),
            "signals":signals(bars,p),
        }

    # Align on common timestamps to avoid look-ahead/misalignment.
    common=set(b.ts for b in data[coins[0]]["bars"])
    for coin in coins[1:]:
        common &= set(b.ts for b in data[coin]["bars"])
    timestamps=sorted(common)
    idxmap={coin:{b.ts:i for i,b in enumerate(data[coin]["bars"])} for coin in coins}

    start_equity=sum(COINS[c]["capital"] for c in coins)
    equity=start_equity
    peak=equity
    maxdd=0.0
    positions={}
    next_entry={c:0 for c in coins}
    trades=[]
    fees=funding=gross_total=0.0

    def open_risk_pct():
        return sum(v["risk_pct"] for v in positions.values())

    def group_risk_pct(group):
        return sum(v["risk_pct"] for c,v in positions.items() if GROUP[c]==group)

    for step,ts in enumerate(timestamps):
        # exits first
        for coin in list(positions.keys()):
            state=positions[coin]
            pos=state["pos"]
            i=idxmap[coin][ts]
            b=data[coin]["bars"][i]
            p=data[coin]["profile"]
            mode=MODE[coin]
            regime=data[coin]["regimes"][i]

            pos.funding_cash += -pos.side*pos.notional*b.funding
            fav=((b.h/pos.entry_price)-1)*100 if pos.side==1 else ((pos.entry_price/b.l)-1)*100
            pos.mfe_pct=max(pos.mfe_pct,fav); pos.hwm=max(pos.hwm,b.h); pos.lwm=min(pos.lwm,b.l)
            hold=i-pos.entry_idx
            adverse=((b.l/pos.entry_price)-1)*100 if pos.side==1 else ((pos.entry_price/b.h)-1)*100
            pnlpct=((b.c/pos.entry_price)-1)*100*pos.side
            ep=None; reason=None

            stop_pct=p.stop_pct
            target_pct=p.target_pct
            trail_activation=p.trail_activation_pct
            trail_pct=p.trail_pct
            if mode=="dynamic_v2":
                if regime=="TREND":
                    target_pct*=1.35; trail_pct*=1.15
                elif regime in ("CHOP","COMPRESSION"):
                    target_pct*=0.80; trail_activation*=0.85

            if adverse <= -stop_pct:
                raw=pos.entry_price*(1-stop_pct/100) if pos.side==1 else pos.entry_price*(1+stop_pct/100)
                ep=adverse_fill(raw,pos.side,False); reason="STOP"
            elif pnlpct >= target_pct:
                raw=pos.entry_price*(1+target_pct/100) if pos.side==1 else pos.entry_price*(1-target_pct/100)
                ep=adverse_fill(raw,pos.side,False); reason="TARGET"
            else:
                if not pos.trailing_active and pos.mfe_pct>=trail_activation:
                    pos.trailing_active=True
                    d=pos.entry_price*trail_pct/100
                    pos.trail_stop=max(pos.entry_price,pos.hwm-d) if pos.side==1 else min(pos.entry_price,pos.lwm+d)
                if pos.trailing_active:
                    d=pos.entry_price*trail_pct/100
                    if pos.side==1:
                        pos.trail_stop=max(pos.trail_stop or pos.entry_price,pos.hwm-d,pos.entry_price)
                        if b.l<=pos.trail_stop: ep=adverse_fill(pos.trail_stop,pos.side,False); reason="TRAIL"
                    else:
                        pos.trail_stop=min(pos.trail_stop or pos.entry_price,pos.lwm+d,pos.entry_price)
                        if b.h>=pos.trail_stop: ep=adverse_fill(pos.trail_stop,pos.side,False); reason="TRAIL"
                if ep is None and hold>=p.max_hold_hours:
                    ep=adverse_fill(b.c,pos.side,False); reason="MAX_HOLD"

            if ep is not None:
                gross=(ep-pos.entry_price)*pos.qty*pos.side
                ef=abs(ep*pos.qty)*TAKER_FEE_BPS/10000
                net=gross-pos.entry_fee-ef+pos.funding_cash
                equity+=net; gross_total+=gross; fees+=pos.entry_fee+ef; funding+=pos.funding_cash
                trades.append({
                    "coin":coin,"net":net,"hold":hold,"reason":reason,
                    "entry_regime":state["entry_regime"],"risk_pct":state["risk_pct"]
                })
                peak=max(peak,equity)
                if peak>0: maxdd=max(maxdd,(peak-equity)/peak*100)
                next_entry[coin]=i+p.cooldown_hours
                if mode=="dynamic_v2" and net<=0:
                    next_entry[coin]=max(next_entry[coin],i+COOLDOWN_AFTER_LOSS[coin])
                del positions[coin]

        # rank candidate entries by signal strength
        candidates=[]
        for coin in coins:
            if coin in positions: continue
            i=idxmap[coin][ts]
            if i<next_entry[coin]: continue
            direction,score=data[coin]["signals"][i]
            if direction==0: continue
            regime=data[coin]["regimes"][i]
            mult=permission_mult(coin,MODE[coin],regime)
            if mult<=0: continue
            candidates.append((abs(score),coin,direction,score,regime,mult))
        candidates.sort(reverse=True)

        for _,coin,direction,score,regime,mult in candidates:
            if len(positions)>=MAX_OPEN_POSITIONS: break
            desired_risk=BASE_RISK[coin]*mult
            avail_total=MAX_TOTAL_RISK_PCT-open_risk_pct()
            avail_group=MAX_GROUP_RISK_PCT-group_risk_pct(GROUP[coin])
            risk_pct=min(desired_risk,avail_total,avail_group)
            if risk_pct<=0.05: continue

            i=idxmap[coin][ts]
            b=data[coin]["bars"][i]
            p=data[coin]["profile"]
            cfg=COINS[coin]
            entry=adverse_fill(b.c,direction,True)
            risk_budget=max(equity,0)*risk_pct/100
            notional=min(risk_budget/max(p.stop_pct/100,1e-6),max(equity,0)*cfg["max_leverage"])
            if notional<=0: continue
            qty=notional/entry; fee=notional*TAKER_FEE_BPS/10000
            pos=Position(direction,i,entry,qty,notional,fee,entry,entry)
            positions[coin]={"pos":pos,"entry_regime":regime,"risk_pct":risk_pct}

    # close leftovers
    for coin,state in list(positions.items()):
        pos=state["pos"]; b=data[coin]["bars"][-1]
        ep=adverse_fill(b.c,pos.side,False)
        gross=(ep-pos.entry_price)*pos.qty*pos.side
        ef=abs(ep*pos.qty)*TAKER_FEE_BPS/10000
        net=gross-pos.entry_fee-ef+pos.funding_cash
        equity+=net; gross_total+=gross; fees+=pos.entry_fee+ef; funding+=pos.funding_cash
        trades.append({"coin":coin,"net":net,"hold":len(data[coin]["bars"])-1-pos.entry_idx,"reason":"END","entry_regime":state["entry_regime"],"risk_pct":state["risk_pct"]})

    wins=[t for t in trades if t["net"]>0]; losses=[t for t in trades if t["net"]<=0]
    sw=sum(t["net"] for t in wins); sl=abs(sum(t["net"] for t in losses))
    pf=sw/sl if sl else (999 if sw>0 else 0)
    net=equity-start_equity

    by_coin={}
    for coin in coins:
        ct=[t for t in trades if t["coin"]==coin]
        by_coin[coin]={
            "trades":len(ct),
            "net_pnl_usd":round(sum(t["net"] for t in ct),2),
            "wins":sum(1 for t in ct if t["net"]>0)
        }

    summary={
        "start_equity":round(start_equity,2),"end_equity":round(equity,2),
        "return_pct":round((equity/start_equity-1)*100,2),"net_pnl_usd":round(net,2),
        "profit_factor":round(pf,3),"max_drawdown_pct":round(maxdd,2),
        "trades":len(trades),"win_rate_pct":round(len(wins)/len(trades)*100,2) if trades else 0,
        "fees_usd":round(fees,2),"funding_usd":round(funding,2),
        "max_total_risk_pct":MAX_TOTAL_RISK_PCT,"max_group_risk_pct":MAX_GROUP_RISK_PCT,
        "max_open_positions":MAX_OPEN_POSITIONS,"excluded_eth":args.exclude_eth,
        "by_coin":by_coin,
    }
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    with (out/"trades.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(trades[0].keys()) if trades else ["coin"]); w.writeheader(); w.writerows(trades)
    lines=["# Shared Capital Portfolio","",
           f"- Start equity: \${summary['start_equity']}",
           f"- End equity: \${summary['end_equity']}",
           f"- Return: {summary['return_pct']}%",
           f"- Net P&L: \${summary['net_pnl_usd']}",
           f"- Profit factor: {summary['profit_factor']}",
           f"- Max drawdown: {summary['max_drawdown_pct']}%",
           f"- Trades: {summary['trades']}",
           f"- Fees: \${summary['fees_usd']}",
           "",
           "| Coin | Trades | Wins | Net P&L |",
           "|---|---:|---:|---:|"]
    for coin,x in by_coin.items():
        lines.append(f"| {coin} | {x['trades']} | {x['wins']} | \${x['net_pnl_usd']} |")
    (out/"report.md").write_text("\\n".join(lines))

if __name__=="__main__":
    main()
