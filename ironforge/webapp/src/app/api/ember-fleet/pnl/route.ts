/**
 * EMBER (Robinhood fleet) realized P&L — same-origin proxy to the
 * spreadworks-backend Render service (avoids browser CORS).
 *
 *   GET https://spreadworks-backend.onrender.com/api/spreadworks/ember/pnl
 *
 * This is the Robinhood fleet on account 570892331 (call_diag/night_shift/
 * divhike/xsp_flow/astra3_live/tv_book/spike) — a completely different
 * product from the backtester proxied at /api/ember/[...path]. Mirrors that
 * proxy's pattern (and the volatility-advisor proxy's single-GET shape).
 * Response shape is the raw backend aggregate_pnl() payload — see
 * spreadworks/backend/ember/pnl.py.
 */
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const SPREADWORKS_BASE =
  process.env.SPREADWORKS_BACKEND_URL || 'https://spreadworks-backend.onrender.com'
const FETCH_TIMEOUT_MS = 10_000

export async function GET() {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  try {
    const url = `${SPREADWORKS_BASE.replace(/\/$/, '')}/api/spreadworks/ember/pnl`
    // no-store: this is live realized P&L, never cache a stale $ total.
    const resp = await fetch(url, { signal: controller.signal, cache: 'no-store' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const payload = await resp.json()
    return NextResponse.json(payload)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 502 })
  } finally {
    clearTimeout(timer)
  }
}
