import { z } from 'zod'

/**
 * Waitlist domain: validation + normalization, shared by the /waitlist form and the
 * /api/waitlist route so client and server enforce the same rules (per the 8/26
 * developer handoff). Email is the canonical dedupe key.
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
const CAPITAL_VALUES = CAPITAL_RANGES.map((r) => r.value) as [CapitalRange, ...CapitalRange[]]

const NAME_RE = /^[A-Za-z][A-Za-z '-]{0,59}$/

/** Normalize a US phone to E.164 (+1XXXXXXXXXX); '' when it can't be resolved. */
export function normalizePhone(phone: string): string {
  const d = String(phone ?? '').replace(/\D/g, '')
  if (d.length === 10) return `+1${d}`
  if (d.length === 11 && d.startsWith('1')) return `+${d}`
  return ''
}

/** The raw client payload shape. */
export const waitlistSchema = z.object({
  firstName: z.string().trim().regex(NAME_RE, 'Enter your first name.'),
  lastName: z.string().trim().regex(NAME_RE, 'Enter your last name.'),
  email: z.string().trim().toLowerCase().email('Enter a valid email address.'),
  phone: z.string().trim().refine((p) => normalizePhone(p) !== '', 'Enter a valid US phone number.'),
  city: z.string().trim().min(1, 'Enter your city.').max(80),
  state: z.string().trim().length(2, 'Select your state.'),
  tradingCapitalRange: z.enum(CAPITAL_VALUES, { message: 'Choose a range.' }),
  communicationConsent: z.literal(true, { message: 'Please agree to continue.' }),
})

export type WaitlistInput = z.infer<typeof waitlistSchema>

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

/** Server-side normalization AFTER schema validation. */
export function normalizeWaitlist(input: WaitlistInput): NormalizedWaitlist {
  return {
    firstName: input.firstName.trim(),
    lastName: input.lastName.trim(),
    email: input.email.trim().toLowerCase(),
    phone: normalizePhone(input.phone),
    city: input.city.trim(),
    state: input.state.trim().toUpperCase(),
    tradingCapitalRange: input.tradingCapitalRange,
    consent: true,
  }
}

/** Client-side field validation → { field: message }. Empty object = valid. */
export function validateWaitlistClient(v: {
  firstName: string; lastName: string; email: string; phone: string
  city: string; state: string; tradingCapitalRange: string; communicationConsent: boolean
}): Record<string, string> {
  const r = waitlistSchema.safeParse(v)
  if (r.success) return {}
  const out: Record<string, string> = {}
  for (const issue of r.error.issues) {
    const key = String(issue.path[0] ?? '')
    if (key && !out[key]) out[key] = issue.message
  }
  return out
}
