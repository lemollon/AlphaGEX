// Research service only. Preserve the immutable original replay and build tests.
const Module=require('node:module'),path=require('node:path');
const target=path.resolve(__dirname,'spark_flame_current_3y_20260928.cjs');
if(process.argv[1]&&path.resolve(process.argv[1])===target&&!process.argv.includes('--self-test')){
 const previous=Module._extensions['.cjs'];
 const loader=process.env.RESEARCH_INDEX_MINUTE_IMPORT==='1'
  ? "require('./index_minutes_theta_importer.cjs').main().catch(error=>{console.error('INDEX_IMPORT_FATAL',error&&error.stack?error.stack:String(error));process.exitCode=1;});"
  : (process.env.FLAME_EVENT_RISK_SWEEP==='1' ? "require('./flame_event_risk_sweep_20260930.cjs').start();" : null);
 if(loader) Module._extensions['.cjs']=function(module,filename){if(filename===target){Module._extensions['.cjs']=previous;return module._compile(loader,filename);}return previous(module,filename);};
}
