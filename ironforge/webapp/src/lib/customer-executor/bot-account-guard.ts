/**
 * Bot-traded Tradier account guard (6YB71371 double-trade guard).
 *
 * SPARK and FLAME trade a small, fixed set of Tradier accounts DIRECTLY via
 * tradier.ts (TRADIER_FLAME_ACCOUNT_ID and friends — see bot-account-registry.ts).
 * If one of those SAME physical brokerage accounts is ALSO connected as a customer
 * broker account (SnapTrade or direct Tradier OAuth), mirroring a master position
 * into it would place the trade a second time, with two independently-managed,
 * uncoordinated closes fighting over the same real position. This module is the
 * one place that decides whether a given customer broker account IS one of the
 * accounts the bots already trade — used both at connection/activation time
 * (lib/enrollment/eligibility.ts) and at mirror time (customer-executor/executor.ts).
 *
 * FAILS CLOSED: an account whose number cannot be confidently determined is
 * treated as blocked, never as clear. Getting this wrong in the "safe" direction
 * only costs a skipped mirror; getting it wrong in the other direction risks a
 * real double-trade in a real brokerage account.
 *
 * Pure: no I/O, no clock, no crypto. Callers decrypt/normalize before calling in.
 */

const TRADIER_SLUG = 'TRADIER'

/** Strip everything but letters/digits and uppercase, so formatting differences
 *  (dashes, spaces, lowercase) never produce a false non-match. */
export function normalizeAccountNumber(raw: string): string {
  return raw.trim().toUpperCase().replace(/[^A-Z0-9]/g, '')
}

/** Last 4 normalized characters — mirrors eligibility.ts's maskAccountNumber convention. */
export function accountLast4(raw: string): string {
  const n = normalizeAccountNumber(raw)
  return n.length >= 4 ? n.slice(-4) : n
}

export interface BotAccountGuardInput {
  /** Decrypted brokerage account reference, if one could be read. Null/empty = unknown
   *  (missing ciphertext, decrypt failure, or never captured). Never pass a raw
   *  SnapTrade internal id here believing it to be the account number — pass null. */
  decryptedAccountRef?: string | null
  /** Masked display value as stored (e.g. '••••7371'). Used only when the full
   *  reference above is unavailable. */
  displayMask?: string | null
  /** Normalized institution slug (e.g. via lib/enrollment/eligibility's
   *  normalizeInstitutionSlug), 'TRADIER' for both SnapTrade's Tradier integration
   *  and the direct Tradier OAuth connection. Null when unknown. */
  brokerSlug?: string | null
  /** Full Tradier account numbers the bots trade directly (bot-account-registry.ts).
   *  Passed in by the caller so this module stays pure / no env reads. */
  knownBotAccountNumbers: string[]
}

export type BotAccountGuardVerdict =
  | { blocked: false }
  | { blocked: true; reason: 'full_number_match' | 'masked_last4_match'; matchedLast4: string }
  | { blocked: true; reason: 'unverifiable' }

/**
 * Is this customer broker account one of the accounts the bots already trade
 * directly? Three ways to answer, tried in order of confidence:
 *
 *  1. Full number known → normalize and compare in full. A miss here is a
 *     confirmed answer (this account is NOT a bot account) — no need to fall
 *     through to the weaker checks.
 *  2. Full number unknown, but the institution is confirmed to be something
 *     OTHER than Tradier → also a confirmed answer (a non-Tradier account can
 *     never be one of our Tradier bot accounts).
 *  3. Full number unknown, institution is Tradier (or unconfirmed) → fall back
 *     to last-4 + institution. A Tradier account whose last 4 match a known bot
 *     account is blocked and logged loudly; anything else that still cannot be
 *     ruled out (institution unknown, or no mask available) is UNVERIFIABLE and
 *     fails closed.
 */
export function checkBotTradedAccount(input: BotAccountGuardInput): BotAccountGuardVerdict {
  const known = input.knownBotAccountNumbers
    .map((a) => normalizeAccountNumber(String(a ?? '')))
    .filter((a) => a.length > 0)

  const ref = input.decryptedAccountRef ? normalizeAccountNumber(input.decryptedAccountRef) : ''
  if (ref.length > 0) {
    const hit = known.find((k) => k === ref)
    return hit
      ? { blocked: true, reason: 'full_number_match', matchedLast4: hit.slice(-4) }
      : { blocked: false }
  }

  const slug = input.brokerSlug ? String(input.brokerSlug).toUpperCase() : null
  if (slug != null && slug !== TRADIER_SLUG) {
    return { blocked: false }
  }

  const maskLast4 = input.displayMask ? accountLast4(input.displayMask) : ''
  if (slug === TRADIER_SLUG && maskLast4.length === 4) {
    const hit = known.find((k) => k.length >= 4 && k.slice(-4) === maskLast4)
    return hit
      ? { blocked: true, reason: 'masked_last4_match', matchedLast4: maskLast4 }
      : { blocked: false }
  }

  return { blocked: true, reason: 'unverifiable' }
}
