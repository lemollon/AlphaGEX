'use strict';
const assert=require('node:assert/strict');
const A=require('./spark_flame_event_offense_adapter.cjs');
const scenarios=require('./spark_flame_event_offense.cjs').grid();

function bars(){
 const spy=new Map(),vix=new Map();
 for(let m=540;m<960;m++){spy.set(m,{open:100,high:100.05,low:99.95,close:100});vix.set(m,20);}
 // Two completed closes below the old range and a 0.30% five-minute decline.
 for(const [m,c] of [[600,100],[601,99.99],[602,99.98],[603,99.97],[604,99.80],[605,99.70]])spy.set(m,{open:c,high:c+.03,low:c-.03,close:c});
 for(let m=601;m<=605;m++)vix.set(m,20.8);
 return {spy,vix};
}
function quote(signal,minute){
 if(minute===606)return null; // proves entry waits beyond the signal bar.
 if(minute===607)return {buy:{bid:.78,ask:.82,bidSize:5,askSize:5},sell:{bid:.18,ask:.22,bidSize:5,askSize:5}};
 if(minute<607)return null;
 return {buy:{bid:1.22,ask:1.26,bidSize:5,askSize:5},sell:{bid:.32,ask:.36,bidSize:5,askSize:5}};
}
const scenario=scenarios.find(x=>x.id==='breakout_all_0.01_0.5_0_3_hold');
assert(scenario);
const {spy,vix}=bars();
async function main(){
const budgetSkip=await A.runDay({scenario,events:['CPI'],spy,vix,close:615,dayStartEquity:2000,cash:2000,host:{reservedMargin:500},quoteAt:quote});
assert.equal(budgetSkip.status,'skipped');assert.equal(budgetSkip.reason,'budget_cash_or_quote_gate');
const r=await A.runDay({scenario,events:['CPI'],spy,vix,close:615,dayStartEquity:20000,cash:20000,host:{reservedMargin:500},quoteAt:quote});
assert.equal(r.status,'closed');assert.equal(r.entry.entry,607);assert.equal(r.entry.n,3); // $65.40 max loss, 1% of $20k = three lots.
assert.equal(r.feeModel.roundTripPerSpread,1.4);
assert.equal(Math.round((r.cashAfter-r.cashBefore)*100)/100,r.pnl);
const combined=A.combineDay({hostPnl:-100,offense:r,cashBefore:2000});
assert.equal(combined.combinedPnl,Math.round((-100+r.pnl)*100)/100);
assert.throws(()=>A.combineDay({hostPnl:NaN,offense:r,cashBefore:2000}),/combined_ledger_inputs_invalid/);
console.log(JSON.stringify({passed:true,cases:'causal next-quote entry, explicit two-leg side fees, budget/cash gate, chronological cash reconciliation, no baseline-PnL reuse'}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
