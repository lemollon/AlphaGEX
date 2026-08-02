/**
 * API client with silent access-token refresh.
 *
 * Tokens live in expo-secure-store (iOS Keychain / Android Keystore), never
 * AsyncStorage — APP-046 requires tokens encrypted at rest, and AsyncStorage is plain
 * text readable by anything with filesystem access on a rooted/jailbroken device.
 *
 * The refresh is SINGLE-FLIGHT. Screens poll concurrently (Forge, Ledger, Community all
 * fetch on focus), so an expired access token would otherwise fire N simultaneous
 * refreshes. That is not merely wasteful: refresh tokens are single-use with reuse
 * detection server-side, so the 2nd..Nth would present an already-rotated token, trip
 * the theft alarm, and log the customer out of every device. One in-flight promise,
 * shared by all callers, is a correctness requirement rather than an optimisation.
 */
import * as SecureStore from 'expo-secure-store'
import Constants from 'expo-constants'

const API_BASE: string =
  (Constants.expoConfig?.extra as { apiBase?: string } | undefined)?.apiBase ??
  'https://ironforge.trade'

const ACCESS_KEY = 'ironforge.accessToken'
const REFRESH_KEY = 'ironforge.refreshToken'

export class AuthExpiredError extends Error {
  constructor() {
    super('Session expired')
    this.name = 'AuthExpiredError'
  }
}

export interface TokenPair {
  accessToken: string
  refreshToken: string
}

export async function saveTokens(pair: TokenPair): Promise<void> {
  await SecureStore.setItemAsync(ACCESS_KEY, pair.accessToken)
  await SecureStore.setItemAsync(REFRESH_KEY, pair.refreshToken, {
    // Requires the device to have been unlocked at least once since boot. Background
    // refresh still works; the token just isn't readable from a cold locked device.
    keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK,
  })
}

export async function clearTokens(): Promise<void> {
  await SecureStore.deleteItemAsync(ACCESS_KEY).catch(() => {})
  await SecureStore.deleteItemAsync(REFRESH_KEY).catch(() => {})
}

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_KEY)
}

export async function hasSession(): Promise<boolean> {
  return (await SecureStore.getItemAsync(REFRESH_KEY)) !== null
}

/** Shared in-flight refresh — see the single-flight note above. */
let refreshInFlight: Promise<string | null> | null = null

async function doRefresh(): Promise<string | null> {
  const refreshToken = await SecureStore.getItemAsync(REFRESH_KEY)
  if (!refreshToken) return null

  const res = await fetch(`${API_BASE}/api/auth/mobile/refresh`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ refreshToken }),
  }).catch(() => null)

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

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

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
    ...((opts.headers as Record<string, string>) ?? {}),
  }
  if (token) headers.authorization = `Bearer ${token}`
  if (opts.body !== undefined) headers['content-type'] = 'application/json'

  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  })

  if (res.status === 401 && !opts._retried && !opts.stepUpToken) {
    const fresh = await refreshAccessToken()
    if (!fresh) throw new AuthExpiredError()
    return api<T>(path, { ...opts, _retried: true })
  }

  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    const msg =
      (detail as { error?: string } | null)?.error ?? `Request failed (${res.status})`
    throw new Error(msg)
  }

  return (await res.json()) as T
}

/** Unauthenticated POST, for sign-in and password reset. */
export async function apiPublic<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(body),
  })
  const json = (await res.json().catch(() => null)) as Record<string, unknown> | null
  if (!res.ok) {
    throw new Error((json?.error as string) ?? `Request failed (${res.status})`)
  }
  return json as T
}

export { API_BASE }
