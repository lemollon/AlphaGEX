/**
 * Mobile refresh-token store — the revocable half of the token pair.
 *
 * The access token is stateless (mobile-token.ts) because the Edge middleware cannot
 * reach the database. Everything that must be *withdrawable* therefore lives here:
 * the refresh token itself, rotation, theft detection, and the epoch bump that kills
 * outstanding access tokens.
 *
 * Node runtime only (node:crypto + pg). Never import this from middleware.
 */

import { randomBytes, createHash } from 'crypto'
import {
  customerQuery,
  customerExecute,
  customerTransaction,
  isCustomersDbConfigured,
} from '@/lib/customers-db'
import { MOBILE_SESSION_POLICY } from '@/lib/auth/mobile-policy'
import { signAccessToken } from '@/lib/auth/mobile-token'

export interface DeviceContext {
  deviceId?: string | null
  platform?: string | null
  appVersion?: string | null
  userAgent?: string | null
}

export interface TokenPair {
  accessToken: string
  accessExpiresAt: string
  refreshToken: string
  refreshExpiresAt: string
}

export type RefreshFailure = 'invalid' | 'expired' | 'idle' | 'reuse' | 'unconfigured'

/** Only the sha256 hash is stored; the raw value exists solely in the app's keychain. */
function hashToken(raw: string): string {
  return createHash('sha256').update(raw).digest('hex')
}

function newRefreshToken(): { raw: string; hash: string } {
  const raw = randomBytes(32).toString('base64url')
  return { raw, hash: hashToken(raw) }
}

/** Current epoch for a user; 0 when the row is missing so callers behave predictably. */
export async function currentEpoch(userId: string): Promise<number> {
  const rows = await customerQuery<{ token_epoch: number }>(
    `SELECT token_epoch FROM users WHERE id = $1 LIMIT 1`,
    [userId],
  )
  return rows[0]?.token_epoch ?? 0
}

/**
 * Mint a fresh pair. `familyId` continues an existing rotation chain (refresh);
 * omit it to start a new one (login).
 */
export async function issueTokenPair(
  userId: string,
  ctx: DeviceContext = {},
  familyId?: string,
): Promise<TokenPair> {
  const now = Date.now()
  const epoch = await currentEpoch(userId)
  const { raw, hash } = newRefreshToken()
  const refreshExpires = new Date(now + MOBILE_SESSION_POLICY.refreshTtlSec * 1000)

  await customerExecute(
    `INSERT INTO mobile_refresh_tokens
       (user_id, family_id, token_hash, device_id, platform, app_version, user_agent, expires_at)
     VALUES ($1, COALESCE($2::uuid, gen_random_uuid()), $3, $4, $5, $6, $7, $8)`,
    [
      userId,
      familyId ?? null,
      hash,
      ctx.deviceId ?? null,
      ctx.platform ?? null,
      ctx.appVersion ?? null,
      (ctx.userAgent ?? '').slice(0, 300) || null,
      refreshExpires.toISOString(),
    ],
  )

  return {
    accessToken: await signAccessToken(userId, epoch, now),
    accessExpiresAt: new Date(now + MOBILE_SESSION_POLICY.accessTtlSec * 1000).toISOString(),
    refreshToken: raw,
    refreshExpiresAt: refreshExpires.toISOString(),
  }
}

interface StoredToken {
  id: string
  user_id: string
  family_id: string
  expires_at: string
  last_used_at: string
  revoked_at: string | null
  revoked_reason: string | null
}

/**
 * Single-use rotation with theft detection.
 *
 * Presenting a token already marked 'rotated' means two parties hold the same raw
 * value — the legitimate device and someone else. We cannot tell which is which, so
 * we revoke the entire family AND bump token_epoch (killing outstanding access
 * tokens), forcing a password re-login. Failing safe here is worth the logout.
 *
 * The whole check-and-swap runs in one transaction with SELECT ... FOR UPDATE so two
 * concurrent refreshes from the same device cannot both succeed.
 */
export async function rotateRefreshToken(
  rawRefresh: string,
  ctx: DeviceContext = {},
): Promise<TokenPair | { error: RefreshFailure }> {
  if (!isCustomersDbConfigured()) return { error: 'unconfigured' }
  if (!rawRefresh) return { error: 'invalid' }

  const hash = hashToken(rawRefresh)
  const now = Date.now()

  type RotateOutcome = { error: RefreshFailure } | { userId: string; familyId: string }

  const outcome = await customerTransaction<RotateOutcome>(async (run) => {
    const rows = (await run(
      `SELECT id, user_id, family_id, expires_at, last_used_at, revoked_at, revoked_reason
         FROM mobile_refresh_tokens
        WHERE token_hash = $1
        FOR UPDATE`,
      [hash],
    )) as unknown as StoredToken[]

    const row = rows?.[0]
    if (!row) return { error: 'invalid' as const }

    if (row.revoked_at) {
      // Already used (or already killed). If it was consumed by a legitimate
      // rotation, this presentation is a replay — burn the family.
      if (row.revoked_reason === 'rotated') {
        await run(
          `UPDATE mobile_refresh_tokens
              SET revoked_at = now(), revoked_reason = 'reuse_detected'
            WHERE family_id = $1 AND revoked_at IS NULL`,
          [row.family_id],
        )
        await run(`UPDATE users SET token_epoch = token_epoch + 1 WHERE id = $1`, [row.user_id])
        await run(
          `INSERT INTO audit_events (user_id, event_type, metadata)
           VALUES ($1, 'MOBILE_REFRESH_REUSE', $2)`,
          [row.user_id, JSON.stringify({ familyId: row.family_id })],
        )
        return { error: 'reuse' as const }
      }
      return { error: 'invalid' as const }
    }

    if (new Date(row.expires_at).getTime() <= now) return { error: 'expired' as const }

    // APP-010 inactivity timeout — dead even though the absolute expiry has not passed.
    const idleMs = now - new Date(row.last_used_at).getTime()
    if (idleMs > MOBILE_SESSION_POLICY.refreshIdleTtlSec * 1000) return { error: 'idle' as const }

    await run(
      `UPDATE mobile_refresh_tokens
          SET revoked_at = now(), revoked_reason = 'rotated', last_used_at = now()
        WHERE id = $1`,
      [row.id],
    )
    return { userId: row.user_id, familyId: row.family_id }
  })

  if ('error' in outcome) return outcome
  return issueTokenPair(outcome.userId, ctx, outcome.familyId)
}

/** Sign out one device. Idempotent, and never reveals whether the token existed. */
export async function revokeRefreshToken(rawRefresh: string, reason = 'logout'): Promise<void> {
  if (!rawRefresh || !isCustomersDbConfigured()) return
  await customerExecute(
    `UPDATE mobile_refresh_tokens
        SET revoked_at = now(), revoked_reason = $2
      WHERE token_hash = $1 AND revoked_at IS NULL`,
    [hashToken(rawRefresh), reason],
  )
}

/**
 * Sign out EVERY device and invalidate outstanding access tokens.
 * Called on password change/reset and on reuse detection.
 */
export async function revokeAllForUser(userId: string, reason: string): Promise<void> {
  if (!isCustomersDbConfigured()) return
  await customerTransaction(async (run) => {
    await run(
      `UPDATE mobile_refresh_tokens
          SET revoked_at = now(), revoked_reason = $2
        WHERE user_id = $1 AND revoked_at IS NULL`,
      [userId, reason],
    )
    // The epoch bump is what kills already-issued STATELESS access tokens.
    await run(`UPDATE users SET token_epoch = token_epoch + 1 WHERE id = $1`, [userId])
  })
}
