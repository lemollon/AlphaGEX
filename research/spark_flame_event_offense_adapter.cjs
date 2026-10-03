/*
 * Chronological research-only adapter for event-day debit-spread offense.
 *
 * This module intentionally has no network, database, broker, order, or
 * persistence code.  The replay runner supplies quality-controlled completed
 * minute bars and authentic provider quotes.  It holds cash/margin in time
 * order so an offensive spread cannot be priced as an after-the-fact offset
 * to a host strategy's already-computed dollar P&L.
 */
'use strict';

const O=require('./spark_flame_event_offense.cjs');
const round=x=>Math.round((x+Number.EPSILON)*100)/100;

// Existing research convention is $1.40 round trip for a two-leg spread.
// Make the side/leg accounting explicit: 2 legs * 2 sides * $0.35 = $1.40.
const FEES=Object.freeze({perLegPerSide:.35,open:.70,close:.70});

function assertMoney(x,name){if(!Number.isFinite(x)||x<0)throw Error(`invalid_${name}`);}
function quoteKey(signal){return `${signal.right}:${signal.buyStrike}:${signal.sellStrike}`;}

function normalizeQuote(raw){
 if(!raw)return null;
 const q={buy:raw.buy,sell:raw.sell};
 for(const leg of [q.buy,q.sell]){
  if(!leg||![leg.bid,leg.ask,leg.bidSize,leg.askSize].every(Number.isFinite))return null;
  if(leg.bid<0||leg.ask<=0||leg.ask<leg.bid||leg.bidSize<0||leg.askSize<0)return null;
 }
 return q;
}

async function nextExecutable(signal,from,close,quoteAt){
 for(let minute=from;minute<close;minute++){
  const q=normalizeQuote(await quoteAt(signal,minute));
  if(q)return {minute,quote:q};
 }
 return null;
}

/*
 * Run at most one offense trade for a single scenario/account/day.
 *
 * Inputs:
 * - spy/vix: Maps keyed by exchange-local minute start.
 * - quoteAt(signal, minute): returns the authentic synchronized two-leg quote
 *   for that exact signal contract/minute, or null. The runner must not
 *   substitute theoretical values or stale observations.
 * - host: live host state known at decision time only. `reservedMargin`
 *   prevents double-spending buying power. `right`/`entry` are required by the
 *   overlay component; `threatened` is a causal controller flag.
 */
async function runDay({scenario,events,spy,vix,close,dayStartEquity,cash,host=null,slip=0,quoteAt}){
 if(!scenario||!Array.isArray(events)||!(spy instanceof Map)||!(vix instanceof Map))throw Error('invalid_offense_inputs');
 if(typeof quoteAt!=='function')throw Error('quote_lookup_required');
 assertMoney(dayStartEquity,'day_start_equity');assertMoney(cash,'cash');assertMoney(slip,'slippage');
 const hostMargin=host?.reservedMargin??0;assertMoney(hostMargin,'host_margin');
 let availableCash=round(cash-hostMargin);
 if(availableCash<0)return {status:'skipped',reason:'host_margin_exceeds_cash',cashBefore:cash,cashAfter:cash,hostMargin};
 const start=570, last=Math.min(930,close-1); // no new entry after 15:30 ET
 let signal=null, entry=null;
 const admission={signals:0,rejections:{},lastRejected:null};
 const reject=(reason,details={})=>{admission.rejections[reason]=(admission.rejections[reason]||0)+1;admission.lastRejected={reason,...details};};
 for(let decisionMinute=start;decisionMinute<=last;decisionMinute++){
  const visibleHost=scenario.family==='overlay'&&host?.threatened?host:null;
  signal=O.entrySignal(scenario,decisionMinute,spy,vix,events,visibleHost);
  if(!signal)continue;
  admission.signals++;
  // Recompute the signal every completed minute. Evaluate only the next
  // minute's quote; never wait into the future and then resume an earlier
  // decision clock or abandon the entire day after a rejected candidate.
  const executionMinute=decisionMinute+1;
  if(executionMinute>=close)continue;
  const q=normalizeQuote(await quoteAt(signal,executionMinute));
  if(!q){reject('no_executable_entry_quote',{decisionMinute});continue;}
  const assessment=O.entryAssessment(signal,q,dayStartEquity,availableCash,scenario,slip,FEES);
  if(!assessment.order){reject(assessment.reason,{decisionMinute,...assessment});continue;}
  const order=assessment.order;
  const candidate={minute:executionMinute};
  entry={...order,entry:candidate.minute};
  break;
 }
 if(!entry)return {status:'skipped',reason:admission.signals?'all_causal_entries_rejected':'no_causal_signal',admission,cashBefore:cash,cashAfter:cash,hostMargin};
 const quotes=new Map();
 for(let minute=entry.entry;minute<close;minute++)quotes.set(minute,normalizeQuote(await quoteAt(entry,minute)));
 const exit=O.exitTrade(entry,quotes,close,scenario,slip);
 if(exit.unresolved)return {status:'unresolved',reason:exit.unresolved,admission,signal,entry,cashBefore:cash,cashAfter:cash,hostMargin};
 const entryCash=round(cash-entry.reservedCash);
 const exitProceeds=round((exit.exitValue*100-entry.fees.close)*entry.n);
 const cashAfter=round(entryCash+exitProceeds);
 const reconciledPnl=round(cashAfter-cash);
 if(Math.abs(reconciledPnl-exit.pnl)>.001)throw Error('offense_cash_reconciliation_failed');
 return {
  status:'closed',admission,signal,entry:{...entry,contractKey:quoteKey(entry)},exit,
  cashBefore:cash,cashAfter,hostMargin,entryCash,exitProceeds,
  maxCashAtRisk:round(entry.reservedCash+hostMargin),pnl:reconciledPnl,
  feeModel:{...FEES,roundTripPerSpread:round((FEES.open+FEES.close))},
 };
}

function combineDay({hostPnl,offense,cashBefore}){
 if(!offense||!Number.isFinite(hostPnl)||!Number.isFinite(cashBefore))throw Error('combined_ledger_inputs_invalid');
 if(offense.status==='unresolved')return {unresolved:offense.reason};
 const offensePnl=offense.status==='closed'?offense.pnl:0;
 // Host P&L must come from the same chronological replay ledger. This helper
 // merely reconciles the resulting cash movements; it never accepts a
 // baseline summary or retrospective avoided-loss credit as offense revenue.
 return {hostPnl,offensePnl,combinedPnl:round(hostPnl+offensePnl),cashBefore,estimatedCashAfter:round(cashBefore+hostPnl+offensePnl)};
}

module.exports={FEES,normalizeQuote,nextExecutable,runDay,combineDay};
