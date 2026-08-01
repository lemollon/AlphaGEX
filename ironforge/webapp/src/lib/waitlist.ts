/**
 * Waitlist domain: validation + normalization, shared by the /waitlist form and the
 * /api/waitlist route so client and server enforce the same rules (8/26 handoff).
 * Hand-rolled (matches lib/signup-validation.ts) — no external validation dependency.
 * Email is the canonical dedupe key.
 */

export const CONSENT_VERSION = 'waitlist-v1-2026-08-01'
export const WAITLIST_SOURCE = 'ironforge.trade/waitlist'
export const CONSENT_COPY =
  'I agree to receive IronForge launch updates and account-related communications by email and phone.'

/** Approved trading-capital ranges (radio cards). Slug ↔ label; never labeled as income. */
export const CAPITAL_RANGES = [
  { value: 'under_5000', label: 'Under $5,000' },
  { value: '5000_10000', label: '$5,000 – $10,000' },
  { value: '10000_25000', label: '$10,000 – $25,000' },
  { value: '25000_50000', label: '$25,000 – $50,000' },
  { value: '50000_plus', label: '$50,000+' },
] as const

export type CapitalRange = (typeof CAPITAL_RANGES)[number]['value']
const CAPITAL_VALUES: readonly string[] = CAPITAL_RANGES.map((r) => r.value)

const NAME_RE = /^[A-Za-z][A-Za-z '-]{0,59}$/
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export interface WaitlistRaw {
  firstName: string
  lastName: string
  email: string
  phone: string
  city: string
  state: string
  tradingCapitalRange: string
  communicationConsent: boolean
}

export interface NormalizedWaitlist {
  firstName: string
  lastName: string
  email: string
  phone: string
  city: string
  state: string
  tradingCapitalRange: CapitalRange
  consent: true
}

/** Normalize a US phone to E.164 (+1XXXXXXXXXX); '' when it can't be resolved. */
export function normalizePhone(phone: string): string {
  const d = String(phone ?? '').replace(/\D/g, '')
  if (d.length === 10) return `+1${d}`
  if (d.length === 11 && d.startsWith('1')) return `+${d}`
  return ''
}

/** Field-level validation → { field: message }. Empty object = valid. */
export function validateWaitlistClient(v: Partial<WaitlistRaw>): Record<string, string> {
  const e: Record<string, string> = {}
  const firstName = String(v.firstName ?? '').trim()
  const lastName = String(v.lastName ?? '').trim()
  const email = String(v.email ?? '').trim()
  const city = String(v.city ?? '').trim()
  const state = String(v.state ?? '').trim()

  if (!NAME_RE.test(firstName)) e.firstName = 'Enter your first name.'
  if (!NAME_RE.test(lastName)) e.lastName = 'Enter your last name.'
  if (!EMAIL_RE.test(email.toLowerCase())) e.email = 'Enter a valid email address.'
  if (normalizePhone(String(v.phone ?? '')) === '') e.phone = 'Enter a valid US phone number.'
  if (city.length < 1 || city.length > 80) e.city = 'Enter your city.'
  if (state.length !== 2) e.state = 'Select your state.'
  if (!CAPITAL_VALUES.includes(String(v.tradingCapitalRange ?? ''))) e.tradingCapitalRange = 'Choose a range.'
  if (v.communicationConsent !== true) e.communicationConsent = 'Please agree to continue.'
  return e
}

/**
 * Server-side validate + normalize. Returns the normalized record, or the field
 * errors when invalid.
 */
export function validateWaitlist(
  input: Partial<WaitlistRaw>,
): { ok: true; data: NormalizedWaitlist } | { ok: false; fieldErrors: Record<string, string> } {
  const fieldErrors = validateWaitlistClient(input)
  if (Object.keys(fieldErrors).length > 0) return { ok: false, fieldErrors }
  return {
    ok: true,
    data: {
      firstName: String(input.firstName).trim(),
      lastName: String(input.lastName).trim(),
      email: String(input.email).trim().toLowerCase(),
      phone: normalizePhone(String(input.phone)),
      city: String(input.city).trim(),
      state: String(input.state).trim().toUpperCase(),
      tradingCapitalRange: String(input.tradingCapitalRange) as CapitalRange,
      consent: true,
    },
  }
}
