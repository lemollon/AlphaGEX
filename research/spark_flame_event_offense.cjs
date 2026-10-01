/* Pure research components. No network, orders, account persistence or live logic.
 * Minute keys identify bar starts. A signal at t uses observations <=t-1.
 * The adapter must fetch authentic synchronized quotes and replay cash/margin.
 */
'use strict';
const round=x=>Math.round((x+Number.EPSILON)*100)/100;
function eventAllows(scope,events){
 return scope==='all'||(scope==='fed'?events.includes('FOMC'):events.some(x=>['FOMC','CPI','PAYROLLS'].includes(x)));
}
function entrySignal(s,t,spy,vix,events,host=null){
 if(t>930||!eventAllows(s.scope,events))return null;
 let start=570,lookback=15;
 if(s.family==='post_release'){
  if(events.includes('FOMC'))start=840+s.wait;
  else if(events.some(x=>['CPI','PAYROLLS'].includes(x)))start=570+s.wait;
  else return null;
  lookback=5;
 }
 if(s.family==='overlay'&&(!host||host.right!=='put'||t<=host.entry))return null;
 if(t<start+2)return null;
 const history=[];
 for(let m=t-lookback-2;m<=t-3;m++){
  const b=spy.get(m);if(!b||![b.high,b.low,b.close].every(x=>Number.isFinite(x)&&x>0))return null;
  history.push(b);
 }
 const a=spy.get(t-2),b=spy.get(t-1),old=spy.get(t-6),v=vix.get(t-1),vo=vix.get(t-6);
 if(!a||!b||!old||!(v>0&&vo>0))return null;
 const lo=Math.min(...history.map(x=>x.low)),hi=Math.max(...history.map(x=>x.high));
 const spy5Pct=(b.close/old.close-1)*100,vix5Pct=(v/vo-1)*100;
 let right=null;
 if(a.close<lo&&b.close<lo&&spy5Pct<=-.25&&vix5Pct>=s.vixRise)right='put';
 if(s.family!=='overlay'&&a.close>hi&&b.close>hi&&spy5Pct>=.25&&vix5Pct<=0)right='call';
 if(!right)return null;
 // Contract identity is fixed using the last known close, not the next bar.
 const buyStrike=Math.floor(b.close+.5),sellStrike=buyStrike+(right==='put'?-2:2);
 return {decisionMinute:t,observedThrough:t-1,right,buyStrike,sellStrike,spy5Pct,vix5Pct,rangeLow:lo,rangeHigh:hi};
}
function executable(quote,n=1){
 if(!quote)return false;
 for(const x of [quote.buy,quote.sell])if(!x||![x.bid,x.ask,x.bidSize,x.askSize].every(Number.isFinite)||x.bid<0||x.ask<=0||x.ask<x.bid)return false;
 return quote.buy.askSize>=n&&quote.sell.bidSize>=n;
}
function entryOrder(signal,quote,dayStartEquity,availableCash,s,slip,fees){
 if(!executable(quote)||![fees.open,fees.close].every(x=>Number.isFinite(x)&&x>=0))return null;
 const debit=round(quote.buy.ask-quote.sell.bid+2*slip);
 if(!(debit>0&&debit<2))return null;
 const maximumLoss=round(debit*100+fees.open+fees.close);
 const budget=Math.min(dayStartEquity*s.budget,availableCash);
 const n=Math.min(Math.floor((budget+1e-8)/maximumLoss),Math.floor(quote.buy.askSize),Math.floor(quote.sell.bidSize));
 if(n<1)return null; // Never force a lot above its risk budget.
 return {...signal,n,debit,maximumLoss,fees:{...fees},reservedCash:round((debit*100+fees.open)*n)};
}
function sellValue(q,n,slip){
 if(!q)return null;
 for(const x of [q.buy,q.sell])if(!x||![x.bid,x.ask,x.bidSize,x.askSize].every(Number.isFinite)||x.bid<0||x.ask<=0||x.bid>x.ask)return null;
 if(q.buy.bidSize<n||q.sell.askSize<n)return null;
 const value=round(q.buy.bid-q.sell.ask-2*slip);
 return value>=0&&value<=2?value:null;
}
function exitTrade(order,quotes,close,s,slip){
 let trigger=null;
 for(let t=order.entry+1;t<close;t++){
  // Close signals use a completed prior minute, execution uses t or later.
  const mark=sellValue(quotes.get(t-1),order.n,slip);
  if(trigger===null&&t>order.entry+1&&mark!==null){
   if(mark>=order.debit*(1+s.target))trigger={minute:t-1,reason:'offense_target'};
   else if(mark<=order.debit*.5)trigger={minute:t-1,reason:'offense_stop'};
  }
  if(trigger===null&&s.preConference&&t===869)trigger={minute:868,reason:'pre_press_conference'};
  if(trigger===null&&t===close-3)trigger={minute:t-1,reason:'session_guard'};
  if(trigger){
   const exitValue=sellValue(quotes.get(t),order.n,slip);
   if(exitValue!==null)return {exit:t,triggerMinute:trigger.minute,reason:trigger.reason,exitValue,pnl:round(((exitValue-order.debit)*100-order.fees.open-order.fees.close)*order.n)};
  }
 }
 return {unresolved:'offense_triggered_exit_has_no_executable_quote'};
}
function grid(){
 const out=[];
 for(const family of ['breakout','post_release','overlay'])for(const scope of ['fed','major','all']){
  if(family==='post_release'&&scope==='all')continue;
  for(const budget of [.005,.01])for(const target of [.5,1])for(const wait of family==='post_release'?[5,15]:[0])for(const vixRise of family==='breakout'?[3,5]:[3]){
   out.push({id:[family,scope,budget,target,wait,vixRise].join('_'),family,scope,budget,target,wait,vixRise,preConference:false});
  }
 }
 return out;
}
module.exports={entrySignal,entryOrder,exitTrade,eventAllows,grid};
