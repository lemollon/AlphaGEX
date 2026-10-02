const assert=require('node:assert/strict');
const R=require('./flame_event_risk_sweep_20260930.cjs');
let day='2024-06-03';let ratio=.80,reqs=0,shortBid=.30;
function reset(){for(const a of R.accounts){a.equity=a.deposit;a.peak=a.deposit;a.floorPeak=a.deposit;a.triggered=false;a.days=[];a.trades=[];}}
function seed(){R.setTestHistories({vix:Array.from({length:21},(_,i)=>({day:new Date(Date.UTC(2024,0,1+i)).toISOString().slice(0,10),close:i===20?20*ratio:20})),eod:{'2024-05-30':499,'2024-05-31':500,[day]:500}});}
global.fetch=async raw=>{
 const u=new URL(raw);reqs++;assert(u.pathname.startsWith('/v3/'));assert(!u.pathname.includes('order'));
 if(u.searchParams.get('symbol')==='XSP')return new Response('no observations',{status:404});
 const rows=[];const stamp=m=>day+'T'+String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0')+':00';
 if(u.pathname.endsWith('/ohlc')){rows.push('symbol,timestamp,open,high,low,close,volume');for(let m=570;m<960;m++)rows.push(`SPY,${stamp(m)},500,500.1,499.9,500,1000`);}
 else{const k=+u.searchParams.get('strike'),right=u.searchParams.get('right'),short=right==='put'?k===499:k===501;rows.push('symbol,expiration,right,strike,timestamp,bid,ask,bid_size,ask_size');for(let m=570;m<960;m++)rows.push(`SPY,${day},${right},${k},${stamp(m)},${short?shortBid:.04},${short?shortBid+.01:.05},100,100`);}
 return new Response(rows.join('\n')+'\n',{headers:{'X-Market-Data-Provider':'thetadata'}});
};
(async()=>{
 seed();await R.replayDay(day);
 const base=R.accounts.filter(a=>a.scenario.id==='flame_base');
 assert.equal(base.length,2,'Baseline assertions must exercise both actual fill cases');
 for(const a of base){assert.equal(a.days[0].hostN,2);assert.equal(a.days[0].pnl,a.fillCase==='natural'?47.2:41.2);}
 assert(reqs<25,'historical data must be shared across paths');
 // Risk-capped scenarios are explicit revision candidates, not the retired
 // implicit `risk10` profile. Both fill paths must exercise every cap.
 const risk=R.accounts.filter(a=>a.bot==='flame'&&a.scenario.id.includes('_riskcap_'));
 assert.equal(risk.length,24,'twelve explicit risk-cap scenarios must cover both fills');
 assert.equal(R.scenarioRiskCapacity({equity:200000,scenario:{maxRiskPct:.10}},2,18000,0),1);
 reset();day='2024-06-12';ratio=.75;seed();await R.replayDay(day);
 const guarded=R.accounts.filter(a=>a.scenario.eventGuard);
 for(const a of guarded){assert.equal(a.days[0].hostN,0);assert.equal(a.days[0].flintN,0,'FOMC blackout must not admit FLINT');}
 assert.equal(R.accounts.length,468,'all 234 scenarios must exercise natural and adverse fill paths');
 console.log(JSON.stringify({passed:true,paths:468,tests:'baseline parity fixture, VIX-minute and retained-profit admission variants, explicit per-trade risk-cap and adaptive-minute candidates, FOMC full new-entry blackout, shared quotes, zero order endpoints; SYNTHETIC fixtures only'}));
})().catch(e=>{console.error(e);process.exitCode=1;});
