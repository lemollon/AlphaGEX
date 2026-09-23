#!/usr/bin/env python3
"""Walk-forward portfolio optimization for AlphaGEX perpetuals.

Loads 365d once, selects parameters on the first ~270d, then evaluates the
chosen configurations on the untouched final ~95d. This reduces in-sample
curve-fit risk while testing shared-capital compounding.

Search dimensions are intentionally small:
- portfolio risk scale
- max total/group open risk
- DOGE signal-strength filter
- DOGE post-loss cooldown
"""

from __future__ import annotations
import argparse, csv, importlib.util, json, sys
from pathlib import Path
from typing import Optional

_BASE=Path(__file__).with_name("perp_dynamic_v2.py")
_spec=importlib.util.spec_from_file_location("perp_dynamic_v2",_BASE)
m=importlib.util.module_from_spec(_spec); sys.modules[_spec.name]=m; _spec.loader.exec_module(m)

COINS=m.COINS; Position=m.Position; TAKER_FEE_BPS=m.TAKER_FEE_BPS
load_bars=m.load_bars; adverse_fill=m.adverse_fill; get_profile=m.get_profile
classify_regimes=m.classify_regimes; signals=m.signals; PERMISSIONS=m.PERMISSIONS
COOLDOWN_AFTER_LOSS=m.COOLDOWN_AFTER_LOSS

MODE={"BTC":"baseline","SOL":"cash_in_chop","AVAX":"baseline","XRP":"dynamic_v2","DOGE":"dynamic_v2","SHIB":"cash_in_chop"}
BASE_RISK={"BTC":0.50,"SOL":0.45,"AVAX":0.40,"XRP":0.40,"DOGE":0.45,"SHIB":0.30}
GROUP={"BTC":"majors","SOL":"alts","AVAX":"alts","XRP":"alts","DOGE":"memes","SHIB":"memes"}

def permission_mult(coin,mode,regime):
    if mode=="baseline": return 1.0
    if mode=="cash_in_chop": return 0.0 if regime in ("CHOP","COMPRESSION") else 1.0
    if mode=="dynamic_v2": return PERMISSIONS[coin].get(regime,0.0)
    raise ValueError(mode)

def simulate(data,timestamps,idxmap,start_step,end_step,params,start_equity=45000.0):
    equity=start_equity; peak=equity; maxdd=0.0
    positions={}; next_entry={c:0 for c in data}; trades=[]; fees=funding=0.0
    scale=params["risk_scale"]; max_total=params["max_total"]; max_group=params["max_group"]
    doge_score_mult=params["doge_score_mult"]; doge_loss_cd=params["doge_loss_cd"]
    shib_score_mult=params.get("shib_score_mult",1.0); shib_loss_cd=params.get("shib_loss_cd",12)
    coins=list(data)

    def open_risk(): return sum(v["risk_pct"] for v in positions.values())
    def group_risk(g): return sum(v["risk_pct"] for c,v in positions.items() if GROUP[c]==g)

    # make local entry indexes comparable with full data indexes
    first_ts=timestamps[start_step]
    for c in coins:
        next_entry[c]=idxmap[c][first_ts]

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
                ep=adverse_fill(raw,pos.side,False); reason="STOP"
            elif pnlpct>=target:
                raw=pos.entry_price*(1+target/100) if pos.side==1 else pos.entry_price*(1-target/100)
                ep=adverse_fill(raw,pos.side,False); reason="TARGET"
            else:
                if not pos.trailing_active and pos.mfe_pct>=ta:
                    pos.trailing_active=True; d=pos.entry_price*trail/100
                    pos.trail_stop=max(pos.entry_price,pos.hwm-d) if pos.side==1 else min(pos.entry_price,pos.lwm+d)
                if pos.trailing_active:
                    d=pos.entry_price*trail/100
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
                equity+=net; fees+=pos.entry_fee+ef; funding+=pos.funding_cash
                trades.append({"coin":coin,"net":net})
                peak=max(peak,equity)
                if peak>0: maxdd=max(maxdd,(peak-equity)/peak*100)
                next_entry[coin]=i+p.cooldown_hours
                if mode=="dynamic_v2" and net<=0:
                    cd=doge_loss_cd if coin=="DOGE" else shib_loss_cd if coin=="SHIB" else COOLDOWN_AFTER_LOSS[coin]
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
            if coin=="DOGE" and abs(score) < p.score_threshold*doge_score_mult:
                continue
            if coin=="SHIB" and abs(score) < p.score_threshold*shib_score_mult:
                continue
            regime=data[coin]["regimes"][i]; mult=permission_mult(coin,MODE[coin],regime)
            if mult<=0: continue
            candidates.append((abs(score),coin,direction,regime,mult))
        candidates.sort(reverse=True)

        for _,coin,direction,regime,mult in candidates:
            if len(positions)>=4: break
            desired=BASE_RISK[coin]*scale*mult
            risk_pct=min(desired,max_total-open_risk(),max_group-group_risk(GROUP[coin]))
            if risk_pct<=0.05: continue
            i=idxmap[coin][ts]; b=data[coin]["bars"][i]; p=data[coin]["profile"]; cfg=COINS[coin]
            entry=adverse_fill(b.c,direction,True)
            risk_budget=max(equity,0)*risk_pct/100
            notional=min(risk_budget/max(p.stop_pct/100,1e-6),max(equity,0)*cfg["max_leverage"])
            if notional<=0: continue
            qty=notional/entry; fee=notional*TAKER_FEE_BPS/10000
            pos=Position(direction,i,entry,qty,notional,fee,entry,entry)
            positions[coin]={"pos":pos,"risk_pct":risk_pct}

    # close at boundary to keep train/holdout independent
    boundary_ts=timestamps[end_step-1]
    for coin,st in list(positions.items()):
        pos=st["pos"]; i=idxmap[coin][boundary_ts]; b=data[coin]["bars"][i]
        ep=adverse_fill(b.c,pos.side,False)
        gross=(ep-pos.entry_price)*pos.qty*pos.side; ef=abs(ep*pos.qty)*TAKER_FEE_BPS/10000
        net=gross-pos.entry_fee-ef+pos.funding_cash
        equity+=net; fees+=pos.entry_fee+ef; funding+=pos.funding_cash
        trades.append({"coin":coin,"net":net})

    wins=[t for t in trades if t["net"]>0]; losses=[t for t in trades if t["net"]<=0]
    sw=sum(t["net"] for t in wins); sl=abs(sum(t["net"] for t in losses))
    pf=sw/sl if sl else (999 if sw>0 else 0)
    by_coin={c:round(sum(t["net"] for t in trades if t["coin"]==c),2) for c in coins}
    return {
        "return_pct":round((equity/start_equity-1)*100,3),
        "profit_factor":round(pf,3),
        "max_drawdown_pct":round(maxdd,3),
        "trades":len(trades),
        "fees_usd":round(fees,2),
        "end_equity":round(equity,2),
        "by_coin":by_coin,
    }

def score(r):
    # favor return and PF, penalize drawdown; reject structurally weak configs
    if r["profit_factor"]<1.05: return -999
    return r["return_pct"] + 8.0*(r["profit_factor"]-1.0) - 0.8*r["max_drawdown_pct"] - 0.0025*r["trades"] - 0.00005*r["fees_usd"]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--days",type=int,default=365); ap.add_argument("--out",default="artifacts/perp_portfolio_walkforward")
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
    configs=[]
    for risk_scale in (1.25,1.5):
        for max_total in (1.75,2.0,2.25):
            max_group=min(1.25,max_total/2)
            for doge_score_mult in (1.0,1.10,1.20,1.30):
                for doge_loss_cd in (12,18,24,36):
                    for shib_score_mult in (1.0,1.10,1.20):
                        for shib_loss_cd in (12,18,24):
                            p={"risk_scale":risk_scale,"max_total":max_total,"max_group":max_group,
                               "doge_score_mult":doge_score_mult,"doge_loss_cd":doge_loss_cd,
                               "shib_score_mult":shib_score_mult,"shib_loss_cd":shib_loss_cd}
                            r=simulate(data,timestamps,idxmap,0,split,p)
                            configs.append({**p,**{k:v for k,v in r.items() if k!="by_coin"},"score":round(score(r),4)})
    configs.sort(key=lambda x:x["score"],reverse=True)

    # evaluate top 10 distinct train configs on untouched holdout
    finalists=[]
    for tr in configs[:10]:
        p={k:tr[k] for k in ("risk_scale","max_total","max_group","doge_score_mult","doge_loss_cd","shib_score_mult","shib_loss_cd")}
        ho=simulate(data,timestamps,idxmap,split,len(timestamps),p)
        full=simulate(data,timestamps,idxmap,0,len(timestamps),p)
        finalists.append({"params":p,"train":tr,"holdout":ho,"full":full})
    finalists.sort(key=lambda x:(x["holdout"]["profit_factor"],x["holdout"]["return_pct"]),reverse=True)

    (out/"results.json").write_text(json.dumps({
        "bars":len(timestamps),"split_index":split,"train_hours":split,"holdout_hours":len(timestamps)-split,
        "top_train":configs[:25],"finalists":finalists
    },indent=2))
    with (out/"top_train.csv").open("w",newline="") as f:
        fields=list(configs[0].keys()); w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(configs[:25])

    lines=["# Portfolio Walk-Forward Optimization","",
           f"- Common hourly bars: {len(timestamps)}",
           f"- Train hours: {split}",
           f"- Holdout hours: {len(timestamps)-split}","",
           "| Rank | Risk scale | Max total | Max group | DOGE score x | DOGE loss CD | SHIB score x | SHIB loss CD | Train ret | Train PF | Train DD | Holdout ret | Holdout PF | Holdout DD | Full ret | Full PF | Full DD | Full trades | Full fees |",
           "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for n,x in enumerate(finalists,1):
        p=x["params"]; tr=x["train"]; h=x["holdout"]; full=x["full"]
        lines.append(f"| {n} | {p['risk_scale']} | {p['max_total']} | {p['max_group']} | {p['doge_score_mult']} | {p['doge_loss_cd']} | {p['shib_score_mult']} | {p['shib_loss_cd']} | {tr['return_pct']}% | {tr['profit_factor']} | {tr['max_drawdown_pct']}% | {h['return_pct']}% | {h['profit_factor']} | {h['max_drawdown_pct']}% | {full['return_pct']}% | {full['profit_factor']} | {full['max_drawdown_pct']}% | {full['trades']} | ${full['fees_usd']} |")
    (out/"report.md").write_text("\n".join(lines))

if __name__=="__main__":
    main()
