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

/** A price as Stripe reports it, enough to check it against what the site advertises. */
export interface StripePriceSummary {
  id: string
  /** Minor units, e.g. 1000 for $10.00. */
  unit_amount: number | null
  currency: string
  recurring: { interval: string } | null
  /** Product id this price belongs to — a corrected price must stay on the same product. */
  product: string
}

export interface PriceSyncResult {
  lookupKey: string
  /** True if ANYTHING was written to Stripe — including a partial run. */
  changed: boolean
  advertised: number
  wasAmount: number | null
  newPriceId?: string
  archivedPriceId?: string
  /** Set when the price was corrected but cleanup did not finish. */
  warning?: string
  detail: string
}

/**
 * Make Stripe charge what the site advertises for ONE lookup key.
 *
 * Stripe prices are IMMUTABLE — an amount cannot be edited. Correcting one means
 * creating a new price, moving the lookup key onto it (transfer_lookup_key, which
 * detaches it from the old price atomically), and archiving the old one so nothing
 * can resolve back to it.
 *
 * DELIBERATELY NOT PARAMETERISED BY AMOUNT. The caller passes the lookup key; the
 * amount comes from `advertisedDollars`, which callers source from plans.ts. This can
 * only ever converge Stripe TOWARD the published price — it cannot set an arbitrary
 * number, so it is not a general-purpose "change our pricing" tool.
 *
 * Idempotent: already-matching prices are a no-op.
 *
 * Does NOT touch existing subscriptions. Anyone already subscribed keeps the price
 * they signed up at until they are migrated — deliberate, since silently repricing a
 * live subscriber is worse than the drift being fixed.
 */
export async function syncPriceToAdvertised(
  lookupKey: string,
  advertisedDollars: number,
): Promise<PriceSyncResult> {
  const current = await findPriceByLookupKey(lookupKey)
  if (!current) {
    return {
      lookupKey, changed: false, advertised: advertisedDollars, wasAmount: null,
      detail: `No active price with lookup key ${lookupKey} — create it in Stripe first.`,
    }
  }

  const wantMinor = Math.round(advertisedDollars * 100)
  const cur = (current.currency || 'usd').toUpperCase()

  // Already the right amount. Still reconcile the PRODUCT DEFAULT: a stale default
  // pointing at an old price is how a $15 price survived a correction to $10 —
  // Stripe refuses to archive a product's default price, so the first run left it
  // active. This makes a re-run finish the job instead of reporting "nothing to do".
  if (current.unit_amount === wantMinor) {
    const cleanup = await retireStaleDefault(current.product, current.id, wantMinor)
    return {
      lookupKey,
      changed: cleanup.changed,
      advertised: advertisedDollars,
      wasAmount: current.unit_amount / 100,
      archivedPriceId: cleanup.archivedPriceId,
      detail: cleanup.changed
        ? `Already ${advertisedDollars.toFixed(2)} ${cur}. ${cleanup.detail}`
        : 'Already matches the advertised price.',
    }
  }

  const created = await stripeRequest<{ id: string }>('POST', '/prices', {
    product: current.product,
    unit_amount: wantMinor,
    currency: current.currency || 'usd',
    recurring: { interval: current.recurring?.interval || 'month' },
    lookup_key: lookupKey,
    transfer_lookup_key: true,
  })

  // From here the price is ALREADY corrected — the lookup key now resolves to the new
  // price, so checkout charges the right amount even if the cleanup below fails. Any
  // failure past this point must still report changed:true, or an operator reading
  // "nothing to do" would believe a live billing change never happened.
  const base = {
    lookupKey,
    changed: true,
    advertised: advertisedDollars,
    wasAmount: current.unit_amount === null ? null : current.unit_amount / 100,
    newPriceId: created.id,
  }
  try {
    const cleanup = await retireStaleDefault(current.product, created.id, wantMinor)
    return {
      ...base,
      archivedPriceId: cleanup.archivedPriceId ?? current.id,
      detail: `Created a ${advertisedDollars.toFixed(2)} ${cur} price and moved lookup key ${lookupKey} onto it. ${cleanup.detail}`,
    }
  } catch (e: unknown) {
    return {
      ...base,
      warning: 'PRICE CORRECTED, CLEANUP INCOMPLETE — the old price is still active. Re-run to finish.',
      detail: `Created a ${advertisedDollars.toFixed(2)} ${cur} price and moved lookup key ${lookupKey} onto it; checkout now charges the right amount. Could not retire the old price: ${e instanceof Error ? e.message : String(e)}`,
    }
  }
}

/**
 * Point the product's default price at `keepPriceId` and archive the price it displaced.
 *
 * Stripe REFUSES to archive a price that is its product's default ("This price cannot be
 * archived because it is the default price of its product"), so the default must be moved
 * first. Without this, a corrected product is left with the old amount still active AND
 * still the default — invisible to lookup-key resolution, but live for anything that uses
 * the product default (payment links, dashboard-created invoices).
 *
 * Only ever archives a price whose amount DIFFERS from the advertised one, so a legitimate
 * second price on the same product (an annual plan, say) is never touched.
 */
async function retireStaleDefault(
  productId: string,
  keepPriceId: string,
  advertisedMinor: number,
): Promise<{ changed: boolean; archivedPriceId?: string; detail: string }> {
  const product = await stripeRequest<{ default_price: string | null }>('GET', `/products/${productId}`)
  const displaced = product.default_price
  if (displaced === keepPriceId) return { changed: false, detail: 'Product default already correct.' }

  await stripeRequest('POST', `/products/${productId}`, { default_price: keepPriceId })
  if (!displaced) return { changed: true, detail: 'Set the product default price.' }

  const old = await stripeRequest<{ id: string; active: boolean; unit_amount: number | null }>(
    'GET', `/prices/${displaced}`,
  )
  if (!old.active || old.unit_amount === advertisedMinor) {
    return { changed: true, detail: 'Set the product default price; nothing to archive.' }
  }
  await stripeRequest('POST', `/prices/${displaced}`, { active: false })
  return {
    changed: true,
    archivedPriceId: displaced,
    detail: `Moved the product default off the old price and archived it (was $${((old.unit_amount ?? 0) / 100).toFixed(2)}).`,
  }
}

/**
 * Resolves the full active Price behind a lookup key.
 *
 * Returns the AMOUNT as well as the id, because the id alone cannot tell you
 * whether Stripe is about to charge what the marketing page says. See
 * /api/ops/billing-readiness, which uses this to catch a price drift before a
 * customer is billed the wrong number.
 */
export async function findPriceByLookupKey(lookupKey: string): Promise<StripePriceSummary | null> {
  const res = await stripeRequest<StripeList<StripePriceSummary>>('GET', '/prices', {
    lookup_keys: [lookupKey],
    active: true,
    limit: 1,
  })
  return res.data[0] ?? null
}

/** Resolves a Stripe Price id from its lookup key. Returns null when no active price matches. */
export async function findPriceIdByLookupKey(lookupKey: string): Promise<string | null> {
  return (await findPriceByLookupKey(lookupKey))?.id ?? null
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
/**
 * SETUP-mode checkout — collect a reusable payment method with $0 DUE TODAY (§7).
 *
 * Automate must "collect payment method and create subscription/trial arrangement only
 * after setup rules are satisfied; UI shows $0 due today". Subscription-mode checkout
 * cannot express that: it always creates a subscription, and the only way to avoid an
 * immediate charge is trial_period_days — which starts a CALENDAR trial at checkout,
 * exactly what §7 forbids ("Do not start the trial clock at card capture").
 *
 * So enrollment captures the card here, and the subscription is created later, inside
 * the activation transaction, by createTrialingSubscription().
 */
export async function createSetupCheckout(opts: {
  customerId: string
  userId: string
  /** Absent on the enrollment-funnel path — the agent isn't chosen until AGENT-01. */
  bot?: string
  /** Lets the webhook advance the right enrollment when the session completes. */
  enrollmentId?: string
  successUrl: string
  cancelUrl: string
}): Promise<{ id: string; url: string }> {
  // Carried so the webhook and the later activation can attribute this back.
  const metadata: Record<string, string> = { ironforge_user_id: opts.userId }
  if (opts.bot) metadata.bot = opts.bot
  if (opts.enrollmentId) metadata.enrollment_id = opts.enrollmentId
  return stripeRequest<{ id: string; url: string }>('POST', '/checkout/sessions', {
    mode: 'setup',
    customer: opts.customerId,
    success_url: opts.successUrl,
    cancel_url: opts.cancelUrl,
    metadata,
  })
}

/** A payment method actually attached to this customer — the §4 "payment method is valid" input. */
export async function hasUsablePaymentMethod(customerId: string): Promise<boolean> {
  try {
    const res = await stripeRequest<StripeList<{ id: string }>>('GET', '/payment_methods', {
      customer: customerId,
      type: 'card',
      limit: 1,
    })
    return (res.data?.length ?? 0) > 0
  } catch {
    // Unknown => treated as INVALID. The activation predicate must never be told
    // "valid" on a failed lookup.
    return false
  }
}

/**
 * Create the subscription in `trialing`, with the trial end far out.
 *
 * The far date is a HOLD, not the real trial length: our ledger decides when five
 * ELIGIBLE TRADING DAYS have passed and then calls endTrialNow(). Stripe stays the
 * billing authority; the calendar authority is lib/enrollment/trading-days.ts.
 *
 * Called ONLY from the activation transaction — this is the moment §7 permits the trial
 * clock to start.
 */
export async function createTrialingSubscription(opts: {
  customerId: string
  priceId: string
  userId: string
  bot: string
  /** Generous upper bound; the ledger ends it earlier. */
  holdDays?: number
}): Promise<{ id: string; status: string }> {
  const holdDays = opts.holdDays ?? 60
  const trialEnd = Math.floor(Date.now() / 1000) + holdDays * 24 * 60 * 60
  return stripeRequest<{ id: string; status: string }>('POST', '/subscriptions', {
    customer: opts.customerId,
    items: [{ price: opts.priceId }],
    trial_end: trialEnd,
    // Without this Stripe may void the subscription when the trial ends with no
    // default payment method; we want it to charge the card captured at enrollment.
    trial_settings: { end_behavior: { missing_payment_method: 'cancel' } },
    metadata: { ironforge_user_id: opts.userId, bot: opts.bot },
  })
}

/** End the trial NOW — the ledger reached five eligible trading days; bill it (§7). */
export async function endTrialNow(subscriptionId: string): Promise<{ id: string; status: string }> {
  return stripeRequest<{ id: string; status: string }>('POST', `/subscriptions/${subscriptionId}`, {
    trial_end: 'now',
    proration_behavior: 'none',
  })
}

export async function createSubscriptionCheckout(opts: {
  customerId: string
  priceId: string
  userId: string
  bot: string
  trialDays: number
  successUrl: string
  cancelUrl: string
}): Promise<{ id: string; url: string }> {
  // Stripe rejects trial_period_days below 1, so only include it for a real trial
  // (bot plans pass 5; Community passes 0 = charge immediately, no trial).
  const subscription_data: Record<string, unknown> = {
    metadata: { ironforge_user_id: opts.userId, bot: opts.bot },
  }
  if (opts.trialDays > 0) subscription_data.trial_period_days = opts.trialDays

  const session = await stripeRequest<{ id: string; url: string }>('POST', '/checkout/sessions', {
    mode: 'subscription',
    customer: opts.customerId,
    client_reference_id: opts.userId,
    line_items: [{ price: opts.priceId, quantity: 1 }],
    subscription_data,
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
 * Opens Stripe's hosted Customer Portal so a subscriber can change plan, update
 * their card, download receipts, or cancel — self-service, on Stripe, never on us.
 * The portal must be enabled once in the Stripe dashboard (Settings → Billing →
 * Customer portal); until then Stripe returns an error and the caller surfaces a
 * clean "not available yet", same as the checkout gate.
 */
export async function createBillingPortalSession(opts: {
  customerId: string
  returnUrl: string
}): Promise<{ url: string }> {
  const session = await stripeRequest<{ url: string }>('POST', '/billing_portal/sessions', {
    customer: opts.customerId,
    return_url: opts.returnUrl,
  })
  return { url: session.url }
}

export interface StripeSubscription {
  id: string
  status: string
  current_period_end?: number
  items: { data: Array<{ id: string; price?: { id?: string; lookup_key?: string | null } }> }
}

/** Fetches a subscription (with its single line item) so we can swap that item's price. */
export async function retrieveSubscription(id: string): Promise<StripeSubscription> {
  return stripeRequest<StripeSubscription>('GET', `/subscriptions/${encodeURIComponent(id)}`)
}

/**
 * Upgrades an existing single-bot subscription to the two-bot bundle in place, rather than opening
 * a second $50 subscription. It swaps the subscription's line item to the bundle price (so the
 * customer's total becomes the bundle price, not 2×single), prorating the difference, and stamps
 * `metadata.bots` so the webhook grants BOTH bot entitlements from the one subscription.
 *
 * Trials are preserved: if the first bot is still trialing, Stripe keeps the trial and bills the
 * bundle price when it ends. No new card entry is needed — the payment method is already on file.
 */
export async function upgradeSubscriptionToBundle(opts: {
  subscriptionId: string
  itemId: string
  bundlePriceId: string
  userId: string
  bots: string // CSV, e.g. "spark,flame"
}): Promise<StripeSubscription> {
  return stripeRequest<StripeSubscription>('POST', `/subscriptions/${encodeURIComponent(opts.subscriptionId)}`, {
    items: [{ id: opts.itemId, price: opts.bundlePriceId }],
    proration_behavior: 'create_prorations',
    // Only the keys sent are changed; metadata.bot from creation is preserved.
    metadata: { ironforge_user_id: opts.userId, bots: opts.bots },
  })
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
