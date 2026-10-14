/**
 * API client with silent access-token refresh.
 *
 * Tokens live in the Keychain / Keystore via api/storage.ts, never AsyncStorage —
 * APP-046 requires tokens encrypted at rest, and AsyncStorage is plain text readable by
 * anything with filesystem access on a rooted/jailbroken device. (storage.ts falls back
 * to localStorage on WEB only, which is a developer-preview target that is never
 * shipped — see the note there.)
 *
 * The refresh is SINGLE-FLIGHT. Screens poll concurrently (Forge, Ledger, Community all
 * fetch on focus), so an expired access token would otherwise fire N simultaneous
 * refreshes. That is not merely wasteful: refresh tokens are single-use with reuse
 * detection server-side, so the 2nd..Nth would present an already-rotated token, trip
 * the theft alarm, and log the customer out of every device. One in-flight promise,
 * shared by all callers, is a correctness requirement rather than an optimisation.
 */
import Constants from 'expo-constants'
import { mutate as swrMutate } from 'swr'
import { setItem, getItem, deleteItem, AFTER_FIRST_UNLOCK } from '@/api/storage'
import { ApiError } from '@/api/errors'
import { reportNetworkSuccess, reportNetworkFailure } from '@/live/connectivity'
import { reportClientError } from '@/monitoring/crashReport'

export { ApiError }

const API_BASE: string =
  (Constants.expoConfig?.extra as { apiBase?: string } | undefined)?.apiBase ??
  'https://ironforge.trade'

/**
 * 2026-10-14: every raw `fetch()` to our own API previously carried NO timeout of
 * any kind — each call site relied entirely on the native layer's own (iOS
 * URLSession ~60s, can be effectively unbounded on some connection-hang shapes)
 * eventually rejecting. A caller awaiting an unbounded fetch has no way to ever
 * recover: a screen that sets a `sending`/`submitting` flag before the call and
 * only clears it in a `finally` after it settles — exactly app/sparky.tsx's
 * composer, and the waitlist form's submit button — stays locked (disabled input,
 * disabled button) for as long as the hang lasts, with NOTHING to show for it: a
 * request that never completes a connection never reaches Render's logs either,
 * so server-side nothing can prove or disprove it happened. A tester describing
 * "it just blinks and does nothing, nothing was ever sent" is the exact shape
 * this produces — and it was not unique to one screen, because nothing in this
 * file (or waitlist/api.ts, which reaches the same host directly) had ever
 * applied a bound. 15s is generous for every route this app calls (Sparky's own
 * LLM round-trip measures ~2s in production logs) while being short enough that
 * a real hang resolves to a visible, reportable error instead of an indefinite
 * lock.
 *
 * ONE helper, used by every first-party fetch in this app (api(), apiPublic(),
 * and waitlist/api.ts's submitWaitlist — doRefresh() above keeps its own
 * REFRESH_TIMEOUT_MS AbortController since its needs differ slightly), so this
 * can never again silently regress to "forgot the timeout on this one call site."
 */
export const DEFAULT_TIMEOUT_MS = 15_000

export async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } finally {
    clearTimeout(timeoutId)
  }
}

const ACCESS_KEY = 'ironforge.accessToken'
const REFRESH_KEY = 'ironforge.refreshToken'

export class AuthExpiredError extends Error {
  constructor() {
    super('Session expired')
    this.name = 'AuthExpiredError'
  }
}

/**
 * `fetch()` only rejects for a network-level failure — no connectivity, DNS,
 * or (the case this exists for) `react-native-ssl-public-key-pinning`
 * refusing the TLS handshake because the server's certificate chain no
 * longer matches the pinned hashes in security/ssl-pinning.ts. Left
 * unwrapped, that rejection is a raw native exception string ("Exception in
 * HostFunction: ...", "java.io.IOException: Certificate pinning failure")
 * surfacing wherever a screen's `catch (e) { ... (e as Error).message }`
 * happens to render it — every screen in this app follows that exact
 * pattern (see billing.tsx, account.tsx). Converting it here, once, means
 * every caller already shows something a customer can act on instead of a
 * crash-ish string, with no per-screen change needed.
 */
function throwSecureConnectionError(cause?: unknown): never {
  // Report the REAL native error before converting it to the friendly
  // message below — "Secure connection failed" is what the customer sees,
  // but what actually tripped (SSL pin mismatch, DNS, timeout, offline) only
  // exists in `cause`, and would otherwise vanish the instant this throws.
  const isTimeout = cause instanceof Error && cause.name === 'AbortError'
  reportClientError({
    kind: 'network_error',
    message: isTimeout
      ? `timeout after ${DEFAULT_TIMEOUT_MS}ms`
      : cause instanceof Error ? cause.message : String(cause ?? 'unknown fetch failure'),
    stack: cause instanceof Error ? cause.stack : undefined,
  })
  throw new Error(
    isTimeout
      ? 'IronForge took too long to respond. Check your connection and try again.'
      : 'Secure connection to IronForge failed. Check your connection and try again.',
  )
}

export interface TokenPair {
  accessToken: string
  refreshToken: string
}

/**
 * Session-change subscribers.
 *
 * The root auth gate reads hasSession() ONCE at mount, so without this it never learns
 * that the session changed while the app was running. That is not a cosmetic lag, it
 * is a lockout in both directions:
 *
 *   sign IN  — tokens saved, the screen calls router.replace('/'), the gate still
 *              believes signedIn === false and immediately replaces back to /sign-in.
 *              The customer sees "Signing in…", then a blank login form, forever.
 *   sign OUT — tokens cleared, the screen calls router.replace('/sign-in'), the gate
 *              still believes signedIn === true and bounces them back INTO the app.
 *
 * Notifying from the two functions that own the tokens, rather than from each screen,
 * is deliberate: a future caller cannot forget to announce the change, and the silent
 * clearTokens() inside doRefresh() (reuse detection / idle expiry) now routes to
 * sign-in on its own instead of leaving a signed-out app rendering empty states.
 */
type SessionListener = (signedIn: boolean) => void
const sessionListeners = new Set<SessionListener>()

/** Subscribe to sign-in / sign-out. Returns an unsubscribe suitable for useEffect. */
export function onSessionChange(fn: SessionListener): () => void {
  sessionListeners.add(fn)
  return () => {
    sessionListeners.delete(fn)
  }
}

function notifySession(signedIn: boolean): void {
  for (const fn of [...sessionListeners]) fn(signedIn)
}

export async function saveTokens(pair: TokenPair): Promise<void> {
  await setItem(ACCESS_KEY, pair.accessToken)
  await setItem(REFRESH_KEY, pair.refreshToken, {
    // Requires the device to have been unlocked at least once since boot. Background
    // refresh still works; the token just isn't readable from a cold locked device.
    keychainAccessible: AFTER_FIRST_UNLOCK,
  })
  notifySession(true)
}

export async function clearTokens(): Promise<void> {
  await deleteItem(ACCESS_KEY).catch(() => {})
  await deleteItem(REFRESH_KEY).catch(() => {})
  // No SWRConfig provider is set up anywhere in this app, so every useSWR() call shares
  // one process-lifetime global cache keyed only by path (e.g. '/api/live/agents') —
  // never by user. Without this, signing out and a DIFFERENT account signing in on the
  // same device would render the first account's balances/positions until each screen's
  // own revalidation happened to complete. Clearing every key's DATA (not re-fetching —
  // there's nothing to authenticate the re-fetch with yet, and the sign-in screen is
  // about to unmount every screen that held these keys anyway) closes that window.
  await swrMutate(() => true, undefined, { revalidate: false }).catch(() => {})
  notifySession(false)
}

export async function getAccessToken(): Promise<string | null> {
  return getItem(ACCESS_KEY)
}

export async function hasSession(): Promise<boolean> {
  return (await getItem(REFRESH_KEY)) !== null
}

/** Shared in-flight refresh — see the single-flight note above. */
let refreshInFlight: Promise<string | null> | null = null

/**
 * Bounded so a hung connection can't block every waiting caller (this is the shared
 * single-flight promise — Forge/Ledger/Community all await it) for an unbounded time.
 *
 * This does NOT close the deeper race where the server successfully rotates the
 * refresh token but the response is lost in transit: the client still holds the
 * now-already-consumed old refresh token, and the NEXT refresh attempt reads as reuse
 * server-side, revoking the whole device family. Fixing that needs a grace period on
 * the server's reuse-detection window (mobile-session.ts) — a deliberate security
 * change, not a client-only fix, and out of scope here.
 */
const REFRESH_TIMEOUT_MS = 15_000

async function doRefresh(): Promise<string | null> {
  const refreshToken = await getItem(REFRESH_KEY)
  if (!refreshToken) return null

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), REFRESH_TIMEOUT_MS)
  const res = await fetch(`${API_BASE}/api/auth/mobile/refresh`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ refreshToken }),
    signal: controller.signal,
  })
    .catch(() => null)
    .finally(() => clearTimeout(timeout))

  if (!res || !res.ok) {
    // 401 here means invalid / expired / idle / REUSE-DETECTED. In every one of those
    // cases the server has already invalidated this device, so holding the tokens
    // would only produce more failing calls.
    if (res && res.status === 401) await clearTokens()
    return null
  }

  const json = (await res.json().catch(() => null)) as
    | { accessToken?: string; refreshToken?: string }
    | null
  if (!json?.accessToken || !json.refreshToken) {
    await clearTokens()
    return null
  }

  await saveTokens({ accessToken: json.accessToken, refreshToken: json.refreshToken })
  return json.accessToken
}

/**
 * Exported for the ONE caller that cannot go through api(): the Sparky chat stream,
 * which needs a raw streaming fetch and therefore has to drive its own 401 retry.
 * Still single-flight — that is the whole point of sharing this promise.
 */
export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

/**
 * Capability header announcing "this build understands step-up and will present a
 * step-up token on a gated route" (webapp's lib/auth/mobile-step-up.ts). Sent on
 * EVERY authenticated call, not just the gated ones — the server decides per-route
 * whether step-up applies at all; this header only tells it which protocol this
 * client speaks. MUST match STEP_UP_CAPABLE_HEADER in that file exactly.
 */
const STEP_UP_CAPABLE_HEADER = 'x-ironforge-stepup'

export interface ApiOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  /** Step-up token for a sensitive action (MOBILE_SESSION_POLICY.stepUpActions). */
  stepUpToken?: string
  /** Internal: prevents infinite retry recursion. */
  _retried?: boolean
}

/**
 * Authenticated fetch. On 401 it refreshes ONCE and replays the request; if the refresh
 * fails it throws AuthExpiredError so the UI can route to sign-in rather than render a
 * confusing empty state.
 */
export async function api<T = unknown>(path: string, opts: ApiOptions = {}): Promise<T> {
  const token = opts.stepUpToken ?? (await getAccessToken())

  const headers: Record<string, string> = {
    accept: 'application/json',
    [STEP_UP_CAPABLE_HEADER]: '1',
    ...((opts.headers as Record<string, string>) ?? {}),
  }
  if (token) headers.authorization = `Bearer ${token}`
  if (opts.body !== undefined) headers['content-type'] = 'application/json'

  // Offline handling (#294): a network-layer failure (fetch itself rejecting — no
  // connection, DNS, timeout) reports here directly, distinct from an ordinary HTTP
  // error status below, which proves the request actually reached the server. This
  // is also the case react-native-ssl-public-key-pinning triggers on a pin mismatch
  // (security/ssl-pinning.ts), so it gets the same clear "secure connection failed"
  // message as every other network-layer failure here — never a raw native
  // exception string. fetchWithTimeout's bound is ALSO funneled through this same
  // catch (AbortController.abort() makes fetch reject, same as any other network
  // failure) so a stalled request fails the exact same visible way as being
  // offline, rather than needing a third error path a caller has to separately
  // handle — see fetchWithTimeout's own docstring above for why this exists at all.
  // No caller passes its own `signal` today — if one ever does, the timeout would
  // otherwise silently override it. Fail loudly instead of guessing.
  if (opts.signal) throw new Error('api(): opts.signal is not supported alongside the built-in timeout')

  let res: Response
  try {
    res = await fetchWithTimeout(`${API_BASE}${path}`, {
      ...opts,
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    })
  } catch (fetchErr) {
    reportNetworkFailure()
    throwSecureConnectionError(fetchErr)
  }
  reportNetworkSuccess()

  if (res.status === 401 && !opts._retried && !opts.stepUpToken) {
    const fresh = await refreshAccessToken()
    if (!fresh) throw new AuthExpiredError()
    return api<T>(path, { ...opts, _retried: true })
  }

  if (!res.ok) {
    const detail = (await res.json().catch(() => null)) as Record<string, unknown> | null
    const msg = (detail?.error as string | undefined) ?? `Request failed (${res.status})`
    throw new ApiError(msg, res.status, detail)
  }

  return (await res.json()) as T
}

/** Unauthenticated POST, for sign-in and password reset. */
export async function apiPublic<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await fetchWithTimeout(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(body),
  }).catch(throwSecureConnectionError)
  const json = (await res.json().catch(() => null)) as Record<string, unknown> | null
  if (!res.ok) {
    throw new Error((json?.error as string) ?? `Request failed (${res.status})`)
  }
  return json as T
}

export { API_BASE }
