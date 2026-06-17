/**
 * Volatility signal escalation ladder.
 *
 *   GET /api/vol-alerts/ladder?events=20
 *
 * Returns the CURRENT per-signal ladder state (idle/watch/tripped/confirmed) plus
 * the most recent transition events. This is the never-drop observation layer that
 * sits underneath the confirmed `vol_alerts` feed — a signal that tripped its
 * trigger but never debounce-confirmed still shows up here. Never 500s the UI: on
 * any error it returns empty arrays.
 */
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'
import { ensureSignalLadderTables } from '@/lib/volAlerts.server'

export const dynamic = 'force-dynamic'

interface StateRow {
  signal_key: string
  state: string
  direction: string | null
  value: number | null
  proximity: number | null
  since: string | null
  updated_at: string | null
}

interface EventRow {
  id: number
  signal_key: string
  direction: string | null
  from_state: string
  to_state: string
  value: number | null
  proximity: number | null
  vix: number | null
  vvix: number | null
  vix3m: number | null
  regime_label: string | null
  created_at: string | null
}

export async function GET(req: NextRequest) {
  try {
    await ensureSignalLadderTables()

    let eventLimit = parseInt(req.nextUrl.searchParams.get('events') || '20', 10)
    if (!Number.isFinite(eventLimit) || eventLimit <= 0) eventLimit = 20
    if (eventLimit > 200) eventLimit = 200

    const states = await query<StateRow>(
      `SELECT signal_key, state, direction, value, proximity,
              since::text      AS since,
              updated_at::text AS updated_at
         FROM vol_signal_state
        ORDER BY signal_key`,
    )

    const events = await query<EventRow>(
      `SELECT id, signal_key, direction, from_state, to_state, value, proximity,
              vix, vvix, vix3m, regime_label,
              created_at::text AS created_at
         FROM vol_signal_events
        ORDER BY created_at DESC
        LIMIT $1`,
      [eventLimit],
    )

    return NextResponse.json({ states, events })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[api/vol-alerts/ladder] ${msg}`)
    return NextResponse.json({ states: [], events: [] })
  }
}
