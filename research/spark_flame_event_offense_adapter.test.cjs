'use strict';
const assert=require('node:assert/strict');
const A=require('./spark_flame_event_offense_adapter.cjs');
const scenarios=require('./spark_flame_event_offense.cjs').grid();

function bars(){
 const spy=new Map(),vix=new Map();
 for(let m=540;m<960;m++){spy.set(m,{open:100,high:100.05,low:99.95,close:100});vix.set(m,20);}
 // Two completed closes below the old range and a 0.30% five-minute decline.
 for(const [m,c] of [[600,100],[601,99.99],[602,99.98],[603,99.97],[604,99.80],[605,99.70],[606,99.60]])spy.set(m,{open:c,high:c+.03,low:c-.03,close:c});
 for(let m=602;m<=606;m++)vix.set(m,20.8);
 return {spy,vix};
}
function quote(signal,minute){
 if(minute===607)return null; // proves entry waits beyond the signal bar.
 if(minute===608)return {buy:{bid:.78,ask:.82,bidSize:5,askSize:5},sell:{bid:.18,ask:.22,bidSize:5,askSize:5}};
 if(minute<608)return null;
 return {buy:{bid:1.22,ask:1.26,bidSize:5,askSize:5},sell:{bid:.32,ask:.36,bidSize:5,askSize:5}};
}
const scenario=scenarios.find(x=>x.id==='breakout_all_0.01_0.5_0_3_hold');
assert(scenario);
const {spy,vix}=bars();
const runner=require('./flame_event_offense_sweep_20261002.cjs');
const mapped=[...runner.quoteMap([{timestamp:'2026-09-28T10:00:00',bid:.10,ask:.12,bid_size:7,ask_size:9}],'2026-09-28').values()][0];
assert.equal(mapped.askSize,9);assert.equal(mapped.bidSize,7);assert.equal(mapped.ask,.12);
async function main(){
const budgetSkip=await A.runDay({scenario,events:['CPI'],spy,vix,close:615,dayStartEquity:2000,cash:2000,host:{reservedMargin:500},quoteAt:quote});
assert.equal(budgetSkip.status,'skipped');assert.equal(budgetSkip.reason,'all_causal_entries_rejected');
assert(budgetSkip.admission.rejections.entry_risk_budget_too_small>0);
assert(budgetSkip.admission.rejections.no_executable_entry_quote>0);
const r=await A.runDay({scenario,events:['CPI'],spy,vix,close:615,dayStartEquity:20000,cash:20000,host:{reservedMargin:500},quoteAt:quote});
assert.equal(r.status,'closed');assert.equal(r.entry.entry,608);assert.equal(r.entry.n,3); // $65.40 max loss, 1% of $20k = three lots.
assert.equal(r.feeModel.roundTripPerSpread,1.4);
assert.equal(Math.round((r.cashAfter-r.cashBefore)*100)/100,r.pnl);
// A rejected earlier candidate must not suppress a later affordable entry.
const retryCalls=[];
const retryQuote=(signal,minute)=>{
 retryCalls.push(minute);
 if(minute<608)return quote(signal,minute);
 return {buy:{bid:.11,ask:.13,bidSize:5,askSize:5},sell:{bid:.02,ask:.04,bidSize:5,askSize:5}};
};
const retry=await A.runDay({scenario,events:['CPI'],spy,vix,close:615,dayStartEquity:2000,cash:2000,quoteAt:retryQuote});
assert.equal(retry.status,'closed');assert.equal(retry.entry.entry,608);
assert(retry.entry.maximumLoss*retry.entry.n<=20);
assert.equal(retry.admission.rejections.no_executable_entry_quote,1);
assert(retryCalls.every((m,i)=>i===0||m>=retryCalls[i-1]));
const O=require('./spark_flame_event_offense.cjs');
const signal={right:'put',buyStrike:100,sellStrike:98};
const q=quote(signal,608);
assert.equal(O.entryAssessment(signal,q,2000,2000,scenario,0,A.FEES).reason,'entry_risk_budget_too_small');
assert.equal(O.entryAssessment(signal,q,20000,10,scenario,0,A.FEES).reason,'entry_cash_too_small');
const combined=A.combineDay({hostPnl:-100,offense:r,cashBefore:2000});
assert.equal(combined.combinedPnl,Math.round((-100+r.pnl)*100)/100);
assert.throws(()=>A.combineDay({hostPnl:NaN,offense:r,cashBefore:2000}),/combined_ledger_inputs_invalid/);
console.log(JSON.stringify({passed:true,cases:'causal next-quote entry, explicit two-leg side fees, budget/cash gate, chronological cash reconciliation, no baseline-PnL reuse'}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
