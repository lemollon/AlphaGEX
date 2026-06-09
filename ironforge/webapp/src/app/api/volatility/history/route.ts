/**
 * Volatility Regime Advisor history — same-origin proxy to the AlphaGEX backend.
 *
 *   GET https://alphagex-api.onrender.com/api/vix/regime-advisor/history?days=N
 *
 * Mirrors the BLAZE gex-context proxy pattern (avoids browser CORS).
 * `days` query param defaults to 180.
 */
import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const ALPHAGEX_BASE = process.env.ALPHAGEX_API_BASE || 'https://alphagex-api.onrender.com'
const FETCH_TIMEOUT_MS = 5_000

export async function GET(request: NextRequest) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  try {
    const daysParam = request.nextUrl.searchParams.get('days')
    const days = daysParam && Number.isFinite(Number(daysParam)) ? Number(daysParam) : 180
    const url = `${ALPHAGEX_BASE.replace(/\/$/, '')}/api/vix/regime-advisor/history?days=${days}`
    // no-store: keep the proxy from freezing a stale upstream response in Next's data cache.
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
