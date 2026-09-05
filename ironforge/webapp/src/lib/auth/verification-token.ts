import { createHash, randomBytes, randomInt } from 'crypto'

// Email verification tokens: the RAW token goes in the verification link; only its
// sha256 HASH is stored in email_verification_tokens. (Sub-project C.)

export const TOKEN_TTL_MS = 24 * 60 * 60 * 1000 // 24 hours

export function hashToken(raw: string): string {
  return createHash('sha256').update(raw).digest('hex')
}

export function generateToken(): { raw: string; hash: string } {
  const raw = randomBytes(32).toString('base64url')
  return { raw, hash: hashToken(raw) }
}

export function isExpired(expiresAt: Date | string, now: Date): boolean {
  const exp = expiresAt instanceof Date ? expiresAt : new Date(expiresAt)
  return now.getTime() >= exp.getTime()
}

// 6-digit email verification CODE — additive alongside the link above, added for
// the mobile enrollment funnel (9/5). Lives on the same email_verification_tokens
// row as the link, and is rotated together with it on every resend.

export const CODE_TTL_MS = 15 * 60 * 1000 // 15 minutes
export const MAX_CODE_ATTEMPTS = 5

/** Zero-padded 6-digit code, e.g. "004821". Never stored in plain text — see hashCode. */
export function generateCode(): string {
  return String(randomInt(0, 1_000_000)).padStart(6, '0')
}

/**
 * The code alone is only ~20 bits of entropy, so it is salted with the user_id
 * before hashing — a leaked hash for one user's row cannot be replayed against
 * another user's still-open code, and a rainbow table over all 1,000,000 codes
 * would have to be rebuilt per user_id.
 */
export function hashCode(code: string, userId: string): string {
  return createHash('sha256').update(`${code}:${userId}`).digest('hex')
}
