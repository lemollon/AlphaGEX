import { Client } from 'pg'

/**
 * Cluster-wide singleton lock for the trading scanner.
 *
 * WHY THIS EXISTS
 * The scanner places REAL broker orders. Its only other double-fill protection
 * (`_lastProductionPlacedAt` in scanner.ts) is an in-memory map whose correctness
 * argument is "JavaScript's single-threaded event loop" — true within ONE process
 * and worthless across two. The DB gate can't substitute either: the position
 * INSERT happens AFTER Tradier fills, so two processes both read zero rows and
 * both place. A real double-fill already happened on 2026-05-18 from a zombie
 * async tick inside a single process; two processes reproduce it structurally.
 *
 * SCANNER_ENABLED (see db.ts) stops the *other service* from scanning. It does
 * NOT stop a second INSTANCE of the scanner service — Render scale-out, or the
 * overlap window during a zero-downtime deploy where the new instance passes its
 * health check (which hits the DB, which starts the scanner) before the old one
 * drains. This lock is what makes the guarantee hold regardless of process count.
 *
 * HOW
 * `pg_try_advisory_lock` is session-scoped: held until explicitly unlocked or the
 * connection ends, and it never blocks. We hold it on a DEDICATED Client, not a
 * pooled one — a pooled connection can be recycled or reaped while idle, which
 * would silently drop the lock while the scanner kept running.
 *
 * FAIL CLOSED. Any error acquiring the lock means "someone else may be scanning",
 * so we do not scan. A silent bot is recoverable; a double order is not.
 */

// Arbitrary but fixed: "ironforge scanner". Must never change — changing it
// would let an old and a new deploy each hold a different lock and both scan.
const SCANNER_LOCK_KEY = 8_147_321_906

let _client: Client | null = null
let _held = false

/**
 * Try to become the one scanning process.
 *
 * Returns true only if this process now holds the lock. The connection is kept
 * open for the lifetime of the process — do not close it.
 */
export async function acquireScannerLock(): Promise<boolean> {
  if (_held) return true

  const client = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : undefined,
    // Name it so `pg_stat_activity` shows who is holding the lock during an incident.
    application_name: 'ironforge-scanner-lock',
  })

  try {
    await client.connect()
    const res = await client.query<{ locked: boolean }>(
      'SELECT pg_try_advisory_lock($1) AS locked',
      [SCANNER_LOCK_KEY],
    )
    const locked = res.rows[0]?.locked === true

    if (!locked) {
      // Another process is scanning. Expected during a deploy overlap.
      await client.end().catch(() => {})
      console.log('[scanner-lock] another process holds the scanner lock — not scanning in this process')
      return false
    }

    _client = client
    _held = true

    // If the lock connection dies, the lock is gone but our intervals are not.
    // Rather than keep scanning unprotected, make the failure loud and fatal:
    // the process exits, Render restarts it, and it re-races for the lock
    // cleanly. Continuing to trade after losing the singleton guarantee is the
    // one outcome this whole module exists to prevent.
    client.on('error', (err) => {
      console.error('[scanner-lock] FATAL: lock connection lost — exiting so we cannot trade unprotected:', err)
      _held = false
      _client = null
      process.exit(1)
    })

    console.log('[scanner-lock] acquired — this process is the scanner')
    return true
  } catch (err) {
    console.error('[scanner-lock] could not acquire lock — refusing to scan (fail closed):', err)
    await client.end().catch(() => {})
    return false
  }
}

/** True if this process currently holds the scanner lock. For diagnostics. */
export function holdsScannerLock(): boolean {
  return _held
}

/** Test-only: release the lock and close the dedicated connection. */
export async function __releaseScannerLockForTests(): Promise<void> {
  if (_client) {
    await _client.query('SELECT pg_advisory_unlock($1)', [SCANNER_LOCK_KEY]).catch(() => {})
    await _client.end().catch(() => {})
  }
  _client = null
  _held = false
}
