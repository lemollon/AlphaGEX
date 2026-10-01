'use strict';
const assert=require('node:assert/strict');
const P=require('./spark_flame_profit_lock.cjs');

assert.equal(P.mondayOf('2026-10-01'),'2026-09-28');
let s=P.beginDay(null,'2026-09-28',500000,500000);
s=P.closeDay(s,530000); // $300 earned on Monday.
s=P.beginDay(s,'2026-09-29',530000,500000);
let r=P.admission(s,530000,10000,0,{weekRetention:.50,accountRetention:.50});
assert.equal(r.eligible,true);assert.equal(r.retainedFloorCents,515000);
r=P.admission(s,530000,16000,0,{weekRetention:.50,accountRetention:.50});
assert.equal(r.eligible,false);assert.equal(r.reason,'profit_lock_retained_profit');
r=P.cappedLots(s,530000,3,10000,0,{weekRetention:.50,accountRetention:.50});
assert.equal(r.lots,1,'only $150 of the $300 win is available for new risk');
r=P.admission(s,530000,10000,6000,{weekRetention:.50,accountRetention:.50});
assert.equal(r.availableRiskCents,9000);assert.equal(r.eligible,false,'earlier accepted risk is reserved');
s=P.beginDay(s,'2026-10-05',530000,500000);
r=P.admission(s,530000,16000,0,{weekRetention:.50,accountRetention:.50});
assert.equal(r.eligible,false,'account-level retention still protects an earlier win across weeks');
assert.throws(()=>P.admission(s,530000,10000,0,{weekRetention:1.1}),/invalid_retention/);
console.log('PASS: daily/weekly/account retained-profit floors, prior-risk reservation, week rollover, lot cap, invalid configuration');
