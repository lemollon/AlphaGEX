/**
 * tastytrade direct-OAuth client (third brokerage provider, alongside SnapTrade and Tradier).
 * tastytrade is already connectable today through SnapTrade (see
 * onboarding/brokerage/brokerages/route.ts) — this is the DIRECT lane, pursued for better data
 * fidelity (real options approval level + buying power, vs. SnapTrade's capability-only gate for
 * tastytrade) and native multi-leg order support. See KnowledgeVault
 * 01-projects/ironforge/sessions/2026-08-07-tastytrade-partnership-path.md for the grounded facts
 * this was built from (read from developer.tastytrade.com/oauth/, 2026-08-07).
 *
 * Config-guarded like tradier-oauth.ts: unset creds -> isTastytradeOAuthConfigured() === false and
 * the routes degrade to a clean 503. Multi-user access requires tastytrade's own "trusted third
 * party" review (requested 2026-08-12, api.support@tastytrade.com, still pending as of 2026-10-13)
 * — until approved, only the requesting account itself can authorize via a personal OAuth grant.
 * Endpoints/params follow tastytrade's documented OAuth2 + REST API; VERIFY AGAINST CURRENT
 * tastytrade DOCS AT INTEGRATION TIME, same caveat tradier-oauth.ts carries for Tradier.
 *
 * Access tokens are encrypted at rest by the caller via @/lib/crypto/secret-box.
 */
export class TastytradeOAuthNotConfiguredError extends Error {
  constructor() {
    super('TASTYTRADE_OAUTH_CLIENT_ID / TASTYTRADE_OAUTH_CLIENT_SECRET are not configured')
    this.name = 'TastytradeOAuthNotConfiguredError'
  }
}

export function isTastytradeOAuthConfigured(): boolean {
  return !!process.env.TASTYTRADE_OAUTH_CLIENT_ID && !!process.env.TASTYTRADE_OAUTH_CLIENT_SECRET
}

/**
 * Prod by default; set TASTYTRADE_OAUTH_BASE=https://api.cert.tastyworks.com for sandbox testing
 * (resets every 24h — positions/balances/trades wiped, per the 8/7 vault notes).
 */
export function tastytradeApiBase(): string {
  return process.env.TASTYTRADE_OAUTH_BASE || 'https://api.tastyworks.com'
}

/** The user-authorize page is a SEPARATE host from the API — tastytrade's own split, not ours. */
export function tastytradeAuthorizeBase(): string {
  return process.env.TASTYTRADE_OAUTH_AUTHORIZE_BASE || 'https://my.tastytrade.com'
}

/** 🚨 Per the 8/7 vault notes: tastytrade rejects OAuth requests with no User-Agent header. */
const USER_AGENT = 'IronForge/1.0 (+https://ironforge.trade)'

const SCOPES = 'read trade openid'

/**
 * Is PKCE enabled for tastytrade?
 *
 * DEFAULT OFF, same reasoning as tradierPkceEnabled(): sending a code_challenge the provider
 * doesn't expect, then a code_verifier on exchange it never asked for, can break a working
 * exchange outright. Flip TASTYTRADE_OAUTH_PKCE=true once confirmed against tastytrade's current
 * OAuth docs or their own support channel. PKCE generation/storage itself lives in
 * @/lib/enrollment/oauth-state.ts, shared across all providers.
 */
export function tastytradePkceEnabled(): boolean {
  return process.env.TASTYTRADE_OAUTH_PKCE === 'true'
}

export function buildAuthorizeUrl(state: string, redirectUri: string, codeChallenge?: string): string {
  const u = new URL('/auth.html', tastytradeAuthorizeBase())
  u.searchParams.set('client_id', process.env.TASTYTRADE_OAUTH_CLIENT_ID as string)
  u.searchParams.set('redirect_uri', redirectUri)
  u.searchParams.set('response_type', 'code')
  u.searchParams.set('scope', SCOPES)
  u.searchParams.set('state', state)
  if (codeChallenge) {
    u.searchParams.set('code_challenge', codeChallenge)
    u.searchParams.set('code_challenge_method', 'S256')
  }
  return u.toString()
}

export interface TastytradeToken {
  accessToken: string
  refreshToken?: string
  expiresAt?: string // ISO
}

/**
 * Exchange an authorization code for an access token.
 *
 * Unlike Tradier (HTTP Basic client auth), tastytrade's documented OAuth2 token endpoint takes
 * client_id/client_secret in the JSON body alongside the code. Access tokens are short-lived
 * (15 min per the 8/7 notes); the refresh token does not expire.
 */
export async function exchangeCodeForToken(
  code: string,
  redirectUri: string,
  codeVerifier?: string | null,
): Promise<TastytradeToken> {
  if (!isTastytradeOAuthConfigured()) throw new TastytradeOAuthNotConfiguredError()
  const res = await fetch(`${tastytradeApiBase()}/oauth/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'User-Agent': USER_AGENT,
    },
    body: JSON.stringify({
      grant_type: 'authorization_code',
      code,
      client_id: process.env.TASTYTRADE_OAUTH_CLIENT_ID,
      client_secret: process.env.TASTYTRADE_OAUTH_CLIENT_SECRET,
      redirect_uri: redirectUri,
      ...(codeVerifier ? { code_verifier: codeVerifier } : {}),
    }),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`tastytrade token exchange ${res.status}: ${detail.slice(0, 200)}`)
  }
  const j = (await res.json()) as { access_token: string; refresh_token?: string; expires_in?: number }
  return {
    accessToken: j.access_token,
    refreshToken: j.refresh_token,
    expiresAt: j.expires_in ? new Date(Date.now() + j.expires_in * 1000).toISOString() : undefined,
  }
}

/** Refresh token never expires per the 8/7 notes, but the access token does (15 min). */
export async function refreshAccessToken(refreshToken: string): Promise<TastytradeToken> {
  if (!isTastytradeOAuthConfigured()) throw new TastytradeOAuthNotConfiguredError()
  const res = await fetch(`${tastytradeApiBase()}/oauth/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'User-Agent': USER_AGENT,
    },
    body: JSON.stringify({
      grant_type: 'refresh_token',
      refresh_token: refreshToken,
      client_id: process.env.TASTYTRADE_OAUTH_CLIENT_ID,
      client_secret: process.env.TASTYTRADE_OAUTH_CLIENT_SECRET,
    }),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`tastytrade token refresh ${res.status}: ${detail.slice(0, 200)}`)
  }
  const j = (await res.json()) as { access_token: string; refresh_token?: string; expires_in?: number }
  return {
    accessToken: j.access_token,
    refreshToken: j.refresh_token ?? refreshToken,
    expiresAt: j.expires_in ? new Date(Date.now() + j.expires_in * 1000).toISOString() : undefined,
  }
}

async function tastytradeGet(token: string, path: string): Promise<unknown> {
  const res = await fetch(`${tastytradeApiBase()}${path}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/json', 'User-Agent': USER_AGENT },
  })
  if (!res.ok) {
    throw new Error(`tastytrade GET ${path} ${res.status}: ${(await res.text().catch(() => '')).slice(0, 200)}`)
  }
  return res.json()
}

export interface TastytradeAccount {
  account_id: string
  name?: string
  /** tastytrade account-type-name: Individual | IRA | Roth IRA | Margin | Cash | ... */
  classification?: string
  status?: string
  /**
   * Approval level, if tastytrade's trading-status endpoint exposes one for this account.
   * UNVERIFIED FIELD NAME — this is the whole business case for the direct lane (see header
   * comment), so confirm the real shape against a live sandbox account before trusting it in
   * production. Absent means UNKNOWN, never "fine" (eligibility.ts fails closed on null).
   */
  option_level?: number
}

/** List the user's tastytrade accounts. */
export async function getProfileAccounts(token: string): Promise<TastytradeAccount[]> {
  const j = (await tastytradeGet(token, '/customers/me/accounts')) as {
    data?: { items?: Array<{ account?: Record<string, unknown> }> }
  }
  const items = j.data?.items ?? []
  return items.map(({ account: a = {} }) => ({
    account_id: String(a['account-number'] ?? ''),
    name: typeof a['nickname'] === 'string' ? (a['nickname'] as string) : undefined,
    classification: typeof a['account-type-name'] === 'string' ? (a['account-type-name'] as string) : undefined,
    status: a['is-closed'] === true ? 'closed' : 'active',
  }))
}

/**
 * Options approval level for one account, from tastytrade's trading-status endpoint.
 *
 * Returns null on any failure or if the field is absent — the safe reading, matching
 * getAccountOptionBuyingPower's contract in tradier-oauth.ts. See the UNVERIFIED note on
 * TastytradeAccount.option_level above.
 */
export async function getAccountOptionsLevel(token: string, accountId: string): Promise<number | null> {
  try {
    const j = (await tastytradeGet(token, `/accounts/${encodeURIComponent(accountId)}/trading-status`)) as {
      data?: { ['options-level']?: unknown }
    }
    const level = j.data?.['options-level']
    const n = typeof level === 'number' ? level : Number(level)
    return Number.isFinite(n) ? n : null
  } catch {
    return null
  }
}

/**
 * Option buying power for one account ("derivative buying power" in tastytrade's balances
 * response). FAILS CLOSED (null) on any failure — eligibility.ts refuses an unknown value rather
 * than assuming it's fine.
 */
export async function getAccountOptionBuyingPower(token: string, accountId: string): Promise<number | null> {
  try {
    const j = (await tastytradeGet(token, `/accounts/${encodeURIComponent(accountId)}/balances`)) as {
      data?: { ['derivative-buying-power']?: unknown; ['cash-balance']?: unknown }
    }
    const bp = j.data?.['derivative-buying-power'] ?? j.data?.['cash-balance']
    const n = typeof bp === 'number' ? bp : Number(bp)
    return Number.isFinite(n) ? n : null
  } catch {
    return null
  }
}
