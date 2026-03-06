/**
 * Tradier API client for live option quotes and IC mark-to-market.
 *
 * The webapp calls Tradier directly so the Positions tab can show
 * real-time unrealized P&L without waiting for the notebook to run.
 */

const TRADIER_API_KEY = process.env.TRADIER_API_KEY || ''
// Use production Tradier for QUOTES (read-only, accurate pricing).
// Sandbox orders go through SANDBOX_URL (line 222) with per-account sandbox keys.
const TRADIER_BASE_URL =
  process.env.TRADIER_BASE_URL || 'https://api.tradier.com/v1'

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
export function buildOccSymbol(
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
/*  Sandbox Order Execution (3 accounts: User, Matt, Logan)            */
/* ------------------------------------------------------------------ */

// Sandbox URL is always sandbox.tradier.com — never production.
// TRADIER_BASE_URL may point to production for live quotes, but
// sandbox keys only work against the sandbox API.
const SANDBOX_URL = 'https://sandbox.tradier.com/v1'

interface SandboxAccount {
  name: string
  apiKey: string
  cachedAccountId?: string
}

/** Load all configured sandbox accounts from env vars. */
function getSandboxAccounts(): SandboxAccount[] {
  const accounts: SandboxAccount[] = []
  const userKey = process.env.TRADIER_SANDBOX_KEY_USER || ''
  const mattKey = process.env.TRADIER_SANDBOX_KEY_MATT || ''
  const loganKey = process.env.TRADIER_SANDBOX_KEY_LOGAN || ''

  if (userKey) accounts.push({ name: 'User', apiKey: userKey })
  if (mattKey) accounts.push({ name: 'Matt', apiKey: mattKey })
  if (loganKey) accounts.push({ name: 'Logan', apiKey: loganKey })
  return accounts
}

const _sandboxAccounts = getSandboxAccounts()

async function sandboxPost(
  endpoint: string,
  body: Record<string, string>,
  apiKey: string,
): Promise<any> {
  if (!apiKey) return null

  const url = `${SANDBOX_URL}${endpoint}`

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      Accept: 'application/json',
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams(body).toString(),
    cache: 'no-store',
  })

  if (!res.ok) return null
  return res.json()
}

async function sandboxGet(
  endpoint: string,
  params: Record<string, string> | undefined,
  apiKey: string,
): Promise<any> {
  if (!apiKey) return null

  const url = new URL(`${SANDBOX_URL}${endpoint}`)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  }

  const res = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${apiKey}`,
      Accept: 'application/json',
    },
    cache: 'no-store',
  })

  if (!res.ok) return null
  return res.json()
}

/** Auto-discover sandbox account ID from profile. */
const _accountIdCache: Record<string, string> = {}

async function getAccountIdForKey(apiKey: string): Promise<string | null> {
  if (_accountIdCache[apiKey]) return _accountIdCache[apiKey]

  const data = await sandboxGet('/user/profile', undefined, apiKey)
  if (!data) return null

  let account = data.profile?.account
  if (Array.isArray(account)) account = account[0]
  const accountId = account?.account_number?.toString()
  if (accountId) _accountIdCache[apiKey] = accountId
  return accountId || null
}

/** Get available buying power for a sandbox account. */
async function getSandboxBuyingPower(
  apiKey: string,
  accountId: string,
): Promise<number | null> {
  const data = await sandboxGet(
    `/accounts/${accountId}/balances`,
    undefined,
    apiKey,
  )
  if (!data) return null
  const balances = data.balances || {}
  const bp = balances.option_buying_power ?? balances.buying_power
  return bp != null ? parseFloat(bp) : null
}

export interface SandboxOrderInfo {
  order_id: number
  contracts: number
  fill_price?: number | null
}

export interface SandboxCloseInfo {
  order_id: number
  contracts: number
  fill_price?: number | null
}

/**
 * Query a sandbox order and return the average fill price.
 * Retries up to 3 times with 1s delay for pending orders.
 */
async function getOrderFillPrice(
  apiKey: string,
  accountId: string,
  orderId: number,
): Promise<number | null> {
  for (let attempt = 0; attempt < 3; attempt++) {
    const data = await sandboxGet(
      `/accounts/${accountId}/orders/${orderId}`,
      undefined,
      apiKey,
    )
    if (!data) {
      await new Promise((r) => setTimeout(r, 1000))
      continue
    }

    const order = data.order || {}
    const status = order.status || ''

    if (status === 'filled') {
      // avg_fill_price on order level for multileg
      if (order.avg_fill_price != null) {
        return Math.abs(parseFloat(order.avg_fill_price))
      }
      // Fallback: calculate from leg fills
      let legs = order.leg || []
      if (!Array.isArray(legs)) legs = [legs]
      if (legs.length > 0) {
        let total = 0
        for (const leg of legs) {
          const side = leg.side || ''
          const fill = parseFloat(leg.avg_fill_price || '0')
          if (side.includes('sell')) total += fill
          else total -= fill
        }
        return total !== 0 ? Math.abs(total) : null
      }
    }

    if (['pending', 'open', 'partially_filled'].includes(status)) {
      await new Promise((r) => setTimeout(r, 1000))
      continue
    }

    // rejected, canceled, expired
    return null
  }
  return null
}

/**
 * Place an Iron Condor in ALL configured sandbox accounts.
 *
 * Each account sizes independently based on its OWN buying power:
 * - Query account balance → compute usable BP (85%)
 * - max_contracts = floor(usableBP / collateralPer) — NO cap
 *
 * Returns Record<accountName, {order_id, contracts}> for successful placements.
 */
export async function placeIcOrderAllAccounts(
  ticker: string,
  expiration: string,
  putShort: number,
  putLong: number,
  callShort: number,
  callLong: number,
  _paperContracts: number,
  totalCredit: number,
  tag?: string,
): Promise<Record<string, SandboxOrderInfo>> {
  const results: Record<string, SandboxOrderInfo> = {}

  // Shared OCC symbols — same strikes for all accounts
  const occPs = buildOccSymbol(ticker, expiration, putShort, 'P')
  const occPl = buildOccSymbol(ticker, expiration, putLong, 'P')
  const occCs = buildOccSymbol(ticker, expiration, callShort, 'C')
  const occCl = buildOccSymbol(ticker, expiration, callLong, 'C')

  // Collateral per contract
  const spreadWidth = putShort - putLong
  const collateralPer = Math.max(0, (spreadWidth - totalCredit) * 100)
  if (collateralPer <= 0) return results

  // Process User first (for fill price later), then others in parallel
  const userAccts = _sandboxAccounts.filter((a) => a.name === 'User')
  const otherAccts = _sandboxAccounts.filter((a) => a.name !== 'User')

  async function placeForAccount(acct: SandboxAccount) {
    try {
      const accountId = await getAccountIdForKey(acct.apiKey)
      if (!accountId) return

      // Query this account's own buying power
      const bp = await getSandboxBuyingPower(acct.apiKey, accountId)
      if (bp == null || bp < collateralPer) {
        console.warn(
          `Sandbox [${acct.name}]: BP=$${bp} insufficient (need $${collateralPer.toFixed(2)}/contract)`,
        )
        return
      }

      // Size based on THIS account's BP — NO max cap
      const usableBP = bp * 0.85
      const acctContracts = Math.max(1, Math.floor(usableBP / collateralPer))

      console.log(
        `Sandbox [${acct.name}]: BP=$${bp.toFixed(0)} → usable=$${usableBP.toFixed(0)} → ${acctContracts} contracts`,
      )

      const orderBody: Record<string, string> = {
        class: 'multileg',
        symbol: ticker,
        type: 'market',
        duration: 'day',
        'option_symbol[0]': occPs, 'side[0]': 'sell_to_open', 'quantity[0]': String(acctContracts),
        'option_symbol[1]': occPl, 'side[1]': 'buy_to_open',  'quantity[1]': String(acctContracts),
        'option_symbol[2]': occCs, 'side[2]': 'sell_to_open', 'quantity[2]': String(acctContracts),
        'option_symbol[3]': occCl, 'side[3]': 'buy_to_open',  'quantity[3]': String(acctContracts),
      }
      if (tag) orderBody.tag = tag.slice(0, 255)

      const result = await sandboxPost(
        `/accounts/${accountId}/orders`,
        orderBody,
        acct.apiKey,
      )
      if (result?.order?.id) {
        // Read back actual fill price
        let fillPrice: number | null = null
        try {
          fillPrice = await getOrderFillPrice(acct.apiKey, accountId, result.order.id)
        } catch {
          // Non-fatal
        }
        results[acct.name] = {
          order_id: result.order.id,
          contracts: acctContracts,
          fill_price: fillPrice,
        }
      }
    } catch (err: any) {
      console.warn(`Sandbox IC order failed [${acct.name}]: ${err.message}`)
    }
  }

  // User first (sequential), then others in parallel
  for (const acct of userAccts) await placeForAccount(acct)
  await Promise.all(otherAccts.map(placeForAccount))

  return results
}

/* ------------------------------------------------------------------ */
/*  Detailed leg quotes (for position-detail)                          */
/* ------------------------------------------------------------------ */

export interface LegQuote {
  symbol: string
  bid: number
  ask: number
  mid: number
  last: number
}

/**
 * Fetch quotes for multiple OCC symbols in a single API call.
 * Returns a map of symbol → LegQuote.
 */
export async function getBatchOptionQuotes(
  occSymbols: string[],
): Promise<Record<string, LegQuote>> {
  if (!TRADIER_API_KEY || occSymbols.length === 0) return {}

  const data = await tradierGet('/markets/quotes', {
    symbols: occSymbols.join(','),
  })
  if (!data) return {}

  const results: Record<string, LegQuote> = {}
  let quotes = data.quotes?.quote
  if (!quotes) return results
  if (!Array.isArray(quotes)) quotes = [quotes]

  for (const q of quotes) {
    if (!q?.symbol || q.bid == null) continue
    const bid = parseFloat(q.bid || '0')
    const ask = parseFloat(q.ask || '0')
    results[q.symbol] = {
      symbol: q.symbol,
      bid,
      ask,
      mid: Math.round(((bid + ask) / 2) * 10000) / 10000,
      last: parseFloat(q.last || '0'),
    }
  }
  return results
}

/* ------------------------------------------------------------------ */
/*  Sandbox account positions (for per-account P&L)                    */
/* ------------------------------------------------------------------ */

export interface SandboxPosition {
  symbol: string
  quantity: number
  cost_basis: number
  market_value: number
  gain_loss: number
  gain_loss_percent: number
}

export interface SandboxAccountDetail {
  name: string
  positions: SandboxPosition[]
  total_cost: number
  total_market_value: number
  total_pnl: number
}

/**
 * Get the loaded sandbox accounts (name + apiKey pairs).
 * Used by position-detail route to query each account.
 */
export function getLoadedSandboxAccounts(): Array<{ name: string; apiKey: string }> {
  return _sandboxAccounts.map((a) => ({ name: a.name, apiKey: a.apiKey }))
}

/**
 * Fetch positions from a sandbox account and filter to the given OCC symbols.
 */
export async function getSandboxAccountPositions(
  apiKey: string,
  filterSymbols?: string[],
): Promise<SandboxPosition[]> {
  const accountId = await getAccountIdForKey(apiKey)
  if (!accountId) return []

  const data = await sandboxGet(
    `/accounts/${accountId}/positions`,
    undefined,
    apiKey,
  )
  if (!data) return []

  let positions = data.positions?.position
  if (!positions) return []
  if (!Array.isArray(positions)) positions = [positions]

  const filterSet = filterSymbols ? new Set(filterSymbols) : null

  return positions
    .filter((p: any) => !filterSet || filterSet.has(p.symbol))
    .map((p: any) => ({
      symbol: p.symbol || '',
      quantity: parseFloat(p.quantity || '0'),
      cost_basis: parseFloat(p.cost_basis || '0'),
      market_value: parseFloat(p.market_value || '0'),
      gain_loss: parseFloat(p.gain_loss || '0'),
      gain_loss_percent: parseFloat(p.gain_loss_percent || '0'),
    }))
}

/**
 * Close an Iron Condor in ALL configured sandbox accounts.
 *
 * Reads per-account contract counts from sandboxOpenInfo (stored at open time).
 * Falls back to the paper position's contracts if legacy format.
 *
 * Returns Record<accountName, orderId> for successful closes.
 */
export async function closeIcOrderAllAccounts(
  ticker: string,
  expiration: string,
  putShort: number,
  putLong: number,
  callShort: number,
  callLong: number,
  paperContracts: number,
  closePrice: number,
  tag?: string,
  sandboxOpenInfo?: Record<string, SandboxOrderInfo | number> | null,
): Promise<Record<string, SandboxCloseInfo>> {
  const results: Record<string, SandboxCloseInfo> = {}

  const occPs = buildOccSymbol(ticker, expiration, putShort, 'P')
  const occPl = buildOccSymbol(ticker, expiration, putLong, 'P')
  const occCs = buildOccSymbol(ticker, expiration, callShort, 'C')
  const occCl = buildOccSymbol(ticker, expiration, callLong, 'C')

  await Promise.all(
    _sandboxAccounts.map(async (acct) => {
      try {
        const accountId = await getAccountIdForKey(acct.apiKey)
        if (!accountId) return

        // Determine how many contracts this account opened
        let closeQty = paperContracts
        const acctInfo = sandboxOpenInfo?.[acct.name]
        if (acctInfo && typeof acctInfo === 'object' && 'contracts' in acctInfo) {
          closeQty = acctInfo.contracts
        }

        const orderBody: Record<string, string> = {
          class: 'multileg',
          symbol: ticker,
          type: 'market',
          duration: 'day',
          'option_symbol[0]': occPs, 'side[0]': 'buy_to_close',  'quantity[0]': String(closeQty),
          'option_symbol[1]': occPl, 'side[1]': 'sell_to_close', 'quantity[1]': String(closeQty),
          'option_symbol[2]': occCs, 'side[2]': 'buy_to_close',  'quantity[2]': String(closeQty),
          'option_symbol[3]': occCl, 'side[3]': 'sell_to_close', 'quantity[3]': String(closeQty),
        }
        if (tag) orderBody.tag = tag.slice(0, 255)

        const result = await sandboxPost(
          `/accounts/${accountId}/orders`,
          orderBody,
          acct.apiKey,
        )
        if (result?.order?.id) {
          // Read back actual fill price
          let fillPrice: number | null = null
          try {
            fillPrice = await getOrderFillPrice(acct.apiKey, accountId, result.order.id)
          } catch {
            // Non-fatal
          }
          results[acct.name] = {
            order_id: result.order.id,
            contracts: closeQty,
            fill_price: fillPrice,
          }
        }
      } catch (err: any) {
        console.warn(`Sandbox IC close failed [${acct.name}]: ${err.message}`)
      }
    }),
  )

  return results
}
