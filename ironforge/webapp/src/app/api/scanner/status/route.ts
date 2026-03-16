import { NextResponse } from 'next/server'
import { dbQuery } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET /api/scanner/status
 *
 * Consolidated scanner health endpoint — returns all bots' heartbeats,
 * scan counts, last errors, and staleness in a single call.
 *
 * Use this for external monitoring / uptime checks:
 *   - Poll every 30-60s
 *   - Alert if any bot's last_heartbeat > 5 minutes old during market hours
 *   - Alert if overall status is "degraded" or "down"
 */
export async function GET() {
  try {
    // All heartbeats in one query
    const heartbeats = await dbQuery(`
      SELECT bot_name, last_heartbeat, status, scan_count, details
      FROM bot_heartbeats
      ORDER BY bot_name
    `)

    // Latest error per bot (last 1 hour)
    const errors = await dbQuery(`
      SELECT DISTINCT ON (bot_name) bot_name, log_time, message
      FROM (
        SELECT 'flame' as bot_name, log_time, message FROM flame_logs
          WHERE level = 'ERROR' AND log_time > NOW() - INTERVAL '1 hour'
        UNION ALL
        SELECT 'spark', log_time, message FROM spark_logs
          WHERE level = 'ERROR' AND log_time > NOW() - INTERVAL '1 hour'
        UNION ALL
        SELECT 'inferno', log_time, message FROM inferno_logs
          WHERE level = 'ERROR' AND log_time > NOW() - INTERVAL '1 hour'
      ) combined
      ORDER BY bot_name, log_time DESC
    `)

    const errorMap: Record<string, { time: string; message: string }> = {}
    for (const e of errors) {
      errorMap[e.bot_name] = { time: e.log_time, message: e.message }
    }

    const now = Date.now()
    const STALE_THRESHOLD_MS = 5 * 60 * 1000 // 5 minutes

    const bots = heartbeats.map((hb: any) => {
      const lastBeat = hb.last_heartbeat ? new Date(hb.last_heartbeat).getTime() : 0
      const ageMs = lastBeat ? now - lastBeat : null
      const ageMins = ageMs != null ? Math.round(ageMs / 60_000 * 10) / 10 : null
      const isStale = ageMs != null ? ageMs > STALE_THRESHOLD_MS : true
      const name = (hb.bot_name || '').toLowerCase()

      let details: Record<string, any> = {}
      try { details = typeof hb.details === 'string' ? JSON.parse(hb.details) : (hb.details || {}) } catch { /* */ }

      return {
        bot: name,
        status: hb.status || 'unknown',
        last_heartbeat: hb.last_heartbeat,
        age_minutes: ageMins,
        is_stale: isStale,
        scan_count: hb.scan_count || 0,
        spot_price: details.spot ?? null,
        vix: details.vix ?? null,
        last_action: details.action ?? null,
        last_reason: details.reason ?? null,
        last_error: errorMap[name] ?? null,
      }
    })

    // Determine if we expect the scanner to be active (market hours approximation)
    const ctNow = new Date(now)
    // Simple CT approximation — real CT uses America/Chicago but this is close enough for health
    const utcHour = ctNow.getUTCHours()
    const utcDay = ctNow.getUTCDay()
    const isWeekday = utcDay >= 1 && utcDay <= 5
    // CT = UTC-5 (CST) or UTC-6 (CDT). Market 8:30-15:00 CT = ~13:30-20:00 UTC (CDT) or 14:30-21:00 (CST)
    const roughlyMarketHours = isWeekday && utcHour >= 13 && utcHour < 21

    const anyStale = bots.some((b: any) => b.is_stale)
    const anyError = bots.some((b: any) => b.status === 'error')
    const noBots = bots.length === 0

    let overall: string
    if (noBots) overall = 'down'
    else if (anyError) overall = 'degraded'
    else if (roughlyMarketHours && anyStale) overall = 'degraded'
    else overall = 'ok'

    return NextResponse.json({
      status: overall,
      market_likely_open: roughlyMarketHours,
      stale_threshold_minutes: STALE_THRESHOLD_MS / 60_000,
      bots,
      checked_at: new Date().toISOString(),
    }, { status: overall === 'ok' ? 200 : 503 })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json(
      { status: 'down', error: msg, bots: [], checked_at: new Date().toISOString() },
      { status: 503 },
    )
  }
}
