import { NextRequest, NextResponse } from 'next/server'
import { createHash, createHmac } from 'crypto'
import { isCustomersDbConfigured, customerExecute } from '@/lib/customers-db'
import { snaptradeCanonicalJson, snaptradeSignatureValid } from '@/lib/snaptrade-webhook'

/**
 * TEMPORARY diagnostics for webhook 401s — logs enough to distinguish "wrong consumer key in
 * env" from "canonicalization mismatch" WITHOUT ever logging a secret: env client id (public),
 * an 8-char sha256 fingerprint of the consumer key, and 6-char prefixes of the received vs
 * computed signatures. Remove once the SnapTrade dashboard test passes.
 */
function logWebhook401(body: Record<string, unknown>, sigHeader: string | null) {
  try {
    const key = process.env.SNAPTRADE_CONSUMER_KEY ?? ''
    const keyFp = key ? createHash('sha256').update(key).digest('hex').slice(0, 8) : 'UNSET'
    const computed = key
      ? createHmac('sha256', key).update(snaptradeCanonicalJson(body)).digest('base64')
      : 'n/a'
    console.error('[brokerage/webhook] 401 diag', {
      envClientId: process.env.SNAPTRADE_CLIENT_ID ?? 'UNSET',
      consumerKeyFp: keyFp,
      consumerKeyLen: key.length,
      sigHeaderPresent: sigHeader != null,
      sigHeaderLen: sigHeader?.length ?? 0,
      sigHeaderPrefix: sigHeader?.slice(0, 6) ?? '',
      computedPrefix: computed.slice(0, 6),
      bodyKeys: Object.keys(body).sort().join(','),
    })
  } catch (e) {
    console.error('[brokerage/webhook] 401 diag failed', e)
  }
}

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * SnapTrade webhook listener (no session). Verified two ways, either passes:
 *  - Signature header = HMAC-SHA256(canonical JSON body, consumer key), base64 — the current
 *    SnapTrade mechanism ("webhook secrets are deprecated");
 *  - legacy body.webhookSecret === SNAPTRADE_WEBHOOK_SECRET, kept for old listeners.
 * Keeps brokerage_connections.status in sync as connections are added/broken/removed and touches
 * last_synced_at on holdings updates. Always 200s after a valid signature/secret so SnapTrade does
 * not retry-storm; 401 only when both checks fail. Public path (self-guarded).
 */
export async function POST(req: NextRequest) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>

  const legacySecret = process.env.SNAPTRADE_WEBHOOK_SECRET
  const legacyOk = Boolean(legacySecret) && body.webhookSecret === legacySecret
  if (!legacyOk && !snaptradeSignatureValid(body, req.headers.get('signature'))) {
    logWebhook401(body, req.headers.get('signature'))
    return NextResponse.json({ ok: false }, { status: 401 })
  }
  if (!isCustomersDbConfigured()) return NextResponse.json({ ok: true })

  const eventType = String(body.eventType ?? body.type ?? '')
  const snaptradeUserId = body.userId ? String(body.userId) : null
  const authorizationId = body.brokerageAuthorizationId ? String(body.brokerageAuthorizationId) : null

  // Map SnapTrade events → our connection status.
  const statusByEvent: Record<string, string> = {
    CONNECTION_ADDED: 'active',
    CONNECTION_UPDATED: 'active',
    CONNECTION_FIXED: 'active',
    CONNECTION_BROKEN: 'disabled',
    CONNECTION_DELETED: 'removed',
    CONNECTION_REMOVED: 'removed',
  }

  try {
    if (eventType === 'ACCOUNT_HOLDINGS_UPDATED' && snaptradeUserId) {
      await customerExecute(
        `UPDATE brokerage_connections SET last_synced_at = now(), updated_at = now()
           WHERE user_id = (SELECT id FROM users WHERE snaptrade_user_id = $1)`,
        [snaptradeUserId],
      )
    } else if (statusByEvent[eventType] && snaptradeUserId) {
      const newStatus = statusByEvent[eventType]
      await customerExecute(
        `UPDATE brokerage_connections SET status = $3, updated_at = now()
           WHERE user_id = (SELECT id FROM users WHERE snaptrade_user_id = $1)
             AND ($2::text IS NULL OR authorization_id = $2)`,
        [snaptradeUserId, authorizationId, newStatus],
      )
      // If a connection broke/was removed and none remain active, clear the user flag.
      await customerExecute(
        `UPDATE users SET brokerage_connected = FALSE, updated_at = now()
           WHERE snaptrade_user_id = $1
             AND NOT EXISTS (
               SELECT 1 FROM brokerage_connections bc
                WHERE bc.user_id = users.id AND bc.status = 'active')`,
        [snaptradeUserId],
      )
    }
  } catch (e) {
    console.error('[brokerage/webhook] update failed:', eventType, e)
    // Still 200 — SnapTrade retries are not helpful for our internal write failures.
  }

  return NextResponse.json({ ok: true })
}
