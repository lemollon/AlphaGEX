import { NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import {
  isCustomersDbConfigured,
  customerQuery,
  customerTransaction,
} from '@/lib/customers-db'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Executes the PII purge for account-deletion requests past their grace period.
 * This is the destructive half of /delete-account (see
 * app/api/account/deletion-request/route.ts, which only RECORDS a request).
 *
 * GET  — dry run. Exactly who would be purged, and who is blocked and why.
 * POST — apply. Irreversible.
 *
 * ── Two deliberate deviations from the other /api/ops routes ────────────────
 *
 * 1. NO `isPublicMode()` BYPASS. Every other ops route opens up when
 *    IRONFORGE_PUBLIC_MODE is true. Inheriting that here would mean a single
 *    env var turns an unauthenticated mass-anonymise loose on the customer
 *    table. An operator session is required unconditionally.
 *
 * 2. SHIPS DISARMED. POST refuses unless ACCOUNT_PURGE_ENABLED === 'true'.
 *    The dry run works regardless, so the safe half needs no ceremony and the
 *    destructive half cannot fire because someone guessed a URL.
 *
 * The users row is ANONYMISED, never deleted: ~20 tables carry
 * user_id REFERENCES users(id), and those records (trades, enrollments, legal
 * acceptances, the audit log) are exactly what /delete-account promises to keep
 * in de-identified form. Severing the identity is the deletion.
 */

/** Mirrors the request route. Allowlist of settled states — a status invented later blocks. */
const SETTLED_STATUSES = ['closed', 'skipped'] as const
const GRACE_PERIOD_DAYS = 14

/**
 * Tables holding ONLY identifying data or credentials for a user. These rows are
 * destroyed outright rather than de-identified — there is no record-keeping
 * argument for retaining a push token or a half-used password-reset token.
 * Ordered so that children go before parents.
 */
const PII_ONLY_TABLES = [
  // notification_deliveries.push_device_id REFERENCES push_devices with no cascade,
  // so deliveries must go first.
  'notification_deliveries',
  'push_devices',
  'notification_prefs',
  'mobile_refresh_tokens',
  'email_verification_tokens',
  'password_reset_tokens',
  'oauth_states',
  // community_reactions.message_id cascades from community_messages, but a user's
  // reactions to OTHER people's messages are their own data, so delete them explicitly.
  'community_reactions',
  'community_messages',
  'community_presence',
] as const
// Deliberately NOT in the list above:
//   community_forge_posts — system-generated daily slots keyed by slot_key, not user
//     content. It has no user_id at all; a DELETE ... WHERE user_id would throw and
//     roll back the whole purge. It DOES hold a non-cascading FK into
//     community_messages, which is handled explicitly below.
//   community_moderation_events — the moderation history is worth keeping, but
//     message_excerpt is the user's own words, so that column is nulled instead.
//   community_message_reports / community_blocks — these have NO user_id column
//     (reporter_id, and blocker_id/blocked_id). Adding them to the list above would
//     throw on the first row and roll the whole purge back, exactly like
//     community_forge_posts. Both are handled explicitly below.

interface EligibleRow {
  request_id: string
  user_id: string
  requested_at: string
  email: string | null
  snaptrade_user_id: string | null
}

async function requireOperator() {
  // No isPublicMode() escape hatch here — see the header comment.
  const ops = await getSession()
  if (!ops.userId) {
    return NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 })
  }
  return null
}

async function eligible(): Promise<EligibleRow[]> {
  return customerQuery<EligibleRow>(
    `SELECT r.id AS request_id, r.user_id, r.requested_at, u.email, u.snaptrade_user_id
       FROM account_deletion_requests r
       JOIN users u ON u.id = r.user_id
      WHERE r.status = 'requested'
        AND r.requested_at <= now() - ($1::int * INTERVAL '1 day')
      ORDER BY r.requested_at ASC`,
    [GRACE_PERIOD_DAYS],
  )
}

/** Unsettled positions per candidate user. Re-checked at purge time, not trusted from request time. */
async function unsettledByUser(userIds: string[]): Promise<Map<string, number>> {
  const out = new Map<string, number>()
  if (userIds.length === 0) return out
  const rows = await customerQuery<{ user_id: string; n: string }>(
    `SELECT user_id, COUNT(*)::text AS n
       FROM customer_positions
      WHERE user_id = ANY($1::uuid[]) AND status <> ALL($2::text[])
      GROUP BY user_id`,
    [userIds, SETTLED_STATUSES as unknown as string[]],
  )
  for (const r of rows) out.set(r.user_id, Number(r.n))
  return out
}

export async function GET() {
  const blocked = await requireOperator()
  if (blocked) return blocked
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }

  const rows = await eligible()
  const unsettled = await unsettledByUser(rows.map((r) => r.user_id))
  return NextResponse.json({
    ok: true,
    dryRun: true,
    armed: process.env.ACCOUNT_PURGE_ENABLED === 'true',
    gracePeriodDays: GRACE_PERIOD_DAYS,
    eligible: rows.length,
    wouldPurge: rows.filter((r) => !unsettled.has(r.user_id)).length,
    blocked: rows.filter((r) => unsettled.has(r.user_id)).length,
    requests: rows.map((r) => ({
      requestId: r.request_id,
      userId: r.user_id,
      requestedAt: r.requested_at,
      // Shown so an operator can recognise the account before authorising an
      // irreversible action. This endpoint is operator-only.
      email: r.email,
      blockedBy: unsettled.has(r.user_id)
        ? `${unsettled.get(r.user_id)} unsettled position(s)`
        : null,
    })),
  })
}

export async function POST() {
  const blocked = await requireOperator()
  if (blocked) return blocked
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }
  if (process.env.ACCOUNT_PURGE_ENABLED !== 'true') {
    return NextResponse.json(
      {
        ok: false,
        error: 'disarmed',
        message:
          'Purge is disarmed. Set ACCOUNT_PURGE_ENABLED=true to enable. Run GET first to see what would be purged.',
      },
      { status: 409 },
    )
  }

  const rows = await eligible()
  const unsettled = await unsettledByUser(rows.map((r) => r.user_id))

  const purged: string[] = []
  const skipped: { userId: string; reason: string }[] = []

  for (const r of rows) {
    // Re-checked here, per user, immediately before destroying anything. State can
    // have moved in the 14 days since the request: a customer whose bot re-opened a
    // position must not be anonymised out from under live money.
    if (unsettled.has(r.user_id)) {
      skipped.push({ userId: r.user_id, reason: `${unsettled.get(r.user_id)} unsettled position(s)` })
      continue
    }

    // Delete at the processor BEFORE the local ids are nulled, or the handle needed
    // to do it is gone. Outside the transaction because it is a remote call: a DB
    // rollback cannot un-delete a SnapTrade user, so the ordering is chosen so the
    // failure mode is "still deleted remotely, retried locally" rather than an
    // orphaned remote record we can no longer address.
    if (isSnapTradeConfigured() && r.snaptrade_user_id) {
      try {
        await getSnapTrade().authentication.deleteSnapTradeUser({ userId: r.snaptrade_user_id })
      } catch (e) {
        skipped.push({
          userId: r.user_id,
          reason: `snaptrade delete failed: ${e instanceof Error ? e.message : String(e)}`,
        })
        continue
      }
    }

    try {
      await customerTransaction(async (q) => {
        // community_forge_posts.message_id -> community_messages(id) has NO cascade,
        // so a system forge post pointing at one of this user's messages would make
        // the delete below fail on a FK violation and roll the whole purge back.
        // Release the pointer first; the slot row itself is not user data.
        await q(
          `UPDATE community_forge_posts SET message_id = NULL
            WHERE message_id IN (SELECT id FROM community_messages WHERE user_id = $1)`,
          [r.user_id],
        )

        // UGC safety rows keyed by something other than user_id — deleted before
        // community_messages so nothing is left pointing at a vanished author.
        // Reports this user FILED are their own data. Reports ABOUT them ride the
        // ON DELETE CASCADE from community_messages, so they need no handling here.
        await q(`DELETE FROM community_message_reports WHERE reporter_id = $1`, [r.user_id])
        // Blocks go both ways: their own list, and their entry in other people's
        // lists — which is dead weight once every message of theirs is gone.
        await q(`DELETE FROM community_blocks WHERE blocker_id = $1 OR blocked_id = $1`, [r.user_id])

        for (const table of PII_ONLY_TABLES) {
          await q(`DELETE FROM ${table} WHERE user_id = $1`, [r.user_id])
        }

        // Keep the moderation record (abuse history is worth retaining) but drop the
        // quoted text, which is the user's own words.
        await q(
          `UPDATE community_moderation_events SET message_excerpt = NULL WHERE user_id = $1`,
          [r.user_id],
        )

        // Anonymise in place. NOT NULL columns get placeholders, not NULL. The email
        // placeholder embeds the user id so the UNIQUE index still holds across many
        // purged accounts, and uses .invalid (RFC 2606) so it can never be delivered
        // to or re-registered.
        await q(
          `UPDATE users
              SET first_name = 'Deleted',
                  last_name = 'User',
                  email = 'deleted+' || id::text || '@deleted.invalid',
                  phone = '',
                  state = '',
                  referral_code = NULL,
                  promo_code = NULL,
                  password_hash = 'PURGED:' || gen_random_uuid()::text,
                  snaptrade_user_id = NULL,
                  snaptrade_user_secret = NULL,
                  account_status = 'deleted',
                  email_verified = FALSE,
                  phone_verified = FALSE,
                  brokerage_connected = FALSE,
                  updated_at = now()
            WHERE id = $1`,
          [r.user_id],
        )

        // Strip request metadata too — the IP and user-agent that filed the request
        // are themselves personal data, and keeping them would undercut the purge.
        await q(
          `UPDATE account_deletion_requests
              SET status = 'purged', purged_at = now(),
                  requested_ip = NULL, requested_user_agent = NULL
            WHERE id = $1`,
          [r.request_id],
        )

        // The audit row records THAT the account was purged, deliberately with no
        // identifying content beyond the (now anonymised) user id.
        await q(
          `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'ACCOUNT_PURGED', $2)`,
          [r.user_id, JSON.stringify({ requestId: r.request_id })],
        )
      })
      purged.push(r.user_id)
    } catch (e) {
      skipped.push({
        userId: r.user_id,
        reason: `purge failed: ${e instanceof Error ? e.message : String(e)}`,
      })
    }
  }

  return NextResponse.json({ ok: true, purged: purged.length, skipped, purgedUserIds: purged })
}
