/* Finalize an already completed full audit; no performance checkpoint writes. */
const http=require('node:http'),imp=require('./index_minutes_theta_importer.cjs');
let state={stage:'starting'};
const gapSql=`WITH expected AS(SELECT s.day,generate_series(s.day+'09:30:00'::time,s.day+s.close_time-interval '1 minute',interval '1 minute') ts FROM research_quality_sessions_20261001 s) SELECT day::text,count(*) expected,count(*) FILTER(WHERE spy.ts IS NULL) missing_spy,count(*) FILTER(WHERE vix.ts IS NULL) missing_vix FROM expected e LEFT JOIN research_spy_minute_valid spy ON spy.ts=e.ts LEFT JOIN research_vix_index_minute_valid vix ON vix.ts=e.ts GROUP BY day HAVING count(*) FILTER(WHERE spy.ts IS NULL OR vix.ts IS NULL)>0 ORDER BY day`;
async function main(){
 http.createServer((req,res)=>{res.setHeader('Content-Type','application/json');if(req.url==='/health')return res.end('{"ok":true}');if(req.headers.authorization!=='Bearer '+process.env.RESEARCH_ACCESS_TOKEN){res.statusCode=403;return res.end('{}');}res.end(JSON.stringify(state));}).listen(Number(process.env.PORT||10000),'0.0.0.0');
 const Pool=imp.loadPool(),pool=new Pool({connectionString:process.env.RESEARCH_DATABASE_URL,max:1,ssl:true}),c=await pool.connect();
 const save=async()=>{state.updatedAt=new Date().toISOString();await c.query("UPDATE research_dataset_quality_reports SET report=$1::jsonb,updated_at=now() WHERE run_id='20261001-quality-v1'",[JSON.stringify(state)]);};
 try{
  if((await c.query('SELECT current_database() db')).rows[0].db!=='alphagex_backtest')throw Error('isolation_required');
  state=(await c.query("SELECT report FROM research_dataset_quality_reports WHERE run_id='20261001-quality-v1'")).rows[0]?.report;
  if(!state?.checks?.minute_gaps)throw Error('full_audit_not_complete');
  state.stage='finalizing';state.imports??=[];state.checks.options_chain_snapshots=[{rows:0,note:'Read-only independent query confirmed empty table; not a historical execution source.'}];await save();
  // Retry missing full days from authenticated provider, never interpolate.
  for(const gap of state.checks.minute_gaps)for(const [field,table,ep,symbol,mode] of [
   ['missing_spy','spy_minute_3y','/v3/stock/history/ohlc','SPY','ohlc'],
   ['missing_vix','vix_index_price_3y','/v3/index/history/price','VIX','price']]){
   if(+gap[field]===0)continue;
   try{const rows=await imp.importRange(c,table,ep,symbol,gap.day,gap.day,mode);state.imports.push({table,day:gap.day,rows,verified:rows>0,reason:'minute_gap_recheck'});}
   catch(e){state.imports.push({table,day:gap.day,error:e.message,verified:false});}
   await save();
  }
  for(const [table,name] of [['research_spy_option_minute_valid','research_spy_prior_eod_valid'],['research_vix_option_minute_valid','research_vix_prior_eod_valid']]){
   await c.query(`CREATE OR REPLACE VIEW ${name} AS SELECT r.* FROM ${table} r WHERE prior_eod_trade_date<trade_date AND prior_eod_underlying_price>0 AND prior_eod_underlying_price<'Infinity'::float8 AND CASE WHEN upper(cp) IN ('C','CALL') THEN prior_eod_call_bid>=0 AND prior_eod_call_ask>0 AND prior_eod_call_bid<=prior_eod_call_ask AND prior_eod_call_ask<'Infinity'::float8 AND prior_eod_call_oi>=0 ELSE prior_eod_put_bid>=0 AND prior_eod_put_ask>0 AND prior_eod_put_bid<=prior_eod_put_ask AND prior_eod_put_ask<'Infinity'::float8 AND prior_eod_put_oi>=0 END`);
  }
  await c.query("COMMENT ON TABLE vix_minute_3y IS 'INVALID_SOURCE: audited 2026-10-01; all 305762 OHLC rows zero. Not VIX index signals. Use research_vix_index_minute_valid; no synthesized OHLC.'");
  await c.query("COMMENT ON TABLE spy_history_full IS 'PARTIAL older-history backfill (2020 through July 2022 as of 2026-10-01). Not new subminute data.'");
  await c.query("COMMENT ON VIEW research_spy_prior_eod_valid IS 'Prior-session feature observations only. Filtered crossed/negative/missing prices and OI; never contemporaneous execution quotes.'");
  await c.query("COMMENT ON VIEW research_vix_prior_eod_valid IS 'VIX OPTION prior-session features, not the VIX index. Never contemporaneous execution quotes.'");
  for(const [dataset,key,value] of [
   ['vix_minute_3y','quality_status','INVALID_SOURCE_ALL_ZERO_OHLC: use vix_index_price_3y; preserve raw for audit'],
   ['vix_index_price_3y','quality_source','ThetaData index PRICE minute points; positive observations, not OHLC'],
   ['spy_history_full','quality_status','PARTIAL_OLDER_HISTORY_BACKFILL: 2020-01-03 through 2022-07-29'],
   ['the_rock_3y','quality_execution_source','Trade bars/priorEOD features only; no historical NBBO/depth. Use authenticated option quote provider for fills'],
   ['global','quality_views','research_spy_minute_valid,research_vix_index_minute_valid,research_spy_option_minute_valid,research_vix_option_minute_valid,research_spy_prior_eod_valid,research_vix_prior_eod_valid; frozen751calendar and halfdays']]){
    await c.query('DELETE FROM dataset_metadata WHERE dataset=$1 AND key=$2',[dataset,key]);
    await c.query('INSERT INTO dataset_metadata(dataset,key,value) VALUES($1,$2,$3)',[dataset,key,value]);
  }
  state.checks.minute_gaps=(await c.query(gapSql)).rows;
  state.checks.curated_minute_coverage=(await c.query("SELECT 'spy' series,count(*) rows,count(DISTINCT trade_date) days,min(trade_date) first_day,max(trade_date) last_day FROM research_spy_minute_valid UNION ALL SELECT 'vix_index',count(*),count(DISTINCT trade_date),min(trade_date),max(trade_date) FROM research_vix_index_minute_valid")).rows;
  state.checks.expected_calendar=(await c.query("SELECT count(*) days,sum(extract(epoch FROM close_time-'09:30:00'::time)/60)::int expected_minutes FROM research_quality_sessions_20261001")).rows;
  state.checks.views=(await c.query("SELECT table_name FROM information_schema.views WHERE table_name LIKE 'research_%_valid' ORDER BY table_name")).rows;
  state.limits.push('Crossed prior-EOD quotes are excluded from dedicated EOD feature views, not repaired into invented prices. GEX metadata has unknown intraday availability: do not use as causal minute signal until original provenance is recovered.');
  state.stage=state.checks.minute_gaps.length?'complete_with_coverage_limits':'complete_with_source_limits';
  await save();console.log('QUALITY_FINALIZED '+JSON.stringify({stage:state.stage,gaps:state.checks.minute_gaps,coverage:state.checks.curated_minute_coverage}));
 }catch(e){state??={};state.stage='blocked';state.error=e.message;console.error('QUALITY_FINALIZER_BLOCKED '+e.message);throw e;}
 finally{c.release();await pool.end();}
}
module.exports={main};if(require.main===module)main().catch(e=>{console.error(e.message);process.exitCode=1;});

