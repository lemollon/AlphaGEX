// Bounded read-only diagnostic for the unresolved 2025-11-24 Spark FLINT exit.
// Preloaded only by the research service; does not import or change replay state.
'use strict';
if (/spark_flame_current_3y_20260928\.cjs$/.test(process.argv[1]||'')&&!process.argv.includes('--self-test')) {
 (async()=>{
  const base=process.env.THETADATA_BASE_URL||'http://thetadata-proxy:10000';
  for(const strike of [669,671])for(const interval of ['1m','1s']){
   const params={symbol:'SPY',right:'call',strike,expiration:'2025-11-24',date:'2025-11-24',interval,start_time:interval==='1m'?'11:05:00':'15:56:55',end_time:interval==='1m'?'16:00:00':'15:57:05'};
   const url=new URL('/v3/option/history/quote',base);Object.entries(params).forEach(([k,v])=>url.searchParams.set(k,String(v)));
   try{
    const response=await fetch(url,{signal:AbortSignal.timeout(45000),headers:{'Cache-Control':'no-cache'}});
    if(!response.ok||response.headers.get('X-Market-Data-Provider')!=='thetadata')throw Error('provider_status_'+response.status);
    const raw=await response.text(),lines=raw.trim().split(/\r?\n/),header=lines.shift().split(',');
    const rows=lines.map(l=>Object.fromEntries(l.split(',').map((v,i)=>[header[i],v])));
    const selected=interval==='1s'?rows:rows.filter(r=>/15:5[6-9]:00/.test(r.timestamp||''));
    console.log('SF3Y_GUARD_PROBE '+JSON.stringify({params,rowCount:rows.length,sha256:require('node:crypto').createHash('sha256').update(raw).digest('hex'),selected}));
   }catch(e){console.log('SF3Y_GUARD_PROBE '+JSON.stringify({params,error:String(e.message)}));}
  }
 })();
}
