// Shared signup validation — used by both the /signup client form and the
// /api/auth/signup server stub so the rules stay in lockstep.
// Rules follow IronForge Account Creation Developer Handoff v1, §3–4.

export interface SignupPayload {
  firstName: string
  lastName: string
  email: string
  phone: string
  state: string
  password: string
  confirmPassword: string
  referralCode?: string
  ageConfirmed: boolean
  noAdviceAcknowledged: boolean
  electronicCommConsent: boolean
}

export interface PasswordRules {
  minLength: boolean
  upper: boolean
  lower: boolean
  number: boolean
  special: boolean
}

export interface PasswordCheck {
  valid: boolean
  rules: PasswordRules
}

export interface NormalizedSignup {
  firstName: string
  lastName: string
  email: string
  phone: string
  state: string
  referralCode: string
}

export interface SignupValidation {
  ok: boolean
  errors: Partial<Record<keyof SignupPayload, string>>
  normalized: NormalizedSignup
}

export const PASSWORD_MIN_LENGTH = 12

export function normalizeEmail(email: string): string {
  return String(email ?? '').trim().toLowerCase()
}

export function isValidEmail(email: string): boolean {
  const e = normalizeEmail(email)
  // Simple, deliberately strict-enough format check: local@domain.tld
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)
}

// Best-effort E.164 normalization for US numbers. Falls back to a +-prefixed
// digit string when we cannot confidently map it.
export function normalizePhone(phone: string): string {
  const digits = String(phone ?? '').replace(/\D/g, '')
  if (digits.length === 10) return `+1${digits}`
  if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`
  return digits ? `+${digits}` : ''
}

export function isValidPhone(phone: string): boolean {
  const digits = String(phone ?? '').replace(/\D/g, '')
  if (digits.length === 10) return true
  if (digits.length === 11 && digits.startsWith('1')) return true
  return false
}

export function checkPassword(password: string): PasswordCheck {
  const p = String(password ?? '')
  const rules: PasswordRules = {
    minLength: p.length >= PASSWORD_MIN_LENGTH,
    upper: /[A-Z]/.test(p),
    lower: /[a-z]/.test(p),
    number: /[0-9]/.test(p),
    special: /[^A-Za-z0-9]/.test(p),
  }
  const valid = Object.values(rules).every(Boolean)
  return { valid, rules }
}

export function validateSignup(payload: SignupPayload): SignupValidation {
  const errors: Partial<Record<keyof SignupPayload, string>> = {}

  const firstName = String(payload.firstName ?? '').trim()
  const lastName = String(payload.lastName ?? '').trim()
  const email = normalizeEmail(payload.email)
  const phone = normalizePhone(payload.phone)
  const state = String(payload.state ?? '').trim()
  const referralCode = String(payload.referralCode ?? '').trim().toUpperCase()

  if (!firstName) errors.firstName = 'First name is required.'
  if (!lastName) errors.lastName = 'Last name is required.'

  if (!isValidEmail(payload.email)) {
    errors.email = 'Enter a valid email address.'
  }

  if (!isValidPhone(payload.phone)) {
    errors.phone = 'Enter a valid US mobile number, e.g. (555) 123-4567.'
  }

  if (!state) errors.state = 'Select your state of residence.'

  if (!checkPassword(payload.password).valid) {
    errors.password =
      'Password must include at least 12 characters, uppercase, lowercase, number, and special character.'
  }

  if (payload.confirmPassword !== payload.password) {
    errors.confirmPassword = 'Passwords do not match.'
  }

  if (!payload.ageConfirmed) {
    errors.ageConfirmed = 'You must confirm you are at least 18 years old.'
  }
  if (!payload.noAdviceAcknowledged) {
    errors.noAdviceAcknowledged = 'You must acknowledge the no-advice statement.'
  }
  if (!payload.electronicCommConsent) {
    errors.electronicCommConsent = 'You must consent to electronic communications.'
  }

  return {
    ok: Object.keys(errors).length === 0,
    errors,
    normalized: { firstName, lastName, email, phone, state, referralCode },
  }
}
