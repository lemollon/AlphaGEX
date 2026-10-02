/**
 * BLAZE Directional Chart — server-side data source for BlazeDirectionalChart.tsx.
 *
 * Used to proxy two alphagex-api endpoints (`/api/gex/SPY`, `/api/gex/SPY/levels`)
 * into one same-origin response. Both were deleted in a964d310 ("cleanup: focus
 * AlphaGEX on VALOR and crypto perpetuals") and 404 in production. Replaced with
 * the same Tradier-chain + TradingVolatility sources market-brief.ts uses — see
 * lib/gex-levels.ts. Never fabricates a value: anything unavailable is null.
 *
 * Response shape is what BlazeDirectionalChart.tsx consumes — kept stable except
 * `max_pain` and `mm_state`, which have no local replacement and are now always
 * null / 'UNKNOWN' rather than a stale/guessed number.
 *   {
 *     symbol, spot_price, vix, net_gex, call_gex, put_gex,
 *     call_wall, put_wall, flip_point, max_pain,
 *     regime, mm_state, rating,
 *     vix_is_estimated, data_date, timestamp,
 *     levels: { call_wall:{price,distance_pct}, put_wall:..., gamma_flip:..., max_pain:... }
 *   }
 */
import { NextRequest, NextResponse } from 'next/server'
import { fetchGexLevels, regimeFromNetGex } from '@/lib/gex-levels'
import { getTvMarketStructure } from '@/lib/gex/trading-volatility-client'
import { getQuote } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

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
function deriveRating(regime: string | null, spot: number | null, flip: number | null): string {
  if (!regime) return 'NEUTRAL'
  const isPos = regime.includes('POSITIVE')
  const isNeg = regime.includes('NEGATIVE')
  if (!isPos && !isNeg) return 'NEUTRAL'
  if (spot == null || flip == null) return isPos ? 'CAUTIOUS_BULLISH' : 'CAUTIOUS_BEARISH'
  const above = spot > flip
  if (isPos && above) return 'BULLISH'
  if (isPos && !above) return 'CAUTIOUS_BULLISH'
  if (isNeg && above) return 'CAUTIOUS_BEARISH'
  return 'BEARISH'
}

function pctFromSpot(level: number | null, spot: number | null): number | null {
  if (level == null || spot == null || spot === 0) return null
  return Math.round(((level - spot) / spot) * 10000) / 100
}

export async function GET(_req: NextRequest) {
  try {
    const [levels, tv, vixQuote] = await Promise.all([
      fetchGexLevels('SPY', 45),
      getTvMarketStructure('SPY'),
      getQuote('VIX'),
    ])

    const spot = levels.spot
    const flip = tv?.gammaFlipPrice && tv.gammaFlipPrice > 0 ? tv.gammaFlipPrice : null
    const regime = levels.net_gex != null ? regimeFromNetGex(levels.net_gex) : null

    return NextResponse.json({
      symbol: 'SPY',
      spot_price: spot,
      vix: vixQuote?.last ?? null,
      vix_is_estimated: false,
      net_gex: levels.net_gex,
      call_gex: levels.call_gex,
      put_gex: levels.put_gex,
      call_wall: levels.call_wall,
      put_wall: levels.put_wall,
      flip_point: flip,
      max_pain: null,
      regime,
      mm_state: 'UNKNOWN',
      rating: deriveRating(regime, spot, flip),
      data_date: null,
      timestamp: new Date().toISOString(),
      levels: {
        call_wall: { price: levels.call_wall, distance_pct: pctFromSpot(levels.call_wall, spot) },
        put_wall: { price: levels.put_wall, distance_pct: pctFromSpot(levels.put_wall, spot) },
        gamma_flip: { price: flip, distance_pct: pctFromSpot(flip, spot) },
        max_pain: { price: null, distance_pct: null },
      },
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 502 })
  }
}
