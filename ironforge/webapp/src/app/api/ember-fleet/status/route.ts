/**
 * EMBER (Robinhood fleet) status — same-origin proxy to the
 * spreadworks-backend Render service (avoids browser CORS).
 *
 *   GET https://spreadworks-backend.onrender.com/api/spreadworks/ember/status
 *
 * See pnl/route.ts for why this is a separate proxy namespace from
 * /api/ember/[...path] (the unrelated backtester).
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
    const url = `${SPREADWORKS_BASE.replace(/\/$/, '')}/api/spreadworks/ember/status`
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
