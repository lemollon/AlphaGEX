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

/** Get available option expirations for a symbol. */
export async function getOptionExpirations(
  symbol: string,
): Promise<string[]> {
  const data = await tradierGet('/markets/options/expirations', {
    symbol,
    includeAllRoots: 'true',
  })
  if (!data) return []
  const dates = data.expirations?.date
  if (!dates) return []
  return Array.isArray(dates) ? dates : [dates]
}

/** Get the entry credit for an Iron Condor (sell at bid, buy at ask). */
export async function getIcEntryCredit(
  ticker: string,
  expiration: string,
  putShort: number,
  putLong: number,
  callShort: number,
  callLong: number,
): Promise<{
  putCredit: number
  callCredit: number
  totalCredit: number
  source: string
} | null> {
  const [psQ, plQ, csQ, clQ] = await Promise.all([
    getOptionQuote(buildOccSymbol(ticker, expiration, putShort, 'P')),
    getOptionQuote(buildOccSymbol(ticker, expiration, putLong, 'P')),
    getOptionQuote(buildOccSymbol(ticker, expiration, callShort, 'C')),
    getOptionQuote(buildOccSymbol(ticker, expiration, callLong, 'C')),
  ])

  if (!psQ || !plQ || !csQ || !clQ) return null

  // Conservative paper fills: sell at bid, buy at ask
  let putCredit = psQ.bid - plQ.ask
  let callCredit = csQ.bid - clQ.ask

  // Mid-price fallback if negative
  if (putCredit <= 0 || callCredit <= 0) {
    const psMid = (psQ.bid + psQ.ask) / 2
    const plMid = (plQ.bid + plQ.ask) / 2
    const csMid = (csQ.bid + csQ.ask) / 2
    const clMid = (clQ.bid + clQ.ask) / 2
    putCredit = Math.max(0, psMid - plMid)
    callCredit = Math.max(0, csMid - clMid)
  }

  return {
    putCredit: Math.round(putCredit * 10000) / 10000,
    callCredit: Math.round(callCredit * 10000) / 10000,
    totalCredit: Math.round((putCredit + callCredit) * 10000) / 10000,
    source: 'TRADIER_LIVE',
  }
}

/** Whether the Tradier API key is configured. */
export function isConfigured(): boolean {
  return !!TRADIER_API_KEY
}

/* ------------------------------------------------------------------ */
/*  Sandbox Order Execution                                            */
/* ------------------------------------------------------------------ */

const TRADIER_ACCOUNT_ID = process.env.TRADIER_ACCOUNT_ID || ''

async function tradierPost(
  endpoint: string,
  body: Record<string, string>,
): Promise<any> {
  if (!TRADIER_API_KEY) return null

  const url = `${TRADIER_BASE_URL}${endpoint}`

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${TRADIER_API_KEY}`,
      Accept: 'application/json',
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams(body).toString(),
    cache: 'no-store',
  })

  if (!res.ok) return null
  return res.json()
}

/** Auto-discover sandbox account ID from profile if not configured. */
let _cachedAccountId: string | null = null

export async function getAccountId(): Promise<string | null> {
  if (TRADIER_ACCOUNT_ID) return TRADIER_ACCOUNT_ID
  if (_cachedAccountId) return _cachedAccountId

  const data = await tradierGet('/user/profile')
  if (!data) return null

  let account = data.profile?.account
  if (Array.isArray(account)) account = account[0]
  const accountId = account?.account_number?.toString()
  if (accountId) _cachedAccountId = accountId
  return accountId || null
}

/**
 * Place an Iron Condor as a multileg order in Tradier sandbox.
 *
 * Returns { orderId, status } or null on failure.
 */
export async function placeIcOrder(
  ticker: string,
  expiration: string,
  putShort: number,
  putLong: number,
  callShort: number,
  callLong: number,
  contracts: number,
  totalCredit: number,
  tag?: string,
): Promise<{ orderId: number; status: string } | null> {
  const accountId = await getAccountId()
  if (!accountId) return null

  const body: Record<string, string> = {
    class: 'multileg',
    symbol: ticker,
    type: 'credit',
    duration: 'day',
    price: totalCredit.toFixed(2),
    'option_symbol[0]': buildOccSymbol(ticker, expiration, putShort, 'P'),
    'side[0]': 'sell_to_open',
    'quantity[0]': String(contracts),
    'option_symbol[1]': buildOccSymbol(ticker, expiration, putLong, 'P'),
    'side[1]': 'buy_to_open',
    'quantity[1]': String(contracts),
    'option_symbol[2]': buildOccSymbol(ticker, expiration, callShort, 'C'),
    'side[2]': 'sell_to_open',
    'quantity[2]': String(contracts),
    'option_symbol[3]': buildOccSymbol(ticker, expiration, callLong, 'C'),
    'side[3]': 'buy_to_open',
    'quantity[3]': String(contracts),
  }
  if (tag) body.tag = tag.slice(0, 255)

  const result = await tradierPost(`/accounts/${accountId}/orders`, body)
  if (!result?.order) return null

  return {
    orderId: result.order.id,
    status: result.order.status || 'unknown',
  }
}

/**
 * Close an Iron Condor by placing the opposite multileg order in sandbox.
 */
export async function closeIcOrder(
  ticker: string,
  expiration: string,
  putShort: number,
  putLong: number,
  callShort: number,
  callLong: number,
  contracts: number,
  closePrice: number,
  tag?: string,
): Promise<{ orderId: number; status: string } | null> {
  const accountId = await getAccountId()
  if (!accountId) return null

  const body: Record<string, string> = {
    class: 'multileg',
    symbol: ticker,
    type: 'debit',
    duration: 'day',
    price: closePrice.toFixed(2),
    'option_symbol[0]': buildOccSymbol(ticker, expiration, putShort, 'P'),
    'side[0]': 'buy_to_close',
    'quantity[0]': String(contracts),
    'option_symbol[1]': buildOccSymbol(ticker, expiration, putLong, 'P'),
    'side[1]': 'sell_to_close',
    'quantity[1]': String(contracts),
    'option_symbol[2]': buildOccSymbol(ticker, expiration, callShort, 'C'),
    'side[2]': 'buy_to_close',
    'quantity[2]': String(contracts),
    'option_symbol[3]': buildOccSymbol(ticker, expiration, callLong, 'C'),
    'side[3]': 'sell_to_close',
    'quantity[3]': String(contracts),
  }
  if (tag) body.tag = tag.slice(0, 255)

  const result = await tradierPost(`/accounts/${accountId}/orders`, body)
  if (!result?.order) return null

  return {
    orderId: result.order.id,
    status: result.order.status || 'unknown',
  }
}
