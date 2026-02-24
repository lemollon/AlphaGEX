/**
 * Tradier API client for live option quotes and IC mark-to-market.
 *
 * The webapp calls Tradier directly so the Positions tab can show
 * real-time unrealized P&L without waiting for the notebook to run.
 */

const TRADIER_API_KEY = process.env.TRADIER_API_KEY || ''
const TRADIER_BASE_URL =
  process.env.TRADIER_BASE_URL || 'https://sandbox.tradier.com/v1'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface OptionQuote {
  bid: number
  ask: number
  last: number
  symbol: string
}

interface Quote {
  last: number
  bid: number
  ask: number
  symbol: string
}

export interface IcMtmResult {
  cost_to_close: number
  put_short_ask: number
  put_long_bid: number
  call_short_ask: number
  call_long_bid: number
  spot_price: number | null
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Build OCC option symbol: SPY260226P00585000 */
function buildOccSymbol(
  ticker: string,
  expiration: string,
  strike: number,
  optionType: 'P' | 'C',
): string {
  const d = new Date(expiration + 'T12:00:00')
  const yy = String(d.getFullYear()).slice(2)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const strikePart = String(Math.round(strike * 1000)).padStart(8, '0')
  return `${ticker}${yy}${mm}${dd}${optionType}${strikePart}`
}

async function tradierGet(
  endpoint: string,
  params?: Record<string, string>,
): Promise<any> {
  if (!TRADIER_API_KEY) return null

  const url = new URL(`${TRADIER_BASE_URL}${endpoint}`)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  }

  const res = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${TRADIER_API_KEY}`,
      Accept: 'application/json',
    },
    cache: 'no-store',
  })

  if (!res.ok) return null
  return res.json()
}

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */

export async function getQuote(symbol: string): Promise<Quote | null> {
  const data = await tradierGet('/markets/quotes', { symbols: symbol })
  if (!data) return null
  let quote = data.quotes?.quote
  if (Array.isArray(quote)) quote = quote[0]
  if (!quote?.last) return null
  return {
    last: parseFloat(quote.last),
    bid: parseFloat(quote.bid || '0'),
    ask: parseFloat(quote.ask || '0'),
    symbol: quote.symbol,
  }
}

export async function getOptionQuote(
  occSymbol: string,
): Promise<OptionQuote | null> {
  const data = await tradierGet('/markets/quotes', { symbols: occSymbol })
  if (!data) return null
  let quote = data.quotes?.quote
  if (Array.isArray(quote)) quote = quote[0]
  if (!quote || quote.bid == null) return null
  if (data.quotes?.unmatched_symbols) return null
  return {
    bid: parseFloat(quote.bid || '0'),
    ask: parseFloat(quote.ask || '0'),
    last: parseFloat(quote.last || '0'),
    symbol: occSymbol,
  }
}

/**
 * Get current cost-to-close for an Iron Condor by fetching live quotes
 * for all four legs.  Returns null when any leg quote is unavailable.
 */
export async function getIcMarkToMarket(
  ticker: string,
  expiration: string,
  putShort: number,
  putLong: number,
  callShort: number,
  callLong: number,
): Promise<IcMtmResult | null> {
  const [psQ, plQ, csQ, clQ, spotQ] = await Promise.all([
    getOptionQuote(buildOccSymbol(ticker, expiration, putShort, 'P')),
    getOptionQuote(buildOccSymbol(ticker, expiration, putLong, 'P')),
    getOptionQuote(buildOccSymbol(ticker, expiration, callShort, 'C')),
    getOptionQuote(buildOccSymbol(ticker, expiration, callLong, 'C')),
    getQuote(ticker),
  ])

  if (!psQ || !plQ || !csQ || !clQ) return null

  // Cost to close = buy back shorts (at ask) - sell longs (at bid)
  const cost = psQ.ask + csQ.ask - plQ.bid - clQ.bid
  return {
    cost_to_close: Math.max(0, Math.round(cost * 10000) / 10000),
    put_short_ask: psQ.ask,
    put_long_bid: plQ.bid,
    call_short_ask: csQ.ask,
    call_long_bid: clQ.bid,
    spot_price: spotQ?.last ?? null,
  }
}

/** Whether the Tradier API key is configured. */
export function isConfigured(): boolean {
  return !!TRADIER_API_KEY
}
