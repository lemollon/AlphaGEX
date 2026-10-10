/**
 * BLAZE — GEX feed client. Used to fetch
 * https://alphagex-api.onrender.com/api/gex/SPY, but that route was deleted
 * in a964d310 ("cleanup: focus AlphaGEX on VALOR and crypto perpetuals") and
 * every call has 404'd since. Now computes dealer gamma directly from the
 * live Tradier option chain via lib/gex-levels.ts — the same helper
 * market-brief.ts uses (fix/market-brief-gex-source, PR #3073) — plus a
 * TradingVolatility gamma-flip read. Mirrors trading/helios/gex_client.py in
 * shape only; the data path is now local, not a call to alphagex-api.
 *
 * Field mapping (GexSnapshot <- gex-levels.ts / trading-volatility-client.ts / Tradier):
 *   symbol              <- input param
 *   spot                <- fetchGexLevels().spot (Tradier quote). No live spot ⇒ THROW
 *                          (GexFetchError) rather than fabricate 0 — every downstream
 *                          setup keys strikes off spot, so this is the one field that
 *                          must skip the whole cycle, exactly like the old 404 did.
 *   net_gex             <- fetchGexLevels().net_gex; null (no OI/gamma on either side)
 *                          -> 0, which regimeFromNetGex() reads as NEUTRAL. wall_fade
 *                          and wall_break both require a POSITIVE/NEGATIVE regime, so
 *                          NEUTRAL is a clean skip; flip_cross compares net_gex sign
 *                          across two snapshots, so 0 never satisfies the sign-flip check.
 *   call_wall/put_wall  <- fetchGexLevels().call_wall/put_wall; null (no OI on that
 *                          side) -> 0, which setups.ts already treats as "no wall"
 *                          (every wall check there is guarded by `cw > 0` / `pw > 0`).
 *   flip_point          <- getTvMarketStructure().gammaFlipPrice; no TV API key or the
 *                          feed is unreachable -> 0, which flip_cross already treats as
 *                          "no flip" (`if (flip <= 0) return null`).
 *   vix                 <- Tradier VIX quote; missing/non-positive -> 0 (feeds sigma
 *                          below to 0; only used for logging otherwise).
 *   regime              <- regimeFromNetGex(net_gex) (imported from gex-levels.ts).
 *   sigma_1d_band_width <- spot * (vix/100) * sqrt(1/252); spot or vix missing -> 0,
 *                          and wall_fade/wall_break both require `sigma > 0`, so a 0
 *                          sigma is a clean skip, never a fabricated band.
 *   snapshot_at         <- Date.now() — this is a live compute now, not a cached
 *                          upstream timestamp, so there is no staleness to detect.
 *
 * BLAZE/FLARE never read max_pain or mm_state (grep confirms no reference in
 * setups.ts/scanner.ts/executor.ts), so there is nothing to null out for those.
 *
 * Never fabricates: every degraded field above resolves to the exact "off"
 * value the setups already treat as absent, never a stale or guessed number.
 * GexStaleError is kept for the scanner.ts catch blocks that still reference
 * it, but a live compute has no upstream snapshot to go stale, so it is no
 * longer thrown from here.
 */
import { GexSnapshot } from './types'
import { fetchGexLevels, regimeFromNetGex } from '../gex-levels'
import { getTvMarketStructure } from '../gex/trading-volatility-client'
import { getQuote } from '../tradier'

const TRADING_DAYS_PER_YEAR = 252.0
const SQRT_INV_TRADING_DAYS = Math.sqrt(1.0 / TRADING_DAYS_PER_YEAR)

export class GexStaleError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'GexStaleError'
  }
}

export class GexFetchError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'GexFetchError'
  }
}

/**
 * @param symbol the underlying to compute GEX for.
 * @param _staleMaxSeconds unused now — kept for call-site compatibility
 *   (scanner.ts passes DEFAULT_BLAZE_CONFIG.gex_stale_max_seconds / 600).
 *   A live compute has no upstream timestamp to age-check.
 */
export async function fetchGexSnapshot(
  symbol: string = 'SPY',
  _staleMaxSeconds: number = 90,
): Promise<GexSnapshot> {
  const [levels, tv, vixQuote] = await Promise.all([
    fetchGexLevels(symbol, 45),
    getTvMarketStructure(symbol).catch(() => null),
    getQuote('VIX').catch(() => null),
  ])

  if (!levels.spot || levels.spot <= 0) {
    throw new GexFetchError(`gex_client: no spot price for ${symbol}`)
  }

  const spot = levels.spot
  const netGex = levels.net_gex ?? 0
  const vix = vixQuote?.last && vixQuote.last > 0 ? vixQuote.last : 0
  const sigma1d = spot > 0 && vix > 0
    ? spot * (vix / 100.0) * SQRT_INV_TRADING_DAYS
    : 0

  return {
    symbol,
    spot,
    net_gex: netGex,
    flip_point: tv?.gammaFlipPrice && tv.gammaFlipPrice > 0 ? tv.gammaFlipPrice : 0,
    call_wall: levels.call_wall ?? 0,
    put_wall: levels.put_wall ?? 0,
    vix,
    regime: regimeFromNetGex(netGex),
    sigma_1d_band_width: sigma1d,
    snapshot_at: new Date(),
  }
}
