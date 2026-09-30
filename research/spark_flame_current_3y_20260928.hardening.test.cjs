// Fault injection only: no network, credentials, real DB, or production edits.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const vm=require('node:vm');
const {createRequire}=require('node:module');
const G=require('./spark_flame_gamma_reconstruction.cjs');
const engine=path.join(__dirname,'spark_flame_current_3y_20260928.cjs');
const originalSource=fs.readFileSync(engine,'utf8'),nativeRequire=createRequire(engine);
// Optional mutation checks prove the suite detects removal of safeguards.
const mutations={
 one_attempt:s=>s.replace('attempt<3','attempt<1'),
 omit_weekend_expiry:s=>s.replace('const supplementalExpiries=missingPriorExpiries(day,closingChains,morningOI);','const supplementalExpiries=[];'),
 omit_account_restore:s=>s.replace('accounts.splice(0,accounts.length,...saved.accounts);','')
};
const mutation=process.env.SF3Y_TEST_MUTATION;
if(mutation&&!mutations[mutation])throw Error('unknown test mutation');
const source=mutation?mutations[mutation](originalSource):originalSource;
const plain=x=>JSON.parse(JSON.stringify(x));
function harness({fetch,pg,alterSource=false}={}){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sf3y-fault-'));
 const timers=[],timeouts=[];
 const requireShim=name=>{
  if(name==='/tmp/sf3y-pg/node_modules/pg'){assert(pg,'unexpected DB initialization');return pg;}
  if(name==='node:child_process')throw Error('subprocess_forbidden');
  if(name==='node:fs'&&alterSource)return {...fs,readFileSync:(file,...args)=>file===engine?source+'\n// changed numerical version\n':fs.readFileSync(file,...args)};
  return nativeRequire(name);
 };
 const module={exports:{}};
 const context={require:requireShim,module,__filename:engine,__dirname,
  process:{env:{RESEARCH_OUTPUT_DIR:dir,RESEARCH_DATABASE_URL:'postgres://synthetic.invalid/alphagex_backtest',FLAME_FAST_START:'on',SPARK_FAST_START:'on'},argv:[]},
  console:{log(){},error(){}},Buffer,URL,Response,structuredClone,
  AbortSignal:{timeout:ms=>{timeouts.push(ms);return AbortSignal.timeout(5);}},
  setTimeout:(fn,ms)=>{timers.push(ms);queueMicrotask(fn);},
  fetch:fetch||(()=>{throw Error('network_forbidden');})};
 vm.runInNewContext(source+`\nmodule.exports.fault={request,Quotes,loadGammaDay,missingPriorExpiries,initCheckpointStore,saveCheckpoint,execute,gammaDecision,snapshot,realizeSpread,
 state:STATE,accounts,SPX,gammaSet:x=>{gamma=x;},historiesSet:x=>{vix=x.vix;eod=x.eod;reconstructGammaEnabled=false;},
 injectExecution:fn=>{selfTest=()=>{};initCheckpointStore=async()=>false;histories=async()=>{};warmGamma=async()=>{};replayDay=fn;}};`,context,{filename:engine});
 return {r:module.exports.fault,publicReplay:module.exports.replayDay,dir,timers,timeouts,cleanup:()=>fs.rmSync(dir,{recursive:true,force:true})};
}
function fixtureFetch({xsp=false,missingMinute=null,badSymbol=false}={}){
 return async raw=>{
  const u=new URL(raw),day=u.searchParams.get('date'),symbol=u.searchParams.get('symbol');
  assert(u.pathname.startsWith('/v3/'));assert(!u.pathname.includes('order'));
  if(symbol==='XSP'&&!xsp)return new Response('no observations',{status:404});
  const stamp=m=>day+'T'+String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0')+':00';
  const rows=[];
  if(u.pathname.endsWith('/ohlc')){
   rows.push('symbol,timestamp,open,high,low,close,volume');
   for(let m=570;m<960;m++)rows.push(`${badSymbol?'QQQ':'SPY'},${stamp(m)},500,500.1,499.9,500,1000`);
  }else if(u.pathname.endsWith('/quote')){
   rows.push('symbol,expiration,right,strike,timestamp,bid,ask,bid_size,ask_size');
   const right=u.searchParams.get('right'),k=+u.searchParams.get('strike'),short=right==='put'&&[498,499].includes(k);
   for(let m=570;m<960;m++)if(m!==missingMinute)rows.push(`${symbol},${day},${right},${k},${stamp(m)},${short?.30:.04},${short?.31:.05},100,100`);
  }else throw Error('unexpected_fixture_request');
  return new Response(rows.join('\n')+'\n',{headers:{'X-Market-Data-Provider':'thetadata'}});
 };
}
function seed(h,day='2024-06-03'){
 const vix=Array.from({length:21},(_,i)=>({day:new Date(Date.UTC(2024,0,1+i)).toISOString().slice(0,10),close:i===20?16:20}));
 h.r.historiesSet({vix,eod:{[day]:500}});
}
test('transient provider errors recover with bounded retries and backoff',async()=>{
 let n=0;const h=harness({fetch:async()=>++n<3?new Response('down',{status:503}):new Response('a\n1\n')});
 try{assert.deepEqual(plain(await h.r.request('https://fixture.invalid/data')),[{a:'1'}]);assert.equal(n,3);assert.deepEqual(h.timeouts,[45000,45000,45000]);assert.deepEqual(h.timers,[1000,2000]);}finally{h.cleanup();}
});
test('a hung fetch aborts after three bounded attempts',async()=>{
 let n=0;const h=harness({fetch:async(_,options)=>{n++;return new Promise((_,reject)=>{
  const keeper=setTimeout(()=>reject(Error('test_timeout_not_aborted')),100);
  options.signal.addEventListener('abort',()=>{clearTimeout(keeper);reject(Error('aborted'));},{once:true});
 });}});
 try{await assert.rejects(h.r.request('https://fixture.invalid/data'),/aborted/);assert.equal(n,3);assert.deepEqual(h.timeouts,[45000,45000,45000]);}finally{h.cleanup();}
});
test('explicit no-data is not retried or converted to a quote',async()=>{
 let n=0;const h=harness({fetch:async()=>{n++;return new Response('absent',{status:404});}});
 try{const q=new h.r.Quotes('2024-06-03',960);assert.equal((await q.leg('XSP','put',498,665)).size,0);assert.equal(n,1);assert.equal(q.gaps[0].reason,'provider_explicit_no_observations');}finally{h.cleanup();}
});
test('unverified provider is rejected rather than accepted as historical data',async()=>{
 const h=harness({fetch:async()=>new Response('a\n1\n')});
 try{await assert.rejects(h.r.request('https://fixture.invalid/data',{},true),/unverified_provider/);}finally{h.cleanup();}
});
test('malformed contract identity cannot enter the quote cache',async()=>{
 const h=harness({fetch:async()=>new Response('symbol,strike,right,expiration,timestamp,bid,ask,bid_size,ask_size\nQQQ,498,put,2024-06-03,2024-06-03T11:05:00,1,1.1,10,10\n',{headers:{'X-Market-Data-Provider':'thetadata'}})});
 try{await assert.rejects(new h.r.Quotes('2024-06-03',960).leg('SPY','put',498,665),/wrong_option_symbol/);}finally{h.cleanup();}
});
test('weekend supplement requests the missing exact expiry without dropping OI',async()=>{
 const day='2023-09-18',priorDay='2023-09-15',exp='2023-11-17',spot=443.37,calls=[];
 const rows=['call','put'].map(right=>{const p=G.price(right,spot,443,63/365,.2);return `SPY,${exp},443,${right},${p-.001},${p+.001}`;});
 const h=harness({fetch:async raw=>{const u=new URL(raw);calls.push(u);
  let body;if(u.pathname.endsWith('open_interest'))body='symbol,expiration,strike,right,open_interest\n'+['call','put'].map(r=>`SPY,${exp},443,${r},100`).join('\n');
  else body='symbol,expiration,strike,right,bid,ask\n'+(u.searchParams.get('expiration')===exp?rows.join('\n'):'');
  return new Response(body+'\n',{headers:{'X-Market-Data-Provider':'thetadata'}});
 }});
 try{h.r.historiesSet({vix:[],eod:{[priorDay]:spot}});const result=await h.r.loadGammaDay(day,443.65);
  assert.equal(result.used,2);assert.equal(result.unpricedOIContracts,0);assert.equal(result.ivTermExtrapolated,0);
  const supplement=calls.find(u=>u.searchParams.get('expiration')===exp);assert(supplement);assert.equal(supplement.searchParams.get('date'),priorDay);assert.equal(supplement.searchParams.get('max_dte'),'0');
 }finally{h.cleanup();}
});
test('term surface interpolates total variance and preserves option side',()=>{
 const surface=new Map([['2024-06-10:call',[{k:500,iv:.2}]],['2024-06-24:call',[{k:500,iv:.3}]]]);
 const x=G.surfaceIV(surface,'2024-06-17','call',500,'2024-05-31',()=>960);
 assert.equal(x.term,'interpolated');assert(Math.abs(x.iv*x.iv*17-(.04*10+.09*24)/2)<1e-10);
 assert.equal(G.surfaceIV(surface,'2024-06-17','put',500,'2024-05-31',()=>960),null);
});
test('surface wings and missing maturity have explicit extrapolation labels',()=>{
 const surface=new Map([['2024-06-10:call',[{k:490,iv:.25},{k:510,iv:.2}]]]);
 const x=G.surfaceIV(surface,'2024-06-24','call',520,'2024-05-31',()=>960);
 assert.equal(x.term,'extrapolated');assert.equal(x.wing,true);assert.equal(x.iv,.2);
});
test('absent same-side surface fails instead of silently omitting positive OI',()=>{
 const day='2024-06-03',priorDay='2024-05-31',exp='2024-06-28',p=G.price('call',500,500,28/365,.2);
 assert.throws(()=>G.reconstruct({day,priorDay,minute:665,spot:500,priorSpot:500,
  closingChains:[{symbol:'SPY',expiration:exp,strike:500,right:'call',bid:p-.01,ask:p+.01}],
  morningOI:['call','put'].map(right=>({expiration:exp,strike:500,right,open_interest:100}))}),/gamma_no_reconstructable_chain|gamma_expiry_surface_missing/);
});
test('gamma upsizing ignores future records and incompatible source series',()=>{
 const h=harness();try{const history={};for(let i=1;i<=20;i++)history[`2024-05-${String(i).padStart(2,'0')}`]={source:G.SOURCE,value:100+i};history['2024-06-03']={source:G.SOURCE,value:200};h.r.gammaSet(history);
  const before=plain(h.r.gammaDecision('2024-06-03'));assert.equal(before.eligible,true);
  history['2024-06-04']={source:G.SOURCE,value:1e20};history['2024-05-31']={source:'different_vendor',value:1e20};h.r.gammaSet(history);
  assert.deepEqual(plain(h.r.gammaDecision('2024-06-03')),before);
 }finally{h.cleanup();}
});
test('half-day Flame stays out and Spark settles at the early close',async()=>{
 const h=harness({fetch:fixtureFetch()});try{const day='2024-07-03';seed(h,day);const d=await nativeReplay(h,day);
  assert.equal(d.close,780);assert(h.r.accounts.filter(a=>a.bot==='flame').every(a=>a.trades.length===0));
  assert(h.r.accounts.filter(a=>a.bot==='spark').every(a=>a.trades.length>0&&a.trades.every(t=>t.exit===780)));
 }finally{h.cleanup();}
});
// Access the exported public replay function without modifying engine bytes.
function nativeReplay(h,day){return h.publicReplay(day);}
test('XSP uses independent SPX settlement, not the SPY close',async()=>{
 const h=harness({fetch:fixtureFetch({xsp:true})});try{seed(h);h.r.SPX['2024-06-03']=4960;await nativeReplay(h,'2024-06-03');
  for(const a of h.r.accounts){const trades=a.trades.filter(t=>t.symbol==='XSP');assert(trades.length);assert(trades.every(t=>t.reason==='cash_settlement'&&t.pnl<0));}
 }finally{h.cleanup();}
});
test('accepted XSP without SPX close cannot produce a complete result',async()=>{
 const h=harness({fetch:fixtureFetch({xsp:true})});try{seed(h);await nativeReplay(h,'2024-06-03');h.r.state.completed=h.r.state.total=1;
  assert(h.r.snapshot().summary.every(a=>!a.complete&&a.unresolved.some(x=>x.reasons.includes('SPX_settlement_missing'))));
 }finally{h.cleanup();}
});
test('missing intraday marks remain visible even when terminal payoff resolves',async()=>{
 const h=harness({fetch:fixtureFetch({missingMinute:700})});try{seed(h);await nativeReplay(h,'2024-06-03');
  const a=h.r.accounts.find(a=>a.bot==='spark'&&a.profile==='current_customer_package'&&a.fillCase==='natural');assert(a.days[0].markGaps>0);assert.equal(a.unresolved.length,0);
 }finally{h.cleanup();}
});
test('wrong stock identity blocks replay',async()=>{
 const h=harness({fetch:fixtureFetch({badSymbol:true})});try{seed(h);await assert.rejects(nativeReplay(h,'2024-06-03'),/wrong_stock_identity/);}finally{h.cleanup();}
});
test('missing guard quotes cannot invent a protective exit fill',()=>{
 const h=harness();try{const result=h.r.realizeSpread({right:'put',short:500,long:498,at:()=>null},665,.25,new Map([[957,{open:499.5}]]),960,500,0);assert.equal(result.unresolved,'guard_quote_missing');}finally{h.cleanup();}
});
function memoryDB(name='alphagex_backtest'){
 const values=new Map(),queries=[];class Pool{async query(sql,args=[]){queries.push(sql);
  if(sql==='SELECT current_database() name')return {rows:[{name}]};
  if(sql.startsWith('CREATE TABLE'))return {rows:[]};
  if(sql.startsWith('SELECT checkpoint'))return {rows:values.has(args[0])?[{checkpoint:values.get(args[0])}]:[]};
  if(sql.startsWith('INSERT INTO')){values.set(args[0],args[3]);return {rows:[]};}
  throw Error('unexpected_sql');}}
 return {pg:{Pool},values,queries};
}
test('checkpoint refuses a production database before any write',async()=>{
 const db=memoryDB('production'),h=harness({pg:db.pg});try{await assert.rejects(h.r.initCheckpointStore(),/isolated_backtest_database/);assert.equal(db.queries.length,1);assert.equal(db.values.size,0);}finally{h.cleanup();}
});
test('cold restart restores equity, fast-start, floors, trades and gamma exactly',async()=>{
 const db=memoryDB(),a=harness({pg:db.pg}),b=harness({pg:db.pg});try{
  assert.equal(await a.r.initCheckpointStore(),false);a.r.state.completed=35;a.r.state.stage='running';
  const account=a.r.accounts[0];account.equity=215432;account.floorPeak=230000;account.triggered=true;account.fast.marker='checkpoint_test';account.trades.push({day:'2024-06-03',pnl:12.34,leg:'host_spy',n:1});
  a.r.gammaSet({'2024-06-03':{source:G.SOURCE,value:12345}});a.r.SPX['2024-06-03']=5300;await a.r.saveCheckpoint();
  assert.equal(await b.r.initCheckpointStore(),true);assert.equal(b.r.state.completed,35);assert.deepEqual(plain(b.r.accounts),plain(a.r.accounts));assert.deepEqual(plain(b.r.snapshot().gammaReconstruction),plain(a.r.snapshot().gammaReconstruction));assert.equal(b.r.SPX['2024-06-03'],5300);
 }finally{a.cleanup();b.cleanup();}
});
test('changed engine hash cannot reuse an earlier performance checkpoint',async()=>{
 const db=memoryDB(),a=harness({pg:db.pg}),b=harness({pg:db.pg,alterSource:true});try{
  await a.r.initCheckpointStore();a.r.state.completed=35;await a.r.saveCheckpoint();assert.equal(await b.r.initCheckpointStore(),false);assert.equal(b.r.state.completed,0);
 }finally{a.cleanup();b.cleanup();}
});
test('corrupted checkpoint is rejected, never treated as a successful restart',async()=>{
 const db=memoryDB(),a=harness({pg:db.pg}),b=harness({pg:db.pg});try{await a.r.initCheckpointStore();await a.r.saveCheckpoint();const key=[...db.values.keys()][0];db.values.set(key,Buffer.from('corrupt'));await assert.rejects(b.r.initCheckpointStore());assert.equal(b.r.state.completed,0);}finally{a.cleanup();b.cleanup();}
});
test('three day failures restore mutated accounts and stop with invalid paths',async()=>{
 const h=harness();try{h.r.injectExecution(async()=>{h.r.accounts[0].equity=0;h.r.accounts[0].trades.push({pnl:999});throw Error('injected_after_account_mutation');});await h.r.execute();
  assert.equal(h.r.state.stage,'blocked');assert.equal(h.r.state.completed,3);assert.equal(h.r.state.dataErrors.length,3);assert.match(h.r.state.error,/three_consecutive/);
  assert(h.r.accounts.every(a=>a.equity===a.deposit&&a.trades.length===0&&a.unresolved.length===3));assert(h.r.snapshot().summary.every(a=>!a.complete));
 }finally{h.cleanup();}
});
