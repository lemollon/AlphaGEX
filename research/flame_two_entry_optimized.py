"""Optimized fresh-source SPY two-entry test; research only.
Same strategy rules as flame_two_entry_102d.py, but downloads only:
  - full SPY stock day
  - option chain snapshot at actual decision times
  - the two selected option legs for the open trade
No saved price inputs, no prior trade outputs.
"""
from __future__ import annotations
import csv, json, os, threading, hashlib
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal as D
from http.server import HTTPServer
import flame_reset_stock as patched

core=patched.core
U=core.U
core.SPEC.update({
 "id":"flame-two-entry-optimized-102d-20260923",
 "start":"2025-01-01","end":"2025-05-30",
 "closures":["2025-01-01","2025-01-09","2025-01-20","2025-02-17","2025-04-18","2025-05-26"],
 "expected_sessions":102,"widths_dollars":[2],"profiles_units":{"natural":0},
 "decision_et_minute":720,"flat_et_minute":945,"max_requests":500,"deadline_seconds":3600,
 "scope":"retrospective sequential-entry comparison, optimized fresh acquisition, not unseen validation",
 "no_saved_price_inputs":True,"no_previous_trade_inputs":True,
})
MIN_EFF=D("0.30"); LATEST_SECOND_DECISION=900; COOLDOWN_MINUTES=5

def hhmm(m):
 h=m//60; mm=m%60
 return f"{h:02d}:{mm:02d}:00"

def full_stock_rows(rows,day):
 out={}
 for r in rows:
  m=core.minute(r["timestamp"],day)
  if m==core.SPEC["flat_et_minute"]: continue
  if not 570<=m<core.SPEC["flat_et_minute"]: raise core.DataError("stock_outside_rth:"+day+":"+str(m))
  if r.get("symbol","SPY")!="SPY" or m in out: raise core.DataError("stock_identity_or_duplicate")
  v={k:D(str(r[k]))*U for k in ["open","high","low","close"]}; vol=D(str(r["volume"]))
  if not all(x.is_finite() and x>0 for x in v.values()) or not vol.is_finite() or vol<0: raise core.DataError("stock_invalid")
  eps=D("0.000001"); top=max(v["open"],v["close"]); bot=min(v["open"],v["close"])
  if v["low"]-bot>eps or top-v["high"]>eps: raise core.DataError("stock_invalid_ohlc")
  if v["low"]>bot:v["low"]=bot
  if v["high"]<top:v["high"]=top
  out[m]=v
 exp=list(range(570,core.SPEC["flat_et_minute"]))
 if sorted(out)!=exp: raise core.DataError("missing_stock_minutes:"+day)
 return out

def bars5(stock,decision):
 b=[]
 for m in range(570,decision,5):
  if m+5>decision:break
  xs=[stock[j] for j in range(m,m+5)]
  b.append({"open":xs[0]["open"],"close":xs[-1]["close"],"high":max(x["high"] for x in xs),"low":min(x["low"] for x in xs)})
 return b

def efficiency_at(stock,decision):
 b=bars5(stock,decision)
 if len(b)<13:return D(0)
 c=[x["close"] for x in b]; diff=c[-1]-c[-13]
 travel=sum(abs(y-x) for x,y in zip(c[-13:-1],c[-12:]))
 return D(abs(diff))/D(travel) if travel else D(0)

def spot_at(stock,decision): return stock[decision-1]["close"]

def parse_snapshot(rows,day,decision):
 q={}
 for r in rows:
  if r.get("symbol")!="SPY" or r.get("right","").lower() not in ("p","put"): raise core.DataError("wrong_option_identity")
  if r.get("expiration","")[:10].replace("-","")!=day.replace("-",""): raise core.DataError("wrong_expiration")
  m=core.minute(r["timestamp"],day)
  if m!=decision: raise core.DataError("wrong_snapshot_minute")
  k=core.units(r["strike"])
  try:
   bid,ask=core.units(r["bid"]),core.units(r["ask"]); bs,az=D(str(r["bid_size"])),D(str(r["ask_size"]))
   if not bs.is_finite() or not az.is_finite() or bid<0 or ask<=0 or bid>ask or bs<1 or az<1: continue
  except Exception: continue
  q[k]=(bid,ask,int(bs),int(az))
 return q

def choose_snapshot(q,spot,w):
 choices=[]; lower=spot-core.SPEC["short_strike_search_dollars_below"]*U
 for k,s in q.items():
  if not lower<=k<spot:continue
  l=q.get(k-w*U)
  if l is None:continue
  credit=s[0]-l[1]; spread=s[1]-s[0]+l[1]-l[0]
  if w*U*core.SPEC["credit_min_pct_width"]<=100*credit<=w*U*core.SPEC["credit_max_pct_width"] and spread<=core.SPEC["max_combined_quote_width_units"]:
   choices.append((abs(100*credit-w*U*core.SPEC["credit_target_pct_width"]),spread,k))
 return min(choices)[2] if choices else None

def parse_leg(rows,day,k):
 out={}
 for r in rows:
  if r.get("symbol")!="SPY": raise core.DataError("wrong_leg_symbol")
  if core.units(r["strike"])!=k: raise core.DataError("wrong_leg_strike")
  m=core.minute(r["timestamp"],day)
  try:
   bid,ask=core.units(r["bid"]),core.units(r["ask"]); bs,az=D(str(r["bid_size"])),D(str(r["ask_size"]))
   if not bs.is_finite() or not az.is_finite() or bid<0 or ask<=0 or bid>ask or bs<1 or az<1: continue
  except Exception: continue
  out[m]=(bid,ask,int(bs),int(az))
 return out

class DayFeed:
 def __init__(self,feed,day,stock):
  self.feed=feed;self.day=day;self.stock=stock;self.snap={};self.legs={}
 def snapshot(self,m):
  if m in self.snap:return self.snap[m]
  p={"symbol":"SPY","date":self.day,"expiration":self.day,"right":"put","strike":"*","interval":"1m","start_time":hhmm(m),"end_time":hhmm(m)}
  fp=self.feed.get("/v3/option/history/quote",p)
  with fp.open() as f:q=parse_snapshot(csv.DictReader(f),self.day,m)
  self.snap[m]=q;return q
 def leg(self,k,start):
  key=(k,start)
  if key in self.legs:return self.legs[key]
  p={"symbol":"SPY","date":self.day,"expiration":self.day,"right":"put","strike":str(D(k)/U),"interval":"1m","start_time":hhmm(start),"end_time":hhmm(core.SPEC["flat_et_minute"])}
  fp=self.feed.get("/v3/option/history/quote",p)
  with fp.open() as f:d=parse_leg(csv.DictReader(f),self.day,k)
  self.legs[key]=d;return d

def replay_selected(df,k,w,decision):
 t=decision+1;end=core.SPEC["flat_et_minute"];short=df.leg(k,t);long=df.leg(k-w*U,t)
 def mk(m):
  s=short.get(m);l=long.get(m)
  if s is None or l is None:return None
  return (s[0]-l[1],s[1]-l[0],s[1]-s[0]+l[1]-l[0],s,l)
 p=mk(t)
 if p is None:return {"status":"skip","reason":"no_entry_quote"}
 credit=p[0]
 if not w*U*core.SPEC["credit_min_pct_width"]<=100*credit<=w*U*core.SPEC["credit_max_pct_width"]:return {"status":"skip","reason":"entry_credit_changed"}
 if p[2]>core.SPEC["max_combined_quote_width_units"]:return {"status":"skip","reason":"entry_spread_widened"}
 fee=core.SPEC["fee_cents_roundtrip"];risk=w*U-credit+fee
 base={"short_units":k,"width":w,"credit_units":credit,"risk_cents":risk,"decision_minute_et":decision,"entry_minute_et":t}
 worst=0;best=0;within=0
 for m in range(t,end):
  q=mk(m)
  if q is None:return {**base,"status":"unresolved","reason":"missing_open_position_quote","at_minute":m}
  debit=q[1]
  if debit<0:return {**base,"status":"unresolved","reason":"negative_synthetic_debit"}
  mark=credit-debit-fee;worst=min(worst,mark);best=max(best,mark);within=max(within,best-mark)
  reason="stop" if debit>=2*credit else "target" if debit*100<=50*credit else "time" if m==end-1 else None
  if reason:
   x=mk(m+1)
   if x is None:return {**base,"status":"unresolved","reason":"missing_exit_quote"}
   close=x[1];pnl=credit-close-fee
   return {**base,"status":"trade","reason":reason,"exit_minute_et":m+1,"debit_units":close,"net_cents":pnl,
    "worst_open_cents":min(worst,pnl),"best_open_cents":max(best,pnl),"within_trade_drawdown_cents":max(within,best-pnl)}
 raise AssertionError("missing_exit")

def candidate(df,decision):
 eff=efficiency_at(df.stock,decision)
 if eff<MIN_EFF:return None,{"reason":"efficiency","eff":str(eff)}
 q=df.snapshot(decision);k=choose_snapshot(q,spot_at(df.stock,decision),2)
 if k is None:return None,{"reason":"no_candidate","eff":str(eff)}
 tr=replay_selected(df,k,2,decision)
 return tr,{"eff":str(eff),"decision":decision}

def second(df,first,mode):
 if not first or first.get("status")!="trade" or first["reason"]=="time":return None,{"reason":"first_not_rearmed"}
 start=((first["exit_minute_et"]+COOLDOWN_MINUTES+4)//5)*5;seen_below=False
 for d in range(start,LATEST_SECOND_DECISION+1,5):
  eff=efficiency_at(df.stock,d)
  if eff<MIN_EFF:seen_below=True;continue
  if mode=="rearm" and not seen_below:continue
  q=df.snapshot(d);k=choose_snapshot(q,spot_at(df.stock,d),2)
  if k is None:continue
  tr=replay_selected(df,k,2,d)
  if tr["status"]=="skip":continue
  return tr,{"eff":str(eff),"decision":d,"seen_below":seen_below}
 return None,{"reason":"no_fresh_second_setup","seen_below":seen_below}

def summarize(days,daily,mode):
 eq=200000;peak=eq;dd=0;profit=0;n=w=l=stops=secondn=secondw=secondl=0;worst=0;months=set();rej=Counter()
 for day in days:
  months.add(day[:7])
  for idx,tr in enumerate(daily[day][mode]):
   if tr is None:continue
   if tr["status"]!="trade":rej[tr["reason"]]+=1;continue
   if tr["risk_cents"]*100>eq*core.SPEC["position_risk_pct"]:rej["risk_budget"]+=1;continue
   n+=1;p=tr["net_cents"];profit+=p;worst=min(worst,p)
   if p>0:w+=1
   elif p<0:l+=1
   if idx==1:
    secondn+=1
    if p>0:secondw+=1
    elif p<0:secondl+=1
   if tr["reason"]=="stop":stops+=1
   dd=max(dd,peak-(eq+tr["worst_open_cents"]));eq+=p;peak=max(peak,eq);dd=max(dd,peak-eq)
 bills=len(months)*core.SPEC["monthly_bill_cents"]
 return {"mode":mode,"sessions":len(days),"trades":n,"wins":w,"losses":l,"win_rate":round(100*w/n,1) if n else 0,
  "second_entries":secondn,"second_wins":secondw,"second_losses":secondl,"stops":stops,"trading_net":core.money(profit),
  "subscription":core.money(bills),"customer_net":core.money(profit-bills),"ending_equity":core.money(eq),
  "max_drawdown":core.money(dd),"worst_trade":core.money(worst),"rejections":dict(rej),"qualification":"RETROSPECTIVE_ONLY"}

def execute():
 core.STATE["stage"]="running";feed=core.Feed();days=core.session_days();daily={}
 extra={"min_efficiency":"0.30","max_entries":2,"cooldown_minutes":5,"latest_second_decision":900,"modes":["one_entry","two_recheck","two_rearm"]}
 core.emit("two_entry_opt_spec",configuration=core.SPEC,extra=extra,sha256=hashlib.sha256(json.dumps({"spec":core.SPEC,"extra":extra},sort_keys=True).encode()).hexdigest())
 try:
  for day in days:
   p={"symbol":"SPY","date":day,"interval":"1m","start_time":"09:30:00","end_time":"15:45:00","venue":"utp_cta"}
   fp=feed.get("/v3/stock/history/ohlc",p)
   with fp.open() as f:stock=full_stock_rows(csv.DictReader(f),day)
   df=DayFeed(feed,day,stock);first,m1=candidate(df,720);r,m2=second(df,first,"recheck");a,m3=second(df,first,"rearm")
   daily[day]={"one_entry":[first],"two_recheck":[first,r],"two_rearm":[first,a]}
   core.emit("two_entry_opt_day",day=day,first=first,first_meta=m1,second_recheck=r,second_recheck_meta=m2,second_rearm=a,second_rearm_meta=m3)
  totals=[summarize(days,daily,m) for m in ["one_entry","two_recheck","two_rearm"]]
  for x in totals:core.emit("two_entry_opt_summary",**x)
  core.STATE["stage"]="complete";core.emit("two_entry_opt_complete",days=len(days),provider_requests=feed.n,prior_inputs=0)
 except Exception as e:
  core.STATE["stage"]="failed";core.emit("two_entry_opt_failed",kind=type(e).__name__,reason=str(e)[:400],completed_days=len(daily),provider_requests=feed.n)

if __name__=="__main__":
 if os.getenv("FLAME_FRESH_MODE")=="two-entry-opt-102d":
  threading.Thread(target=execute,daemon=True).start()
 HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),core.Handler).serve_forever()
