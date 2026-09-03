/**
 * Password strength rules — ported 1:1 from webapp `src/lib/signup-validation.ts`
 * `checkPassword()` so the reset-password screen enforces exactly the same policy the
 * server does. Do not drift these independently; if the web rules change, mirror them
 * here.
 */

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

export const PASSWORD_MIN_LENGTH = 12

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
