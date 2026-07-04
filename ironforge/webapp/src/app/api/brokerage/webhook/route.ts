import { NextRequest, NextResponse } from 'next/server'
import { createHash, createHmac } from 'crypto'
import { isCustomersDbConfigured, customerExecute } from '@/lib/customers-db'
import {
  snaptradeCanonicalJson,
  snaptradeCanonicalJsonSpaced,
  snaptradeRawSignatureValid,
  snaptradeSignatureValid,
} from '@/lib/snaptrade-webhook'

/**
 * TEMPORARY diagnostics for webhook 401s — logs enough to distinguish "wrong consumer key in
 * env" from "canonicalization mismatch" WITHOUT ever logging a secret: env client id (public),
 * an 8-char sha256 fingerprint of the consumer key, and 6-char prefixes of the received vs
 * computed signatures. Remove once the SnapTrade dashboard test passes.
 */
function omit(obj: Record<string, unknown>, k: string): Record<string, unknown> {
  const out = { ...obj }
  delete out[k]
  return out
}

function logWebhook401(body: Record<string, unknown>, sigHeader: string | null, raw: string) {
  try {
    const key = process.env.SNAPTRADE_CONSUMER_KEY ?? ''
    const keyFp = key ? createHash('sha256').update(key).digest('hex').slice(0, 8) : 'UNSET'
    const h = (content: string) =>
      key ? createHmac('sha256', key).update(content).digest('base64').slice(0, 6) : 'n/a'
    const noSecret = { ...body }
    delete noSecret.webhookSecret
    console.error('[brokerage/webhook] 401 diag', {
      envClientId: process.env.SNAPTRADE_CLIENT_ID ?? 'UNSET',
      consumerKeyFp: keyFp,
      consumerKeyLen: key.length,
      sigHeaderPrefix: sigHeader?.slice(0, 6) ?? 'MISSING',
      canonPrefix: h(snaptradeCanonicalJson(body)),
      rawPrefix: h(raw),
      canonNoSecretPrefix: h(snaptradeCanonicalJson(noSecret)),
      // serialization-variant matrix: spaced = Python json.dumps default separators
      spacedPrefix: h(snaptradeCanonicalJsonSpaced(body)),
      spacedNoSecretPrefix: h(snaptradeCanonicalJsonSpaced(noSecret)),
      canonNoTypoPrefix: h(snaptradeCanonicalJson(omit(body, 'webookId'))),
      spacedNoTypoPrefix: h(snaptradeCanonicalJsonSpaced(omit(body, 'webookId'))),
      canonNoIdPrefix: h(snaptradeCanonicalJson(omit(body, 'webhookId'))),
      wsKeyRawPrefix: typeof body.webhookSecret === 'string'
        ? createHmac('sha256', body.webhookSecret).update(raw).digest('base64').slice(0, 6)
        : 'n/a',
      rawLen: raw.length,
      canonLen: snaptradeCanonicalJson(body).length,
      fieldTypes: Object.keys(body)
        .sort()
        .map((k) => `${k}:${typeof body[k]}`)
        .join(','),
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
  const raw = await req.text().catch(() => '')
  let body: Record<string, unknown> = {}
  try {
    body = JSON.parse(raw) as Record<string, unknown>
  } catch {
    /* leave {} */
  }

  const legacySecret = process.env.SNAPTRADE_WEBHOOK_SECRET
  const legacyOk = Boolean(legacySecret) && body.webhookSecret === legacySecret
  const header = req.headers.get('signature')
  // SnapTrade docs say the signature covers the canonical (sorted/compact) JSON, but accept the
  // raw wire bytes too — equivalent when their sender serializes the same way, and robust when
  // it doesn't (numbers/key order survive without re-serialization drift).
  const sigOk =
    snaptradeSignatureValid(body, header) || snaptradeRawSignatureValid(raw, header)
  if (!legacyOk && !sigOk) {
    logWebhook401(body, header, raw)
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
