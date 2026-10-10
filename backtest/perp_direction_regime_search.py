#!/usr/bin/env python3
"""Direction/regime refinement for the best free-data perp profiles."""

from __future__ import annotations
import argparse, csv, importlib.util, json, math, sys
from dataclasses import asdict, replace
from pathlib import Path

_BASE = Path(__file__).with_name("perp_coin_profile_search.py")
_spec = importlib.util.spec_from_file_location("perp_coin_profile_search", _BASE)
_mod = importlib.util.module_from_spec(_spec); sys.modules[_spec.name]=_mod; _spec.loader.exec_module(_mod)

Bar=_mod.Bar; COINS=_mod.COINS; Result=_mod.Result; Position=_mod.Position
TAKER_FEE_BPS=_mod.TAKER_FEE_BPS; load_bars=_mod.load_bars; adverse_fill=_mod.adverse_fill
rolling_std=_mod.rolling_std; profiles_for=_mod.profiles_for; signals=_mod.signals

BASE_NAMES={
 "BTC":["breakout48_macro","breakout24_strict"],
 "ETH":["breakout24_strict","breakout48_macro"],
 "SOL":["fast_macro","breakout24"],
 "AVAX":["breakout48","fast_stricter"],
 "XRP":["fast_stricter","fast_macro"],
 "DOGE":["breakout48","slow_strict"],
 "SHIB":["breakout24","breakout48"],
}
SIDES=("both","long","short")
REGIMES=("all","vol_expand","vol_compress")

def get_profile(coin,name):
    for p in profiles_for(coin):
        if p.name==name: return p
    raise KeyError((coin,name))

def regime_mask(bars, regime):
    if regime=="all": return [True]*len(bars)
    closes=[b.c for b in bars]
    rets=[0.0]+[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))]
    v24=rolling_std(rets,24); v72=rolling_std(rets,72)
    out=[]
    for a,b in zip(v24,v72):
        if not a or not b:
            out.append(False); continue
        ratio=a/b
        out.append(ratio>=1.10 if regime=="vol_expand" else ratio<=0.90)
    return out

def run(coin,bars,p,side_mode,regime):
    cfg=COINS[coin]; start=cfg["capital"]; equity=start; peak=start; maxdd=0.0
    sig=signals(bars,p); mask=regime_mask(bars,regime)
    pos=None; next_entry=0; trades=[]; fees=funding=gross_total=0.0
    for i,b in enumerate(bars):
        if pos:
            pos.funding_cash += -pos.side*pos.notional*b.funding
            fav=((b.h/pos.entry_price)-1)*100 if pos.side==1 else ((pos.entry_price/b.l)-1)*100
            pos.mfe_pct=max(pos.mfe_pct,fav); pos.hwm=max(pos.hwm,b.h); pos.lwm=min(pos.lwm,b.l)
            hold=i-pos.entry_idx
            adverse=((b.l/pos.entry_price)-1)*100 if pos.side==1 else ((pos.entry_price/b.h)-1)*100
            pnlpct=((b.c/pos.entry_price)-1)*100*pos.side
            ep=None
            if adverse <= -p.stop_pct:
                raw=pos.entry_price*(1-p.stop_pct/100) if pos.side==1 else pos.entry_price*(1+p.stop_pct/100)
                ep=adverse_fill(raw,pos.side,False)
            elif pnlpct >= p.target_pct:
                raw=pos.entry_price*(1+p.target_pct/100) if pos.side==1 else pos.entry_price*(1-p.target_pct/100)
                ep=adverse_fill(raw,pos.side,False)
            else:
                if not pos.trailing_active and pos.mfe_pct>=p.trail_activation_pct:
                    pos.trailing_active=True; d=pos.entry_price*p.trail_pct/100
                    pos.trail_stop=max(pos.entry_price,pos.hwm-d) if pos.side==1 else min(pos.entry_price,pos.lwm+d)
                if pos.trailing_active:
                    d=pos.entry_price*p.trail_pct/100
                    if pos.side==1:
                        pos.trail_stop=max(pos.trail_stop or pos.entry_price,pos.hwm-d,pos.entry_price)
                        if b.l<=pos.trail_stop: ep=adverse_fill(pos.trail_stop,pos.side,False)
                    else:
                        pos.trail_stop=min(pos.trail_stop or pos.entry_price,pos.lwm+d,pos.entry_price)
                        if b.h>=pos.trail_stop: ep=adverse_fill(pos.trail_stop,pos.side,False)
                if ep is None and hold>=p.max_hold_hours: ep=adverse_fill(b.c,pos.side,False)
            if ep is not None:
                gross=(ep-pos.entry_price)*pos.qty*pos.side; ef=abs(ep*pos.qty)*TAKER_FEE_BPS/10000
                net=gross-pos.entry_fee-ef+pos.funding_cash; equity+=net
                gross_total+=gross; fees+=pos.entry_fee+ef; funding+=pos.funding_cash
                trades.append({"net":net,"hold":hold}); peak=max(peak,equity)
                if peak>0: maxdd=max(maxdd,(peak-equity)/peak*100)
                next_entry=i+p.cooldown_hours; pos=None
        if pos is None and i>=next_entry and mask[i]:
            direction,score=sig[i]
            if direction==0: continue
            if side_mode=="long" and direction<0: continue
            if side_mode=="short" and direction>0: continue
            entry=adverse_fill(b.c,direction,True)
            rb=max(equity,0)*p.risk_pct/100
            notional=min(rb/max(p.stop_pct/100,1e-6),max(equity,0)*cfg["max_leverage"])
            if notional<=0: continue
            qty=notional/entry; fee=notional*TAKER_FEE_BPS/10000
            pos=Position(direction,i,entry,qty,notional,fee,entry,entry)
    if pos:
        b=bars[-1]; ep=adverse_fill(b.c,pos.side,False); gross=(ep-pos.entry_price)*pos.qty*pos.side
        ef=abs(ep*pos.qty)*TAKER_FEE_BPS/10000; net=gross-pos.entry_fee-ef+pos.funding_cash
        equity+=net; gross_total+=gross; fees+=pos.entry_fee+ef; funding+=pos.funding_cash
        trades.append({"net":net,"hold":len(bars)-1-pos.entry_idx})
    wins=[t for t in trades if t["net"]>0]; losses=[t for t in trades if t["net"]<=0]
    sw=sum(t["net"] for t in wins); sl=abs(sum(t["net"] for t in losses)); pf=sw/sl if sl else (999 if sw>0 else 0)
    net=equity-start
    return Result(coin=coin,strategy=f"{p.name}:{side_mode}:{regime}",start_equity=round(start,2),end_equity=round(equity,2),
      return_pct=round((equity/start-1)*100,2),max_drawdown_pct=round(maxdd,2),trades=len(trades),wins=len(wins),losses=len(losses),
      win_rate_pct=round(len(wins)/len(trades)*100,2) if trades else 0,profit_factor=round(pf,3),
      expectancy_usd=round(net/len(trades),2) if trades else 0,avg_trade_pct=round(net/start*100/len(trades),4) if trades else 0,
      avg_hold_hours=round(sum(t["hold"] for t in trades)/len(trades),2) if trades else 0,fees_usd=round(fees,2),
      funding_usd=round(funding,2),gross_pnl_usd=round(gross_total,2),net_pnl_usd=round(net,2))

def robust(rows):
    pos=sum(1 for r in rows if r.return_pct>0 and r.profit_factor>1)
    s=sum(r.return_pct*.4+(min(r.profit_factor,2)-1)*35-r.max_drawdown_pct*.3 for r in rows)/len(rows)
    s+=pos*15
    if pos<2: s-=20
    return round(s,3)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--windows",default="30,90,180"); ap.add_argument("--out",default="artifacts/perp_direction_regime")
    a=ap.parse_args(); windows=sorted(int(x) for x in a.windows.split(",")); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    allrows=[]; winners=[]
    for coin,cfg in COINS.items():
        bars=load_bars(cfg["hl"],max(windows)); ranked=[]
        for base in BASE_NAMES[coin]:
            p=get_profile(coin,base)
            for side in SIDES:
                for regime in REGIMES:
                    rows=[]
                    for d in windows:
                        cut=bars[-1].ts-d*24*60*60*1000; sub=[b for b in bars if b.ts>=cut]
                        r=run(coin,sub,p,side,regime); rows.append(r); x=asdict(r); x["window_days"]=d; allrows.append(x)
                    ranked.append((robust(rows),base,side,regime,rows))
        ranked.sort(key=lambda x:x[0],reverse=True)
        sc,base,side,regime,rows=ranked[0]
        winners.append({"coin":coin,"base":base,"side":side,"regime":regime,"score":sc,
            "positive_windows":sum(1 for r in rows if r.return_pct>0 and r.profit_factor>1),
            "return_30d":rows[windows.index(30)].return_pct,"return_90d":rows[windows.index(90)].return_pct,
            "return_180d":rows[windows.index(180)].return_pct,"pf_180d":rows[windows.index(180)].profit_factor,
            "dd_180d":rows[windows.index(180)].max_drawdown_pct,"trades_180d":rows[windows.index(180)].trades,
            "runner_up":f"{ranked[1][1]}:{ranked[1][2]}:{ranked[1][3]}"})
    with (out/"all_results.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(allrows[0].keys())); w.writeheader(); w.writerows(allrows)
    with (out/"winners.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(winners[0].keys())); w.writeheader(); w.writerows(winners)
    (out/"winners.json").write_text(json.dumps(winners,indent=2))
    lines=["# Direction and Regime Refinement","",
      "| Coin | Base | Side | Regime | +Windows | 30d | 90d | 180d | PF | DD | Trades |",
      "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for x in winners: lines.append(f"| {x['coin']} | {x['base']} | {x['side']} | {x['regime']} | {x['positive_windows']}/3 | {x['return_30d']}% | {x['return_90d']}% | {x['return_180d']}% | {x['pf_180d']} | {x['dd_180d']}% | {x['trades_180d']} |")
    (out/"report.md").write_text("\n".join(lines))
if __name__=="__main__": main()
