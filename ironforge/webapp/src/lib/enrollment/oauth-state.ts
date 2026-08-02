import { createHash, randomBytes } from 'crypto'
import { customerQuery, customerExecute } from '@/lib/customers-db'

/**
 * OAuth state + PKCE, server-side and single-use (Enrollment spec §8 threat table:
 * "OAuth CSRF/replay → State + PKCE + one-time callback + short expiry").
 *
 * WHY THIS REPLACES THE SIGNED-STATE APPROACH. The previous state was a stateless
 * HMAC token. That gives CSRF protection and expiry, but it CANNOT give the other two
 * controls the spec names:
 *
 *  - ONE-TIME USE is impossible without a server record. A stateless token is valid
 *    every time it is presented, so a replayed callback replays the whole exchange.
 *  - PKCE is defeated if the verifier travels with the request. Embedding it in the
 *    state would hand an attacker who intercepts the redirect both halves at once,
 *    which is exactly what PKCE exists to prevent. The verifier must stay server-side
 *    and never leave this process.
 *
 * So the state is now an opaque random id; everything sensitive stays in the database.
 *
 * Expiry is 10 MINUTES, per §3 BROKER-01 ("state expires after 10 minutes"). The old
 * signed state used 15.
 */

/** §3 BROKER-01. */
const STATE_TTL_MS = 10 * 60 * 1000

/** Which surface initiated the round-trip. An allowlisted literal, never a URL. */
export type OAuthReturnTo = 'enroll' | 'onboarding'

export function asReturnTo(v: unknown): OAuthReturnTo {
  return v === 'enroll' ? 'enroll' : 'onboarding'
}

/**
 * Which CLIENT started the round-trip. Decides whether the callback redirects to a web
 * page or to the /app/brokerage/return deep-link bridge.
 *
 * Stored SERVER-SIDE with the rest of the state, and derived from how the caller
 * authenticated — never accepted from a request body. A caller that could name its own
 * return surface could aim our post-OAuth redirect wherever it liked; the state record
 * IS the authorization.
 */
export type OAuthClient = 'web' | 'mobile'

export function asClient(v: unknown): OAuthClient {
  return v === 'mobile' ? 'mobile' : 'web'
}

export interface OAuthStateRecord {
  state: string
  userId: string
  brokerCode: string
  codeVerifier: string | null
  returnTo: OAuthReturnTo
  client: OAuthClient
}

function b64url(buf: Buffer): string {
  return buf.toString('base64url')
}

/** RFC 7636: 43–128 chars of unreserved characters. 32 random bytes → 43 base64url chars. */
export function generateCodeVerifier(): string {
  return b64url(randomBytes(32))
}

/** RFC 7636 S256: BASE64URL(SHA256(ASCII(verifier))). */
export function codeChallengeS256(verifier: string): string {
  return b64url(createHash('sha256').update(verifier, 'ascii').digest())
}

/**
 * Create a single-use state. Returns the opaque state to put on the authorize URL and,
 * when PKCE is requested, the challenge to send with it. The VERIFIER is never returned
 * to the caller-facing layer — it is read back only at callback time.
 */
export async function createOAuthState(opts: {
  userId: string
  brokerCode: string
  /** Only send a challenge to providers that support PKCE — see tradier-oauth.ts. */
  pkce: boolean
  /** Where the callback should land the customer. Allowlisted literal, never a URL. */
  returnTo?: OAuthReturnTo
  /** Web page vs mobile deep-link bridge. Derive from the caller's auth, not its body. */
  client?: OAuthClient
}): Promise<{ state: string; codeChallenge?: string }> {
  const state = b64url(randomBytes(32))
  const verifier = opts.pkce ? generateCodeVerifier() : null

  await customerExecute(
    `INSERT INTO oauth_states (state, user_id, broker_code, code_verifier, expires_at, return_to, client)
     VALUES ($1, $2, $3, $4, now() + interval '10 minutes', $5, $6)`,
    [state, opts.userId, opts.brokerCode, verifier, asReturnTo(opts.returnTo), asClient(opts.client)],
  )

  return verifier ? { state, codeChallenge: codeChallengeS256(verifier) } : { state }
}

/**
 * Consume a state EXACTLY ONCE.
 *
 * The single-use guarantee is the UPDATE's own WHERE clause, not a read-then-write:
 * `consumed_at IS NULL` is evaluated inside the same statement that sets it, so two
 * concurrent callbacks with the same state cannot both match. A read-then-write would
 * leave a window where both see NULL and both proceed — which is the replay this is
 * supposed to stop.
 *
 * Returns null for missing, expired OR already-consumed, deliberately without saying
 * which: "Replayed or mismatched state returns a safe failure" (§4).
 */
export async function consumeOAuthState(state: string | null | undefined): Promise<OAuthStateRecord | null> {
  if (!state) return null
  const rows = await customerQuery<{
    state: string; user_id: string; broker_code: string; code_verifier: string | null
    return_to: string | null; client: string | null
  }>(
    `UPDATE oauth_states
        SET consumed_at = now()
      WHERE state = $1
        AND consumed_at IS NULL
        AND expires_at > now()
      RETURNING state, user_id, broker_code, code_verifier, return_to, client`,
    [state],
  )
  const r = rows[0]
  if (!r) return null
  return {
    state: r.state,
    userId: r.user_id,
    brokerCode: r.broker_code,
    codeVerifier: r.code_verifier,
    returnTo: asReturnTo(r.return_to),
    client: asClient(r.client),
  }
}

/**
 * Housekeeping. Consumed/expired rows have no value once past the TTL, and an OAuth
 * state table is append-heavy — every abandoned connect attempt leaves one.
 */
export async function purgeExpiredOAuthStates(): Promise<void> {
  await customerExecute(`DELETE FROM oauth_states WHERE expires_at < now() - interval '1 day'`)
}

export const OAUTH_STATE_TTL_MS = STATE_TTL_MS
