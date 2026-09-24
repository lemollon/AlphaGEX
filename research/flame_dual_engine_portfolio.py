"""Combined Flame portfolio test: Research engine + EBB engine, rules kept separate.
Research: 12:00 ET decision, efficiency >= .30, $2-wide credit-selected spread,
50% target / 2x stop / 15:45 ET time exit.
EBB: 14:05 ET decision, prior-session VIX decay <= .80, short $1 below SPY,
$2 wide, no stop/target, settle at SPY close.
Shared governor: one Flame account, one subscription, whole contracts, portfolio
open-risk cap. Research only; no live changes.
"""
from __future__ import annotations
import csv, io, json, os, threading, urllib.request, hashlib
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal as D, ROUND_HALF_UP
from http.server import HTTPServer
import flame_two_entry_optimized as base

core=base.core
U=core.U
core.SPEC.update({
 "id":"flame-dual-engine-portfolio-102d-20260924",
 "start":"2025-01-01","end":"2025-05-30",
 "closures":["2025-01-01","2025-01-09","2025-01-20","2025-02-17","2025-04-18","2025-05-26"],
 "expected_sessions":102,"max_requests":500,"deadline_seconds":3600,
 "scope":"Research and EBB independent engines on one $2k Flame account; retrospective only",
 "no_saved_price_inputs":True,"no_previous_trade_inputs":True,
})
VIX_URL="https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
EBB_DECISION=845
EBB_WIDTH=2
EBB_OTM=1
EBB_VIX_CEILING=D("0.80")
EBB_MIN_CREDIT=D("0.10")
FEE_CENTS=core.SPEC["fee_cents_roundtrip"]

def emit(event,**kw): core.emit(event,**kw)

def get_vix():
 req=urllib.request.Request(VIX_URL,headers={"User-Agent":"AlphaGEX-Flame-Research/1.0","Cache-Control":"no-cache"})
 raw=urllib.request.urlopen(req,timeout=30).read()
 rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
 vals=[]
 for r in rows:
  try:
   dt=datetime.strptime(r["DATE"],"%m/%d/%Y").date().isoformat()
   c=D(str(r["CLOSE"]))
   if c.is_finite() and c>0: vals.append((dt,c))
  except Exception: continue
 vals.sort()
 return vals,hashlib.sha256(raw).hexdigest()

def vix_gate(vix,day):
 hist=[x for x in vix if x[0]<day]
 if len(hist)<21:return {"ok":False,"reason":"vix_unknown"}
 prior=hist[-1][1]; window=max(x[1] for x in hist[-21:-1])
 if window<=0:return {"ok":False,"reason":"vix_bad_window"}
 ratio=prior/window
 return {"ok":ratio<=EBB_VIX_CEILING,"reason":None if ratio<=EBB_VIX_CEILING else "vix_decay",
         "ratio":float(ratio),"prior":float(prior),"window_max":float(window)}

def get_stock(feed,day):
 p={"symbol":"SPY","date":day,"interval":"5m","start_time":"09:30:00","end_time":"16:00:00","venue":"utp_cta"}
 fp=feed.get("/v3/stock/history/ohlc",p); out={}
 with fp.open() as f:
  for r in csv.DictReader(f):
   m=core.minute(r["timestamp"],day)
   if m==960: continue
   if not 570<=m<960 or (m-570)%5: raise core.DataError("stock_grid:"+day+":"+str(m))
   try:
    v={k:D(str(r[k]))*U for k in ["open","high","low","close"]}
    vol=D(str(r["volume"]))
   except Exception as e: raise core.DataError("stock_numeric:"+day+":"+str(m)) from e
   if not all(x.is_finite() and x>0 for x in v.values()) or not vol.is_finite() or vol<0: raise core.DataError("stock_invalid:"+day)
   out[m]=v
 exp=list(range(570,960,5))
 if sorted(out)!=exp: raise core.DataError("missing_stock_5m:"+day+":"+repr(sorted(set(exp)-set(out))[:10]))
 return out

def research_bars(stock,decision):
 return [stock[m] for m in range(570,decision,5)]

def research_eff(stock,decision=720):
 b=research_bars(stock,decision); c=[x["close"] for x in b]
 if len(c)<13:return D(0)
 travel=sum(abs(y-x) for x,y in zip(c[-13:-1],c[-12:]))
 return abs(c[-1]-c[-13])/travel if travel else D(0)

def spot(stock,decision): return stock[decision-5]["close"]

def research_trade(df):
 eff=research_eff(df.stock,720)
 if eff<D("0.30"): return None,{"reason":"efficiency","eff":str(eff)}
 q=df.snapshot(720); k=base.choose_snapshot(q,spot(df.stock,720),2)
 if k is None:return None,{"reason":"no_candidate","eff":str(eff)}
 tr=base.replay_selected(df,k,2,720)
 return tr,{"eff":str(eff),"decision":720}

def ebb_trade(df,vix_info):
 if not vix_info["ok"]: return None,{"reason":vix_info["reason"],**vix_info}
 s=spot(df.stock,EBB_DECISION)/U
 short_dollars=(s-D(EBB_OTM)).quantize(D("1"),rounding=ROUND_HALF_UP)
 k=int(short_dollars*U); lk=k-EBB_WIDTH*U
 # Production structure is fixed by spot; historical execution uses next-minute natural leg quotes.
 start=EBB_DECISION+1
 # EBB needs only the executable 14:06 ET quote. One exact-minute chain snapshot
 # supplies both fixed strikes and is equivalent to two separate leg requests.
 q=df.snapshot(start)
 a=q.get(k); b=q.get(lk)
 if a is None or b is None:return None,{"reason":"no_entry_quote",**vix_info}
 credit=a[0]-b[1]
 if credit < int(EBB_MIN_CREDIT*U):return None,{"reason":"min_credit","credit":float(D(credit)/U),**vix_info}
 close=df.stock[955]["close"]
 intrinsic=max(D(0),min(D(EBB_WIDTH)*U,D(k)-close))
 pnl=int(credit-intrinsic-FEE_CENTS)
 risk=int(EBB_WIDTH*U-credit+FEE_CENTS)
 return {"status":"trade","reason":"settlement","decision_minute_et":EBB_DECISION,"entry_minute_et":start,
         "exit_minute_et":960,"short_units":k,"width":EBB_WIDTH,"credit_units":credit,
         "risk_cents":risk,"net_cents":pnl,"spy_close_units":str(close),
         "intrinsic_units":int(intrinsic)},{"ratio":vix_info.get("ratio"),"prior":vix_info.get("prior"),"window_max":vix_info.get("window_max")}

def summarize(days,daily,mode,cap_pct):
 eq=200000; peak=eq; maxdd=0; profit=0; bills=5000*len(set(d[:7] for d in days))
 counts=Counter(); blocked=Counter(); engine=Counter(); engine_pnl=Counter()
 for day in days:
  r=daily[day]["research"]; e=daily[day]["ebb"]
  # Research decision occurs first.
  active_r=False
  if r and r.get("status")=="trade":
   if r["risk_cents"]*100 <= eq*cap_pct:
    active_r=True; counts["trades"]+=1; engine["research"]+=1; engine_pnl["research"]+=r["net_cents"]
   else: blocked["research_risk"]+=1
  # If Research closes before EBB decision, realize it before evaluating EBB.
  if active_r and r["exit_minute_et"]<=EBB_DECISION:
   eq+=r["net_cents"]; profit+=r["net_cents"]; peak=max(peak,eq); maxdd=max(maxdd,peak-eq); active_r=False
  if e and e.get("status")=="trade":
   openrisk=(r["risk_cents"] if active_r else 0)+e["risk_cents"]
   if openrisk*100 <= eq*cap_pct:
    counts["trades"]+=1; engine["ebb"]+=1; engine_pnl["ebb"]+=e["net_cents"]
    eq+=e["net_cents"]; profit+=e["net_cents"]; peak=max(peak,eq); maxdd=max(maxdd,peak-eq)
   else: blocked["ebb_portfolio_risk"]+=1
  # Research settles in accounting if it remained open past EBB decision.
  if active_r:
   eq+=r["net_cents"]; profit+=r["net_cents"]; peak=max(peak,eq); maxdd=max(maxdd,peak-eq)
  # Outcome counts use accepted trades only via engine P&L summary elsewhere.
 # Re-scan accepted logic for W/L is omitted from cap summary; P&L is authoritative.
 return {"mode":mode,"cap_pct":cap_pct,"sessions":len(days),"trades":counts["trades"],
         "research_trades":engine["research"],"ebb_trades":engine["ebb"],
         "research_pnl":core.money(engine_pnl["research"]),"ebb_pnl":core.money(engine_pnl["ebb"]),
         "trading_net":core.money(profit),"subscription":core.money(bills),
         "customer_net":core.money(profit-bills),"ending_equity":core.money(eq),
         "max_closed_equity_drawdown":core.money(maxdd),"blocked":dict(blocked),
         "qualification":"RETROSPECTIVE_ONLY"}

def engine_alone(days,daily,key):
 pnl=0;n=w=l=0; worst=0
 for d in days:
  t=daily[d][key]
  if t and t.get("status")=="trade":
   n+=1;p=t["net_cents"];pnl+=p;worst=min(worst,p)
   if p>0:w+=1
   elif p<0:l+=1
 bills=5000*len(set(d[:7] for d in days))
 return {"engine":key,"trades":n,"wins":w,"losses":l,"win_rate":round(100*w/n,1) if n else 0,
         "trading_net":core.money(pnl),"subscription":core.money(bills),"customer_net":core.money(pnl-bills),
         "worst_trade":core.money(worst),"qualification":"RETROSPECTIVE_ONLY"}

def execute():
 core.STATE["stage"]="running"; feed=core.Feed(); days=core.session_days(); daily={}
 try:
  vix,vix_sha=get_vix()
  emit("dual_spec",configuration=core.SPEC,vix_source=VIX_URL,vix_sha256=vix_sha,
       research_rules={"decision_et":720,"efficiency_min":0.30,"target_pct":50,"stop_mult":2,"width":2},
       ebb_rules={"decision_et":845,"vix_decay_ceiling":0.80,"otm_dollars":1,"width":2,"exit":"close_settlement","stop":None},
       portfolio_caps=[10,20],live_changed=False)
  for day in days:
   stock=get_stock(feed,day)
   df=base.DayFeed(feed,day,stock)
   r,rm=research_trade(df)
   vg=vix_gate(vix,day)
   e,em=ebb_trade(df,vg)
   daily[day]={"research":r,"research_meta":rm,"ebb":e,"ebb_meta":em}
   emit("dual_day",day=day,research=r,research_meta=rm,ebb=e,ebb_meta=em)
  emit("dual_engine_summary",**engine_alone(days,daily,"research"))
  emit("dual_engine_summary",**engine_alone(days,daily,"ebb"))
  for cap in (10,20): emit("dual_portfolio_summary",**summarize(days,daily,"combined",cap))
  core.STATE["stage"]="complete";emit("dual_complete",days=len(days),provider_requests=feed.n,prior_inputs=0,vix_sha256=vix_sha)
 except Exception as e:
  core.STATE["stage"]="failed";emit("dual_failed",kind=type(e).__name__,reason=str(e)[:500],completed_days=len(daily),provider_requests=feed.n)

if __name__=="__main__":
 if os.getenv("FLAME_FRESH_MODE")=="dual-engine-102d":
  threading.Thread(target=execute,daemon=True).start()
 HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),core.Handler).serve_forever()
