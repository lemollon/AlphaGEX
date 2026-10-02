/* Isolated research. No broker SDK, credentials, trading DB or order endpoints.
 * Base this branch on 3637fd18396b9ab532ee0d9bd42281338353a8a2.
 * Native Node TypeScript stripping executes production PURE functions unchanged.
 */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const zlib=require('node:zlib');
let checkpointPool=null;
let checkpointKey=null;
const assert = require('node:assert/strict');
const { stripTypeScriptTypes } = require('node:module');
const ROOT = path.resolve(__dirname, '..');
const LIB = path.join(ROOT, 'ironforge/webapp/src/lib');
const C = require(path.join(LIB, 'customer-executor/contracts.ts'));
const F = require(path.join(LIB, 'flint.ts'));
const L = require(path.join(LIB, 'ebb-sizing.ts'));
const X = require(path.join(LIB, 'xsp-swap.ts'));
const FAST = require(path.join(LIB, 'fast-start-sizing.ts'));
const GAMMA=require('./spark_flame_gamma_reconstruction.cjs');
const PROFIT_LOCK=require('./spark_flame_profit_lock.cjs');
const MINUTE_BRAIN=require('./flame_minute_brain.cjs');
let reconstructGammaEnabled=true;
let separateSrc=fs.readFileSync(path.join(LIB,'spark-flint-separate.ts'),'utf8').replace(/import\s*\{[^}]*\}\s*from\s*'\.\/flint'/,'');
const S=new Function('evaluateFlintProfitGate',`${stripTypeScriptTypes(separateSrc).replace(/\bexport\s+/g,'')}; return {decideSparkFlintContracts};`)(F.evaluateFlintProfitGate);
// Only the pure prefix; the persistence section is deliberately never loaded.
let oneSrc = fs.readFileSync(path.join(LIB, 'one-strategy.ts'), 'utf8');
oneSrc = oneSrc.slice(0, oneSrc.indexOf('// Persistence for INTERNAL'));
oneSrc = oneSrc.replace(/import\s*\{[\s\S]*?\}\s*from\s*'\.\/customer-executor\/contracts'/, '');
const oneJS = stripTypeScriptTypes(oneSrc).replace(/\bexport\s+/g, '');
const O = new Function('deps', 'process', `const {currentFloorLevelCents,evaluateCalmUpsize,evaluateDepositFloorCap,evaluateFastStartUpsize,evaluateFlintCushion}=deps; ${oneJS}; return {evaluateOneStrategyHostSizing,decideOneStrategyFlintContracts};`)(C, process);

const SPEC = {
  // New engine identity: this is a fresh, fully re-compounded replay which
  // uses the imported VIX *index* minute series for pre-entry admission.
  // It deliberately does not reuse the completed event-risk performance.
  id: 'spark-flame-dynamic-event-protection-20261001-v1', sourceCommit: '3637fd18396b9ab532ee0d9bd42281338353a8a2',
  start: '2023-09-29', end: '2026-09-28', seeds: { flame: 2000, spark: 5000 },
  bots: { spark: { start: 665, end: 680, offset: 2, width: 5, vix: .90 }, flame: { start: 845, end: 850, offset: 1, width: 2, vix: .80 } },
  clock: 'America/New_York; CT clocks + 1 hour', creditFloor: .10,
  putGuardBuffer: .50, callGuardBuffer: .25, guardMinutesBeforeClose: 3,
  profitTarget: null, stop: null, mainTradesPerDay: 1, flintTradesPerDay: 1,
  customerPct: 20, floorN: 3, floorK: .10, floorMargin: 50, calmRatio: .70,
  calmMinDeposit: 4000, flintBase: 1, flintGammaUpsize: true, xspSwap: true,
  feeDollarsPerSpread: 1.40, monthlyFeeExternalDollars: 50,
  profiles: ['current_customer_package', 'internal_one_strategy', 'legacy_highwater_ladder', 'legacy_profit_ladder_fast_start'],
  fillCases: { natural: 0, adverse3c: .03 },
  execution: 'minute snapshot sell-bid/buy-ask; quote size checked; invalid guard snapshot scans first valid synchronized second within that minute; no guaranteed fills; same-minute stock OPEN is spot proxy',
  settlement: 'ThetaData official SPY EOD close; XSP requires independent SPX close / 10',
  gammaCoverage: 'Uniform reconstructed 0..60 DTE call/put dollar gamma: prior-close Theta quotes/IV, morning OI, 11:05 ET spot; 20 prior-session warmup. Modelled historical inputs, not identical Tradier observations.',
  xspCoverage: 'Enabled. Missing XSP quotes fall back per source; missing SPX settlement on an accepted swap makes that profile unresolved.',
  dynamicCoverage: 'Shock and giveback exits apply to SPY host/FLINT and XSP host using recorded quotes. Completed-minute signals execute at the next or later executable minute. An unfilled triggered exit blocks the path. Historical broker fills are not established.',
  eventCoverage: 'BLS historical release calendars and Fed scheduled decision dates; retrospective availability assumed. Original point-in-time schedules and unscheduled timestamped headlines not recovered. No release outcomes/surprise values enter rules.',
  blackout: 'BLACKOUT_HALT_ENABLED=false in frozen source', weekdaySkips: [],
  dependencies: 'No external Node packages. Private ThetaData proxy for historical market data.',
};
const OUT = process.env.RESEARCH_OUTPUT_DIR || '/tmp/flame-event-risk-sweep';
fs.mkdirSync(OUT, { recursive: true });
const STATE = { stage: 'created', run: SPEC.id, completed: 0, total: 0, dataErrors: [], currentDay: null, requests: 0, startedAt: null };
const rowsByDay = new Map();
let report = null;
const emit = (event, fields = {}) => console.log('SF3Y ' + JSON.stringify({ event, utc: new Date().toISOString(), ...fields }));
const sha = x => crypto.createHash('sha256').update(x).digest('hex');
const money = x => Math.round((x + Number.EPSILON) * 100) / 100;
const cents = x => Math.round(x * 100);
const iso = d => d.toISOString().slice(0, 10);
const clock = m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}:00`;
const closures = new Set([
 '2023-11-23','2023-12-25',
 '2024-01-01','2024-01-15','2024-02-19','2024-03-29','2024-05-27','2024-06-19','2024-07-04','2024-09-02','2024-11-28','2024-12-25',
 '2025-01-01','2025-01-09','2025-01-20','2025-02-17','2025-04-18','2025-05-26','2025-06-19','2025-07-04','2025-09-01','2025-11-27','2025-12-25',
 '2026-01-01','2026-01-19','2026-02-16','2026-04-03','2026-05-25','2026-06-19','2026-07-03','2026-09-07',
]);
const halves = new Set(['2023-11-24','2024-07-03','2024-11-29','2024-12-24','2025-07-03','2025-11-28','2025-12-24']);
function sessions() {
 const out = [];
 for (let d = new Date(SPEC.start+'T00:00:00Z'); iso(d) <= SPEC.end; d.setUTCDate(d.getUTCDate()+1)) {
  if (![0,6].includes(d.getUTCDay()) && !closures.has(iso(d))) out.push(iso(d));
 }
 return out;
}
// RFC4180 CSV, including quoted commas and escaped quotes.
function csv(body) {
 const data = []; let row = [], field = '', quoted = false;
 for (let i=0; i<body.length; i++) {
  const c=body[i];
  if (c==='"') { if (quoted && body[i+1]==='"') {field+='"';i++;} else quoted=!quoted; }
  else if (c===',' && !quoted) {row.push(field);field='';}
  else if (c==='\n' && !quoted) {row.push(field.replace(/\r$/, ''));if(row.some(Boolean))data.push(row);row=[];field='';}
  else field+=c;
 }
 if (field || row.length) {row.push(field.replace(/\r$/, ''));data.push(row);}
 const headers=(data.shift() || []).map((x,i)=>(i===0?x.replace(/^\uFEFF/,''):x).trim().toLowerCase());
 return data.map(r=>Object.fromEntries(headers.map((k,i)=>[k,r[i] ?? ''])));
}
function minute(timestamp, day) {
 // Provider CSV history normally uses naive ET wall time. A timezone suffix
 // is converted rather than silently treating UTC as exchange local time.
 let s=String(timestamp); let d, h, m;
 if (/Z$|[+-]\d\d:\d\d$/.test(s)) {
  const parts = new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(s));
  const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));d=`${p.year}-${p.month}-${p.day}`;h=+p.hour;m=+p.minute;
 } else {const match=s.match(/^(\d{4}-\d\d-\d\d)[ T](\d\d):(\d\d):/);if(!match)throw Error('invalid_timestamp');[,d,h,m]=match;}
 if(d!==day)throw Error('wrong_timestamp_date');return +h*60 + +m;
}
const manifest=[];
async function request(url, params={}, provider=false) {
 let last;
 for(let attempt=0;attempt<3;attempt++) {
  STATE.requests++;const u=new URL(url);Object.entries(params).forEach(([k,v])=>u.searchParams.set(k,String(v)));
  try {
   const r=await fetch(u,{signal:AbortSignal.timeout(45000),headers:{'Cache-Control':'no-cache'}});
   if(!r.ok){const e=Error(`http_${r.status}`);e.retryable=[429,500,502,503,504].includes(r.status);throw e;}
   if(provider && r.headers.get('X-Market-Data-Provider')!=='thetadata')throw Error('unverified_provider');
   const body=await r.text();if(!body.trim())throw Error('empty_response');
   const parsed=csv(body);
   const entry={url,params,bytes:Buffer.byteLength(body),sha256:sha(body),fetchedAt:new Date().toISOString(),schema:Object.keys(parsed[0]||{}),sample:parsed[0]||null};
   manifest.push(entry);fs.writeFileSync(path.join(OUT,`${manifest.length}.csv`),body);return parsed;
 } catch(e) {e.researchRequest={url,params};last=e;if(e.retryable===false)break;if(attempt<2)await new Promise(resolve=>setTimeout(resolve,1000*(attempt+1)));}
 }
 throw last;
}
const BASE = process.env.THETADATA_BASE_URL || 'http://thetadata-proxy:10000';
const feed = (endpoint, params) => request(BASE+endpoint, params, true);
let vix=[], eod={}, gamma={'2026-09-28':{value:13643544500.438574,source:'tradier_chain_dollar_gex_dte0-60'}};
// Date -> { before, entry }, both are raw VIX index observations.  The
// separate vix_minute_3y OHLC import is intentionally never used here.
const vixMinute=new Map();
let currentVixTape=new Map();
function vixRatio(day) {
 const p=vix.filter(x=>x.day<day);if(p.length<21)throw Error('vix_history_short');
 const prior=p.at(-1), max=Math.max(...p.slice(-21,-1).map(x=>x.close));
 return {ratio:prior.close/max,prior:prior.close,priorDay:prior.day,max};
}
async function histories() {
 const vr=await request('https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv');
 vix=vr.map(r=>{const [m,d,y]=r.date.split('/');return {day:`${y}-${m.padStart(2,'0')}-${d.padStart(2,'0')}`,close:+r.close};}).filter(x=>Number.isFinite(x.close)&&x.close>0).sort((a,b)=>a.day.localeCompare(b.day));
 for(const y of [2023,2024,2025,2026]) {
  const rr=await feed('/v3/stock/history/eod',{symbol:'SPY',start_date:`${y}-01-01`,end_date:y===2026?SPEC.end:`${y}-12-31`});
  for(const r of rr) {const d=(r.date||r.timestamp||r.trade_date||r.created||r.last_trade||'').slice(0,10);const close=+r.close;if(d && Number.isFinite(close)&&close>0)eod[d]=close;}
 }
 if(process.env.GAMMA_FILE)gamma=JSON.parse(fs.readFileSync(process.env.GAMMA_FILE,'utf8'));
 // Read-only public independent index source. If unavailable, do not invent
 // SPX settlement; accepted XSP swaps are flagged unresolved.
 try {
  const rr=await request('https://cdn.cboe.com/api/global/us_indices/daily_prices/SPX_History.csv');
  for(const r of rr){const [m,d,y]=(r.date||'').split('/');if(y&&Number.isFinite(+(r.close||r.spx)))SPX[`${y}-${m.padStart(2,'0')}-${d.padStart(2,'0')}`]=+(r.close||r.spx);}
 } catch(e) {STATE.spxHistoryError=String(e.message);throw e;}
}
const SPX={};
// A provider log on 2026-10-01 established that this exact historical
// contract request returns ThetaData NoDataFoundError but the proxy encodes it
// as 502. Treat it exactly as the runner treats the provider's native 404:
// no quote, no order, no synthetic value. Do not generalize this to errors.
const CONFIRMED_NO_DATA_QUOTES=new Set(['2024-02-07:SPY:call:501']);
function missingPriorExpiries(day,closingChains,morningOI) {
 const present=new Set(closingChains.map(r=>String(r.expiration).slice(0,10)));
 return [...new Set(morningOI.filter(r=>{
  const exp=String(r.expiration).slice(0,10),dte=(Date.parse(exp)-Date.parse(day))/86400000;
  return Number(r.open_interest)>0&&dte>=0&&dte<=60&&!present.has(exp);
 }).map(r=>String(r.expiration).slice(0,10)))].sort();
}
async function loadGammaDay(day,spot) {
 const priorDay=Object.keys(eod).filter(d=>d<day).sort().at(-1);
 if(!priorDay)throw Error('gamma_prior_spot_missing');
 const closingChains=await feed('/v3/option/history/eod',{symbol:'SPY',date:priorDay,expiration:'*',max_dte:61});
 const morningOI=await feed('/v3/option/history/open_interest',{symbol:'SPY',date:day,expiration:'*',max_dte:60});
 // Across weekends/holidays the prior-session 61-DTE bulk window is shorter
 // than today's 60-DTE window. Fetch each omitted expiry explicitly. For an
 // exact expiry max_dte=0 omits the SDK's optional DTE filter; it does not
 // broaden this request to other expirations.
 const supplementalExpiries=missingPriorExpiries(day,closingChains,morningOI);
 for(const expiration of supplementalExpiries){
  let rows;
  try{rows=await feed('/v3/option/history/eod',{symbol:'SPY',date:priorDay,expiration,max_dte:0});}
  catch(e){if(e.message==='http_404')continue;throw e;}
  if(rows.some(r=>String(r.expiration).slice(0,10)!==expiration))throw Error('gamma_supplement_wrong_expiry');
  closingChains.push(...rows);
 }
 const result=GAMMA.reconstruct({day,priorDay,minute:665,spot,priorSpot:eod[priorDay],closingChains,morningOI,closeFor:d=>halves.has(d)?780:960});
 result.supplementalPriorExpiries=supplementalExpiries;
 gamma[day]=result;fs.writeFileSync(path.join(OUT,'gamma-'+day+'.json'),JSON.stringify(result));
 emit('gamma_reconstruction',{...result});return result;
}
async function warmGamma() {
 if(!Object.values(gamma).some(g=>g.source===GAMMA.SOURCE))gamma={};const warm=Object.keys(eod).filter(d=>d<SPEC.start).sort().slice(-20);
 if(warm.length!==20)throw Error('gamma_warmup_history_short');
 STATE.stage='warming_gamma';
 for(const day of warm){if(gamma[day]?.source===GAMMA.SOURCE)continue;STATE.currentDay=day;const rows=await feed('/v3/stock/history/ohlc',{symbol:'SPY',date:day,interval:'1m',start_time:'11:05:00',end_time:'11:06:00',venue:'utp_cta'});const r=rows.find(r=>minute(r.timestamp||r.datetime,day)===665);if(!(Number(r?.open)>0))throw Error('gamma_warmup_spot_missing');await loadGammaDay(day,Number(r.open));await saveCheckpoint();}
}

function usableQuote(r) {
 const bid=+r.bid,ask=+r.ask,bs=+r.bid_size,as=+r.ask_size;
 return Number.isFinite(bid)&&Number.isFinite(ask)&&bid>=0&&ask>0&&bid<=ask&&bs>=0&&as>=0;
}
class Quotes {
 constructor(day,close){this.day=day;this.close=close;this.cache=new Map();this.gaps=[];this.guardCache=new Map();}
 async guardLeg(symbol,right,strike,m) {
  const key=`${symbol}:${right}:${strike}:${m}`;if(this.guardCache.has(key))return this.guardCache.get(key);
  let rows;try{rows=await feed('/v3/option/history/quote',{symbol,right,strike,expiration:this.day,date:this.day,interval:'1s',start_time:clock(m),end_time:clock(m).replace(/:00$/,':59')});}
  catch(e){if(e.message==='http_404'){const empty=new Map();this.guardCache.set(key,empty);return empty;}throw e;}
  const quotes=new Map();for(const r of rows){
   if(r.symbol?.trim()&&r.symbol.trim().toUpperCase()!==symbol)throw Error('wrong_option_symbol');
   if(r.strike?.trim()&&Math.abs(+r.strike-strike)>.001)throw Error('wrong_option_strike');
   if(r.right?.trim()&&!r.right.trim().toLowerCase().startsWith(right[0]))throw Error('wrong_option_right');
   const exp=(r.expiration||'').slice(0,10).replace(/-/g,'');if(exp&&exp!==this.day.replace(/-/g,''))throw Error('wrong_option_expiration');
   const timestamp=r.timestamp||r.datetime;if(minute(timestamp,this.day)!==m)throw Error('guard_quote_outside_minute');
   const match=String(timestamp).match(/[T ]\d\d:\d\d:(\d\d)(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?$/);if(!match)throw Error('invalid_guard_quote_second');
   if(usableQuote(r))quotes.set(+match[1],{bid:+r.bid,ask:+r.ask,bidSize:+r.bid_size,askSize:+r.ask_size,timestamp});
  }
  this.guardCache.set(key,quotes);return quotes;
 }
 async leg(symbol,right,strike,start) {
  const key=`${symbol}:${right}:${strike}`;
  const previous=this.cache.get(key);
  // The first request already includes every later minute through expiry.
  // Reuse those fresh, same-run observations for entry retries; never fetch
  // the same contract's remaining path again at each scanner minute.
  if(previous&&previous.start<=start)return previous.quotes;
  let rr;
  try {rr=await feed('/v3/option/history/quote',{symbol,right,strike,expiration:this.day,date:this.day,interval:'1m',start_time:clock(start),end_time:clock(this.close)});}
  catch(e){
   const confirmedAbsent=CONFIRMED_NO_DATA_QUOTES.has(`${this.day}:${symbol}:${right}:${strike}`);
   if(e.message==='http_404'||(e.message==='http_502'&&confirmedAbsent)){
    this.cache.set(key,{start,quotes:new Map()});this.gaps.push({day:this.day,symbol,right,strike,start,reason:confirmedAbsent?'provider_verified_no_observations':'provider_explicit_no_observations'});return this.cache.get(key).quotes;
   }
   throw e;
  }

  const out=new Map();for(const r of rr){
   // Single-contract history responses may omit identity columns. Their
   // identity is then the explicitly requested API scope, never a guessed
   // contract. Any provided identity must agree with that scope.
   if(r.symbol?.trim()&&r.symbol.trim().toUpperCase()!==symbol)throw Error('wrong_option_symbol');
   if(r.strike?.trim()&&Math.abs(+r.strike-strike)>.001)throw Error('wrong_option_strike');
   if(r.right?.trim()&&!r.right.trim().toLowerCase().startsWith(right[0]))throw Error('wrong_option_right');
   const exp=(r.expiration||'').slice(0,10).replace(/-/g,'');if(exp&&exp!==this.day.replace(/-/g,''))throw Error('wrong_option_expiration');
   const m=minute(r.timestamp||r.datetime,this.day);if(usableQuote(r))out.set(m,{bid:+r.bid,ask:+r.ask,bidSize:+r.bid_size,askSize:+r.ask_size});}
  this.cache.set(key,{start,quotes:out});return out;
 }
 async spread(symbol,right,short,long,start) {
  const s=await this.leg(symbol,right,short,start),l=await this.leg(symbol,right,long,start);
  const repairs={};const corrected=new Map();
  const at=m=>{if(corrected.has(m))return corrected.get(m);const a=s.get(m),b=l.get(m);return a&&b?{
   credit:a.bidSize>0&&b.askSize>0?money(a.bid-b.ask):null,
   // A zero-bid long is left worthless, with no invented sale proceeds.
   // A positive long bid requires displayed size before netting proceeds.
   debit:a.askSize>0&&(b.bid===0||b.bidSize>0)?money(a.ask-b.bid):null,
   bidSize:a.bidSize,askSize:b.askSize}:null;};
  const repairGuardQuote=async m=>{
   if(Number.isFinite(at(m)?.debit))return true;
   const a=await this.guardLeg(symbol,right,short,m),b=await this.guardLeg(symbol,right,long,m);
   for(let second=0;second<60;second++){
    const qs=a.get(second),ql=b.get(second);if(!qs||!ql||qs.askSize<=0||(ql.bid>0&&ql.bidSize<=0))continue;
    corrected.set(m,{credit:null,debit:money(qs.ask-ql.bid),bidSize:qs.bidSize,askSize:ql.askSize});
    repairs[m]={method:'first_valid_synchronized_second_within_guard_minute',second,timestamp:qs.timestamp,longTimestamp:ql.timestamp};return true;
   }
   return false;
  };
  return {symbol,right,short,long,start,at,repairGuardQuote,repairs};
 }
}
function newAccount(bot,profile,fillCase) {
 const deposit=cents(SPEC.seeds[bot]);return {bot,profile,fillCase,deposit,equity:deposit,peak:deposit,floorPeak:deposit,triggered:false,fast:FAST.seedFastStartState(deposit/100),trades:[],days:[],skips:{},unresolved:[],floorBreaches:0,profitLockState:null};
}
const accounts=[];
for(const scenario of scenarioGrid())for(const fillCase of Object.keys(SPEC.fillCases)){const a=newAccount(scenario.bot,'current_customer_package',fillCase);a.scenario=scenario;a.history=[];a.tradeCounts={total:0,host:0,flint:0,addedHost:0};accounts.push(a);}
function hostSize(a, credit, ratio, bidSize, buyingPower=a.equity, callCredit=null) {
 const cfg=SPEC.bots[a.bot], ml=cents((cfg.width-credit)*100);if(ml<=0)return {n:0,ml};
 let n, result;
 if(a.profile.startsWith('legacy')) {
  const capital=a.peak/100;
  n=a.profile==='legacy_profit_ladder_fast_start'?L.ebbProfitLadderContracts(a.bot,a.deposit/100,(a.peak-a.deposit)/100):L.ebbLadderContracts(a.bot,capital);
  if(a.profile==='legacy_profit_ladder_fast_start') {
   result=FAST.decideFastStartSizing(a.fast,{ebbCandidateDay:true,flintCandidateDay:a.bot==='flame'&&callCredit!==null,ebbMaxLossPerLot:ml/100,flintMaxLossPerContract:callCredit!==null?F.flintMaxLoss(1,3,callCredit,1):null,normalEbbLadder:n,equity:a.equity/100,peakProfit:Math.max(0,a.peak-a.deposit)/100},{envVar:a.bot==='flame'?'FLAME_FAST_START':'SPARK_FAST_START'});
   n=result.decision.ebbContracts;
  } else if(a.bot==='flame'&&ratio<=.70&&L.evaluateEbbUpsizeCushion(a.equity/100,a.deposit/100,L.ebbUpsizeExtraContractMaxLoss(cfg.width,credit)).eligible)n++;
  n=L.liquidityCappedLots(n,bidSize).lots;
 } else {
  result=O.evaluateOneStrategyHostSizing({equityCents:a.equity,depositCents:a.deposit,maxLossCentsPerContract:ml,vixRatio:ratio,triggered:a.triggered,peakEquityCents:a.floorPeak});n=result.contracts;
  if(a.profile==='internal_one_strategy')n=L.liquidityCappedLots(n,bidSize).lots;
 }
 // Natural-leg historical fill capacity; no unlimited NBBO size assumption.
 n=Math.min(n,Math.floor(Math.max(0,buyingPower)/ml),Math.floor(bidSize));
 if(a.scenario&&ratio>a.scenario.baseGate)n=capAddedLots(n,a.scenario.risk);
 return {n:Math.max(0,n),ml,result};
}
// The governor is fixed before replay.  It uses only account equity and the
// maximum loss of orders already admitted that day; no realized outcome,
// same-day close, or future volatility is consulted.
function scenarioRiskCapacity(a, n, ml, activeRisk=0) {
 const pct=a.scenario?.maxRiskPct;
 if(!(pct>0))return n;
 const cap=Math.floor(a.equity*pct);
 return Math.max(0,Math.min(n,Math.floor(Math.max(0,cap-activeRisk)/ml)));
}
function profitLockCapacity(a,n,ml,activeRisk=0) {
 if(!a.scenario?.profitLock)return n;
 const decision=PROFIT_LOCK.cappedLots(a.profitLockState,a.equity,n,ml,activeRisk,a.scenario.profitLock);
 if(decision.lots<n)a.profitLockSkips=(a.profitLockSkips||0)+1;
 return decision.lots;
}
function persistHost(a,s) {
 if(!s.result)return;
 if(a.profile.startsWith('legacy'))a.fast=s.result.nextState;
 else {a.floorPeak=s.result.nextPeakEquityCents;a.triggered=s.result.triggeredForSizing;}
}
function gammaDecision(day) {
 const today=gamma[day];const trailing=Object.entries(gamma).filter(([d,g])=>d<day&&g.source===today?.source&&Number.isFinite(g.value)).sort((a,b)=>a[0].localeCompare(b[0])).slice(-20).map(x=>x[1].value);
 return F.evaluateFlintGammaUpsize(today?.value??null,trailing);
}
function flintSize(a,credit,ratio,hostCandidate,host,nDepth,day) {
 const ml=cents(F.flintMaxLoss(1,3,credit,1)), protection=C.currentFloorLevelCents(a.deposit,a.floorPeak,a.triggered,.10);
 const desired=gammaDecision(day).eligible?2:1;
 if(a.profile==='current_customer_package') {
  const planned=C.estimatePlannedHostRiskCents({vixCandidateDay:hostCandidate,equityCents:a.equity,maxDeploymentPct:20,possibleUpsize:true});
  const actual=(host?.n||0)*(host?.ml||0);
  const eligible=C.evaluateFlintCushion({equityCents:a.equity,protectLevelCents:protection,hostCommittedCents:Math.max(planned,actual),maxLossCents:ml,marginCents:5000});
  return {n:eligible.eligible?Math.min(1,nDepth):0,ml,reason:eligible.reason};
 }
 if(a.profile==='internal_one_strategy') {
  // Literal current internal caller plans with $2/.10+commission EVEN when
  // VIX blocks the host. This is intentionally not corrected by the replay.
  const plan=O.evaluateOneStrategyHostSizing({equityCents:a.equity,depositCents:a.deposit,maxLossCentsPerContract:19140,vixRatio:ratio,triggered:a.triggered,peakEquityCents:a.floorPeak});
  const decision=O.decideOneStrategyFlintContracts({desired,base:1,equityCents:a.equity,protectLevelCents:plan.floorLevelCents,hostContracts:plan.contracts,hostMaxLossCentsPerContract:19140,shortStrike:1,longStrike:3,credit,flintMaxLossFn:F.flintMaxLoss});
  return {n:Math.min(decision.contracts,nDepth),ml,reason:decision.reason};
 }
 if(a.profile==='legacy_profit_ladder_fast_start') {
  if(a.bot==='spark') {
   const sparkFloor=a.fast.phase===2?a.deposit+Math.max(0,a.peak-a.deposit)*.25:a.deposit;
   const dec=S.decideSparkFlintContracts({equity:a.equity/100,deposit:a.deposit/100,sparkFloor:sparkFloor/100,flintCandidateDay:true,flintMaxLossPerContract:ml/100,sparkContractsToday:host?.n||0,sparkMaxLossPerContract:(host?.ml||0)/100});
   return {n:Math.min(dec.flintContracts,nDepth),ml,reason:dec.reason};
  }
  const dec=FAST.sizeFlintGivenEbbOutcome(a.fast.phase,a.deposit/100,a.equity/100,(a.peak-a.deposit)/100,host?.n||0,(host?.ml||0)/100,true,ml/100);
  return {n:Math.min(dec.flintContracts,nDepth),ml,reason:dec.reason};
 }
 const dec=F.decideFlintContractsForCushion(desired,1,a.equity/100,a.deposit/100,1,3,credit);
 return {n:Math.min(dec.contracts,nDepth),ml,reason:dec.gate.reason};
}
function dynamicExit(spread,entry,credit,spots,close,slip,controller={},tape=currentVixTape){
 if(!controller.dynamicShock&&!controller.dynamicTrail&&!controller.minuteBrain)return null;
 let peakProfit=0,pending=null;
 for(let m=entry+2;m<close-3;m++){
  // Previous completed-minute signal, next-minute execution. Missing exit
  // quotes defer a triggered exit; never book an exact theoretical stop.
  const decisionMinute=m-1,previous=spread.at(decisionMinute);
  if(!pending&&previous&&Number.isFinite(previous.debit)){
   const markedDebit=Math.max(0,previous.debit+slip),profit=credit-markedDebit;
   peakProfit=Math.max(peakProfit,profit);
   const latest=spots.get(decisionMinute)?.close,prior=spots.get(decisionMinute-5)?.close;
   const vLatest=tape.get(decisionMinute),vPrior=tape.get(decisionMinute-5);
   const spy5Pct=latest>0&&prior>0?(latest/prior-1)*100:null;
   const vix5Pct=vLatest>0&&vPrior>0?(vLatest/vPrior-1)*100:null;
   const brain=controller.minuteBrain?MINUTE_BRAIN.positionDecision({right:spread.right,credit,markedDebit,shortStrike:spread.short,features:MINUTE_BRAIN.completedFeatures({spots,vix:tape,asOf:decisionMinute})}):null;
   const lossArmed=markedDebit>=credit*1.50;
   const shock=spread.right==='put'?spy5Pct!==null&&spy5Pct<=-.25&&vix5Pct!==null&&vix5Pct>=3:spy5Pct!==null&&spy5Pct>=.25;
   const trail=peakProfit>=credit*.25&&profit<=peakProfit*.50;
   const reason=brain?.action==='exit'?'minute_risk_exit':controller.dynamicShock&&lossArmed&&shock?'intraday_shock':controller.dynamicTrail&&trail?'profit_giveback':null;
   if(reason)pending={triggerMinute:decisionMinute,reason,signal:{spy5Pct,vix5Pct,markedDebit,peakProfit,brain}};
  }
  if(pending){const q=spread.at(m);if(q&&Number.isFinite(q.debit)){const exitDebit=Math.max(0,q.debit+slip);return {...pending,exit:m,exitDebit,pnl:money((credit-exitDebit)*100-SPEC.feeDollarsPerSpread)};}}
 }
 if(pending){for(let m=close-3;m<close;m++){const q=spread.at(m);if(q&&Number.isFinite(q.debit)){const exitDebit=Math.max(0,q.debit+slip);return {...pending,exit:m,exitDebit,pnl:money((credit-exitDebit)*100-SPEC.feeDollarsPerSpread)};}}return {unresolved:'triggered_dynamic_exit_without_executable_quote'};}
 return null;
}
function eventBlocked(s,day){return !!(s.eventGuard&&FOMC_DECISION_DAYS.has(day)||s.eventMode==='fed'&&MACRO_CALENDAR[day]?.includes('FOMC')||s.eventMode==='major'&&MACRO_CALENDAR[day]?.some(k=>['FOMC','CPI','PAYROLLS'].includes(k)));}
function realizeSpread(spread,entry,credit,spots,close,settle,slip,controller={}) {
 const dynamic=dynamicExit(spread,entry,credit,spots,close,slip,controller);if(dynamic)return dynamic;
 for(let m=entry+1;m<close-3;m++){
  const q=spread.at(m);if(!q||!Number.isFinite(q.debit))continue;
  const debit=Math.max(0,q.debit+slip);
  if(controller.takePct>0&&debit<=credit*(1-controller.takePct))return {pnl:money((credit-debit)*100-SPEC.feeDollarsPerSpread),exit:m,reason:'profit_lock'};
  if(controller.stopPct>0&&debit>=credit*(1+controller.stopPct))return {pnl:money((credit-debit)*100-SPEC.feeDollarsPerSpread),exit:m,reason:'loss_cap'};
 }
 const buffer=spread.right==='put'?SPEC.putGuardBuffer:SPEC.callGuardBuffer;
 for(let m=close-3;m<close;m++) {
  const spot=spots.get(m)?.open; if(!Number.isFinite(spot))return {unresolved:'missing_guard_stock'};
  const hits=spread.right==='put'?spot<=spread.short+buffer:spot>=spread.short-buffer;
  if(hits) {const q=spread.at(m);if(!q||!Number.isFinite(q.debit))return {unresolved:'guard_quote_missing'};return {pnl:money((credit-Math.max(0,q.debit+slip))*100-SPEC.feeDollarsPerSpread),exit:m,reason:'assignment_guard'};}
 }
 if(!Number.isFinite(settle))return {unresolved:'official_close_missing'};
 const width=Math.abs(spread.short-spread.long);
 const intrinsic=spread.right==='put'?Math.min(width,Math.max(0,spread.short-settle)):Math.min(width,Math.max(0,settle-spread.short));
 return {pnl:money((credit-intrinsic)*100-SPEC.feeDollarsPerSpread),exit:close,reason:'expiry'};
}
async function replayDay(day) {
 const close=halves.has(day)?780:960, vg=vixRatio(day);
 if(checkpointPool){const vi=await checkpointPool.query('SELECT extract(hour from ts)::int*60+extract(minute from ts)::int AS minute,price FROM vix_index_price_3y WHERE trade_date=$1::date ORDER BY ts',[day]);currentVixTape=new Map(vi.rows.map(r=>[+r.minute,+r.price]));if(!currentVixTape.size&&day!=='2023-09-29')throw Error('intraday_VIX_day_missing');}
 const rr=await feed('/v3/stock/history/ohlc',{symbol:'SPY',date:day,interval:'1m',start_time:'09:30:00',end_time:clock(close),venue:'utp_cta'});
 const spots=new Map();for(const r of rr){const m=minute(r.timestamp||r.datetime,day);if(m>=close)continue;if(r.symbol?.trim()&&r.symbol.trim().toUpperCase()!=='SPY')throw Error('wrong_stock_identity');const b={open:+r.open,high:+r.high,low:+r.low,close:+r.close};if(Object.values(b).every(x=>x===0)&&+r.volume===0)continue;if(Object.values(b).some(x=>!Number.isFinite(x)||x<=0))throw Error('invalid_stock');spots.set(m,b);}
 if(!eod[day])throw Error('official_SPY_close_missing');
 if(reconstructGammaEnabled){const spot=spots.get(665)?.open;if(!(spot>0))throw Error('gamma_current_spot_missing');await loadGammaDay(day,spot);}
 for(const a of accounts)a.profitLockState=PROFIT_LOCK.beginDay(a.profitLockState,day,a.equity,a.deposit);
 const dq=new Quotes(day,close), daily={day,vix:vg,close,events:MACRO_CALENDAR[day]||[],intradayVixPoints:currentVixTape.size,minuteInputs:{vix:[...currentVixTape],spyClose:[...spots].map(([m,b])=>[m,b.close])},accounts:[]};
 for(const bot of ['spark','flame']) {
  const cfg=SPEC.bots[bot], group=accounts.filter(a=>a.bot===bot), active=new Map(group.map(a=>[a,[]]));
  const hosts=new Map(), flints=new Set(), brainRejected=new Set();
  // Admission is evaluated after the real SPY minute bars have been loaded,
  // and before any option quote/order calculation.  It cannot see outcomes.
  const candidates=new Map(group.map(a=>[a,scenarioCandidate(a.scenario,vg.ratio,day,spots)]));const candidate=group.some(a=>candidates.get(a));
  Object.assign(daily.minuteAdmission||={},Object.fromEntries(group.map(a=>[`${a.scenario.id}:${a.fillCase}`,minuteAdmission(a.scenario,vg.ratio,day,spots)])));
  for(let m=cfg.start;m<=Math.min(cfg.end,close-1);m++) {
   const spot=spots.get(m)?.open;if(!Number.isFinite(spot))throw Error('entry_stock_missing');
   let put=null,call=null,xsp=null;
   if(candidate&&group.some(a=>!hosts.has(a))) {
    const short=Math.floor(spot-cfg.offset+.5);put=await dq.spread('SPY','put',short,short-cfg.width,m);
   }
   if(group.some(a=>!flints.has(a))) {const k=F.computeFlintStrikes(spot);call=await dq.spread('SPY','call',k.short,k.long,m);}
   for(const a of group) {
   const slip=SPEC.fillCases[a.fillCase], p=put?.at(m), c=call?.at(m);
    let host=hosts.get(a);let proposed=null;
    if(!host&&!brainRejected.has(a)&&candidates.get(a)&&p&&Number.isFinite(p.credit)&&p.credit-slip>=(vg.ratio>a.scenario.baseGate?a.scenario.credit:.10)) {
     proposed=hostSize(a,p.credit-slip,vg.ratio,Math.min(p.bidSize,p.askSize),a.equity-active.get(a).reduce((s,t)=>s+t.risk,0),c&&c.credit-slip>=.10?c.credit-slip:null);
     if(a.scenario.minuteBrain){
      const brain=MINUTE_BRAIN.entryDecision({right:'put',features:MINUTE_BRAIN.completedFeatures({spots,vix:currentVixTape,asOf:m-1})});
      proposed.minuteBrain=brain;
      if(brain.action==='skip'){brainRejected.add(a);proposed=null;}
      else if(brain.action==='wait')proposed.n=Math.floor(proposed.n*brain.sizeMultiplier);
     }
    }
    // FLINT precedes the actual host entry, matching scanner order. Retry
    // profits/credit/quote gates within the entry window until filled.
    // Event mode is a decision-time new-entry blackout, not a hindsight
    // trade filter: on a scheduled FOMC decision day it admits neither a
    // new FLINT spread nor a new host spread.
    const blockedByEvent=eventBlocked(a.scenario,day);
    if(!blockedByEvent&&!flints.has(a)&&c&&c.credit-slip>=.10) {
     const f=flintSize(a,c.credit-slip,vg.ratio,candidates.get(a),host||proposed,Math.floor(Math.min(c.bidSize,c.askSize)),day);
     const available=a.equity-active.get(a).reduce((s,t)=>s+t.risk,0);
     const n=scenarioRiskCapacity(a,Math.min(f.n,Math.floor(Math.max(0,available)/f.ml)),f.ml,active.get(a).reduce((s,t)=>s+t.risk,0));
     const profitLocked=profitLockCapacity(a,n,f.ml,active.get(a).reduce((s,t)=>s+t.risk,0));
     if(profitLocked>0) {active.get(a).push({spread:call,n:profitLocked,credit:c.credit-slip,entry:m,risk:f.ml*profitLocked,leg:'flint',controller:a.scenario});flints.add(a);}
    }
    // The real scanner evaluates FLINT first, then persists the host floor,
    // including a floor-capped zero-sized host decision.
    if(proposed)persistHost(a,proposed);
    if(!host&&proposed&&proposed.n>0) {
     // Re-read buying power after FLINT reserved its collateral.
     const available=a.equity-active.get(a).reduce((s,t)=>s+t.risk,0);proposed.n=Math.min(proposed.n,Math.floor(Math.max(0,available)/proposed.ml));
     const activeRisk=active.get(a).reduce((s,t)=>s+t.risk,0);
     proposed.n=scenarioRiskCapacity(a,proposed.n,proposed.ml,activeRisk);
     proposed.n=profitLockCapacity(a,proposed.n,proposed.ml,activeRisk);
     if(proposed.n<=0)continue;
     hosts.set(a,proposed);
     let decision={nXsp:0,nSpy:proposed.n,reason:'xsp_quote_unavailable'};
     if(SPEC.xspSwap) {
      if(xsp===null)xsp=await dq.spread('XSP','put',put.short,put.long,m);
      const xq=xsp&&xsp.at(m);
      decision=X.decideXspSwap({nHost:proposed.n,spyCreditPerContract:p.credit-slip,xspCreditPerContract:xq?xq.credit-slip:null,xspShortBidSize:xq?.bidSize??null});
      if(decision.nXsp)active.get(a).push({spread:xsp,n:decision.nXsp,credit:xq.credit-slip,entry:m,risk:cents((cfg.width-xq.credit+slip)*100)*decision.nXsp,leg:'host_xsp',controller:a.scenario});
     }
     if(decision.nSpy)active.get(a).push({spread:put,n:decision.nSpy,credit:p.credit-slip,entry:m,risk:proposed.ml*decision.nSpy,leg:'host_spy',controller:a.scenario});
     proposed.xspDecision=decision.reason;
    }
   }
   if(group.every(a=>(hosts.has(a)||!candidates.get(a))&&flints.has(a)))break;
   // Avoid querying all retry quotes when no account could possibly trade FLINT.
   if(group.every(a=>a.equity<=a.deposit)&&group.every(a=>hosts.has(a)||!candidates.get(a)))break;
  }
  for(const a of group) {
   const trades=active.get(a), before=a.equity;let net=0,mtmMin=before,mtmPeak=before,markedDD=0,markGaps=0,unresolved=[];
   // Reject crossed minute snapshots. Scan contemporaneous one-second quotes
   // in chronological order only inside the triggered guard minute. No future
   // minute, stale quote, theoretical price or interpolation supplies an exit.
   for(const t of trades)if(t.spread.symbol==='SPY')for(let m=close-3;m<close;m++){
    const spot=spots.get(m)?.open;if(!Number.isFinite(spot))break;
    const hit=t.spread.right==='put'?spot<=t.spread.short+SPEC.putGuardBuffer:spot>=t.spread.short-SPEC.callGuardBuffer;
    if(hit){await t.spread.repairGuardQuote(m);break;}
   }
   const resolved=trades.map(t=>{
    const result=t.spread.symbol==='XSP'?(dynamicExit(t.spread,t.entry,t.credit,spots,close,SPEC.fillCases[a.fillCase],t.controller)||(SPX[day]?{pnl:money((t.credit-Math.min(cfg.width,Math.max(0,t.spread.short-SPX[day]/10)))*100-SPEC.feeDollarsPerSpread),exit:close,reason:'cash_settlement'}:{unresolved:'SPX_settlement_missing'})):realizeSpread(t.spread,t.entry,t.credit,spots,close,eod[day],SPEC.fillCases[a.fillCase],t.controller);
    if(result.unresolved)unresolved.push(result.unresolved);
    return { ...t,...result };
   });
   for(let m=cfg.start;m<=close;m++) {
    let value=before,known=true;
    for(const t of resolved){if(t.unresolved){known=false;continue;}if(m>=t.exit)value+=cents(t.pnl*t.n);else if(m>=t.entry){const q=t.spread.at(m);if(!q||!Number.isFinite(q.debit)){known=false;continue;}value+=cents((t.credit-q.debit-SPEC.fillCases[a.fillCase])*100*t.n-SPEC.feeDollarsPerSpread*t.n);}}
    if(known){mtmMin=Math.min(mtmMin,value);mtmPeak=Math.max(mtmPeak,value);markedDD=Math.max(markedDD,mtmPeak-value);}else markGaps++;
   }
   if(unresolved.length){a.unresolved.push({day,reasons:unresolved});a.invalidFrom??=day;}
   // No silently compounded missing-day returns. Once a path is unresolved,
   // future outputs remain diagnostic and never become a complete result.
   for(const t of resolved)if(!t.unresolved){const pnl=cents(t.pnl*t.n);net+=pnl;const tr={day,leg:t.leg,symbol:t.spread.symbol,short:t.spread.short,long:t.spread.long,entry:t.entry,exit:t.exit,n:t.n,credit:money(t.credit),pnl:money(pnl/100),reason:t.reason};if(Number.isFinite(t.exitDebit))Object.assign(tr,{exitDebit:t.exitDebit,triggerMinute:t.triggerMinute,signal:t.signal});if(t.spread.repairs[t.exit])tr.quoteRepair=t.spread.repairs[t.exit];a.trades.push(tr);}
   a.equity+=net;a.peak=Math.max(a.peak,a.equity);a.profitLockState=PROFIT_LOCK.closeDay(a.profitLockState,a.equity);
   if(a.triggered&&a.equity<a.deposit)a.floorBreaches++;
   const row={day,before:before/100,after:a.equity/100,pnl:net/100,markedMin:mtmMin/100,markedPeak:mtmPeak/100,markedDD:markedDD/100,markGaps,hostN:hosts.get(a)?.n||0,flintN:resolved.filter(t=>t.leg==='flint').reduce((s,t)=>s+t.n,0),xsp:hosts.get(a)?.xspDecision||null,minuteBrain:hosts.get(a)?.minuteBrain||null,triggered:a.triggered,floor:C.currentFloorLevelCents(a.deposit,a.floorPeak,a.triggered,.10)/100,profitLock:a.scenario.profitLock||null,profitLockSkips:a.profitLockSkips||0,unresolved};
   a.days.push(row);daily.accounts.push({scenarioId:a.scenario.id,bot:a.bot,profile:a.profile,fillCase:a.fillCase,...row});
  }
 }
 daily.quoteAbsences=dq.gaps;return daily;
}
function stats(a) {
 let peak=a.deposit/100,dd=0,ddPct=0,mtmDD=0,streak=0,longest=0;const months={};
 let markedPeak=a.deposit/100;
 for(const d of a.days){mtmDD=Math.max(mtmDD,markedPeak-d.markedMin,d.markedDD);markedPeak=Math.max(markedPeak,d.markedPeak);peak=Math.max(peak,d.after);dd=Math.max(dd,peak-d.after);ddPct=Math.max(ddPct,(peak-d.after)/peak);months[d.day.slice(0,7)]=(months[d.day.slice(0,7)]||0)+d.pnl;streak=d.pnl<0?streak+1:0;longest=Math.max(longest,streak);}
 const pnl=a.equity/100-a.deposit/100, trades=a.trades,losses=trades.filter(t=>t.pnl<0),wins=trades.filter(t=>t.pnl>0);
 // 36 monthly billing cycles from Sep 29, 2023 through Sep 28, 2026;
 // Sep 2026's next renewal lies OUTSIDE this window.
 const monthly=Object.fromEntries(Object.entries(months).map(([m,p])=>[m,{tradingNet:money(p),netAfterExternalSubscription:money(p-(m===SPEC.end.slice(0,7)?0:50))}]));
 const aggregateBy=field=>{const out={};for(const t of trades){const k=field==='month'?t.day.slice(0,7):field==='weekday'?new Date(t.day+'T00:00:00Z').getUTCDay():t[field];const g=out[k]??={trades:0,losses:0,pnl:0};g.trades++;g.losses+=t.pnl<0?1:0;g.pnl=money(g.pnl+t.pnl);}return out;};
 return {bot:a.bot,profile:a.profile,fillCase:a.fillCase,startingEquity:a.deposit/100,endingEquity:a.equity/100,pnl:money(pnl),returnPct:money(100*pnl/(a.deposit/100)),cagrPct:money(100*(Math.pow(Math.max(0,a.equity/a.deposit),1/3)-1)),trades:trades.length,hostTrades:trades.filter(t=>t.leg.startsWith('host')).length,flintTrades:trades.filter(t=>t.leg==='flint').length,winRatePct:trades.length?money(100*wins.length/trades.length):null,maxClosedDrawdown:money(dd),maxClosedDrawdownPct:money(ddPct*100),maxMarkedDrawdownObserved:money(mtmDD),markGapMinutes:a.days.reduce((s,d)=>s+d.markGaps,0),longestLosingDayStreak:longest,worstTrade:losses.length?Math.min(...losses.map(t=>t.pnl)):null,netAfterExternalSubscription:money(pnl-Object.keys(months).filter(m=>m!==SPEC.end.slice(0,7)).length*50),monthly,floorBreaches:a.floorBreaches,unresolved:a.unresolved,invalidFrom:a.invalidFrom||null,clusters:{month:aggregateBy('month'),weekday:aggregateBy('weekday'),leg:aggregateBy('leg'),worstTrades:losses.sort((a,b)=>a.pnl-b.pnl).slice(0,20)},complete:STATE.completed===STATE.total&&!STATE.dataErrors.length&&!a.unresolved.length};
}
function snapshot() {
 const result={spec:SPEC,status:{...STATE},summary:accounts.map(stats),sourceManifest:manifest,gammaCoverageDays:Object.keys(gamma).length,gammaReconstruction:gamma,gammaStudyCoverageDays:Object.keys(gamma).filter(d=>d>=SPEC.start&&d<=SPEC.end).length,fullFeatureHistoricalValidationComplete:false,coverageLimits:['Gamma add-on uses a consistent historical reconstruction, not recorded Tradier greeks; IV is held from the prior close and model assumptions are explicit.','XSP outcomes require authentic SPX settlement; unresolved swaps invalidate affected account paths.','Minute snapshots model fills; actual historical broker execution and assignment are not replayable from these inputs.','Missing or crossed guard-minute snapshots scan the first synchronized valid one-second quote within that same minute. quoteRepair records the observed timestamp; this models execution latency, not verified broker fills.']};
 fs.writeFileSync(path.join(OUT,'checkpoint.json'),JSON.stringify(result,null,2));return result;
}
function selfTest() {
 GAMMA.selfTest();
 assert.deepEqual(csv('a,b\n"x,y","z"\n'),[{a:'x,y',b:'z'}]);
 assert.equal(minute('2024-06-03T15:05:00Z','2024-06-03'),665);
 assert(!sessions().includes('2025-01-09'));assert(halves.has('2024-12-24'));
 assert.deepEqual(missingPriorExpiries('2023-09-18',[{expiration:'2023-11-10'}],[
  {expiration:'2023-11-17',open_interest:100},{expiration:'2023-11-17',open_interest:200},
  {expiration:'2023-11-10',open_interest:100},{expiration:'2023-11-18',open_interest:100},
  {expiration:'2023-11-16',open_interest:0}]),['2023-11-17']);
 assert.deepEqual(F.computeFlintStrikes(500.1),{short:502,long:504});
 const a=newAccount('spark','current_customer_package','natural');
 assert.equal(hostSize(a,.30,.80,100).n,2);assert.equal(hostSize(a,.30,.65,100).n,3);
 const b=newAccount('flame','current_customer_package','natural');assert.equal(hostSize(b,.20,.80,100).n,2);
 assert.equal(flintSize(b,.20,.75,true,{n:2,ml:18000},100,'2024-06-03').n,0);
 const p={right:'put',short:500,long:498,at:m=>({debit:.70})};const spots=new Map([[957,{open:500.4}],[958,{open:501}],[959,{open:501}]]);
 assert.equal(realizeSpread(p,845,.2,spots,960,501,0).pnl,-51.4);
 assert.equal(gammaDecision('2024-06-03').eligible,false);
 const legacy=newAccount('flame','legacy_highwater_ladder','natural');legacy.equity+=100000;legacy.peak=legacy.equity;
 assert.equal(flintSize(legacy,.2,.75,false,null,100,'2024-06-03').n,1);
 emit('self_test',{passed:true,sessions:sessions().length,cases:'pure production sizing, calm add-on, netted cushion, guard costs, CSV, UTC conversion, holiday calendar, gamma fail-closed'});
}
async function unusedOriginalCheckpointStore() {
 if(!process.env.RESEARCH_DATABASE_URL)throw Error('research_checkpoint_database_missing');
 let pg;try{pg=require('/tmp/sf3y-pg/node_modules/pg');}catch{
  require('node:child_process').execFileSync('npm',['install','--no-save','--no-package-lock','--prefix','/tmp/sf3y-pg','pg@8.16.3'],{stdio:'ignore'});
  pg=require('/tmp/sf3y-pg/node_modules/pg');
 }
 checkpointPool=new pg.Pool({connectionString:process.env.RESEARCH_DATABASE_URL,max:1,connectionTimeoutMillis:10000,ssl:true});
 const db=await checkpointPool.query('SELECT current_database() name');
 if(db.rows[0].name!=='alphagex_backtest')throw Error('checkpoint_requires_isolated_backtest_database');
 await checkpointPool.query('CREATE TABLE IF NOT EXISTS spark_flame_research_checkpoints (run_key TEXT PRIMARY KEY, status TEXT NOT NULL, completed INTEGER NOT NULL, checkpoint BYTEA NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())');
 checkpointKey=SPEC.id+':'+sha(fs.readFileSync(__filename))+':'+sha(fs.readFileSync(path.join(__dirname,'spark_flame_gamma_reconstruction.cjs')));
 const r=await checkpointPool.query('SELECT checkpoint FROM spark_flame_research_checkpoints WHERE run_key=$1',[checkpointKey]);
 if(r.rows.length){
  const saved=JSON.parse(zlib.gunzipSync(r.rows[0].checkpoint).toString());
  Object.assign(STATE,saved.state);accounts.splice(0,accounts.length,...saved.accounts);gamma=saved.gamma;vix=saved.vix;eod=saved.eod;Object.assign(SPX,saved.spx);manifest.splice(0,manifest.length,...saved.manifest);for(const [k,v] of saved.daily)rowsByDay.set(k,v);
  emit('resumed_current_run',{completed:STATE.completed,stage:STATE.stage});return true;
 }
 return false;
}
function transientDataError(e) {
 return ['fetch failed','aborted','TimeoutError','AbortError'].includes(String(e.message))
  ||['TimeoutError','AbortError'].includes(e.name)
  ||/^http_(429|500|502|503|504)$/.test(String(e.message));
}
async function recoverDataOperation(task,phase,rollback=()=>{}) {
 let attempts=0;
 for(;;){
  try{
   const result=await task();
   if(attempts){(STATE.dataRecoveries??=[]).push({phase,day:STATE.currentDay,attempts});emit('data_recovered',{phase,day:STATE.currentDay,attempts});}
   delete STATE.retryPhase;delete STATE.retryAttempt;delete STATE.retryError;return result;
  }catch(e){
   rollback();if(!transientDataError(e))throw e;
   attempts++;STATE.stage='waiting_for_data';STATE.retryPhase=phase;STATE.retryAttempt=attempts;STATE.retryError=String(e.message);
   const delayMs=Math.min(60000,15000*2**Math.min(attempts-1,2));
   emit('retrying_data',{phase,day:STATE.currentDay,attempts,delayMs,error:STATE.retryError,request:e.researchRequest||null});
   await saveCheckpoint();await new Promise(resolve=>setTimeout(resolve,delayMs));
  }
 }
}

const BASELINE_KEY='spark-flame-current-3y-20260928-v2-reconstructed-gamma:75214ba4a85515a0e8700b9e388ec569bbb6222d927fb4f199ce0f6e8398e583:d86d19ebc95421cbc1cb1ac06a756554bf230967a47e3c6c1c2ef1b3be7d909f';
// Official FOMC decision days, frozen before replay. The 14:05 ET entry
// window is a decision-time new-entry blackout on these dates; it does not
// use an after-the-fact price response or a news label.
const FOMC_DECISION_DAYS=new Set([
 '2023-11-01','2023-12-13',
 '2024-01-31','2024-03-20','2024-05-01','2024-06-12','2024-07-31','2024-09-18','2024-11-07','2024-12-18',
 '2025-01-29','2025-03-19','2025-05-07','2025-06-18','2025-07-30','2025-09-17','2025-10-29','2025-12-10',
 '2026-01-28','2026-03-18','2026-04-29','2026-06-17','2026-07-29','2026-09-16'
]);
const MACRO_CALENDAR={"2023-10-03":["JOLTS"],"2023-10-06":["PAYROLLS"],"2023-10-11":["PPI"],"2023-10-12":["CPI"],"2023-11-01":["JOLTS","FOMC"],"2023-11-03":["PAYROLLS"],"2023-11-14":["CPI"],"2023-11-15":["PPI"],"2023-12-05":["JOLTS"],"2023-12-08":["PAYROLLS"],"2023-12-12":["CPI"],"2023-12-13":["PPI","FOMC"],"2024-01-03":["JOLTS"],"2024-01-05":["PAYROLLS"],"2024-01-11":["CPI"],"2024-01-12":["PPI"],"2024-01-30":["JOLTS"],"2024-01-31":["FOMC"],"2024-02-02":["PAYROLLS"],"2024-02-13":["CPI"],"2024-02-16":["PPI"],"2024-03-06":["JOLTS"],"2024-03-08":["PAYROLLS"],"2024-03-12":["CPI"],"2024-03-14":["PPI"],"2024-03-20":["FOMC"],"2024-04-02":["JOLTS"],"2024-04-05":["PAYROLLS"],"2024-04-10":["CPI"],"2024-04-11":["PPI"],"2024-05-01":["JOLTS","FOMC"],"2024-05-03":["PAYROLLS"],"2024-05-14":["PPI"],"2024-05-15":["CPI"],"2024-06-04":["JOLTS"],"2024-06-07":["PAYROLLS"],"2024-06-12":["CPI","FOMC"],"2024-06-13":["PPI"],"2024-07-02":["JOLTS"],"2024-07-05":["PAYROLLS"],"2024-07-11":["CPI"],"2024-07-12":["PPI"],"2024-07-30":["JOLTS"],"2024-07-31":["FOMC"],"2024-08-02":["PAYROLLS"],"2024-08-13":["PPI"],"2024-08-14":["CPI"],"2024-09-04":["JOLTS"],"2024-09-06":["PAYROLLS"],"2024-09-11":["CPI"],"2024-09-12":["PPI"],"2024-09-18":["FOMC"],"2024-10-01":["JOLTS"],"2024-10-04":["PAYROLLS"],"2024-10-10":["CPI"],"2024-10-11":["PPI"],"2024-10-29":["JOLTS"],"2024-11-01":["PAYROLLS"],"2024-11-07":["FOMC"],"2024-11-13":["CPI"],"2024-11-14":["PPI"],"2024-12-03":["JOLTS"],"2024-12-06":["PAYROLLS"],"2024-12-11":["CPI"],"2024-12-12":["PPI"],"2024-12-18":["FOMC"],"2025-01-07":["JOLTS"],"2025-01-10":["PAYROLLS"],"2025-01-14":["PPI"],"2025-01-15":["CPI"],"2025-01-29":["FOMC"],"2025-02-04":["JOLTS"],"2025-02-07":["PAYROLLS"],"2025-02-12":["CPI"],"2025-02-13":["PPI"],"2025-03-07":["PAYROLLS"],"2025-03-11":["JOLTS"],"2025-03-12":["CPI"],"2025-03-13":["PPI"],"2025-03-19":["FOMC"],"2025-04-01":["JOLTS"],"2025-04-04":["PAYROLLS"],"2025-04-10":["CPI"],"2025-04-11":["PPI"],"2025-04-29":["JOLTS"],"2025-05-02":["PAYROLLS"],"2025-05-07":["FOMC"],"2025-05-13":["CPI"],"2025-05-15":["PPI"],"2025-06-03":["JOLTS"],"2025-06-06":["PAYROLLS"],"2025-06-11":["CPI"],"2025-06-12":["PPI"],"2025-06-18":["FOMC"],"2025-07-01":["JOLTS"],"2025-07-03":["PAYROLLS"],"2025-07-15":["CPI"],"2025-07-16":["PPI"],"2025-07-29":["JOLTS"],"2025-07-30":["FOMC"],"2025-08-01":["PAYROLLS"],"2025-08-12":["CPI"],"2025-08-14":["PPI"],"2025-09-03":["JOLTS"],"2025-09-05":["PAYROLLS"],"2025-09-10":["PPI"],"2025-09-11":["CPI"],"2025-09-17":["FOMC"],"2025-09-30":["JOLTS"],"2025-10-24":["CPI"],"2025-10-29":["FOMC"],"2025-11-20":["PAYROLLS"],"2025-11-25":["PPI"],"2025-12-09":["JOLTS"],"2025-12-10":["FOMC"],"2025-12-16":["PAYROLLS"],"2025-12-18":["CPI"],"2026-01-07":["JOLTS"],"2026-01-09":["PAYROLLS"],"2026-01-13":["CPI"],"2026-01-14":["PPI"],"2026-01-28":["FOMC"],"2026-01-30":["PPI"],"2026-02-05":["JOLTS"],"2026-02-11":["PAYROLLS"],"2026-02-13":["CPI"],"2026-02-27":["PPI"],"2026-03-06":["PAYROLLS"],"2026-03-11":["CPI"],"2026-03-13":["JOLTS"],"2026-03-18":["PPI","FOMC"],"2026-03-31":["JOLTS"],"2026-04-03":["PAYROLLS"],"2026-04-10":["CPI"],"2026-04-14":["PPI"],"2026-04-29":["FOMC"],"2026-05-05":["JOLTS"],"2026-05-08":["PAYROLLS"],"2026-05-12":["CPI"],"2026-05-13":["PPI"],"2026-06-02":["JOLTS"],"2026-06-05":["PAYROLLS"],"2026-06-10":["CPI"],"2026-06-11":["PPI"],"2026-06-17":["FOMC"],"2026-06-30":["JOLTS"],"2026-07-02":["PAYROLLS"],"2026-07-14":["CPI"],"2026-07-15":["PPI"],"2026-07-29":["FOMC"],"2026-08-04":["JOLTS"],"2026-08-07":["PAYROLLS"],"2026-08-12":["CPI"],"2026-08-13":["PPI"],"2026-09-01":["JOLTS"],"2026-09-04":["PAYROLLS"],"2026-09-10":["PPI"],"2026-09-11":["CPI"],"2026-09-16":["FOMC"]};
function scenarioGrid(){
 const out=[];
 for(const [bot,baseGate,addedGate] of [['flame',.80,.925],['spark',.90,.975]]){
   for(const admission of ['base','add_full','add_half']){
    for(const protection of ['hold','shock','trail','shock_trail']){
     for(const eventMode of ['none','fed','major']){
      // The frozen baseline is retained exactly.  VIX/price admission is
      // only evaluated for incremental, higher-VIX-ratio entries, using
      // observations completed before the original entry minute.
      const minuteModes=admission==='base'?['none']:['none','vix_flat','spy_holding','both'];
      for(const minute of minuteModes){
       const original=admission==='base'&&protection==='hold'&&eventMode==='none';
       const baseId=original?bot+'_base':bot+'_'+admission+'_'+protection+'_'+eventMode;
       out.push({id:minute==='none'?baseId:baseId+'_minute_'+minute,bot,baseGate,gate:admission==='base'?baseGate:addedGate,risk:admission==='add_half'?'50pct':'full',credit:admission==='base'?.10:.20,regime:admission==='base'?'all':'prior_up',eventGuard:false,eventMode,maxRiskPct:null,minute,profitLock:null,takePct:0,stopPct:0,dynamicShock:protection.includes('shock'),dynamicTrail:protection.includes('trail')});
      }
     }
    }
  }
 }
 // Account-level retained-profit governors are compared against the literal
 // customer-package baseline before combining them with any selected VIX or
 // event controller.  This prevents a broad interaction sweep from hiding
 // which safeguard actually reduced customer-facing profit giveback.
 for(const [bot,baseGate] of [['flame',.80],['spark',.90]])for(const [id,profitLock] of [
  ['retain50',{dayRetention:.50,weekRetention:.50,accountRetention:.50}],
  ['retain75',{dayRetention:.75,weekRetention:.75,accountRetention:.50}],
  ['account50',{dayRetention:0,weekRetention:0,accountRetention:.50}],
 ])out.push({id:`${bot}_base_profit_lock_${id}`,bot,baseGate,gate:baseGate,risk:'full',credit:.10,regime:'all',eventGuard:false,eventMode:'none',maxRiskPct:null,minute:'none',profitLock,takePct:0,stopPct:0,dynamicShock:false,dynamicTrail:false});
 // Per-trade loss caps directly address the customer problem: a single
 // late-day guard event must not be large enough to erase a retained streak.
 // Compare the literal base, the higher-credit VIX-gated admission, and the
 // event/shock controller at 10%, 15%, and 20% of current account equity.
 for(const maxRiskPct of [.10,.15,.20])for(const cfg of [
  {id:'base',gate:.80,credit:.10,regime:'all',minute:'none',eventMode:'none',dynamicShock:false},
  {id:'add_full_hold_none_minute_vix_flat',gate:.925,credit:.20,regime:'prior_up',minute:'vix_flat',eventMode:'none',dynamicShock:false},
  {id:'base_shock_major',gate:.80,credit:.10,regime:'all',minute:'none',eventMode:'major',dynamicShock:true},
 ])out.push({id:`flame_${cfg.id}_riskcap_${Math.round(maxRiskPct*100)}`,bot:'flame',baseGate:.80,gate:cfg.gate,risk:'full',credit:cfg.credit,regime:cfg.regime,eventGuard:false,eventMode:cfg.eventMode,maxRiskPct,minute:cfg.minute,profitLock:null,takePct:0,stopPct:0,dynamicShock:cfg.dynamicShock,dynamicTrail:false});
 for(const maxRiskPct of [.10,.15,.20])out.push({id:`flame_base_minute_brain_riskcap_${Math.round(maxRiskPct*100)}`,bot:'flame',baseGate:.80,gate:.80,risk:'full',credit:.10,regime:'all',eventGuard:false,eventMode:'none',maxRiskPct,minute:'none',profitLock:null,takePct:0,stopPct:0,dynamicShock:false,dynamicTrail:false,minuteBrain:true});
 return out;
}
function capAddedLots(n,risk){if(n<=0)return 0;if(risk==='one')return Math.min(n,1);if(risk==='full')return n;return Math.max(1,Math.floor(n*(risk==='75pct'?.75:.50)));}
function minuteAdmission(s,ratio,day,spots){
 // Preserve every original .80-or-lower entry without requiring the new
 // data. The added-day controller fails closed when raw index data is absent.
 if(ratio<=s.baseGate||s.minute==='none')return {eligible:true,reason:'not_required'};
 const decisionMinute=SPEC.bots[s.bot].start;
 // Use only completed minutes. Spark must never consume afternoon inputs.
 const v=vixMinute.get(day)?.[s.bot], before=spots.get(decisionMinute-15)?.open, entry=spots.get(decisionMinute)?.open;
 if(!(v?.before>0&&v?.entry>0&&before>0&&entry>0))return {eligible:false,reason:'minute_input_missing'};
 const vix5Pct=(v.entry/v.before-1)*100,spy15Pct=(entry/before-1)*100;
 const bars=[];for(let m=decisionMinute-15;m<decisionMinute;m++){const b=spots.get(m);if(!b)return {eligible:false,reason:'spy_minute_missing'};bars.push(b);}
 const high=Math.max(...bars.map(b=>b.high)),low=Math.min(...bars.map(b=>b.low)),rangePct=(high/low-1)*100;
 const vixOK=vix5Pct<=.50,spyOK=spy15Pct>=-.10&&rangePct<=.45;
 const eligible=s.minute==='vix_flat'?vixOK:s.minute==='spy_holding'?spyOK:vixOK&&spyOK;
 return {eligible,reason:eligible?'admitted':!vixOK?'vix_rising':'spy_weak_or_volatile',vix5Pct:money(vix5Pct),spy15Pct:money(spy15Pct),rangePct:money(rangePct)};
}
function scenarioCandidate(s,ratio,day,spots){
 if(eventBlocked(s,day))return false;
 if(ratio<=s.baseGate)return true;if(ratio>s.gate)return false;
 if(!minuteAdmission(s,ratio,day,spots).eligible)return false;
 if(s.regime==='all')return true;
 if(s.regime==='gamma_p67')return gammaDecision(day).eligible;
 const prior=Object.keys(eod).filter(d=>d<day).sort().slice(-2);
 if(prior.length!==2)throw Error('prior_trend_history_missing');
 return eod[prior[1]]>=eod[prior[0]];
}
function sweepSelfTest(){
 assert.equal(scenarioGrid().length,234);assert.equal(new Set(scenarioGrid().map(s=>s.id)).size,234);
 assert.equal(scenarioGrid().filter(s=>s.minute!=='none'&&s.gate===s.baseGate).length,0,'baseline must not be selected with new minute filters');
 assert.equal(scenarioGrid().filter(s=>s.minute==='vix_flat').length,51);
 assert.equal(scenarioGrid().filter(s=>s.profitLock).length,6);
 for(const risk of ['full','75pct','50pct','one'])for(let n=0;n<30;n++){assert(capAddedLots(n,risk)<=n);assert(capAddedLots(n,risk)>=0);}
 assert.equal(capAddedLots(0,'one'),0);assert.equal(capAddedLots(3,'50pct'),1);
 const s={baseGate:.80,gate:.85,regime:'all',minute:'none'};assert(scenarioCandidate(s,.80,'2024-01-02',new Map()));assert(scenarioCandidate(s,.85,'2024-01-02',new Map()));assert(!scenarioCandidate(s,.850001,'2024-01-02',new Map()));
 assert(!scenarioCandidate({baseGate:.80,gate:1,regime:'all',eventGuard:true,minute:'none'},.75,'2026-03-18',new Map()));
 const a={equity:2000000,scenario:{maxRiskPct:.10}};assert.equal(scenarioRiskCapacity(a,20,18000,0),11);
 emit('sweep_self_test',{passed:true,scenarios:scenarioGrid().length,paths:scenarioGrid().length*2});
}
function historyRows(a){
 // Checkpoints used to carry every scenario's day rows as live JS arrays.
 // Near the end of a 468-path replay, serializing those arrays temporarily
 // exceeded the 512 MB research instance.  Older rows are now retained as a
 // gzip payload; the active tail stays editable and is expanded only for the
 // single account being summarized.  This changes storage, never a trade.
 const archived=a.historyPacked?JSON.parse(zlib.gunzipSync(Buffer.from(a.historyPacked,'base64')).toString()):[];
 return archived.concat(a.history||[]);
}
function compactHistory(a){
 if(!Array.isArray(a.history)||!a.history.length)return;
 const archived=a.historyPacked?JSON.parse(zlib.gunzipSync(Buffer.from(a.historyPacked,'base64')).toString()):[];
 archived.push(...a.history);
 a.historyPacked=zlib.gzipSync(JSON.stringify(archived)).toString('base64');
 a.history=[];
}
function sweepStats(a,period='full'){
 const selected=historyRows(a).filter(d=>period==='full'||(period==='train'?d[0]<'2025-09-29':d[0]>='2025-09-29'));
 const start=selected[0]?.[1]??a.deposit/100;let peak=start,dd=0,ddpct=0,markedPeak=start,markedDD=0,streak=0,longest=0,worst=0;
 let hosts=0,flints=0,added=0,days=0,markGaps=0;const months={};let lossDays=0;
 for(const d of selected){peak=Math.max(peak,d[2]);dd=Math.max(dd,peak-d[2]);ddpct=Math.max(ddpct,(peak-d[2])/peak);markedDD=Math.max(markedDD,markedPeak-d[4],d[6]);markedPeak=Math.max(markedPeak,d[5]);streak=d[3]<0?streak+1:0;longest=Math.max(longest,streak);lossDays+=d[3]<0?1:0;worst=Math.min(worst,d[3]);hosts+=d[8]>0?1:0;flints+=d[9]>0?1:0;added+=d[10];days+=(d[8]+d[9])>0?1:0;markGaps+=d[7];months[d[0].slice(0,7)]=money((months[d[0].slice(0,7)]||0)+d[3]);}
 const end=selected.at(-1)?.[2]??start,pnl=money(end-start),bills=period==='full'?36:period==='train'?24:12;
 return {startingEquity:start,endingEquity:end,pnl,returnPct:money(100*pnl/start),netAfterExternalSubscription:money(pnl-bills*50),subscriptionCharges:bills*50,maxClosedDrawdown:money(dd),maxClosedDrawdownPct:money(ddpct*100),maxMarkedDrawdownObserved:money(markedDD),markGapMinutes:markGaps,hostTradeDays:hosts,flintTradeDays:flints,addedHostDays:added,tradingDays:days,lossDays,longestLosingDayStreak:longest,worstDay:worst,monthly:months,sessions:selected.length};
}
function sweepSnapshot(){return {spec:{...SPEC,scenarioGrid:scenarioGrid(),trainingEnd:'2025-09-26',validationStart:'2025-09-29',inputReuse:'Only frozen gamma/VIX/EOD/SPX market inputs from the validated baseline checkpoint; every account performance path recomputed; fresh minute quotes fetched once per day across scenarios.'},status:{...STATE},engineHash:sha(fs.readFileSync(__filename)),baselineKey:BASELINE_KEY,summary:accounts.map(a=>({scenario:a.scenario,fillCase:a.fillCase,full:sweepStats(a),train:sweepStats(a,'train'),validation:sweepStats(a,'validation'),tradeCounts:a.tradeCounts,unresolved:a.unresolved,complete:STATE.completed===751&&!STATE.dataErrors.length&&!a.unresolved.length})),coverageLimits:SPEC.gammaCoverage+' '+SPEC.execution};}
function flameCustomerRankings(limit=10){
 const grouped=new Map();
 for(const account of accounts.filter(a=>a.bot==='flame'&&a.profile==='current_customer_package')){
  const item=grouped.get(account.scenario.id)||{scenario:account.scenario};
  item[account.fillCase]=sweepStats(account);
  grouped.set(account.scenario.id,item);
 }
 return [...grouped.values()].filter(x=>x.natural&&x.adverse3c).map(x=>({
  scenario:x.scenario,
  natural:{endingEquity:x.natural.endingEquity,netAfterSubscription:x.natural.netAfterExternalSubscription,maxClosedDrawdown:x.natural.maxClosedDrawdown,maxMarkedDrawdown:x.natural.maxMarkedDrawdownObserved,worstDay:x.natural.worstDay},
  adverse:{endingEquity:x.adverse3c.endingEquity,netAfterSubscription:x.adverse3c.netAfterExternalSubscription,maxClosedDrawdown:x.adverse3c.maxClosedDrawdown,maxMarkedDrawdown:x.adverse3c.maxMarkedDrawdownObserved,worstDay:x.adverse3c.worstDay}
 })).sort((a,b)=>b.adverse.netAfterSubscription-a.adverse.netAfterSubscription||a.adverse.maxMarkedDrawdown-b.adverse.maxMarkedDrawdown).slice(0,limit);
}
async function initCheckpointStore(){
 let pg;try{pg=require('/tmp/sf3y-pg/node_modules/pg');}catch{require('node:child_process').execFileSync('npm',['install','--no-save','--no-package-lock','--prefix','/tmp/sf3y-pg','pg@8.16.3'],{stdio:'ignore'});pg=require('/tmp/sf3y-pg/node_modules/pg');}
 checkpointPool=new pg.Pool({connectionString:process.env.RESEARCH_DATABASE_URL,max:1,connectionTimeoutMillis:10000,ssl:true});
 if((await checkpointPool.query('SELECT current_database() name')).rows[0].name!=='alphagex_backtest')throw Error('isolated_database_required');
 const b=await checkpointPool.query('SELECT status,completed,updated_at FROM spark_flame_research_checkpoints WHERE run_key=$1',[BASELINE_KEY]);
 if(b.rows[0]?.completed!==751||b.rows[0]?.status!=='completed_with_coverage_limits')throw Error('validated_baseline_input_checkpoint_missing');
 emit('baseline_input_status',b.rows[0]);
 const input=JSON.parse(zlib.gunzipSync((await checkpointPool.query('SELECT checkpoint FROM spark_flame_research_checkpoints WHERE run_key=$1',[BASELINE_KEY])).rows[0].checkpoint));
 vix=input.vix;eod=input.eod;gamma=input.gamma;Object.assign(SPX,input.spx);reconstructGammaEnabled=false;
 if(input.accounts.length!==16||input.accounts.some(a=>a.unresolved?.length)||input.state.dataErrors.length)throw Error('invalid_baseline_inputs');
 for(const day of sessions()){const g=gamma[day];if(g?.source!==GAMMA.SOURCE||g.unpricedOIContracts!==0||g.used!==g.positiveOI)throw Error('gamma_input_coverage_invalid');if(!(eod[day]>0)||!(SPX[day]>0))throw Error('settlement_input_missing');}
 // Raw CBOE VIX index bars, not VIX option bars and not synthetic zero OHLC.
 // 2023-09-29 predates the imported series; new high-VIX admissions fail
 // closed on that date while the frozen <=.80 baseline behavior remains.
 const vm=await checkpointPool.query(`SELECT trade_date::text AS day,
   max(price) FILTER (WHERE ts::time='10:59:00') AS spark_before,
   max(price) FILTER (WHERE ts::time='11:04:00') AS spark_entry,
   max(price) FILTER (WHERE ts::time='13:59:00') AS flame_before,
   max(price) FILTER (WHERE ts::time='14:04:00') AS flame_entry
   FROM vix_index_price_3y
   WHERE trade_date BETWEEN $1::date AND $2::date
   GROUP BY trade_date ORDER BY trade_date`,[SPEC.start,SPEC.end]);
 for(const r of vm.rows){const data={};for(const bot of ['spark','flame'])if(+r[bot+'_before']>0&&+r[bot+'_entry']>0)data[bot]={before:+r[bot+'_before'],entry:+r[bot+'_entry']};vixMinute.set(String(r.day).slice(0,10),data);}
 for(const bot of ['spark','flame']){const missing=sessions().filter(d=>!vixMinute.get(d)?.[bot]);if(missing.some(d=>d!=='2023-09-29'))throw Error(`vix_index_minute_coverage_insufficient:${bot}:${missing.join(',')}`);emit('vix_index_minute_coverage',{bot,days:751-missing.length,missing});}
 await checkpointPool.query('CREATE TABLE IF NOT EXISTS flame_event_risk_sweep_days(run_key TEXT NOT NULL,day TEXT NOT NULL,payload BYTEA NOT NULL,PRIMARY KEY(run_key,day))');
 // A report-only revision may intentionally read a completed, frozen sweep.
 // The override is restricted to this isolated research checkpoint and never
 // changes inputs, scenarios, or any production trading code.
 const checkpointSourceHash=process.env.SWEEP_CHECKPOINT_SOURCE_HASH||sha(fs.readFileSync(__filename));
 checkpointKey=SPEC.id+':'+checkpointSourceHash+':'+sha(fs.readFileSync(path.join(__dirname,'spark_flame_gamma_reconstruction.cjs')));
 const r=await checkpointPool.query('SELECT checkpoint FROM spark_flame_research_checkpoints WHERE run_key=$1',[checkpointKey]);
 if(r.rows.length){const saved=JSON.parse(zlib.gunzipSync(r.rows[0].checkpoint));Object.assign(STATE,saved.state);accounts.splice(0,accounts.length,...saved.accounts);manifest.splice(0,manifest.length,...saved.manifest);for(const a of accounts)compactHistory(a);emit('resumed_sweep',{completed:STATE.completed,stage:STATE.stage,historyStorage:'compacted'});return true;}return false;
}
async function saveCheckpoint(){
 if(!checkpointPool)return;
 // Keep checkpoint serialization bounded.  A compacted history is immutable;
 // only rows since the previous checkpoint are held as object arrays.
 for(const a of accounts)compactHistory(a);
 const body=zlib.gzipSync(JSON.stringify({state:STATE,accounts,manifest}));
 await checkpointPool.query('INSERT INTO spark_flame_research_checkpoints(run_key,status,completed,checkpoint) VALUES($1,$2,$3,$4) ON CONFLICT(run_key) DO UPDATE SET status=EXCLUDED.status,completed=EXCLUDED.completed,checkpoint=EXCLUDED.checkpoint,updated_at=NOW()',[checkpointKey,STATE.stage,STATE.completed,body]);
}
async function commitDay(row){
 const detailed={...row,trades:accounts.map(a=>({scenarioId:a.scenario.id,fillCase:a.fillCase,trades:a.trades}))};
 for(let i=0;i<accounts.length;i++){
  const a=accounts[i],d=a.days[0];assert(d&&a.days.length===1);assert.equal(money(a.trades.reduce((s,t)=>s+t.pnl,0)),d.pnl);
  const added=d.hostN>0&&row.vix.ratio>a.scenario.baseGate?1:0;
  a.history.push([d.day,d.before,d.after,d.pnl,d.markedMin,d.markedPeak,d.markedDD,d.markGaps,d.hostN,d.flintN,added]);
  a.tradeCounts.total+=a.trades.length;a.tradeCounts.host+=a.trades.filter(t=>t.leg.startsWith('host')).length;a.tradeCounts.flint+=a.trades.filter(t=>t.leg==='flint').length;a.tradeCounts.addedHost+=added;
  a.trades=[];a.days=[];
 }
 const payload=zlib.gzipSync(JSON.stringify(detailed));
 STATE.completed++;STATE.stage='running';
 await checkpointPool.query('BEGIN');try{await checkpointPool.query('INSERT INTO flame_event_risk_sweep_days(run_key,day,payload) VALUES($1,$2,$3) ON CONFLICT(run_key,day) DO UPDATE SET payload=EXCLUDED.payload',[checkpointKey,row.day,payload]);await saveCheckpoint();await checkpointPool.query('COMMIT');}catch(e){await checkpointPool.query('ROLLBACK');throw e;}
}
async function execute(){
 selfTest();sweepSelfTest();STATE.startedAt=new Date().toISOString();STATE.total=751;STATE.stage='loading_inputs';
 try{
  const resumed=await initCheckpointStore();if(resumed&&['completed_with_coverage_limits','blocked'].includes(STATE.stage)){if(STATE.stage==='completed_with_coverage_limits')emit('flame_customer_rankings',{rankings:flameCustomerRankings()});return;}
  for(const day of sessions().slice(STATE.completed)){
   STATE.currentDay=day;const before=structuredClone(accounts),completedBefore=STATE.completed;
   await recoverDataOperation(async()=>{const row=await replayDay(day);if(row.accounts.length!==accounts.length||row.accounts.some(a=>a.unresolved.length))throw Error('unresolved_sweep_day');await commitDay(row);},'day',()=>{accounts.splice(0,accounts.length,...structuredClone(before));STATE.completed=completedBefore;});
   emit('sweep_progress',{completed:STATE.completed,total:751,day,requests:STATE.requests,memoryMB:Math.round(process.memoryUsage().rss/1048576)});
  }
  const natural=accounts.find(a=>a.scenario.id==='flame_base'&&a.fillCase==='natural'),adverse=accounts.find(a=>a.scenario.id==='flame_base'&&a.fillCase==='adverse3c');
  assert.equal(sweepStats(natural).endingEquity,8185.20);assert.equal(sweepStats(adverse).endingEquity,2116.80);assert.equal(natural.tradeCounts.total,670);assert.equal(adverse.tradeCounts.total,97);
  for(const [fill,end,count] of [['natural',8842.40,930],['adverse3c',4322.40,627]]){const spark=accounts.find(a=>a.scenario.id==='spark_base'&&a.fillCase===fill);assert.equal(sweepStats(spark).endingEquity,end);assert.equal(spark.tradeCounts.total,count);}
  STATE.stage='completed_with_coverage_limits';STATE.baselineParity=true;await saveCheckpoint();emit('sweep_finished',{completed:751,paths:accounts.length,baselineParity:true});emit('flame_customer_rankings',{rankings:flameCustomerRankings()});
 }catch(e){STATE.stage='blocked';STATE.error=String(e.message);STATE.dataErrors.push({day:STATE.currentDay,error:STATE.error});try{await saveCheckpoint();}catch{}emit('sweep_blocked',{...STATE});}
}

function start() {
 process.env.FLAME_FAST_START='on';process.env.SPARK_FAST_START='on';
 const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');res.setHeader('Content-Type','application/json');res.setHeader('Cache-Control','no-store');
  if(url.pathname==='/health'){res.end(JSON.stringify({ok:true}));return;}
  if(!process.env.RESEARCH_ACCESS_TOKEN||req.headers.authorization!==`Bearer ${process.env.RESEARCH_ACCESS_TOKEN}`){res.statusCode=403;res.end(JSON.stringify({error:'private_research'}));return;}
  try {
   if(url.pathname==='/status'||url.pathname==='/')res.end(JSON.stringify({...STATE,engineHash:sha(fs.readFileSync(__filename)),scenarios:scenarioGrid().length,paths:accounts.length}));
   else if(url.pathname==='/report')res.end(JSON.stringify(sweepSnapshot()));
   else if(url.pathname==='/day'){
    const d=url.searchParams.get('date');if(!sessions().includes(d)){res.statusCode=400;res.end('{}');return;}
    const r=await checkpointPool.query('SELECT payload FROM flame_event_risk_sweep_days WHERE run_key=$1 AND day=$2',[checkpointKey,d]);
    if(!r.rows.length){res.statusCode=404;res.end('{}');return;}res.end(zlib.gunzipSync(r.rows[0].payload));
   }else {res.statusCode=404;res.end('{}');}
  }catch(e){res.statusCode=500;res.end(JSON.stringify({error:String(e.message)}));}
 });
 server.listen(Number(process.env.PORT||10000),'0.0.0.0',()=>execute());
}
if(require.main===module){if(process.argv.includes('--self-test')){selfTest();sweepSelfTest();}else start();}
module.exports={start,scenarioGrid,scenarioCandidate,minuteAdmission,dynamicExit,eventBlocked,capAddedLots,scenarioRiskCapacity,profitLockCapacity,FOMC_DECISION_DAYS,MACRO_CALENDAR,sessions,csv,clock,minute,sweepSelfTest,accounts,SPEC,replayDay,setTestHistories:(data)=>{vix=data.vix;eod=data.eod;gamma=data.gamma||{};if(data.vixMinute){vixMinute.clear();for(const [day,row] of data.vixMinute)vixMinute.set(day,row);}reconstructGammaEnabled=false;}};
