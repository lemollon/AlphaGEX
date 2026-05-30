/**
 * Volatility regime alerts feed.
 *
 *   GET /api/vol-alerts?status=active|all&limit=25
 *
 * Returns recorded vol-regime trigger alerts (written by the scanner). Active
 * alerts sort first, then by fired time descending. Never 500s the UI — on any
 * error it returns `{ alerts: [] }`.
 */
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'
import { type VolAlert } from '@/lib/volAlerts'
import { ensureVolAlertsTable } from '@/lib/volAlerts.server'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  try {
    await ensureVolAlertsTable()

    const sp = req.nextUrl.searchParams
    const statusParam = (sp.get('status') || 'all').toLowerCase()
    const status = statusParam === 'active' ? 'active' : 'all'

    let limit = parseInt(sp.get('limit') || '25', 10)
    if (!Number.isFinite(limit) || limit <= 0) limit = 25
    if (limit > 200) limit = 200

    const where = status === 'active' ? `WHERE status = 'active'` : ''
    // Active first, then most-recent activity (resolve time if resolved, else fired time).
    const rows = await query<VolAlert>(
      `SELECT id, signal_key, direction, status, headline, message, regime_label,
              vix, vvix,
              fired_at::text   AS fired_at,
              resolved_at::text AS resolved_at
         FROM vol_alerts
         ${where}
        ORDER BY (status = 'active') DESC,
                 COALESCE(resolved_at, fired_at) DESC
        LIMIT $1`,
      [limit],
    )

    return NextResponse.json({ alerts: rows })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[api/vol-alerts] ${msg}`)
    return NextResponse.json({ alerts: [] })
  }
}
