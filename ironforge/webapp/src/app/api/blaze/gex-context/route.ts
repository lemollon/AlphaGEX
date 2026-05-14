/**
 * BLAZE Directional Chart — server-side proxy that combines two alphagex-api
 * endpoints into one same-origin response (avoids browser CORS).
 *
 *   GET https://alphagex-api.onrender.com/api/gex/SPY        (overview)
 *   GET https://alphagex-api.onrender.com/api/gex/SPY/levels (named levels)
 *
 * Response shape is what BlazeDirectionalChart.tsx consumes — keep it stable:
 *   {
 *     symbol: 'SPY',
 *     spot_price, vix, net_gex, call_gex, put_gex,
 *     call_wall, put_wall, flip_point, max_pain,
 *     regime, mm_state, rating,
 *     vix_is_estimated, data_date, timestamp,
 *     levels: { call_wall:{price,distance_pct}, put_wall:..., gamma_flip:..., max_pain:... }
 *   }
 */
import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const ALPHAGEX_BASE = process.env.ALPHAGEX_API_BASE || 'https://alphagex-api.onrender.com'
const FETCH_TIMEOUT_MS = 5_000

async function fetchJsonWithTimeout(url: string): Promise<any> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  try {
    const resp = await fetch(url, { signal: controller.signal })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return await resp.json()
  } finally {
    clearTimeout(timer)
  }
}

/**
 * Map (regime, spot vs flip) → a human-readable "rating" tag, mirroring the
 * AlphaGEX /gex/profile dashboard's top-right RATING badge.
 *
 *   POSITIVE regime + spot > flip → BULLISH (long-gamma stability above flip)
 *   POSITIVE regime + spot < flip → CAUTIOUS_BULLISH
 *   NEGATIVE regime + spot > flip → CAUTIOUS_BEARISH
 *   NEGATIVE regime + spot < flip → BEARISH (short-gamma instability)
 *   NEUTRAL                       → NEUTRAL
 */
function deriveRating(regime: string, spot: number, flip: number): string {
  const isPos = regime.includes('POSITIVE')
  const isNeg = regime.includes('NEGATIVE')
  if (!isPos && !isNeg) return 'NEUTRAL'
  const above = spot > flip
  if (isPos && above) return 'BULLISH'
  if (isPos && !above) return 'CAUTIOUS_BULLISH'
  if (isNeg && above) return 'CAUTIOUS_BEARISH'
  return 'BEARISH'
}

export async function GET(_req: NextRequest) {
  try {
    const [overview, levels] = await Promise.all([
      fetchJsonWithTimeout(`${ALPHAGEX_BASE.replace(/\/$/, '')}/api/gex/SPY`),
      fetchJsonWithTimeout(`${ALPHAGEX_BASE.replace(/\/$/, '')}/api/gex/SPY/levels`),
    ])

    const od = overview?.data || {}
    const ld = levels?.data || {}
    const spot = Number(od.spot_price ?? ld.spot_price ?? 0)
    const flip = Number(od.flip_point ?? ld?.levels?.gamma_flip?.price ?? 0)
    const regime = String(od.regime || 'NEUTRAL')

    return NextResponse.json({
      symbol: od.symbol || 'SPY',
      spot_price: spot,
      vix: Number(od.vix ?? 0),
      vix_is_estimated: Boolean(od.vix_is_estimated),
      net_gex: Number(od.net_gex ?? 0),
      call_gex: Number(od.call_gex ?? 0),
      put_gex: Number(od.put_gex ?? 0),
      call_wall: Number(od.call_wall ?? ld?.levels?.call_wall?.price ?? 0),
      put_wall: Number(od.put_wall ?? ld?.levels?.put_wall?.price ?? 0),
      flip_point: flip,
      max_pain: Number(od.max_pain ?? ld?.levels?.max_pain?.price ?? 0),
      regime,
      mm_state: String(od.mm_state || 'UNKNOWN'),
      rating: deriveRating(regime, spot, flip),
      data_date: od.data_date || null,
      timestamp: od.timestamp || null,
      levels: ld?.levels || null,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 502 })
  }
}
