/**
 * Promo / founding-offer codes — single source of truth, no server imports so
 * both the signup form (client) and the API (server) validate against one list.
 *
 * IMPORTANT: there is no billing engine yet, so a code cannot discount a live
 * charge. What it does today is get CAPTURED at signup and stored on the user, so
 * the operator honours it when provisioning (see /ops/customers) and it becomes a
 * real Stripe coupon when billing ships. The customer-facing copy must reflect
 * that ("locked in / applied when your account is activated"), never imply an
 * instant discount on a charge that doesn't exist.
 */

export interface Promo {
  /** Canonical, UPPERCASE. Match case-insensitively. */
  code: string
  /** Plan the code unlocks. */
  plan: string
  /** Active bots included at the promo price. */
  bots: number
  /** Monthly price in whole dollars at the promo rate. */
  price: number
  /** The list price this beats (for the strike-through), or null. */
  listPrice: number | null
  /** Short customer-facing headline. */
  headline: string
  /** One-line terms. */
  terms: string
  /** Marketing-only scarcity note (not enforced in code). */
  scarcity: string | null
}

/**
 * FORGE50 — founding offer: Forge Pro (2 bots) at the Starter price, $50/mo,
 * locked while the subscription stays active.
 */
const PROMOS: Record<string, Promo> = {
  FORGE50: {
    code: 'FORGE50',
    plan: 'Forge Pro',
    bots: 2,
    price: 50,
    listPrice: 100,
    headline: '2 active bots for $50/month',
    terms: 'Founding rate — $50/mo for 2 bots, locked for as long as your subscription stays active.',
    scarcity: 'Founding members — first 100 only',
  },
}

/** Normalise a user-entered code. */
export function normalizePromo(raw: string | null | undefined): string {
  return String(raw ?? '').trim().toUpperCase()
}

/** Returns the Promo for a code, or null if it isn't a live code. */
export function lookupPromo(raw: string | null | undefined): Promo | null {
  const code = normalizePromo(raw)
  if (!code) return null
  return PROMOS[code] ?? null
}

export function isValidPromo(raw: string | null | undefined): boolean {
  return lookupPromo(raw) !== null
}
