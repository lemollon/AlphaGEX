import { NextRequest, NextResponse } from 'next/server'
import { safeEqual } from '@/lib/auth/session'
import { upsertEmberTrade, upsertEmberStatus, type EmberTradeUpsert } from '@/lib/ember-trades'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/internal/ember/sync
 *
 * Server-to-server only — called by dev/meltup/ember/reflex_sync.py, never by
 * a browser. Auth is a shared secret (env EMBER_SYNC_SECRET) in the
 * `x-ember-sync-secret` header; an UNSET secret rejects every request (503,
 * never "accept anything" when the env var is missing — same fail-closed
 * convention as every other gate in this codebase).
 *
 * Body:
 *   {
 *     "trades": [{
 *       "source_ref": "SYMBOL|2026-10-05",   // REFLEX's own reflex_key(), unique
 *       "symbol": "SYMBOL",
 *       "opened_at": "2026-10-05T14:32:00Z" | null,
 *       "closed_at": "2026-10-05T19:58:00Z" | null,
 *       "legs": {...} | null,
 *       "qty": 10 | null,
 *       "entry_price": 12.34 | null,
 *       "exit_price": 12.90 | null,
 *       "pnl": 5.60 | null,
 *       "status": "open" | "closed"
 *     }],
 *     "status": {
 *       "state": "ok" | "blocked" | "error" | ...,
 *       "last_heartbeat": "2026-10-05T19:58:05Z",
 *       "open_positions": [...] | null
 *     }
 *   }
 *
 * Upserts each trade by `source_ref` (ON CONFLICT DO UPDATE — see
 * lib/ember-trades.ts) and, if `status` is present, the single ember_status
 * row. Every trade is validated independently; a bad row is reported in
 * `skipped` rather than failing the whole batch (a single malformed row must
 * never block the heartbeat or the rest of the batch).
 */
function isTradeStatus(v: unknown): v is string {
  return typeof v === 'string' && v.length > 0
}

export async function POST(req: NextRequest) {
  const expected = process.env.EMBER_SYNC_SECRET
  if (!expected) {
    return NextResponse.json({ ok: false, error: 'EMBER_SYNC_SECRET is not configured' }, { status: 503 })
  }
  const got = req.headers.get('x-ember-sync-secret')
  if (!got || !safeEqual(got, expected)) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  let body: Record<string, unknown>
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ ok: false, error: 'invalid JSON body' }, { status: 400 })
  }

  const trades = Array.isArray(body.trades) ? (body.trades as Array<Record<string, unknown>>) : []
  let upserted = 0
  const skipped: Array<{ index: number; reason: string }> = []

  for (let i = 0; i < trades.length; i++) {
    const t = trades[i]
    const sourceRef = typeof t.source_ref === 'string' ? t.source_ref.trim() : ''
    const symbol = typeof t.symbol === 'string' ? t.symbol.trim() : ''
    const status = t.status
    if (!sourceRef) { skipped.push({ index: i, reason: 'missing source_ref' }); continue }
    if (!symbol) { skipped.push({ index: i, reason: 'missing symbol' }); continue }
    if (!isTradeStatus(status)) { skipped.push({ index: i, reason: 'missing status' }); continue }

    const trade: EmberTradeUpsert = {
      sourceRef,
      symbol,
      status,
      openedAt: typeof t.opened_at === 'string' ? t.opened_at : null,
      closedAt: typeof t.closed_at === 'string' ? t.closed_at : null,
      legs: t.legs ?? null,
      qty: typeof t.qty === 'number' ? t.qty : null,
      entryPrice: typeof t.entry_price === 'number' ? t.entry_price : null,
      exitPrice: typeof t.exit_price === 'number' ? t.exit_price : null,
      pnl: typeof t.pnl === 'number' ? t.pnl : null,
    }
    try {
      await upsertEmberTrade(trade)
      upserted++
    } catch (e) {
      skipped.push({ index: i, reason: e instanceof Error ? e.message : 'upsert failed' })
    }
  }

  const statusBody = body.status as Record<string, unknown> | undefined
  let statusSynced = false
  if (statusBody && typeof statusBody === 'object') {
    try {
      await upsertEmberStatus({
        state: typeof statusBody.state === 'string' ? statusBody.state : null,
        lastHeartbeat: typeof statusBody.last_heartbeat === 'string' ? statusBody.last_heartbeat : null,
        openPositions: statusBody.open_positions ?? null,
      })
      statusSynced = true
    } catch (e) {
      return NextResponse.json(
        { ok: false, error: `status upsert failed: ${e instanceof Error ? e.message : String(e)}`, upserted, skipped },
        { status: 500 },
      )
    }
  }

  return NextResponse.json({ ok: true, upserted, skipped, statusSynced })
}
