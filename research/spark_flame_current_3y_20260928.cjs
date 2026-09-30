const indexMinuteImportMode =
  process.env.RESEARCH_INDEX_MINUTE_IMPORT === '1' &&
  process.argv[1] && process.argv[1].endsWith('spark_flame_current_3y_20260928.cjs') &&
  !process.argv.includes('--self-test');
if (indexMinuteImportMode) {
  require('./index_minutes_theta_importer.cjs').main().catch(error => {
    console.error('INDEX_IMPORT_FATAL', error && error.stack ? error.stack : String(error));
    process.exitCode = 1;
  });
} else {
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
  id: 'spark-flame-current-3y-20260928-v2-reconstructed-gamma', sourceCommit: '3637fd18396b9ab532ee0d9bd42281338353a8a2',
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
  blackout: 'BLACKOUT_HALT_ENABLED=false in frozen source', weekdaySkips: [],
  dependencies: 'No external Node packages. Private ThetaData proxy for historical market data.',
};
const OUT = process.env.RESEARCH_OUTPUT_DIR || '/tmp/spark-flame-current-3y';
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
  } catch(e) {last=e;if(e.retryable===false)break;if(attempt<2)await new Promise(resolve=>setTimeout(resolve,1000*(attempt+1)));}
 }
 throw last;
}
const BASE = process.env.THETADATA_BASE_URL || 'http://thetadata-proxy:10000';
const feed = (endpoint, params) => request(BASE+endpoint, params, true);
let vix=[], eod={}, gamma={'2026-09-28':{value:13643544500.438574,source:'tradier_chain_dollar_gex_dte0-60'}};
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
  catch(e){if(e.message==='http_404'){this.cache.set(key,{start,quotes:new Map()});this.gaps.push({day:this.day,symbol,right,strike,start,reason:'provider_explicit_no_observations'});return this.cache.get(key).quotes;}throw e;}

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
 const deposit=cents(SPEC.seeds[bot]);return {bot,profile,fillCase,deposit,equity:deposit,peak:deposit,floorPeak:deposit,triggered:false,fast:FAST.seedFastStartState(deposit/100),trades:[],days:[],skips:{},unresolved:[],floorBreaches:0};
}
const accounts=[];
for(const bot of ['flame','spark'])for(const p of SPEC.profiles)for(const fillCase of Object.keys(SPEC.fillCases))accounts.push(newAccount(bot,p,fillCase));
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
 return {n:Math.max(0,n),ml,result};
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
function realizeSpread(spread,entry,credit,spots,close,settle,slip) {
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
 const rr=await feed('/v3/stock/history/ohlc',{symbol:'SPY',date:day,interval:'1m',start_time:'09:30:00',end_time:clock(close),venue:'utp_cta'});
 const spots=new Map();for(const r of rr){const m=minute(r.timestamp||r.datetime,day);if(m>=close)continue;if(r.symbol?.trim()&&r.symbol.trim().toUpperCase()!=='SPY')throw Error('wrong_stock_identity');const b={open:+r.open,high:+r.high,low:+r.low,close:+r.close};if(Object.values(b).every(x=>x===0)&&+r.volume===0)continue;if(Object.values(b).some(x=>!Number.isFinite(x)||x<=0))throw Error('invalid_stock');spots.set(m,b);}
 if(!eod[day])throw Error('official_SPY_close_missing');
 if(reconstructGammaEnabled){const spot=spots.get(665)?.open;if(!(spot>0))throw Error('gamma_current_spot_missing');await loadGammaDay(day,spot);}
 const dq=new Quotes(day,close), daily={day,vix:vg,close,accounts:[]};
 for(const bot of ['spark','flame']) {
  const cfg=SPEC.bots[bot], group=accounts.filter(a=>a.bot===bot), active=new Map(group.map(a=>[a,[]]));
  const hosts=new Map(), flints=new Set();
  const candidate=vg.ratio<=cfg.vix;
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
    if(!host&&p&&p.credit-slip>=.10) {
     proposed=hostSize(a,p.credit-slip,vg.ratio,Math.min(p.bidSize,p.askSize),a.equity-active.get(a).reduce((s,t)=>s+t.risk,0),c&&c.credit-slip>=.10?c.credit-slip:null);
    }
    // FLINT precedes the actual host entry, matching scanner order. Retry
    // profits/credit/quote gates within the entry window until filled.
    if(!flints.has(a)&&c&&c.credit-slip>=.10) {
     const f=flintSize(a,c.credit-slip,vg.ratio,candidate,host||proposed,Math.floor(Math.min(c.bidSize,c.askSize)),day);
     const available=a.equity-active.get(a).reduce((s,t)=>s+t.risk,0);
     const n=Math.min(f.n,Math.floor(Math.max(0,available)/f.ml));
     if(n>0) {active.get(a).push({spread:call,n,credit:c.credit-slip,entry:m,risk:f.ml*n,leg:'flint'});flints.add(a);}
    }
    // The real scanner evaluates FLINT first, then persists the host floor,
    // including a floor-capped zero-sized host decision.
    if(proposed)persistHost(a,proposed);
    if(!host&&proposed&&proposed.n>0) {
     // Re-read buying power after FLINT reserved its collateral.
     const available=a.equity-active.get(a).reduce((s,t)=>s+t.risk,0);proposed.n=Math.min(proposed.n,Math.floor(Math.max(0,available)/proposed.ml));
     if(proposed.n<=0)continue;
     hosts.set(a,proposed);
     let decision={nXsp:0,nSpy:proposed.n,reason:'xsp_quote_unavailable'};
     if(SPEC.xspSwap) {
      if(xsp===null)xsp=await dq.spread('XSP','put',put.short,put.long,m);
      const xq=xsp&&xsp.at(m);
      decision=X.decideXspSwap({nHost:proposed.n,spyCreditPerContract:p.credit-slip,xspCreditPerContract:xq?xq.credit-slip:null,xspShortBidSize:xq?.bidSize??null});
      if(decision.nXsp)active.get(a).push({spread:xsp,n:decision.nXsp,credit:xq.credit-slip,entry:m,risk:cents((cfg.width-xq.credit+slip)*100)*decision.nXsp,leg:'host_xsp'});
     }
     if(decision.nSpy)active.get(a).push({spread:put,n:decision.nSpy,credit:p.credit-slip,entry:m,risk:proposed.ml*decision.nSpy,leg:'host_spy'});
     proposed.xspDecision=decision.reason;
    }
   }
   if(group.every(a=>(hosts.has(a)||!candidate)&&flints.has(a)))break;
   // Avoid querying all retry quotes when no account could possibly trade FLINT.
   if(group.every(a=>a.equity<=a.deposit)&&(hosts.size===group.length||!candidate))break;
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
    const result=t.spread.symbol==='XSP'?(SPX[day]?{pnl:money((t.credit-Math.min(cfg.width,Math.max(0,t.spread.short-SPX[day]/10)))*100-SPEC.feeDollarsPerSpread),exit:close,reason:'cash_settlement'}:{unresolved:'SPX_settlement_missing'}):realizeSpread(t.spread,t.entry,t.credit,spots,close,eod[day],SPEC.fillCases[a.fillCase]);
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
   for(const t of resolved)if(!t.unresolved){const pnl=cents(t.pnl*t.n);net+=pnl;const tr={day,leg:t.leg,symbol:t.spread.symbol,short:t.spread.short,long:t.spread.long,entry:t.entry,exit:t.exit,n:t.n,credit:money(t.credit),pnl:money(pnl/100),reason:t.reason};if(t.spread.repairs[t.exit])tr.quoteRepair=t.spread.repairs[t.exit];a.trades.push(tr);}
   a.equity+=net;a.peak=Math.max(a.peak,a.equity);
   if(a.triggered&&a.equity<a.deposit)a.floorBreaches++;
   const row={day,before:before/100,after:a.equity/100,pnl:net/100,markedMin:mtmMin/100,markedPeak:mtmPeak/100,markedDD:markedDD/100,markGaps,hostN:hosts.get(a)?.n||0,flintN:resolved.filter(t=>t.leg==='flint').reduce((s,t)=>s+t.n,0),xsp:hosts.get(a)?.xspDecision||null,triggered:a.triggered,floor:C.currentFloorLevelCents(a.deposit,a.floorPeak,a.triggered,.10)/100,unresolved};
   a.days.push(row);daily.accounts.push({bot:a.bot,profile:a.profile,fillCase:a.fillCase,...row});
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
async function initCheckpointStore() {
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
async function saveCheckpoint() {
 if(!checkpointPool)return;
 const body=zlib.gzipSync(JSON.stringify({state:STATE,accounts,gamma,vix,eod,spx:SPX,manifest,daily:[...rowsByDay]}));
 await checkpointPool.query('INSERT INTO spark_flame_research_checkpoints(run_key,status,completed,checkpoint) VALUES($1,$2,$3,$4) ON CONFLICT(run_key) DO UPDATE SET status=EXCLUDED.status,completed=EXCLUDED.completed,checkpoint=EXCLUDED.checkpoint,updated_at=NOW()',[checkpointKey,STATE.stage,STATE.completed,body]);
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
   emit('retrying_data',{phase,day:STATE.currentDay,attempts,delayMs,error:STATE.retryError});
   await saveCheckpoint();await new Promise(resolve=>setTimeout(resolve,delayMs));
  }
 }
}
async function execute() {
 selfTest();STATE.startedAt=new Date().toISOString();STATE.stage='loading_history';STATE.total=sessions().length;
 const sourceHashes={};for(const file of ['customer-executor/contracts.ts','one-strategy.ts','ebb-sizing.ts','fast-start-sizing.ts','flint.ts','xsp-swap.ts'])sourceHashes[file]=sha(fs.readFileSync(path.join(LIB,file)));
 emit('frozen_spec',{spec:SPEC,sourceHashes,sessions:STATE.total});
 try {
  const resumed=await initCheckpointStore();
  if(resumed&&['completed_with_coverage_limits','blocked','incomplete'].includes(STATE.stage)){report=snapshot();return;}
  if(!resumed||STATE.retryPhase==='history')await recoverDataOperation(histories,'history');
  if(reconstructGammaEnabled)await recoverDataOperation(warmGamma,'warmup');STATE.stage='running';
  for(const day of sessions().slice(STATE.completed)) {
   STATE.currentDay=day;
   const beforeAccounts=structuredClone(accounts);
   try {const row=await recoverDataOperation(async()=>{const row=await replayDay(day);if(row.accounts.some(a=>a.unresolved?.length))throw Error('unresolved_day_exit:'+row.accounts.flatMap(a=>a.unresolved||[]).join(','));return row;},'day',()=>accounts.splice(0,accounts.length,...structuredClone(beforeAccounts)));STATE.stage='running';rowsByDay.set(day,row);fs.writeFileSync(path.join(OUT,day+'.json'),JSON.stringify(row));emit('day',row);}
   catch(e){accounts.splice(0,accounts.length,...beforeAccounts);STATE.dataErrors.push({day,error:String(e.message)});emit('data_error',{day,error:String(e.message)});for(const a of accounts){a.invalidFrom??=day;a.unresolved.push({day,reasons:['data_error']});}throw e;}
   STATE.completed++;if(STATE.completed%5===0){snapshot();await saveCheckpoint();emit('progress',{...STATE});}
  }
  STATE.stage=STATE.dataErrors.length?'incomplete':'completed_with_coverage_limits';report=snapshot();await saveCheckpoint();emit('finished',{stage:STATE.stage,summary:report.summary});
 }catch(e){STATE.stage='blocked';STATE.error=String(e.message);report=snapshot();try{await saveCheckpoint();}catch{}emit('blocked',{...STATE});}
}
if(require.main===module) {
 process.env.FLAME_FAST_START='on';process.env.SPARK_FAST_START='on';
 if(process.argv.includes('--self-test')) {selfTest();process.exit(0);}
 const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');res.setHeader('Content-Type','application/json');res.setHeader('Cache-Control','no-store');
  if(url.pathname==='/health'){res.end(JSON.stringify({ok:true}));return;}
  const secret=process.env.RESEARCH_ACCESS_TOKEN;
  if(!secret||req.headers.authorization!==`Bearer ${secret}`){res.statusCode=403;res.end(JSON.stringify({error:'private_research'}));return;}
  if(url.pathname==='/status'||url.pathname==='/')res.end(JSON.stringify({...STATE,percent:STATE.total?money(100*STATE.completed/STATE.total):0}));
  else if(url.pathname==='/report')res.end(JSON.stringify(report||snapshot()));
  else if(url.pathname==='/trades')res.end(JSON.stringify(accounts.map(a=>({bot:a.bot,profile:a.profile,fillCase:a.fillCase,trades:a.trades}))));
  else if(url.pathname==='/daily')res.end(JSON.stringify([...rowsByDay.values()]));
  else if(url.pathname==='/source'){
   const number=Number(url.searchParams.get('number'));if(!Number.isInteger(number)||number<1||number>manifest.length){res.statusCode=404;res.end(JSON.stringify({error:'source_not_found'}));return;}
   const file=path.join(OUT,`${number}.csv`);if(!fs.existsSync(file)){res.statusCode=404;res.end(JSON.stringify({error:'raw_source_evicted_on_restart',sha256:manifest[number-1].sha256}));return;}res.setHeader('Content-Type','text/csv');res.end(fs.readFileSync(file,'utf8'));
  }
  else {res.statusCode=404;res.end(JSON.stringify({error:'not_found'}));}
 });
 server.listen(Number(process.env.PORT||10000),'0.0.0.0',()=>execute());
}
module.exports={selfTest,hostSize,flintSize,realizeSpread,sessions,stats,csv,SPEC,replayDay,accounts,setTestHistories: (data)=>{vix=data.vix;eod=data.eod;reconstructGammaEnabled=false;}};

}
