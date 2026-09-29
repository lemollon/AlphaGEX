const assert=require('node:assert/strict');
const R=require('./spark_flame_current_3y_20260928.cjs');
process.env.FLAME_FAST_START='on';process.env.SPARK_FAST_START='on';
const day='2024-06-03',vix=[];
for(let i=0;i<21;i++){let d=new Date('2024-04-01T00:00:00Z');d.setUTCDate(d.getUTCDate()+i);vix.push({day:d.toISOString().slice(0,10),close:i===20?16:20});}
R.setTestHistories({vix,eod:{[day]:500}});
const csv=rows=>rows.map(r=>r.join(',')).join('\n')+'\n';
let orders=0,requests=0;
global.fetch=async raw=>{
 const u=new URL(raw);requests++;
 assert(['http:','https:'].includes(u.protocol));
 if(u.pathname.includes('order')){orders++;throw Error('forbidden');}
 if(u.searchParams.get('symbol')==='XSP')return new Response('not available',{status:404});
 const timestamp=m=>day+'T'+String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0')+':00';
 let rows=[];
 if(u.pathname.endsWith('/ohlc')){
  rows=[['symbol','timestamp','open','high','low','close','volume']];
  for(let m=570;m<=960;m++)rows.push(['SPY',timestamp(m),500,500.1,499.9,500,1000]);
 }else if(u.pathname.endsWith('/quote')){
  const k=+u.searchParams.get('strike'),right=u.searchParams.get('right');
  const short=right==='call'?k===501:[498,499].includes(k);
  rows=[['symbol','expiration','right','strike','timestamp','bid','ask','bid_size','ask_size']];
  for(let m=570;m<=960;m++)rows.push(['SPY',day,right,k,timestamp(m),short?.30:.04,short?.31:.05,100,100]);
 }else throw Error('unexpected_url '+u.pathname);
 return new Response(csv(rows),{status:200,headers:{'X-Market-Data-Provider':'thetadata'}});
};
(async()=>{
 const result=await R.replayDay(day);
 assert.equal(result.accounts.length,16);
 for(const bot of ['flame','spark']){
  const a=R.accounts.find(a=>a.bot===bot&&a.profile==='current_customer_package'&&a.fillCase==='natural');
  assert.equal(a.days[0].hostN,2);assert.equal(a.days[0].flintN,0);
  assert.equal(a.days[0].pnl,47.2);assert.equal(a.trades[0].symbol,'SPY');
  assert.equal(a.days[0].xsp,'xsp_quote_unavailable');
  const b=R.accounts.find(a=>a.bot===bot&&a.profile==='current_customer_package'&&a.fillCase==='adverse3c');assert.equal(b.days[0].pnl,41.2);
 }
 assert.equal(orders,0);
 console.log(JSON.stringify({passed:true,fixture:'SYNTHETIC — not performance results',cases:'16 account paths, caller wiring, contract scaling, commissions, adverse fills, XSP fallback, zero orders',requests}));
})().catch(e=>{console.error(e);process.exitCode=1;});
