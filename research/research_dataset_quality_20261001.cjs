/* Isolated historical research quality audit and verified source repair. */
const fs=require('node:fs'),http=require('node:http');
const importer=require('./index_minutes_theta_importer.cjs');
const sessions=require('./research_quality_sessions_20261001.json');
const halves=new Set(['2023-11-24','2024-07-03','2024-11-29','2024-12-24','2025-07-03','2025-11-28','2025-12-24']);
const status={stage:'starting',checks:{},imports:[],limits:[],updatedAt:new Date().toISOString()};
const log=(event,fields={})=>console.log('RESEARCH_QUALITY '+JSON.stringify({event,...fields}));
async function main(){
 http.createServer((req,res)=>{
  res.setHeader('Content-Type','application/json');res.setHeader('Cache-Control','no-store');
  if(req.url==='/health')return res.end(JSON.stringify({ok:true,stage:status.stage}));
  const token=process.env.RESEARCH_ACCESS_TOKEN;
  if(!token||req.headers.authorization!=='Bearer '+token){res.statusCode=401;return res.end('{}');}
  res.end(JSON.stringify(status));
 }).listen(Number(process.env.PORT||10000),'0.0.0.0');
 const Pool=importer.loadPool(),pool=new Pool({connectionString:process.env.RESEARCH_DATABASE_URL,max:1,ssl:true});
 const c=await pool.connect();
 const check=async(name,sql,params=[])=>{status.checks[name]=(await c.query(sql,params)).rows;status.updatedAt=new Date().toISOString();log('check',{name,result:status.checks[name]});};
 try{
  const id=(await c.query('SELECT current_database() AS db')).rows[0];
  if(id.db!=='alphagex_backtest')throw Error('research_database_isolation_failed');
  await c.query('SET statement_timeout = 240000');
  await importer.setup(c);
  await c.query('CREATE TABLE IF NOT EXISTS research_quality_sessions_20261001 (day date PRIMARY KEY, close_time time NOT NULL)');
  await c.query("INSERT INTO research_quality_sessions_20261001 SELECT * FROM unnest($1::date[],$2::time[]) ON CONFLICT(day) DO UPDATE SET close_time=EXCLUDED.close_time",[sessions,sessions.map(d=>halves.has(d)?'13:00:00':'16:00:00')]);
  // Raw inputs remain unchanged except verified provider upserts of missing dates.
  for(const [table,endpoint,symbol,mode,valid] of [
    ['spy_minute_3y','/v3/stock/history/ohlc','SPY','ohlc','close>0'],
    ['vix_index_price_3y','/v3/index/history/price','VIX','price','price>0']]){
   const missing=(await c.query(`SELECT s.day::text FROM research_quality_sessions_20261001 s WHERE NOT EXISTS(SELECT 1 FROM ${table} r WHERE r.trade_date=s.day AND ${valid}) ORDER BY s.day`)).rows;
   status.stage='importing_missing_source';
   for(const {day} of missing){
    try{const rows=await importer.importRange(c,table,endpoint,symbol,day,day,mode);status.imports.push({table,day,rows,verified:rows>0});}
    catch(e){status.imports.push({table,day,error:e.message,verified:false});}
   }
  }
  status.stage='auditing';
  const ohlc="open>0 AND high>0 AND low>0 AND close>0 AND open<'Infinity'::float8 AND high<'Infinity'::float8 AND low<'Infinity'::float8 AND close<'Infinity'::float8 AND round(high::numeric,8)>=greatest(round(open::numeric,8),round(close::numeric,8),round(low::numeric,8)) AND round(low::numeric,8)<=least(round(open::numeric,8),round(close::numeric,8))";
  for(const table of ['spy_minute_3y','vix_minute_3y','the_rock_3y','vix_history_3y']){
   await check(table,`SELECT count(*) rows,min(trade_date) first_day,max(trade_date) last_day,count(*) FILTER(WHERE ${ohlc}) valid_ohlc,count(*) FILTER(WHERE open=0 AND high=0 AND low=0 AND close=0) zero_placeholders,count(*) FILTER(WHERE ts::date<>trade_date) wrong_date,count(*) FILTER(WHERE date_part('second',ts)<>0) subminute_rows,count(*) FILTER(WHERE volume<0) negative_volume FROM ${table}`);
  }
  for(const table of ['the_rock_3y','vix_history_3y']){
   await check(table+'_identity',`SELECT count(*) FILTER(WHERE strike<=0 OR strike>='Infinity'::float8 OR upper(cp) NOT IN ('C','P','CALL','PUT') OR expiration_date<trade_date) invalid_contract,count(*) FILTER(WHERE prior_eod_trade_date>=trade_date) future_eod,count(*) FILTER(WHERE prior_eod_call_bid>prior_eod_call_ask OR prior_eod_put_bid>prior_eod_put_ask) crossed_prior_eod,count(*) FILTER(WHERE prior_eod_trade_date IS NULL) missing_eod FROM ${table}`);
   await check(table+'_duplicates',`SELECT count(*) duplicate_groups,coalesce(sum(n-1),0) excess_rows FROM(SELECT count(*) n FROM ${table} GROUP BY trade_date,expiration_date,strike,cp,ts HAVING count(*)>1)d`);
  }
  await check('rock_feature_coverage',"SELECT min(trade_date) first_day,max(trade_date) last_day,count(DISTINCT trade_date) days FROM the_rock_3y WHERE gexmin_net_gex IS NOT NULL UNION ALL SELECT min(trade_date),max(trade_date),count(DISTINCT trade_date) FROM the_rock_3y WHERE prior_eod_gamma IS NOT NULL");
  await check('full_history',"SELECT min(trade_date) first_day,max(trade_date) last_day,count(*) rows FROM spy_history_full");
  await check('quote_columns',"SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('the_rock_3y','vix_history_3y') AND (column_name IN ('bid','ask','bid_size','ask_size') OR column_name LIKE '%nbbo%')");
  await c.query(`CREATE OR REPLACE VIEW research_spy_minute_valid AS SELECT r.* FROM spy_minute_3y r JOIN research_quality_sessions_20261001 s ON s.day=r.trade_date WHERE r.ts::date=r.trade_date AND r.ts::time>='09:30:00' AND r.ts::time<s.close_time AND ${ohlc} AND coalesce(volume,0)>=0`);
  await c.query("CREATE OR REPLACE VIEW research_vix_index_minute_valid AS SELECT r.* FROM vix_index_price_3y r JOIN research_quality_sessions_20261001 s ON s.day=r.trade_date WHERE r.ts::date=r.trade_date AND r.ts::time>='09:30:00' AND r.ts::time<s.close_time AND price>0 AND price<'Infinity'::float8");
  for(const table of ['the_rock_3y','vix_history_3y']){
   const name=table==='the_rock_3y'?'research_spy_option_minute_valid':'research_vix_option_minute_valid';
   await c.query(`CREATE OR REPLACE VIEW ${name} AS SELECT r.* FROM ${table} r JOIN research_quality_sessions_20261001 s ON s.day=r.trade_date WHERE r.ts::date=r.trade_date AND r.ts::time>='09:30:00' AND r.ts::time<s.close_time AND ${ohlc} AND volume>0 AND strike>0 AND strike<'Infinity'::float8 AND upper(cp) IN ('C','P','CALL','PUT') AND expiration_date${table==='the_rock_3y'?'=':'>='}trade_date AND (prior_eod_trade_date IS NULL OR prior_eod_trade_date<trade_date)`);
  }
  await check('minute_gaps',`WITH expected AS(SELECT s.day,generate_series(s.day+'09:30:00'::time,s.day+s.close_time-interval '1 minute',interval '1 minute') ts FROM research_quality_sessions_20261001 s) SELECT day::text,count(*) expected,count(*) FILTER(WHERE spy.ts IS NULL) missing_spy,count(*) FILTER(WHERE vix.ts IS NULL) missing_vix FROM expected e LEFT JOIN research_spy_minute_valid spy ON spy.ts=e.ts LEFT JOIN research_vix_index_minute_valid vix ON vix.ts=e.ts GROUP BY day HAVING count(*) FILTER(WHERE spy.ts IS NULL OR vix.ts IS NULL)>0 ORDER BY day`);
  status.limits=[
   'vix_minute_3y OHLC zero placeholders are INVALID; use positive VIX index observations, never VIX option prices.',
   'Minute index observations are not intraminute OHLC or tick data. No synthetic highs/lows.',
   'Option trade bars and prior EOD bid/ask are not executable contemporaneous NBBO; execution still requires provider option quotes.',
   'Prior-EOD and GEX coverage ends early; missing features remain NULL. Net GEX may be daily, not intraday recomputed.',
   'Raw timestamps are America/New_York wall time, not UTC despite connector display suffix.',
   'Curated views use the frozen 751-day study calendar, including early closes; raw source rows are preserved.',
   'Options with no trades have no bars; absent minute bars do not prove missing executable quotes.',
   'Full-history backfill is partial older history; not new subminute coverage.'
  ];
  status.stage=status.checks.minute_gaps.length?'complete_with_coverage_limits':'complete';
  await c.query("CREATE TABLE IF NOT EXISTS research_dataset_quality_reports(run_id text PRIMARY KEY,updated_at timestamptz NOT NULL DEFAULT now(),report jsonb NOT NULL)");
  await c.query("INSERT INTO research_dataset_quality_reports(run_id,report) VALUES('20261001-quality-v1',$1::jsonb) ON CONFLICT(run_id) DO UPDATE SET report=EXCLUDED.report,updated_at=now()",[JSON.stringify(status)]);
  log('finished',{stage:status.stage,imports:status.imports,gapDays:status.checks.minute_gaps.length});
 }catch(e){status.stage='blocked';status.error=e.message;log('blocked',{error:e.message});throw e;}
 finally{c.release();await pool.end();}
}
module.exports={main};if(require.main===module)main().catch(e=>{console.error(e.message);process.exitCode=1;});

