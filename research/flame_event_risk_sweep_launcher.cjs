// Research service only. Preserve the immutable original replay and build tests.
const Module=require('node:module'),path=require('node:path');
const target=path.resolve(__dirname,'spark_flame_current_3y_20260928.cjs');
if(process.argv[1]&&path.resolve(process.argv[1])===target&&!process.argv.includes('--self-test')){
 // Node 24 may leave `.cjs` undefined during `--require` preloading even
 // though CommonJS `.js` handling is available.  Fall back to it so the
 // launcher works both as a preload and as a normal module.
 const previous=Module._extensions['.cjs']||Module._extensions['.js'];
 const loader=process.env.RESEARCH_REPAIR_SPY_GAPS==='1'
  ? "require('./research_repair_spy_minute_gaps_20261001.cjs').main().catch(error=>{console.error('SPY_GAP_REPAIR_FATAL',error.message);process.exitCode=1;});"
  : process.env.RESEARCH_QUALITY_FINALIZE==='1'
  ? "require('./research_dataset_quality_finalize_20261001.cjs').main().catch(error=>{console.error('QUALITY_FINALIZER_FATAL',error.message);process.exitCode=1;});"
  : process.env.RESEARCH_DATA_QUALITY==='1'
  ? "require('./research_dataset_quality_20261001.cjs').main().catch(error=>{console.error('QUALITY_FATAL',error.message);process.exitCode=1;});"
  : process.env.RESEARCH_INDEX_MINUTE_IMPORT==='1'
  ? "require('./index_minutes_theta_importer.cjs').main().catch(error=>{console.error('INDEX_IMPORT_FATAL',error&&error.stack?error.stack:String(error));process.exitCode=1;});"
  : (process.env.MINUTE_CONTROLLER_SWEEP==='1' ? "require('./minute_controller_sweep_20261001.cjs').start();" : (process.env.FLAME_EVENT_RISK_SWEEP==='1' ? "require('./flame_event_risk_sweep_20260930.cjs').start();" : null));
 if(loader) Module._extensions['.cjs']=function(module,filename){if(filename===target){Module._extensions['.cjs']=previous;return module._compile(loader,filename);}return previous(module,filename);};
}
