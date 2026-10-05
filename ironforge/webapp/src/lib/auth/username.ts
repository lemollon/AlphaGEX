/**
 * Username candidate generation shared by every path that creates a customer
 * account from a third-party profile with no username of its own — today the
 * Google OAuth callback and the post-consent completion route, both of which
 * must land on the identical collision behavior.
 */

import { isValidUsername } from '@/lib/signup-validation'
import { customerQuery } from '@/lib/customers-db'

export async function uniqueUsername(base: string): Promise<string> {
  const candidates = [
    base,
    ...Array.from({ length: 4 }, () => `${base}${Math.floor(100 + Math.random() * 900)}`),
  ]
  for (const candidate of candidates) {
    if (!isValidUsername(candidate)) continue
    const rows = await customerQuery<{ id: string }>(
      `SELECT id FROM users WHERE lower(username) = lower($1) LIMIT 1`,
      [candidate],
    )
    if (rows.length === 0) return candidate
  }
  // Astronomically unlikely to be reached, but a username MUST exist — never block
  // account creation on a naming collision.
  return `member${Date.now().toString(36)}`
}
