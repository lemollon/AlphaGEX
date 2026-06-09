/**
 * Volatility Regime Advisor — same-origin proxy to the AlphaGEX backend.
 *
 *   GET https://alphagex-api.onrender.com/api/vix/regime-advisor
 *
 * Mirrors the BLAZE gex-context proxy pattern (avoids browser CORS).
 * Response shape is the raw backend AdvisorPayload — see src/lib/volatility.ts.
 */
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const ALPHAGEX_BASE = process.env.ALPHAGEX_API_BASE || 'https://alphagex-api.onrender.com'
const FETCH_TIMEOUT_MS = 5_000

export async function GET() {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  try {
    const url = `${ALPHAGEX_BASE.replace(/\/$/, '')}/api/vix/regime-advisor`
    // no-store: the upstream regime feed updates intraday; without this Next's
    // data cache freezes the first response and the UI shows a stale as_of/VIX.
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
