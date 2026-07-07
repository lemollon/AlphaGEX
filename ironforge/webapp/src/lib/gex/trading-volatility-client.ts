/**
 * Trading Volatility — market-structure client. Independent gamma-regime read
 * for shadow cross-validation against SPARK/KINDLE's self-computed net GEX
 * (see tradier.ts getNetGex / scanner.ts getNetGexCached). Never throws —
 * callers treat a null return as "feed unavailable," same convention as
 * tradier.ts, so a vendor outage can never block or alter a live trade.
 */
const TV_BASE = process.env.TRADING_VOLATILITY_API_BASE || 'https://stocks.tradingvolatility.net/api/v2'
const TV_API_KEY = process.env.TRADING_VOLATILITY_API_KEY || ''
const TIMEOUT_MS = 5000

export type TvMarketStructure = {
  ticker: string
  gammaToneState: string // 'positive' | 'negative' | 'strong_positive' | 'strong_negative' | ...
  structureRegime: string // e.g. 'above_flip_positive_gamma'
  flipState: string // 'above_flip' | 'below_flip' | 'at_flip'
  gammaFlipPrice: number
  spot: number
  distanceToFlipPct: number
  asof: string
}

async function fetchOnce(url: string): Promise<Response> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    return await fetch(url, {
      headers: { Authorization: `Bearer ${TV_API_KEY}` },
      cache: 'no-store',
      signal: controller.signal,
    })
  } finally {
    clearTimeout(timeout)
  }
}

export async function getTvMarketStructure(ticker: string = 'SPY'): Promise<TvMarketStructure | null> {
  if (!TV_API_KEY) return null
  const url = `${TV_BASE.replace(/\/$/, '')}/tickers/${ticker}/market-structure`
  try {
    let resp = await fetchOnce(url)
    if (!resp.ok) {
      // single retry with 1s backoff, mirrors blaze/gex-client.ts fetchWithRetry
      await new Promise(r => setTimeout(r, 1000))
      resp = await fetchOnce(url)
    }
    if (!resp.ok) return null
    const payload = await resp.json()
    const d = payload?.data
    if (!d) return null
    return {
      ticker,
      gammaToneState: String(d.drivers?.gamma_tone?.state ?? 'unknown'),
      structureRegime: String(d.structure_regime ?? 'unknown'),
      flipState: String(d.drivers?.flip_context?.state ?? 'unknown'),
      gammaFlipPrice: Number(d.key_levels?.gamma_flip) || 0,
      spot: Number(d.key_levels?.spot) || 0,
      distanceToFlipPct: Number(d.supporting_factors?.distance_to_flip_pct) || 0,
      asof: String(payload?.meta?.asof ?? ''),
    }
  } catch {
    return null
  }
}
