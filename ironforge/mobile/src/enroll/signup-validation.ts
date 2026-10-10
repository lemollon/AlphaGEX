/**
 * Client-side mirror of webapp/src/lib/signup-validation.ts (IronForge Account Creation
 * Developer Handoff v1, §3-4). POST /api/auth/signup enforces the same rules
 * server-side and is the actual authority — this exists so /enroll/create-account can
 * show inline field errors before round-tripping, not to replace server validation.
 *
 * Duplicated rather than imported: mobile and webapp are separate apps with no shared
 * package (see src/api/types.ts's own note on the same tradeoff). If the server's rules
 * ever change, this file must change with them.
 */

export interface SignupFields {
  firstName: string
  lastName: string
  username: string
  email: string
  phone: string
  state: string
  password: string
  confirmPassword: string
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

export const PASSWORD_MIN_LENGTH = 12

export const USERNAME_RE = /^[A-Za-z][A-Za-z0-9_]{2,19}$/

export function isValidUsername(username: string): boolean {
  return USERNAME_RE.test(String(username ?? '').trim())
}

export function normalizeEmail(email: string): string {
  return String(email ?? '').trim().toLowerCase()
}

export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizeEmail(email))
}

export function isValidPhone(phone: string): boolean {
  const digits = String(phone ?? '').replace(/\D/g, '')
  if (digits.length === 10) return true
  if (digits.length === 11 && digits.startsWith('1')) return true
  return false
}

export function checkPassword(password: string): { valid: boolean; rules: PasswordRules } {
  const p = String(password ?? '')
  const rules: PasswordRules = {
    minLength: p.length >= PASSWORD_MIN_LENGTH,
    upper: /[A-Z]/.test(p),
    lower: /[a-z]/.test(p),
    number: /[0-9]/.test(p),
    special: /[^A-Za-z0-9]/.test(p),
  }
  return { valid: Object.values(rules).every(Boolean), rules }
}

export type SignupErrors = Partial<Record<keyof SignupFields, string>>

export function validateSignup(f: SignupFields): { ok: boolean; errors: SignupErrors } {
  const errors: SignupErrors = {}

  if (!f.firstName.trim()) errors.firstName = 'First name is required.'
  if (!f.lastName.trim()) errors.lastName = 'Last name is required.'

  if (!f.username.trim()) {
    errors.username = 'Choose a username.'
  } else if (!isValidUsername(f.username)) {
    errors.username = 'Usernames are 3–20 characters — letters, numbers, underscores — and start with a letter.'
  }

  if (!isValidEmail(f.email)) errors.email = 'Enter a valid email address.'
  if (!isValidPhone(f.phone)) errors.phone = 'Enter a valid US mobile number, e.g. (555) 123-4567.'
  if (!f.state.trim()) errors.state = 'Enter your state of residence.'

  if (!checkPassword(f.password).valid) {
    errors.password =
      'Password must include at least 12 characters, uppercase, lowercase, number, and special character.'
  }
  if (f.confirmPassword !== f.password) errors.confirmPassword = 'Passwords do not match.'

  if (!f.ageConfirmed) errors.ageConfirmed = 'You must confirm you are at least 18 years old.'
  if (!f.noAdviceAcknowledged) errors.noAdviceAcknowledged = 'You must acknowledge the no-advice statement.'
  if (!f.electronicCommConsent) errors.electronicCommConsent = 'You must consent to electronic communications.'

  return { ok: Object.keys(errors).length === 0, errors }
}
