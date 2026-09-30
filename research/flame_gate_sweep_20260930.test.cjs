const assert=require('node:assert/strict');
const R=require('./flame_gate_sweep_20260930.cjs');
const day='2024-06-03';let ratio=.80,reqs=0;
function seed(){R.setTestHistories({vix:Array.from({length:21},(_,i)=>({day:new Date(Date.UTC(2024,0,1+i)).toISOString().slice(0,10),close:i===20?20*ratio:20})),eod:{'2024-05-30':499,'2024-05-31':500,[day]:500}});}
global.fetch=async raw=>{
 const u=new URL(raw);reqs++;assert(u.pathname.startsWith('/v3/'));assert(!u.pathname.includes('order'));
 if(u.searchParams.get('symbol')==='XSP')return new Response('no observations',{status:404});
 const rows=[];const stamp=m=>day+'T'+String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0')+':00';
 if(u.pathname.endsWith('/ohlc')){rows.push('symbol,timestamp,open,high,low,close,volume');for(let m=570;m<960;m++)rows.push(`SPY,${stamp(m)},500,500.1,499.9,500,1000`);}
 else{const k=+u.searchParams.get('strike'),right=u.searchParams.get('right'),short=right==='put'?k===499:k===501;rows.push('symbol,expiration,right,strike,timestamp,bid,ask,bid_size,ask_size');for(let m=570;m<960;m++)rows.push(`SPY,${day},${right},${k},${stamp(m)},${short?.30:.04},${short?.31:.05},100,100`);}
 return new Response(rows.join('\n')+'\n',{headers:{'X-Market-Data-Provider':'thetadata'}});
};
(async()=>{
 seed();await R.replayDay(day);
 for(const a of R.accounts){assert.equal(a.days[0].hostN,2);assert.equal(a.days[0].pnl,a.fillCase==='natural'?47.2:41.2);assert.equal(a.days[0].flintN,0);}
 const firstRequests=reqs;assert(firstRequests<25,'historical data must be shared across 506 paths');
 for(const a of R.accounts){a.equity=a.deposit;a.peak=a.deposit;a.floorPeak=a.deposit;a.triggered=false;a.days=[];a.trades=[];}
 ratio=.84;seed();await R.replayDay(day);
 const pick=(gate,risk,credit,regime)=>R.accounts.find(a=>a.fillCase==='natural'&&a.scenario.gate===gate&&a.scenario.risk===risk&&a.scenario.credit===credit&&a.scenario.regime===regime);
 assert.equal(R.accounts[0].days[0].hostN,0);assert.equal(pick(.82,'full',.1,'all').days[0].hostN,0);
 assert.equal(pick(.85,'full',.1,'all').days[0].hostN,2);assert.equal(pick(.85,'50pct',.1,'all').days[0].hostN,1);
 assert.equal(pick(.85,'one',.1,'prior_up').days[0].hostN,1);assert.equal(pick(.85,'full',.1,'gamma_p67').days[0].hostN,0);
 assert.equal(pick(.85,'full',.2,'all').days[0].hostN,2);
 console.log(JSON.stringify({passed:true,paths:506,firstRequests,tests:'baseline invariance, expanded-only sizing/credit/regime, no blocked-host leakage, no invented gamma, shared quotes, zero order endpoints; SYNTHETIC fixtures only'}));
})().catch(e=>{console.error(e);process.exitCode=1;});
