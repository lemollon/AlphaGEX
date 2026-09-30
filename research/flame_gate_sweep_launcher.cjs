// Research service only. Preserve the immutable original replay and build tests.
const Module=require('node:module'),path=require('node:path');
const target=path.resolve(__dirname,'spark_flame_current_3y_20260928.cjs');
if(process.env.FLAME_GATE_SWEEP==='1'&&process.argv[1]&&path.resolve(process.argv[1])===target&&!process.argv.includes('--self-test')){
 const previous=Module._extensions['.cjs'];
 Module._extensions['.cjs']=function(module,filename){if(filename===target){Module._extensions['.cjs']=previous;return module._compile("require('./flame_gate_sweep_20260930.cjs').start();",filename);}return previous(module,filename);};
}
