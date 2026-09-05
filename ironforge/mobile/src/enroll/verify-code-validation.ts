/**
 * Client-side validator for the 6-digit email verification code (mobile enrollment
 * follow-up, 9/5). Mirrors the server's shape check in
 * webapp/src/app/api/auth/verify-code/route.ts (`/^\d{6}$/`) — this exists only so
 * the Continue button can stay disabled and show an inline error before round-tripping,
 * not to replace server validation.
 */

/** Strips non-digits and caps length — what CodeInput feeds into onChangeText. */
export function sanitizeCodeInput(raw: string, length = 6): string {
  return String(raw ?? '').replace(/\D/g, '').slice(0, length)
}

export function isValidVerifyCode(code: string): boolean {
  return /^\d{6}$/.test(String(code ?? '').trim())
}
