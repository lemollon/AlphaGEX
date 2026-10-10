/**
 * Client-side mirror of webapp/src/lib/waitlist.ts (8/26 handoff). POST /api/waitlist
 * enforces the same rules server-side and is the actual authority — this exists so
 * /waitlist can show inline field errors before round-tripping, not to replace server
 * validation.
 *
 * Duplicated rather than imported: mobile and webapp are separate apps with no shared
 * package (same tradeoff as src/enroll/signup-validation.ts's own note). If the
 * server's rules ever change, this file must change with them.
 */

export const CONSENT_COPY =
  'I agree to receive IronForge launch updates and account-related communications by email and phone.'

/** Approved trading-capital ranges (radio rows). Slug <-> label; never labeled as income. */
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

export interface WaitlistFields {
  firstName: string
  lastName: string
  email: string
  phone: string
  city: string
  state: string
  tradingCapitalRange: string
  communicationConsent: boolean
}

export type WaitlistErrors = Partial<Record<keyof WaitlistFields, string>>

/** Normalize a US phone to E.164 (+1XXXXXXXXXX); '' when it can't be resolved. */
export function normalizePhone(phone: string): string {
  const d = String(phone ?? '').replace(/\D/g, '')
  if (d.length === 10) return `+1${d}`
  if (d.length === 11 && d.startsWith('1')) return `+${d}`
  return ''
}

/** Field-level validation -> { field: message }. Empty object = valid. */
export function validateWaitlist(v: Partial<WaitlistFields>): WaitlistErrors {
  const e: WaitlistErrors = {}
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

/** US state + DC two-letter abbreviations, for the state picker. */
export const US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL',
  'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME',
  'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH',
  'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI',
  'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
] as const
