/* Pure account-level research governor.  It has no broker, database, quote,
 * or order side effects.  All amounts are integer cents. */
'use strict';

const mondayOf=day=>{
 const d=new Date(day+'T00:00:00Z');
 const offset=(d.getUTCDay()+6)%7;d.setUTCDate(d.getUTCDate()-offset);
 return d.toISOString().slice(0,10);
};
const positive=n=>Number.isSafeInteger(n)&&n>0?n:0;
const floorAt=(start,peak,retention)=>{
 const profit=positive(peak-start);
 // A zero-profit period supplies no lock floor.  Otherwise a fresh day or
 // week would incorrectly forbid all risk merely because equity equals its
 // opening value.
 return profit?start+Math.floor(profit*retention):0;
};

function beginDay(previous,day,equityCents,depositCents){
 if(!Number.isSafeInteger(equityCents)||!Number.isSafeInteger(depositCents))throw Error('profit_lock_invalid_equity');
 const week=mondayOf(day),sameWeek=previous?.week===week;
 const accountPeak=Math.max(previous?.accountPeakCents??depositCents,equityCents,depositCents);
 return {
  day,week,depositCents,accountPeakCents:accountPeak,
  dayStartCents:equityCents,dayPeakCents:equityCents,
  weekStartCents:sameWeek?previous.weekStartCents:equityCents,
  weekPeakCents:Math.max(sameWeek?previous.weekPeakCents:equityCents,equityCents),
 };
}

function closeDay(state,equityCents){
 if(!state||!Number.isSafeInteger(equityCents))throw Error('profit_lock_invalid_close');
 return {...state,
  dayPeakCents:Math.max(state.dayPeakCents,equityCents),
  weekPeakCents:Math.max(state.weekPeakCents,equityCents),
  accountPeakCents:Math.max(state.accountPeakCents,equityCents),
 };
}

/*
 * A retained-profit floor is a hard admission constraint, not a stop-loss
 * promise.  The caller must pass the displayed worst-case loss (including
 * fees) and all risk already admitted for the day.  With no earned profit,
 * a component imposes no artificial principal-loss limit; normal sizing and
 * margin gates remain responsible for that exposure.
 */
function admission(state,equityCents,proposedLossCents,activeRiskCents,config){
 if(!state||![equityCents,proposedLossCents,activeRiskCents].every(Number.isSafeInteger))throw Error('profit_lock_invalid_input');
 if(!(proposedLossCents>0)||activeRiskCents<0)throw Error('profit_lock_invalid_risk');
 const c={dayRetention:0,weekRetention:0,accountRetention:0,...config};
 for(const k of ['dayRetention','weekRetention','accountRetention'])if(!(c[k]>=0&&c[k]<=1))throw Error('profit_lock_invalid_retention');
 const floors=[
  {scope:'day',cents:floorAt(state.dayStartCents,state.dayPeakCents,c.dayRetention)},
  {scope:'week',cents:floorAt(state.weekStartCents,state.weekPeakCents,c.weekRetention)},
  {scope:'account',cents:floorAt(state.depositCents,state.accountPeakCents,c.accountRetention)},
 ];
 const retainedFloorCents=Math.max(...floors.map(x=>x.cents));
 const availableRiskCents=Math.max(0,equityCents-retainedFloorCents-activeRiskCents);
 const eligible=proposedLossCents<=availableRiskCents;
 const binding=floors.filter(x=>x.cents===retainedFloorCents).map(x=>x.scope);
 return {eligible,reason:eligible?'profit_lock_admitted':'profit_lock_retained_profit',retainedFloorCents,availableRiskCents,binding};
}

function cappedLots(state,equityCents,desiredLots,maxLossPerLotCents,activeRiskCents,config){
 if(!Number.isSafeInteger(desiredLots)||!Number.isSafeInteger(maxLossPerLotCents)||desiredLots<0||maxLossPerLotCents<=0)throw Error('profit_lock_invalid_lots');
 const one=admission(state,equityCents,maxLossPerLotCents,activeRiskCents,config);
 return {...one,lots:Math.min(desiredLots,Math.floor(one.availableRiskCents/maxLossPerLotCents))};
}

module.exports={mondayOf,beginDay,closeDay,admission,cappedLots};
