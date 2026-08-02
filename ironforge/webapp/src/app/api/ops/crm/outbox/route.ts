import { NextRequest, NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { hasValidServiceToken } from '@/lib/auth/session'
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { drainCrmOutbox, replayCrmDeadLetters } from '@/lib/crm/outbox'

/**
 * CRM outbox operations.
 *
 * GET  — queue health: counts by status plus the most recent dead-letters and their errors.
 *        This is the reconciliation view for AC-CRM-009/010.
 * POST {"action":"drain"}  — deliver due events now.
 * POST {"action":"replay"} — put dead-lettered events back in the queue. Optional `eventId`
 *        replays exactly one; otherwise the oldest `limit` (default 100).
 *
 * Why a manual drain exists at all: the background drain is registered inside
 * startScannerLocked(), which only runs where SCANNER_ENABLED=true and the advisory lock is
 * held. If the scanner is not running on the service that owns CUSTOMERS_DATABASE_URL, this
 * endpoint (or a Render cron hitting it with the service token) is the delivery path.
 *
 * Replay is safe to repeat: delivery upserts on a unique matching attribute, so re-running an
 * event converges on the same record rather than duplicating it (spec §10).
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

async function gate(req: NextRequest): Promise<NextResponse | null> {
  const ops = await getSession()
  const viaToken = hasValidServiceToken(req.headers.get('x-ironforge-service'))
  if (!ops.userId && !viaToken) {
    return NextResponse.json({ ok: false, error: 'Operator session or service token required.' }, { status: 401 })
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'CUSTOMERS_DATABASE_URL is not set.' }, { status: 503 })
  }
  return null
}

export async function GET(req: NextRequest) {
  const blocked = await gate(req)
  if (blocked) return blocked

  const counts = await customerQuery<{ status: string; n: string }>(
    `SELECT status, count(*)::text AS n FROM crm_outbox GROUP BY status`,
  )
  const deadLetters = await customerQuery<Record<string, unknown>>(
    `SELECT event_id, event_type, attempts, last_error, created_at, updated_at
       FROM crm_outbox
      WHERE status = 'failed'
      ORDER BY updated_at DESC
      LIMIT 25`,
  )
  const oldestPending = await customerQuery<{ event_id: string; created_at: string }>(
    `SELECT event_id, created_at FROM crm_outbox
      WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1`,
  )

  return NextResponse.json({
    ok: true,
    counts: Object.fromEntries(counts.map((c) => [c.status, Number(c.n)])),
    oldestPending: oldestPending[0] ?? null,
    deadLetters,
  })
}

export async function POST(req: NextRequest) {
  const blocked = await gate(req)
  if (blocked) return blocked

  const body = (await req.json().catch(() => ({}))) as { action?: string; eventId?: string; limit?: number }

  if (body.action === 'replay') {
    const result = await replayCrmDeadLetters(body.limit ?? 100, body.eventId)
    return NextResponse.json({ ok: true, action: 'replay', ...result })
  }

  if (body.action === 'drain' || body.action === undefined) {
    const result = await drainCrmOutbox(body.limit ?? 50)
    return NextResponse.json({ ok: true, action: 'drain', ...result })
  }

  return NextResponse.json(
    { ok: false, error: `unknown action "${body.action}" — expected "drain" or "replay".` },
    { status: 400 },
  )
}
