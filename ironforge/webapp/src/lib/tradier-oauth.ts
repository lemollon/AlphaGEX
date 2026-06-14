/**
 * Tradier direct-OAuth client (brokerage sub-project, second provider). SnapTrade does not
 * support Tradier, so customers link their own Tradier account via Tradier's OAuth 2.0 flow.
 *
 * Config-guarded like snaptrade.ts: unset creds → isTradierOAuthConfigured() === false and the
 * routes degrade to a clean 503. Endpoints/params follow Tradier's OAuth + Trading API; verify
 * against current Tradier docs at integration time. Access tokens are encrypted at rest by the
 * caller via @/lib/crypto/secret-box. NOTE: distinct from TRADIER_API_KEY (IronForge's own bot
 * market-data key) — this uses a Tradier *OAuth application* (client id/secret).
 */
import { createHmac } from 'crypto'

export class TradierOAuthNotConfiguredError extends Error {
  constructor() {
    super('TRADIER_OAUTH_CLIENT_ID / TRADIER_OAUTH_CLIENT_SECRET are not configured')
    this.name = 'TradierOAuthNotConfiguredError'
  }
}

export function isTradierOAuthConfigured(): boolean {
  return !!process.env.TRADIER_OAUTH_CLIENT_ID && !!process.env.TRADIER_OAUTH_CLIENT_SECRET
}

/** Prod by default; set TRADIER_OAUTH_BASE=https://sandbox.tradier.com for sandbox testing. */
export function tradierBase(): string {
  return process.env.TRADIER_OAUTH_BASE || 'https://api.tradier.com'
}

const SCOPES = 'read,trade'

// ---- CSRF state (HMAC-signed, carries the customer id + a short expiry) ----

function b64url(s: string): string {
  return Buffer.from(s).toString('base64url')
}
function hmac(payload: string): string {
  const secret = process.env.IRONFORGE_SESSION_SECRET || ''
  return createHmac('sha256', secret).update(payload).digest('base64url')
}

export function signState(uid: string, now = Date.now()): string {
  const payload = b64url(JSON.stringify({ uid, exp: now + 15 * 60 * 1000 }))
  return `${payload}.${hmac(payload)}`
}

/** Returns the embedded uid if the signature is valid and unexpired, else null. */
export function verifyState(state: string | null | undefined, now = Date.now()): string | null {
  if (!state) return null
  const dot = state.lastIndexOf('.')
  if (dot < 0) return null
  const payload = state.slice(0, dot)
  const sig = state.slice(dot + 1)
  if (hmac(payload) !== sig) return null
  try {
    const { uid, exp } = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'))
    if (typeof uid !== 'string' || typeof exp !== 'number' || now > exp) return null
    return uid
  } catch {
    return null
  }
}

export function buildAuthorizeUrl(state: string): string {
  const u = new URL('/v1/oauth/authorize', tradierBase())
  u.searchParams.set('client_id', process.env.TRADIER_OAUTH_CLIENT_ID as string)
  u.searchParams.set('scope', SCOPES)
  u.searchParams.set('state', state)
  return u.toString()
}

export interface TradierToken {
  accessToken: string
  refreshToken?: string
  expiresAt?: string // ISO
}

/** Exchange an authorization code for an access token (OAuth2, Basic-auth client creds). */
export async function exchangeCodeForToken(code: string): Promise<TradierToken> {
  if (!isTradierOAuthConfigured()) throw new TradierOAuthNotConfiguredError()
  const basic = Buffer.from(
    `${process.env.TRADIER_OAUTH_CLIENT_ID}:${process.env.TRADIER_OAUTH_CLIENT_SECRET}`,
  ).toString('base64')
  const res = await fetch(`${tradierBase()}/v1/oauth/accesstoken`, {
    method: 'POST',
    headers: {
      Authorization: `Basic ${basic}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
    },
    body: new URLSearchParams({ grant_type: 'authorization_code', code }).toString(),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`Tradier token exchange ${res.status}: ${detail.slice(0, 200)}`)
  }
  const j = (await res.json()) as { access_token: string; refresh_token?: string; expires_in?: number }
  return {
    accessToken: j.access_token,
    refreshToken: j.refresh_token,
    expiresAt: j.expires_in ? new Date(Date.now() + j.expires_in * 1000).toISOString() : undefined,
  }
}

async function tradierGet(token: string, path: string): Promise<unknown> {
  const res = await fetch(`${tradierBase()}${path}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(`Tradier GET ${path} ${res.status}: ${(await res.text().catch(() => '')).slice(0, 200)}`)
  return res.json()
}

export interface TradierAccount {
  account_id: string
  name?: string
}

/** List the user's Tradier accounts from their profile. */
export async function getProfileAccounts(token: string): Promise<TradierAccount[]> {
  const j = (await tradierGet(token, '/v1/user/profile')) as {
    profile?: { name?: string; account?: unknown }
  }
  const raw = j.profile?.account
  const arr = Array.isArray(raw) ? raw : raw ? [raw] : []
  return arr.map((a) => {
    const acct = a as { account_number?: string; classification?: string }
    return { account_id: String(acct.account_number ?? ''), name: acct.classification }
  })
}

export interface TradierOrderParams {
  symbol: string
  side: 'buy' | 'sell'
  quantity: number
  type?: 'market' | 'limit'
  duration?: 'day' | 'gtc'
  price?: number
}

function orderBody(p: TradierOrderParams, preview: boolean): string {
  const body: Record<string, string> = {
    class: 'equity',
    symbol: p.symbol,
    side: p.side,
    quantity: String(p.quantity),
    type: p.type ?? 'market',
    duration: p.duration ?? 'day',
  }
  if (p.price != null) body.price = String(p.price)
  if (preview) body.preview = 'true'
  return new URLSearchParams(body).toString()
}

async function tradierOrder(token: string, accountId: string, p: TradierOrderParams, preview: boolean): Promise<unknown> {
  const res = await fetch(`${tradierBase()}/v1/accounts/${encodeURIComponent(accountId)}/orders`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
    },
    body: orderBody(p, preview),
  })
  if (!res.ok) {
    throw new Error(`Tradier order ${res.status}: ${(await res.text().catch(() => '')).slice(0, 200)}`)
  }
  return res.json()
}

/** Dry-run an order to surface estimated cost/commission before the customer approves. */
export function previewOrder(token: string, accountId: string, p: TradierOrderParams): Promise<unknown> {
  return tradierOrder(token, accountId, p, true)
}

/** Place a real order. Returns the broker order id. */
export async function placeOrder(token: string, accountId: string, p: TradierOrderParams): Promise<{ orderId: string | null }> {
  const j = (await tradierOrder(token, accountId, p, false)) as { order?: { id?: number | string } }
  return { orderId: j.order?.id != null ? String(j.order.id) : null }
}
