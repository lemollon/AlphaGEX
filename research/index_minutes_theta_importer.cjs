/* One-time, research-only SPY/VIX index minute import.
 * Uses only THETADATA_BASE_URL and RESEARCH_DATABASE_URL already configured
 * on the isolated Spark/Flame research service. Never reaches broker/order APIs.
 */
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

function loadPool() {
  try { return require('pg').Pool; }
  catch (firstError) {
    // The research runner deliberately has no root package install. Keep this
    // one-shot dependency outside the checkout and never alter production deps.
    const prefix = '/tmp/index-minute-import-pg';
    const target = path.join(prefix, 'node_modules', 'pg');
    if (!fs.existsSync(target)) {
      fs.mkdirSync(prefix, { recursive: true });
      execFileSync('npm', ['install', '--prefix', prefix, '--no-save', '--ignore-scripts', 'pg@8.16.3'],
        { stdio: 'inherit', timeout: 120000 });
    }
    return require(path.join(target)).Pool;
  }
}
const Pool = loadPool();

const START = '2023-10-02';
const END = '2026-09-29';
const BASE = process.env.THETADATA_BASE_URL || 'http://thetadata-proxy:10000';
const DB = process.env.RESEARCH_DATABASE_URL;
if (!DB) throw new Error('research_database_url_missing');

const pool = new Pool({ connectionString: DB, max: 1, ssl: true });
const log = (event, fields = {}) => console.log(`INDEX_IMPORT ${JSON.stringify({ event, utc: new Date().toISOString(), ...fields })}`);

function csv(body) {
  const data = []; let row = [], field = '', quoted = false;
  for (let i = 0; i < body.length; i++) {
    const c = body[i];
    if (c === '"') { if (quoted && body[i + 1] === '"') { field += '"'; i++; } else quoted = !quoted; }
    else if (c === ',' && !quoted) { row.push(field); field = ''; }
    else if (c === '\n' && !quoted) { row.push(field.replace(/\r$/, '')); if (row.some(Boolean)) data.push(row); row = []; field = ''; }
    else field += c;
  }
  if (field || row.length) { row.push(field.replace(/\r$/, '')); data.push(row); }
  const headers = (data.shift() || []).map((x, i) => (i === 0 ? x.replace(/^\uFEFF/, '') : x).trim().toLowerCase());
  return data.map(r => Object.fromEntries(headers.map((k, i) => [k, r[i] ?? ''])));
}

function iso(d) { return d.toISOString().slice(0, 10); }
function ranges() {
  const out = []; let cursor = new Date(`${START}T00:00:00Z`); const end = new Date(`${END}T00:00:00Z`);
  while (cursor <= end) {
    const next = new Date(cursor); next.setUTCDate(next.getUTCDate() + 29);
    out.push([iso(cursor), iso(next > end ? end : next)]);
    cursor = new Date(next); cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return out;
}

async function fetchBars(endpoint, symbol, startDate, endDate) {
  const url = new URL(`${BASE}${endpoint}`);
  Object.entries({ symbol, start_date: startDate, end_date: endDate, interval: '1m', start_time: '09:30:00', end_time: '16:00:00' })
    .forEach(([k, v]) => url.searchParams.set(k, v));
  let last;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(90000), headers: { 'Cache-Control': 'no-cache' } });
      if (!response.ok) throw new Error(`http_${response.status}`);
      if (response.headers.get('x-market-data-provider') !== 'thetadata') throw new Error('unverified_provider');
      const body = await response.text();
      const parsed = csv(body);
      if (parsed.length === 0 || !fetchBars.loggedSample) {
        fetchBars.loggedSample = true;
        log('provider_sample', { endpoint, symbol, startDate, endDate, bytes: body.length,
          headers: Object.keys(parsed[0] || {}), firstRow: parsed[0] || null });
      }
      return parsed;
    } catch (error) {
      last = error;
      if (attempt < 3) await new Promise(resolve => setTimeout(resolve, attempt * 2000));
    }
  }
  throw last;
}

function normalize(rows) {
  return rows.map(row => {
    const rawTs = String(row.timestamp || row.ts || row.datetime || row.date_time || '');
    const match = rawTs.match(/(\\d{4}-\\d{2}-\\d{2})[ T](\\d{2}:\\d{2}:\\d{2})/);
    const ts = match ? \`\${match[1]} \${match[2]}\` : '';
    const tradeDate = ts.slice(0, 10);
    const values = ['open', 'high', 'low', 'close', 'volume', 'count', 'vwap'].map(k => Number(row[k]));
    return { ts, tradeDate, open: values[0], high: values[1], low: values[2], close: values[3], volume: values[4], count: values[5], vwap: values[6] };
  }).filter(r => /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/.test(r.ts)
    && Number.isFinite(r.open) && Number.isFinite(r.high) && Number.isFinite(r.low) && Number.isFinite(r.close));
}

async function setup(client) {
  for (const table of ['spy_minute_3y', 'vix_minute_3y']) {
    await client.query(`CREATE TABLE IF NOT EXISTS ${table} (
      ts timestamp without time zone PRIMARY KEY,
      trade_date date NOT NULL,
      open double precision NOT NULL, high double precision NOT NULL,
      low double precision NOT NULL, close double precision NOT NULL,
      volume bigint, trade_count bigint, vwap double precision,
      provider text NOT NULL DEFAULT 'thetadata', imported_at timestamptz NOT NULL DEFAULT now()
    )`);
    await client.query(`CREATE INDEX IF NOT EXISTS ${table}_trade_date_idx ON ${table}(trade_date)`);
  }
}

async function upsert(client, table, rows) {
  if (!rows.length) return;
  await client.query(`INSERT INTO ${table}
    (ts, trade_date, open, high, low, close, volume, trade_count, vwap)
    SELECT * FROM unnest($1::timestamp[], $2::date[], $3::double precision[], $4::double precision[],
                         $5::double precision[], $6::double precision[], $7::bigint[], $8::bigint[], $9::double precision[])
    ON CONFLICT (ts) DO UPDATE SET
      trade_date=EXCLUDED.trade_date, open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
      close=EXCLUDED.close, volume=EXCLUDED.volume, trade_count=EXCLUDED.trade_count,
      vwap=EXCLUDED.vwap, provider='thetadata', imported_at=now()`, [
    rows.map(r => r.ts), rows.map(r => r.tradeDate), rows.map(r => r.open), rows.map(r => r.high),
    rows.map(r => r.low), rows.map(r => r.close), rows.map(r => Math.trunc(r.volume || 0)),
    rows.map(r => Math.trunc(r.count || 0)), rows.map(r => Number.isFinite(r.vwap) ? r.vwap : null),
  ]);
}

async function importSeries(client, table, endpoint, symbol) {
  let total = 0;
  const maxChunks = Number(process.env.INDEX_IMPORT_MAX_CHUNKS || 0);
  let chunks = 0;
  for (const [startDate, endDate] of ranges()) {
    if (maxChunks > 0 && chunks >= maxChunks) break;
    const rawRows = await fetchBars(endpoint, symbol, startDate, endDate);
    const rows = normalize(rawRows);
    if (rawRows.length > 0 && rows.length === 0) {
      log('normalize_rejected', { table, startDate, endDate, rawRows: rawRows.length,
        headers: Object.keys(rawRows[0] || {}), firstRow: rawRows[0] || null });
    }
    await upsert(client, table, rows); total += rows.length; chunks += 1;
    log('chunk_complete', { table, startDate, endDate, rows: rows.length, total });
  }
  return total;
}

async function main() {
  const client = await pool.connect();
  try {
    await setup(client);
    const spyRows = await importSeries(client, 'spy_minute_3y', '/v3/stock/history/ohlc', 'SPY');
    const vixRows = await importSeries(client, 'vix_minute_3y', '/v3/index/history/ohlc', 'VIX');
    const { rows } = await client.query(`SELECT 'spy' AS series, count(*)::int rows, min(ts) min_ts, max(ts) max_ts, count(DISTINCT trade_date)::int sessions FROM spy_minute_3y
      UNION ALL SELECT 'vix', count(*)::int, min(ts), max(ts), count(DISTINCT trade_date)::int FROM vix_minute_3y`);
    log('complete', { fetched: { spyRows, vixRows }, coverage: rows });
  } finally { client.release(); await pool.end(); }
}

module.exports = { main, csv, normalize, ranges };
if (require.main === module) main().catch(error => { log('failed', { message: error.message }); process.exitCode = 1; });
