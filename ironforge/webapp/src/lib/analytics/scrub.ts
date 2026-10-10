/**
 * PII scrubbing for POST /api/v1/events. Two passes, because a key-based
 * block alone misses a value stuffed under an innocuous key (e.g. `note:
 * "card 4111111111111111"`), and a value-based block alone misses a key like
 * `cardNumber` whose value happens not to match a digit pattern this pass
 * recognizes:
 *
 *  1. KEY pass — drop any prop whose key names money/identity fields outright
 *     (card, account, broker, email, phone, ssn, token, password, secret).
 *  2. VALUE pass — drop any remaining prop whose STRING value looks like an
 *     email address, a phone number, or a long digit run (card/account/SSN).
 *
 * Deliberately conservative: a false positive just drops one telemetry prop;
 * a false negative stores a customer's card or SSN. Ties go to dropping.
 */

const SENSITIVE_KEY_RE = /card|account|broker|email|phone|ssn|ein|ssn|token|password|secret|routing/i
const EMAIL_RE = /[^\s@]+@[^\s@]+\.[^\s@]+/
const PHONE_RE = /(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/
// 9+ consecutive digits (ignoring separators) covers card numbers, SSNs, and
// brokerage account numbers without flagging a 4-6 digit count/amount prop.
const LONG_DIGIT_RE = /(?:\d[\s-]?){9,}/

export function looksLikePii(value: string): boolean {
  return EMAIL_RE.test(value) || PHONE_RE.test(value) || LONG_DIGIT_RE.test(value)
}

export function scrubProps(
  props: Record<string, unknown> | null | undefined,
): Record<string, unknown> | null {
  if (!props || typeof props !== 'object') return null
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(props)) {
    if (SENSITIVE_KEY_RE.test(k)) continue
    if (typeof v === 'string' && looksLikePii(v)) continue
    // Only primitives travel — telemetry props are never nested objects/arrays.
    if (v === null || typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
      out[k] = v
    }
  }
  return Object.keys(out).length > 0 ? out : null
}
