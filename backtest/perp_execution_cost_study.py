#!/usr/bin/env python3
"""Execution-cost optimization for the current AlphaGEX champion portfolio.

Uses the validated 6-coin shared portfolio parameters and compares execution models:
- taker_only
- maker_preferred
- maker_then_taker
- maker_selective

Models:
- maker/taker fees
- maker fill probability
- partial fills
- adverse-selection penalty on maker fills
- fallback-to-taker delay/slippage
"""

from __future__ import annotations
import argparse, csv, importlib.util, json, random, sys
from pathlib import Path
from typing import Optional

_BASE=Path(__file__).with_name("perp_portfolio_walkforward.py")
_spec=importlib.util.spec_from_file_location("perp_portfolio_walkforward",_BASE)
m=importlib.util.module_from_spec(_spec); sys.modules[_spec.name]=m; _spec.loader.exec_module(m)

COINS=m.COINS; Position=m.Position; load_bars=m.load_bars; adverse_fill=m.adverse_fill
get_profile=m.get_profile; classify_regimes=m.classify_regimes; signals=m.signals
permission_mult=m.permission_mult; MODE=m.MODE; BASE_RISK=m.BASE_RISK; GROUP=m.GROUP

CHAMPION={
    "risk_scale":1.5,
    "max_total":2.0,
    "max_group":1.0,
    "doge_score_mult":1.0,
    "doge_loss_cd":12,
    "shib_score_mult":1.0,
    "shib_loss_cd":12,
}

# Conservative fee assumptions. Can be calibrated later to the actual venue/account tier.
TAKER_FEE_BPS=6.0
MAKER_FEE_BPS=1.5
BASE_SLIP_BPS=2.0

EXECUTION_MODELS={
    "taker_only":{
        "maker_prob":0.0,"partial_fill":1.0,"maker_adverse_bps":0.0,
        "fallback_prob":1.0,"fallback_extra_bps":0.0,
    },
    "maker_preferred":{
        "maker_prob":0.70,"partial_fill":0.85,"maker_adverse_bps":0.5,
        "fallback_prob":0.30,"fallback_extra_bps":1.0,
    },
    "maker_then_taker":{
        "maker_prob":0.55,"partial_fill":0.75,"maker_adverse_bps":0.75,
        "fallback_prob":0.45,"fallback_extra_bps":0.75,
    },
    "maker_selective":{
        "maker_prob":0.80,"partial_fill":0.90,"maker_adverse_bps":0.35,
        "fallback_prob":0.20,"fallback_extra_bps":0.5,
    },
}

def exec_entry(price, side, notional, model, high_quality, rng):
    cfg=EXECUTION_MODELS[model]
    maker_prob=cfg["maker_prob"]
    if model=="maker_selective" and not high_quality:
        maker_prob=0.0

    if rng.random() < maker_prob:
        fill_frac=cfg["partial_fill"]
        px=price*(1 + (cfg["maker_adverse_bps"]/10000)*side)
        fee=notional*fill_frac*MAKER_FEE_BPS/10000
        remaining=1-fill_frac
        if remaining>0 and rng.random()<cfg["fallback_prob"]:
            fallback_px=price*(1 + ((BASE_SLIP_BPS+cfg["fallback_extra_bps"])/10000)*side)
            fee += notional*remaining*TAKER_FEE_BPS/10000
            avg_px=px*fill_frac+fallback_px*remaining
            return avg_px, fee, 1.0, "maker_partial_taker"
        return px, fee, fill_frac, "maker"
    px=price*(1+(BASE_SLIP_BPS/10000)*side)
    fee=notional*TAKER_FEE_BPS/10000
    return px, fee, 1.0, "taker"

def exec_exit(price, side, qty, reason):
    # Stops/urgent exits assumed taker. Targets/trails may use maker only later; keep conservative here.
    px=price*(1-(BASE_SLIP_BPS/10000)*side)
    fee=abs(px*qty)*TAKER_FEE_BPS/10000
    return px, fee

def simulate(data,timestamps,idxmap,start_step,end_step,model,seed=42,start_equity=45000.0):
    rng=random.Random(seed)
    equity=start_equity; peak=equity; maxdd=0.0
    positions={}; next_entry={c:0 for c in data}; trades=[]
    fees=funding=0.0
    pset=CHAMPION
    coins=list(data)

    def open_risk(): return sum(v["risk_pct"] for v in positions.values())
    def group_risk(g): return sum(v["risk_pct"] for c,v in positions.items() if GROUP[c]==g)

    first_ts=timestamps[start_step]
    for c in coins: next_entry[c]=idxmap[c][first_ts]

    for ts in timestamps[start_step:end_step]:
        for coin in list(positions):
            st=positions[coin]; pos=st["pos"]; i=idxmap[coin][ts]
            b=data[coin]["bars"][i]; p=data[coin]["profile"]; mode=MODE[coin]; regime=data[coin]["regimes"][i]
            pos.funding_cash += -pos.side*pos.notional*b.funding
            fav=((b.h/pos.entry_price)-1)*100 if pos.side==1 else ((pos.entry_price/b.l)-1)*100
            pos.mfe_pct=max(pos.mfe_pct,fav); pos.hwm=max(pos.hwm,b.h); pos.lwm=min(pos.lwm,b.l)
            hold=i-pos.entry_idx
            adverse=((b.l/pos.entry_price)-1)*100 if pos.side==1 else ((pos.entry_price/b.h)-1)*100
            pnlpct=((b.c/pos.entry_price)-1)*100*pos.side
            stop=p.stop_pct; target=p.target_pct; ta=p.trail_activation_pct; trail=p.trail_pct
            if mode=="dynamic_v2":
                if regime=="TREND": target*=1.35; trail*=1.15
                elif regime in ("CHOP","COMPRESSION"): target*=0.80; ta*=0.85

            ep=None; reason=None
            if adverse<=-stop:
                raw=pos.entry_price*(1-stop/100) if pos.side==1 else pos.entry_price*(1+stop/100)
                ep=raw; reason="STOP"
            elif pnlpct>=target:
                raw=pos.entry_price*(1+target/100) if pos.side==1 else pos.entry_price*(1-target/100)
                ep=raw; reason="TARGET"
            else:
                if not pos.trailing_active and pos.mfe_pct>=ta:
                    pos.trailing_active=True; d=pos.entry_price*trail/100
                    pos.trail_stop=max(pos.entry_price,pos.hwm-d) if pos.side==1 else min(pos.entry_price,pos.lwm+d)
                if pos.trailing_active:
                    d=pos.entry_price*trail/100
                    if pos.side==1:
                        pos.trail_stop=max(pos.trail_stop or pos.entry_price,pos.hwm-d,pos.entry_price)
                        if b.l<=pos.trail_stop: ep=pos.trail_stop; reason="TRAIL"
                    else:
                        pos.trail_stop=min(pos.trail_stop or pos.entry_price,pos.lwm+d,pos.entry_price)
                        if b.h>=pos.trail_stop: ep=pos.trail_stop; reason="TRAIL"
                if ep is None and hold>=p.max_hold_hours:
                    ep=b.c; reason="MAX_HOLD"
            if ep is not None:
                exit_px,exit_fee=exec_exit(ep,pos.side,pos.qty,reason)
                gross=(exit_px-pos.entry_price)*pos.qty*pos.side
                net=gross-pos.entry_fee-exit_fee+pos.funding_cash
                equity+=net; fees+=pos.entry_fee+exit_fee; funding+=pos.funding_cash
                trades.append({"coin":coin,"net":net,"entry_exec":st["entry_exec"],"fill_frac":st["fill_frac"]})
                peak=max(peak,equity)
                if peak>0: maxdd=max(maxdd,(peak-equity)/peak*100)
                next_entry[coin]=i+p.cooldown_hours
                if mode=="dynamic_v2" and net<=0:
                    cd=pset["doge_loss_cd"] if coin=="DOGE" else pset["shib_loss_cd"] if coin=="SHIB" else m.COOLDOWN_AFTER_LOSS[coin]
                    next_entry[coin]=max(next_entry[coin],i+cd)
                del positions[coin]

        candidates=[]
        for coin in coins:
            if coin in positions: continue
            i=idxmap[coin][ts]
            if i<next_entry[coin]: continue
            direction,score=data[coin]["signals"][i]
            if direction==0: continue
            p=data[coin]["profile"]
            if coin=="DOGE" and abs(score)<p.score_threshold*pset["doge_score_mult"]: continue
            if coin=="SHIB" and abs(score)<p.score_threshold*pset["shib_score_mult"]: continue
            regime=data[coin]["regimes"][i]; mult=permission_mult(coin,MODE[coin],regime)
            if mult<=0: continue
            candidates.append((abs(score),coin,direction,regime,mult,score))
        candidates.sort(reverse=True)

        for _,coin,direction,regime,mult,score in candidates:
            if len(positions)>=4: break
            desired=BASE_RISK[coin]*pset["risk_scale"]*mult
            risk_pct=min(desired,pset["max_total"]-open_risk(),pset["max_group"]-group_risk(GROUP[coin]))
            if risk_pct<=0.05: continue
            i=idxmap[coin][ts]; b=data[coin]["bars"][i]; p=data[coin]["profile"]; cfg=COINS[coin]
            risk_budget=max(equity,0)*risk_pct/100
            notional=min(risk_budget/max(p.stop_pct/100,1e-6),max(equity,0)*cfg["max_leverage"])
            if notional<=0: continue
            high_quality = abs(score) >= max(p.score_threshold*1.25, p.score_threshold+0.05)
            entry,fee,fill_frac,entry_exec=exec_entry(b.c,direction,notional,model,high_quality,rng)
            if fill_frac<=0: continue
            notional*=fill_frac
            qty=notional/entry
            pos=Position(direction,i,entry,qty,notional,fee,entry,entry)
            positions[coin]={"pos":pos,"risk_pct":risk_pct*fill_frac,"entry_exec":entry_exec,"fill_frac":fill_frac}

    boundary_ts=timestamps[end_step-1]
    for coin,st in list(positions.items()):
        pos=st["pos"]; i=idxmap[coin][boundary_ts]; b=data[coin]["bars"][i]
        exit_px,exit_fee=exec_exit(b.c,pos.side,pos.qty,"END")
        gross=(exit_px-pos.entry_price)*pos.qty*pos.side
        net=gross-pos.entry_fee-exit_fee+pos.funding_cash
        equity+=net; fees+=pos.entry_fee+exit_fee; funding+=pos.funding_cash
        trades.append({"coin":coin,"net":net,"entry_exec":st["entry_exec"],"fill_frac":st["fill_frac"]})

    wins=[t for t in trades if t["net"]>0]; losses=[t for t in trades if t["net"]<=0]
    sw=sum(t["net"] for t in wins); sl=abs(sum(t["net"] for t in losses))
    pf=sw/sl if sl else (999 if sw>0 else 0)
    maker=sum(1 for t in trades if t["entry_exec"].startswith("maker"))
    return {
        "model":model,"return_pct":round((equity/start_equity-1)*100,2),"profit_factor":round(pf,3),
        "max_drawdown_pct":round(maxdd,2),"trades":len(trades),"fees_usd":round(fees,2),
        "funding_usd":round(funding,2),"end_equity":round(equity,2),
        "maker_entry_pct":round(maker/len(trades)*100,2) if trades else 0,
        "avg_fill_frac":round(sum(t["fill_frac"] for t in trades)/len(trades),3) if trades else 0,
    }

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--days",type=int,default=365); ap.add_argument("--out",default="artifacts/perp_execution_cost_study")
    a=ap.parse_args(); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    coins=list(MODE)
    data={}
    for coin in coins:
        bars=load_bars(COINS[coin]["hl"],a.days); p=get_profile(coin)
        data[coin]={"bars":bars,"profile":p,"regimes":classify_regimes(bars),"signals":signals(bars,p)}
        print("loaded",coin,len(bars))
    common=set(b.ts for b in data[coins[0]]["bars"])
    for coin in coins[1:]: common &= set(b.ts for b in data[coin]["bars"])
    timestamps=sorted(common); idxmap={c:{b.ts:i for i,b in enumerate(data[c]["bars"])} for c in coins}
    split=int(len(timestamps)*270/365)

    rows=[]
    for model in EXECUTION_MODELS:
        # deterministic seeds to compare model assumptions, plus 10-seed stability sample for stochastic fill models
        vals=[simulate(data,timestamps,idxmap,split,len(timestamps),model,seed=s) for s in range(10)]
        full=[simulate(data,timestamps,idxmap,0,len(timestamps),model,seed=s) for s in range(10)]
        row={
            "model":model,
            "holdout_return_avg":round(sum(x["return_pct"] for x in vals)/len(vals),2),
            "holdout_pf_avg":round(sum(x["profit_factor"] for x in vals)/len(vals),3),
            "holdout_dd_avg":round(sum(x["max_drawdown_pct"] for x in vals)/len(vals),2),
            "full_return_avg":round(sum(x["return_pct"] for x in full)/len(full),2),
            "full_pf_avg":round(sum(x["profit_factor"] for x in full)/len(full),3),
            "full_dd_avg":round(sum(x["max_drawdown_pct"] for x in full)/len(full),2),
            "full_fees_avg":round(sum(x["fees_usd"] for x in full)/len(full),2),
            "maker_entry_pct_avg":round(sum(x["maker_entry_pct"] for x in full)/len(full),2),
            "avg_fill_frac":round(sum(x["avg_fill_frac"] for x in full)/len(full),3),
        }
        rows.append(row)
    with (out/"results.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    (out/"results.json").write_text(json.dumps(rows,indent=2))
    lines=["# Execution Cost Study","",
           "| Model | Holdout ret | Holdout PF | Holdout DD | Full ret | Full PF | Full DD | Full fees | Maker entries | Avg fill |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['model']} | {r['holdout_return_avg']}% | {r['holdout_pf_avg']} | {r['holdout_dd_avg']}% | {r['full_return_avg']}% | {r['full_pf_avg']} | {r['full_dd_avg']}% | \${r['full_fees_avg']} | {r['maker_entry_pct_avg']}% | {r['avg_fill_frac']} |")
    (out/"report.md").write_text("\n".join(lines))

if __name__=="__main__":
    main()
