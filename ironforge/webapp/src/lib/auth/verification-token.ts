import { createHash, randomBytes } from 'crypto'

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
