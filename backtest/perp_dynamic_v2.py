#!/usr/bin/env python3
"""Dynamic v2 regime-permission backtest for AlphaGEX perpetuals.

Uses each coin's best current profile as the signal engine, then applies
coin-specific regime permissions instead of generating trades from regimes.

Compared against:
- baseline best profile
- cash_in_chop
- dynamic_v2 permission layer

Free/public Hyperliquid data only.
"""

from __future__ import annotations
import argparse, csv, importlib.util, json, sys
from pathlib import Path
from typing import Optional

_BASE = Path(__file__).with_name("perp_chop_regime_study.py")
_spec = importlib.util.spec_from_file_location("perp_chop_regime_study", _BASE)
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

# Coin-specific permission policy learned from the 365d chop study.
# Values are risk multipliers applied to the base strategy signal.
PERMISSIONS = {
    "BTC":  {"CHOP":0.75,"COMPRESSION":0.50,"NEUTRAL":0.80,"TREND":1.00,"BREAKOUT_UP":1.00,"BREAKOUT_DOWN":1.00,"UNKNOWN":0.00},
    "ETH":  {"CHOP":0.85,"COMPRESSION":0.60,"NEUTRAL":0.75,"TREND":1.00,"BREAKOUT_UP":1.00,"BREAKOUT_DOWN":1.00,"UNKNOWN":0.00},
    "SOL":  {"CHOP":0.00,"COMPRESSION":0.00,"NEUTRAL":0.65,"TREND":1.00,"BREAKOUT_UP":1.00,"BREAKOUT_DOWN":1.00,"UNKNOWN":0.00},
    "AVAX": {"CHOP":0.70,"COMPRESSION":0.40,"NEUTRAL":0.80,"TREND":1.00,"BREAKOUT_UP":1.00,"BREAKOUT_DOWN":1.00,"UNKNOWN":0.00},
    "XRP":  {"CHOP":0.00,"COMPRESSION":0.00,"NEUTRAL":0.55,"TREND":1.00,"BREAKOUT_UP":0.80,"BREAKOUT_DOWN":1.00,"UNKNOWN":0.00},
    "DOGE": {"CHOP":0.00,"COMPRESSION":0.00,"NEUTRAL":0.60,"TREND":1.00,"BREAKOUT_UP":0.80,"BREAKOUT_DOWN":1.00,"UNKNOWN":0.00},
    "SHIB": {"CHOP":0.00,"COMPRESSION":0.25,"NEUTRAL":0.55,"TREND":0.90,"BREAKOUT_UP":1.00,"BREAKOUT_DOWN":0.70,"UNKNOWN":0.00},
}

COOLDOWN_AFTER_LOSS = {
    "BTC": 8, "ETH": 8, "SOL": 10, "AVAX": 8, "XRP": 10, "DOGE": 12, "SHIB": 12
}

def run_mode(coin,bars,mode):
    p=get_profile(coin); cfg=COINS[coin]
    regimes=classify_regimes(bars)
    sigs=signals(bars,p)

    start=cfg["capital"]; equity=start; peak=start; maxdd=0.0
    pos: Optional[Position]=None
    next_entry=0; trades=[]; fees=funding=gross_total=0.0

    for i,b in enumerate(bars):
        if pos:
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
                r=regimes[i]
                # Let winners breathe in trend; tighten dead/noisy environments.
                if r=="TREND":
                    target_pct*=1.35; trail_pct*=1.15
                elif r in ("CHOP","COMPRESSION"):
                    target_pct*=0.80
                    trail_activation*=0.85

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
                trades.append({"net":net,"hold":hold,"regime":getattr(pos,"entry_regime","UNKNOWN"),"reason":reason})
                peak=max(peak,equity)
                if peak>0: maxdd=max(maxdd,(peak-equity)/peak*100)
                next_entry=i+p.cooldown_hours
                if mode=="dynamic_v2" and net<=0:
                    next_entry=max(next_entry,i+COOLDOWN_AFTER_LOSS[coin])
                pos=None

        if pos is None and i>=next_entry:
            direction,_=sigs[i]
            if direction==0: continue
            regime=regimes[i]

            if mode=="baseline":
                risk_mult=1.0
            elif mode=="cash_in_chop":
                if regime in ("CHOP","COMPRESSION"):
                    continue
                risk_mult=1.0
            elif mode=="dynamic_v2":
                risk_mult=PERMISSIONS[coin].get(regime,0.0)
                if risk_mult<=0:
                    continue
            else:
                raise ValueError(mode)

            entry=adverse_fill(b.c,direction,True)
            risk_budget=max(equity,0)*p.risk_pct/100*risk_mult
            notional=min(risk_budget/max(p.stop_pct/100,1e-6),max(equity,0)*cfg["max_leverage"])
            if notional<=0: continue
            qty=notional/entry
            fee=notional*TAKER_FEE_BPS/10000
            pos=Position(direction,i,entry,qty,notional,fee,entry,entry)
            setattr(pos,"entry_regime",regime)

    if pos:
        b=bars[-1]; ep=adverse_fill(b.c,pos.side,False)
        gross=(ep-pos.entry_price)*pos.qty*pos.side; ef=abs(ep*pos.qty)*TAKER_FEE_BPS/10000
        net=gross-pos.entry_fee-ef+pos.funding_cash
        equity+=net; gross_total+=gross; fees+=pos.entry_fee+ef; funding+=pos.funding_cash
        trades.append({"net":net,"hold":len(bars)-1-pos.entry_idx,"regime":getattr(pos,"entry_regime","UNKNOWN"),"reason":"END"})

    wins=[t for t in trades if t["net"]>0]; losses=[t for t in trades if t["net"]<=0]
    sw=sum(t["net"] for t in wins); sl=abs(sum(t["net"] for t in losses))
    pf=sw/sl if sl else (999 if sw>0 else 0)
    net=equity-start
    return {
        "coin":coin,"mode":mode,"return_pct":round((equity/start-1)*100,2),"profit_factor":round(pf,3),
        "max_drawdown_pct":round(maxdd,2),"trades":len(trades),
        "win_rate_pct":round(len(wins)/len(trades)*100,2) if trades else 0.0,
        "fees_usd":round(fees,2),"funding_usd":round(funding,2),"net_pnl_usd":round(net,2)
    }

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--days",type=int,default=365); ap.add_argument("--out",default="artifacts/perp_dynamic_v2")
    a=ap.parse_args(); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for coin,cfg in COINS.items():
        bars=load_bars(cfg["hl"],a.days)
        print("COIN",coin,"bars",len(bars))
        for mode in ("baseline","cash_in_chop","dynamic_v2"):
            r=run_mode(coin,bars,mode); rows.append(r)
            print(coin,mode,r["return_pct"],r["profit_factor"],r["max_drawdown_pct"],r["trades"])
    with (out/"results.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    (out/"results.json").write_text(json.dumps(rows,indent=2))
    lines=["# Dynamic v2 Regime Permission Study","",
           "| Coin | Mode | Return | PF | Max DD | Trades |",
           "|---|---|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['coin']} | {r['mode']} | {r['return_pct']}% | {r['profit_factor']:.2f} | {r['max_drawdown_pct']}% | {r['trades']} |")
    (out/"report.md").write_text("\\n".join(lines))

if __name__=="__main__":
    main()
