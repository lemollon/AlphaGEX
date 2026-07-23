/**
 * Minimal Stripe client over the REST API (no SDK dependency, to keep the build lean and match the
 * gated-degradation pattern used for SnapTrade). If STRIPE_SECRET_KEY is unset, isStripeConfigured()
 * is false and callers return a clean 503 — nothing live happens until the key is provisioned on
 * Render. The secret key is never logged or returned to clients.
 *
 * Webhook signatures are verified with STRIPE_WEBHOOK_SECRET using the documented
 * `t=timestamp,v1=hmac` scheme over `${t}.${rawBody}` (constant-time compare).
 */
import crypto from 'crypto'

const API_BASE = 'https://api.stripe.com/v1'
const STRIPE_VERSION = '2024-06-20'

export class StripeNotConfiguredError extends Error {
  constructor() {
    super('STRIPE_SECRET_KEY is not configured')
    this.name = 'StripeNotConfiguredError'
  }
}

/** A Stripe API error, carrying the structured fields so callers can branch on `code`/`param`. */
export class StripeApiError extends Error {
  code?: string
  type?: string
  param?: string
  statusCode: number
  constructor(status: number, err?: { message?: string; code?: string; type?: string; param?: string }) {
    super(err?.message || `Stripe ${status}`)
    this.name = 'StripeApiError'
    this.statusCode = status
    this.code = err?.code
    this.type = err?.type
    this.param = err?.param
  }
}

/**
 * True when the error is Stripe complaining that a customer id doesn't exist under the current key
 * — e.g. a stored id from the wrong mode (test vs live), or a customer deleted in the dashboard.
 * We self-heal these by recreating the customer.
 */
export function isMissingCustomerError(e: unknown): boolean {
  if (!(e instanceof StripeApiError)) return false
  return e.code === 'resource_missing' && (e.param === 'customer' || /No such customer/i.test(e.message))
}

/** The secret key, trimmed of stray whitespace/newlines that break the Authorization header. */
function secretKey(): string | undefined {
  const k = process.env.STRIPE_SECRET_KEY?.trim()
  return k || undefined
}

export function isStripeConfigured(): boolean {
  return !!secretKey()
}

// Flattens a nested object into Stripe's bracketed form-encoding, e.g.
// { line_items: [{ price: 'x', quantity: 1 }] } -> line_items[0][price]=x&line_items[0][quantity]=1
function encodeForm(obj: Record<string, unknown>, prefix = ''): string[] {
  const parts: string[] = []
  for (const [key, value] of Object.entries(obj)) {
    if (value === undefined || value === null) continue
    const field = prefix ? `${prefix}[${key}]` : key
    if (Array.isArray(value)) {
      value.forEach((item, i) => {
        if (item !== null && typeof item === 'object') {
          parts.push(...encodeForm(item as Record<string, unknown>, `${field}[${i}]`))
        } else {
          parts.push(`${encodeURIComponent(`${field}[${i}]`)}=${encodeURIComponent(String(item))}`)
        }
      })
    } else if (typeof value === 'object') {
      parts.push(...encodeForm(value as Record<string, unknown>, field))
    } else {
      parts.push(`${encodeURIComponent(field)}=${encodeURIComponent(String(value))}`)
    }
  }
  return parts
}

async function stripeRequest<T = any>(
  method: 'GET' | 'POST',
  path: string,
  params?: Record<string, unknown>,
): Promise<T> {
  const key = secretKey()
  if (!key) throw new StripeNotConfiguredError()

  const headers: Record<string, string> = {
    Authorization: `Bearer ${key}`,
    'Stripe-Version': STRIPE_VERSION,
  }
  let url = `${API_BASE}${path}`
  let body: string | undefined
  const encoded = params ? encodeForm(params).join('&') : ''
  if (method === 'GET') {
    if (encoded) url += `?${encoded}`
  } else {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    body = encoded
  }

  const res = await fetch(url, { method, headers, body })
  const json = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new StripeApiError(res.status, (json as { error?: any })?.error)
  }
  return json as T
}

/** Creates a fresh Stripe customer (used by callers, and by self-heal when a stored id is stale). */
export async function createCustomer(opts: { email?: string | null; userId: string }): Promise<string> {
  const created = await stripeRequest<{ id: string }>('POST', '/customers', {
    ...(opts.email ? { email: opts.email } : {}),
    metadata: { ironforge_user_id: opts.userId },
  })
  return created.id
}

interface StripeList<T> {
  data: T[]
}

/** Resolves a Stripe Price id from its lookup key. Returns null when no active price matches. */
export async function findPriceIdByLookupKey(lookupKey: string): Promise<string | null> {
  const res = await stripeRequest<StripeList<{ id: string }>>('GET', '/prices', {
    lookup_keys: [lookupKey],
    active: true,
    limit: 1,
  })
  return res.data[0]?.id ?? null
}

/** Returns an existing Stripe customer id or creates one for this user. */
export async function getOrCreateCustomer(opts: {
  existingId?: string | null
  email?: string | null
  userId: string
}): Promise<string> {
  if (opts.existingId) return opts.existingId
  return createCustomer({ email: opts.email, userId: opts.userId })
}

/** Creates a subscription-mode Checkout Session and returns its hosted url. */
export async function createSubscriptionCheckout(opts: {
  customerId: string
  priceId: string
  userId: string
  bot: string
  trialDays: number
  successUrl: string
  cancelUrl: string
}): Promise<{ id: string; url: string }> {
  const session = await stripeRequest<{ id: string; url: string }>('POST', '/checkout/sessions', {
    mode: 'subscription',
    customer: opts.customerId,
    client_reference_id: opts.userId,
    line_items: [{ price: opts.priceId, quantity: 1 }],
    subscription_data: {
      trial_period_days: opts.trialDays,
      metadata: { ironforge_user_id: opts.userId, bot: opts.bot },
    },
    metadata: { ironforge_user_id: opts.userId, bot: opts.bot },
    allow_promotion_codes: true,
    success_url: opts.successUrl,
    cancel_url: opts.cancelUrl,
  })
  return { id: session.id, url: session.url }
}

export async function retrieveCheckoutSession(id: string): Promise<any> {
  return stripeRequest('GET', `/checkout/sessions/${encodeURIComponent(id)}`)
}

/**
 * Verifies a Stripe webhook signature. Header format: `t=<ts>,v1=<sig>,...`. We recompute
 * HMAC-SHA256 of `${t}.${rawBody}` with the endpoint secret and constant-time compare against
 * any provided v1 signature. Returns false on any malformation rather than throwing.
 */
export function verifyStripeSignature(rawBody: string, sigHeader: string | null, secret: string): boolean {
  if (!sigHeader || !secret) return false
  const parts = Object.fromEntries(
    sigHeader.split(',').map((kv) => {
      const idx = kv.indexOf('=')
      return [kv.slice(0, idx).trim(), kv.slice(idx + 1).trim()]
    }),
  ) as Record<string, string>
  const t = parts['t']
  const v1 = parts['v1']
  if (!t || !v1) return false

  const expected = crypto.createHmac('sha256', secret).update(`${t}.${rawBody}`, 'utf8').digest('hex')
  try {
    const a = Buffer.from(expected, 'hex')
    const b = Buffer.from(v1, 'hex')
    return a.length === b.length && crypto.timingSafeEqual(a, b)
  } catch {
    return false
  }
}
