/**
 * Live proof that the scanner singleton lock works against a real Postgres.
 *
 * Simulates what a two-service deploy (or a zero-downtime deploy overlap) does:
 * two independent connections racing for the same advisory lock. Exactly one
 * must win. Run against a SCRATCH database — never production.
 *
 *   DATABASE_URL=postgres://... node scripts/verify-scanner-lock.mjs
 *
 * Mirrors the key and semantics in src/lib/scanner-lock.ts. If that key changes,
 * change it here too, or this proves nothing.
 */
import pg from 'pg'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

// Read the key out of the module under test rather than duplicating it — a
// hardcoded copy would keep passing after someone changed the real key, which
// is exactly the drift this test exists to catch. Falls back to the literal so
// the script still runs when copied somewhere without the source tree.
const FALLBACK_KEY = 8_147_321_906
function lockKeyFromSource() {
  try {
    const here = dirname(fileURLToPath(import.meta.url))
    const src = readFileSync(join(here, '..', 'src', 'lib', 'scanner-lock.ts'), 'utf8')
    const m = src.match(/SCANNER_LOCK_KEY\s*=\s*([0-9_]+)/)
    if (!m) throw new Error('SCANNER_LOCK_KEY not found in scanner-lock.ts')
    return Number(m[1].replace(/_/g, ''))
  } catch (err) {
    console.warn(`[warn] could not read key from source (${err.message}); using fallback`)
    return FALLBACK_KEY
  }
}

const SCANNER_LOCK_KEY = lockKeyFromSource()
console.log(`Using lock key ${SCANNER_LOCK_KEY}\n`)
const url = process.env.DATABASE_URL
if (!url) {
  console.error('DATABASE_URL required (use a scratch DB, not production)')
  process.exit(2)
}

const ssl = process.env.PGSSL === 'require' ? { rejectUnauthorized: false } : undefined
const connect = async (name) => {
  const c = new pg.Client({ connectionString: url, ssl, application_name: name })
  await c.connect()
  return c
}
const tryLock = async (c) =>
  (await c.query('SELECT pg_try_advisory_lock($1) AS locked', [SCANNER_LOCK_KEY])).rows[0].locked === true

let failures = 0
const check = (label, cond) => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}`)
  if (!cond) failures++
}

const a = await connect('scanner-lock-test-A')
const b = await connect('scanner-lock-test-B')

try {
  // 1. Two processes race → exactly one wins.
  const aGot = await tryLock(a)
  const bGot = await tryLock(b)
  check('exactly one process acquires the lock', aGot !== bGot)
  check('the winner is the first caller (A)', aGot === true && bGot === false)

  // 2. The loser stays locked out while the winner holds it.
  check('loser still cannot acquire on retry', (await tryLock(b)) === false)

  // 3. pg_try_advisory_lock never blocks — a slow DB must not wedge boot.
  const t0 = Date.now()
  await tryLock(b)
  check('non-blocking (returned in <1s)', Date.now() - t0 < 1000)

  // 4. Losing the connection releases the lock, so a restarted process can
  //    take over. This is why scanner-lock.ts exits the process on conn error.
  await a.end()
  // Postgres releases session locks asynchronously on disconnect; poll briefly.
  let reacquired = false
  for (let i = 0; i < 50 && !reacquired; i++) {
    reacquired = await tryLock(b)
    if (!reacquired) await new Promise((r) => setTimeout(r, 100))
  }
  check('lock is released when the holder disconnects (failover works)', reacquired)
} finally {
  await a.end().catch(() => {})
  await b.query('SELECT pg_advisory_unlock_all()').catch(() => {})
  await b.end().catch(() => {})
}

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECK(S) FAILED`)
process.exit(failures === 0 ? 0 : 1)
