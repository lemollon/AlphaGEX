const assert=require('node:assert/strict');
const R=require('./flame_event_risk_sweep_20260930.cjs');
const day='2024-06-03';
const spots=new Map();
for(let m=570;m<960;m++)spots.set(m,{open:500,high:500.1,low:499.9,close:500});
R.setTestHistories({vix:[],eod:{},vixMinute:[[day,{spark:{before:20,entry:20},flame:{before:20,entry:21}}]]});
const spark={bot:'spark',baseGate:.90,minute:'combined'};
const flame={bot:'flame',baseGate:.80,minute:'combined'};
assert.equal(R.minuteAdmission(spark,.95,day,spots).eligible,true,'Spark uses morning VIX');
assert.equal(R.minuteAdmission(flame,.92,day,spots).eligible,false,'Flame uses afternoon VIX');
const initial=R.minuteAdmission(spark,.95,day,spots);
// Mutating the current minute high/low or any future bar cannot affect admission.
for(let m=665;m<960;m++)spots.set(m,{open:m===665?500:100,high:10000,low:1,close:1});
assert.deepEqual(R.minuteAdmission(spark,.95,day,spots),initial);
spots.delete(664);
assert.equal(R.minuteAdmission(spark,.95,day,spots).eligible,false,'Missing completed bar fails closed');
assert.equal(R.minuteAdmission(spark,.90,day,spots).eligible,true,'Original admission is preserved');
console.log('PASS: bot-specific clocks, future-bar invariance, entry-minute exclusion, missing-input rejection, original admission');
