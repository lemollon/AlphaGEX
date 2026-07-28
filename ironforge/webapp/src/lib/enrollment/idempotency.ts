import { customerQuery, customerExecute } from '@/lib/customers-db'

/**
 * Idempotency for create/activate endpoints (Enrollment spec §4).
 *
 * "Repeated payment or activation requests create one logical result" (§12). The
 * failure this prevents is not theoretical: a double-clicked Activate, or a client
 * retry after a timeout where the FIRST request actually succeeded, must not produce
 * two activations, two trials or two orders.
 *
 * How it works: the first caller inserts the key and proceeds; a second caller with
 * the same key loses the insert race and is handed the first call's stored response
 * instead of executing anything. The uniqueness is enforced by the PRIMARY KEY
 * (key, operation) in the database, NOT by a read-then-write check, because a
 * read-then-write has a window between the two where both callers see "not present".
 *
 * Keys are scoped to user + operation (§4), so one customer's key can never collide
 * with or replay into another's.
 */

export class IdempotencyConflict extends Error {
  constructor(readonly storedResponse: unknown) {
    super('Duplicate request')
    this.name = 'IdempotencyConflict'
  }
}

interface KeyRow { response_json: unknown }

/**
 * Claim a key. Returns:
 *   - { claimed: true }  → you are the first caller; do the work, then call `complete`.
 *   - { claimed: false, response } → a previous caller already did it; return `response`.
 *
 * `response` may be null when the first call is still in flight — the correct answer
 * then is a 409, not a second execution.
 */
export async function claimIdempotencyKey(opts: {
  key: string
  userId: string
  operation: string
}): Promise<{ claimed: true } | { claimed: false; response: unknown | null }> {
  // ON CONFLICT DO NOTHING makes the insert the race winner-determiner. RETURNING is
  // empty exactly when someone else already holds the key.
  const inserted = await customerQuery<{ key: string }>(
    `INSERT INTO idempotency_keys (key, user_id, operation)
     VALUES ($1, $2, $3)
     ON CONFLICT (key, operation) DO NOTHING
     RETURNING key`,
    [opts.key, opts.userId, opts.operation],
  )
  if (inserted.length > 0) return { claimed: true }

  // Someone else holds it. Scope the read to THIS user so a guessed key cannot be used
  // to read another customer's stored response.
  const rows = await customerQuery<KeyRow>(
    `SELECT response_json FROM idempotency_keys
      WHERE key = $1 AND operation = $2 AND user_id = $3
      LIMIT 1`,
    [opts.key, opts.operation, opts.userId],
  )
  return { claimed: false, response: rows[0]?.response_json ?? null }
}

/** Store the result so a later replay returns it verbatim instead of re-executing. */
export async function completeIdempotentOperation(opts: {
  key: string
  operation: string
  response: unknown
}): Promise<void> {
  await customerExecute(
    `UPDATE idempotency_keys SET response_json = $3 WHERE key = $1 AND operation = $2`,
    [opts.key, opts.operation, JSON.stringify(opts.response)],
  )
}

/**
 * Release a claim after a FAILED attempt.
 *
 * Without this a transient failure would poison the key forever: the caller could never
 * retry, because the key is held but has no stored response. Only ever called on a path
 * that did not produce a durable side effect.
 */
export async function releaseIdempotencyKey(opts: { key: string; operation: string }): Promise<void> {
  await customerExecute(
    `DELETE FROM idempotency_keys WHERE key = $1 AND operation = $2 AND response_json IS NULL`,
    [opts.key, opts.operation],
  )
}
