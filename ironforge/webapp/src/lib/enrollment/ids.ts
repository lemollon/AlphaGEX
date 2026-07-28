/**
 * Resource id validation for the enrollment API.
 *
 * Every enrollment id is a Postgres UUID. Passing a non-UUID string into a `WHERE id = $1`
 * against a UUID column does not return zero rows — Postgres raises
 * `invalid input syntax for type uuid`, which surfaced as a 500 with
 * `retryable: true`. Two things wrong with that:
 *
 *   - A malformed id is a CLIENT error. It gets the same answer as an id that simply
 *     is not the caller's: "not available". Distinguishing them would also leak whether
 *     a given id exists.
 *   - `retryable: true` invites a client to retry forever something that can never
 *     succeed, and buries a real 500 in the noise (§11).
 *
 * Guarded at the lookup chokepoints rather than in each route, so a future route cannot
 * forget it.
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function isUuid(value: unknown): value is string {
  return typeof value === 'string' && UUID_RE.test(value)
}
