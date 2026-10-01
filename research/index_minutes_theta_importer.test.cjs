/* Source validation tests; no database connection or network calls. */
process.env.RESEARCH_DATABASE_URL='postgresql://unused:unused@localhost/alphagex_backtest';
const assert=require('node:assert/strict');
const m=require('./index_minutes_theta_importer.cjs');
const bar={timestamp:'2023-09-29T09:30:00',open:'433.16',high:'433.33',low:'433.107',close:'433.33000000000004',volume:'10',count:'1',vwap:'433.2'};
assert.equal(m.normalize([bar])[0].close,433.33);
assert.equal(m.normalize([{...bar,open:0,high:0,low:0,close:0,volume:0,count:0}]).length,0);
assert.throws(()=>m.normalize([{...bar,open:0,high:0,low:0,close:0}]),/zero_price_with_activity/);
assert.throws(()=>m.normalize([{...bar,high:'432'}]),/invalid_ohlc_source/);
assert.throws(()=>m.normalize([{...bar,close:'NaN'}]),/invalid_ohlc_nonfinite/);
assert.throws(()=>m.normalize([{...bar,volume:'-1'}]),/invalid_ohlc_activity/);
assert.throws(()=>m.normalize([{...bar,count:'NaN'}]),/invalid_ohlc_activity/);
assert.throws(()=>m.normalize([{...bar,timestamp:'bad'}]),/timestamp/);
assert.equal(m.normalizePrice([{timestamp:bar.timestamp,price:16.06}])[0].price,16.06);
assert.equal(m.normalizePrice([{timestamp:bar.timestamp,price:0}]).length,0);
assert.equal(m.ranges()[0][0],'2023-09-29');
console.log('PASS 11 source validation checks');
