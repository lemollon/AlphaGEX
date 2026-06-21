import { decryptSecret } from '@/lib/crypto/secret-box'
import { customerQuery } from '@/lib/customers-db'

export interface SnapTradeCreds {
  snaptradeUserId: string
  userSecret: string
}

/**
 * Loads + decrypts a customer's SnapTrade credentials from the customers DB, or null if the
 * customer hasn't registered/connected yet. Centralizes the decrypt so the per-trade routes
 * never touch the ciphertext directly. (sub-project: brokerage connection)
 */
export async function loadSnapTradeCreds(userId: string): Promise<SnapTradeCreds | null> {
  const rows = await customerQuery<{ snaptrade_user_id: string | null; snaptrade_user_secret: string | null }>(
    `SELECT snaptrade_user_id, snaptrade_user_secret FROM users WHERE id = $1 LIMIT 1`,
    [userId],
  )
  const u = rows[0]
  if (!u?.snaptrade_user_id || !u.snaptrade_user_secret) return null
  return { snaptradeUserId: u.snaptrade_user_id, userSecret: decryptSecret(u.snaptrade_user_secret) }
}
