/**
 * Tradier API client for live option quotes and IC mark-to-market.
 *
 * The webapp calls Tradier directly so the Positions tab can show
 * real-time unrealized P&L without waiting for the notebook to run.
 *
 * KEY DESIGN: When TRADIER_API_KEY env var is not set, we auto-load
 * the first sandbox account key from the DB. This ensures the scanner
 * can fetch quotes even when all keys are managed via the /accounts UI.
 */

let _tradierApiKey = process.env.TRADIER_API_KEY || ''
let _tradierApiKeyLoadedFromDb = false

// If TRADIER_BASE_URL is not explicitly set AND TRADIER_API_KEY is not set,
// default to sandbox (since DB accounts are sandbox keys).
// If TRADIER_API_KEY IS set, user controls the base URL explicitly.
const TRADIER_BASE_URL =
  process.env.TRADIER_BASE_URL ||
  (_tradierApiKey ? 'https://api.tradier.com/v1' : 'https://sandbox.tradier.com/v1')

/**
 * Ensure we have an API key for quotes — load from DB if env var is empty.
 * Called lazily before the first quote request.
 */
async function ensureQuoteApiKey(): Promise<void> {
  if (_tradierApiKey || _tradierApiKeyLoadedFromDb) return
  _tradierApiKeyLoadedFromDb = true

  try {
    const { query: dbq } = await import('./db')
    const rows = await dbq(
      `SELECT api_key FROM ironforge_accounts
       WHERE is_active = TRUE ORDER BY id LIMIT 1`,
    )
    if (rows.length > 0 && rows[0].api_key) {
      _tradierApiKey = rows[0].api_key.trim()
      console.log(`[tradier] Quote API key loaded from DB (${_tradierApiKey.slice(0, 4)}...) — using ${TRADIER_BASE_URL}`)
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[tradier] Failed to load quote API key from DB: ${msg}`)
  }
}

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface OptionQuote {
  bid: number
  ask: number
  last: number
  mid: number
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
  cost_to_close_mid: number
  /** Cost using last trade prices (matches Tradier portfolio valuation). */
  cost_to_close_last: number
  put_short_ask: number
  put_long_bid: number
  call_short_ask: number
  call_long_bid: number
  spot_price: number | null
  validation_issues?: string[]
  /** Seconds since the most recent quote update across all legs. >300 = likely delayed data. */
  quote_age_seconds?: number
  /** The API base URL used (production vs sandbox). */
  api_source?: string
  /** Per-leg last trade prices used for cost_to_close_last. */
  last_prices?: { ps: number; pl: number; cs: number; cl: number }
}

/** Validation issues found in a set of MTM quotes (empty = passed). */
interface MtmValidation {
  pass: boolean
  issues: string[]
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Default timeout for all Tradier API calls (5 seconds). */
const API_TIMEOUT_MS = 5_000

/** Create an AbortSignal that fires after `ms` milliseconds. */
function timeoutSignal(ms: number = API_TIMEOUT_MS): AbortSignal {
  const controller = new AbortController()
  setTimeout(() => controller.abort(), ms)
  return controller.signal
}

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
  // Lazy-load API key from DB if env var wasn't set
  await ensureQuoteApiKey()

  if (!_tradierApiKey) {
    console.error(`Tradier: API key not configured (no env var, no DB accounts) — cannot call ${endpoint}`)
    return null
  }

  const url = new URL(`${TRADIER_BASE_URL}${endpoint}`)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  }

  let res: Response
  try {
    res = await fetch(url.toString(), {
      headers: {
        Authorization: `Bearer ${_tradierApiKey}`,
        Accept: 'application/json',
      },
      cache: 'no-store',
      signal: timeoutSignal(),
    })
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      console.error(`Tradier: ${endpoint} timed out after ${API_TIMEOUT_MS}ms`)
    } else {
      const msg = err instanceof Error ? err.message : String(err)
      console.error(`Tradier: ${endpoint} fetch failed: ${msg}`)
    }
    return null
  }

  if (!res.ok) {
    console.error(`Tradier: ${endpoint} returned HTTP ${res.status} (${res.statusText})`)
    return null
  }
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
  const bid = parseFloat(quote.bid || '0')
  const ask = parseFloat(quote.ask || '0')
  return {
    bid,
    ask,
    last: parseFloat(quote.last || '0'),
    mid: Math.round(((bid + ask) / 2) * 10000) / 10000,
    symbol: occSymbol,
  }
}

/**
 * Validate MTM option quotes — mirrors the scanner's _validate_mtm logic.
 * Rejects: zero/negative bid+ask, inverted markets, wide spreads (>50% of mid),
 * negative cost_to_close, or cost > 3x entry credit.
 */
function validateMtmQuotes(
  legs: Array<{ label: string; bid: number; ask: number }>,
  rawCost: number,
  entryCredit: number,
): MtmValidation {
  const issues: string[] = []

  for (const { label, bid, ask } of legs) {
    // Short legs (PS, CS) must have positive asks (we buy these back to close).
    // Long legs (PL, CL) can have zero bid/ask — deep OTM 0DTE wings often do.
    const isShortLeg = label === 'PS' || label === 'CS'
    if (isShortLeg && ask <= 0) {
      issues.push(`${label}: zero ask (ask=${ask})`)
    }
    if (bid > ask && ask > 0) {
      issues.push(`${label}: inverted market (bid ${bid} > ask ${ask})`)
    }
    const mid = (bid + ask) / 2
    // Match scanner threshold: only check wide spreads when mid > $0.05
    // Cheap near-expiry options (mid $0.01-$0.05) naturally have wide relative spreads
    if (mid > 0.05 && (ask - bid) > 0.50 * mid) {
      issues.push(`${label}: wide spread (${(ask - bid).toFixed(2)} > 50% of mid ${mid.toFixed(2)})`)
    }
  }

  if (rawCost < 0) {
    issues.push(`Negative raw cost: ${rawCost.toFixed(4)}`)
  }
  if (entryCredit > 0 && rawCost > 3 * entryCredit) {
    issues.push(`Cost ${rawCost.toFixed(4)} > 3x entry ${entryCredit.toFixed(4)}`)
  }

  return { pass: issues.length === 0, issues }
}

/**
 * Get current cost-to-close for an Iron Condor by fetching live quotes
 * for all four legs in a single batch API call.
 *
 * Returns null when any leg quote is unavailable or when quote validation
 * fails (wide spreads, stale data, etc.).
 *
 * Pass entryCredit to enable the "cost > 3x entry" validation check.
 *
 * Two cost figures:
 *   cost_to_close     — worst-case (buy shorts at ask, sell longs at bid).
 *                        Used for PT/SL decisions.
 *   cost_to_close_mid — mark price (bid+ask midpoint for each leg).
 *                        Used for P&L display. Matches Tradier's portfolio
 *                        valuation which uses mark, not last trade.
 */
export async function getIcMarkToMarket(
  ticker: string,
  expiration: string,
  putShort: number,
  putLong: number,
  callShort: number,
  callLong: number,
  entryCredit?: number,
): Promise<IcMtmResult | null> {
  const occPs = buildOccSymbol(ticker, expiration, putShort, 'P')
  const occPl = buildOccSymbol(ticker, expiration, putLong, 'P')
  const occCs = buildOccSymbol(ticker, expiration, callShort, 'C')
  const occCl = buildOccSymbol(ticker, expiration, callLong, 'C')

  // Single batch call for all 4 option legs + underlying (synchronized snapshot)
  const allSymbols = [occPs, occPl, occCs, occCl, ticker].join(',')
  await ensureQuoteApiKey()
  if (!_tradierApiKey) return null

  const data = await tradierGet('/markets/quotes', { symbols: allSymbols })
  if (!data) return null

  let quotes = data.quotes?.quote
  if (!quotes) return null
  if (!Array.isArray(quotes)) quotes = [quotes]

  // Index by symbol for fast lookup
  const bySymbol: Record<string, any> = {}
  for (const q of quotes) {
    if (q?.symbol) bySymbol[q.symbol] = q
  }

  const psRaw = bySymbol[occPs]
  const plRaw = bySymbol[occPl]
  const csRaw = bySymbol[occCs]
  const clRaw = bySymbol[occCl]
  const spotRaw = bySymbol[ticker]

  if (!psRaw || !plRaw || !csRaw || !clRaw) return null
  if (psRaw.bid == null || plRaw.bid == null || csRaw.bid == null || clRaw.bid == null) return null

  // Also reject if any symbol was unmatched by Tradier
  if (data.quotes?.unmatched_symbols) {
    const unmatched = data.quotes.unmatched_symbols
    const unmatchedStr = typeof unmatched === 'string' ? unmatched : JSON.stringify(unmatched)
    const needed = [occPs, occPl, occCs, occCl]
    if (needed.some(s => unmatchedStr.includes(s))) return null
  }

  const parse = (v: any) => parseFloat(v || '0')
  const psQ = { bid: parse(psRaw.bid), ask: parse(psRaw.ask), last: parse(psRaw.last), mid: 0 }
  const plQ = { bid: parse(plRaw.bid), ask: parse(plRaw.ask), last: parse(plRaw.last), mid: 0 }
  const csQ = { bid: parse(csRaw.bid), ask: parse(csRaw.ask), last: parse(csRaw.last), mid: 0 }
  const clQ = { bid: parse(clRaw.bid), ask: parse(clRaw.ask), last: parse(clRaw.last), mid: 0 }
  psQ.mid = Math.round(((psQ.bid + psQ.ask) / 2) * 10000) / 10000
  plQ.mid = Math.round(((plQ.bid + plQ.ask) / 2) * 10000) / 10000
  csQ.mid = Math.round(((csQ.bid + csQ.ask) / 2) * 10000) / 10000
  clQ.mid = Math.round(((clQ.bid + clQ.ask) / 2) * 10000) / 10000

  // Cost to close = buy back shorts (at ask) - sell longs (at bid)
  const rawCost = psQ.ask + csQ.ask - plQ.bid - clQ.bid

  // Validate quotes — matching the scanner's _validate_mtm logic
  // Cap at spread width — theoretical max cost for an IC
  const spreadWidth = Math.round((putShort - putLong) * 100) / 100

  // Mark price cost — uses mid (bid+ask average) for each leg.
  const rawCostMark = psQ.mid + csQ.mid - plQ.mid - clQ.mid
  const costMark = Math.min(Math.max(0, rawCostMark), spreadWidth)

  // Last trade price cost — matches Tradier portfolio's "Price" column.
  // Tradier uses last trade prices for Gain/Loss. Falls back to mid if no last trade.
  const psLast = psQ.last > 0 ? psQ.last : psQ.mid
  const plLast = plQ.last > 0 ? plQ.last : plQ.mid
  const csLast = csQ.last > 0 ? csQ.last : csQ.mid
  const clLast = clQ.last > 0 ? clQ.last : clQ.mid
  const rawCostLast = psLast + csLast - plLast - clLast
  const costLast = Math.min(Math.max(0, rawCostLast), spreadWidth)

  const validation = validateMtmQuotes(
    [
      { label: 'PS', bid: psQ.bid, ask: psQ.ask },
      { label: 'PL', bid: plQ.bid, ask: plQ.ask },
      { label: 'CS', bid: csQ.bid, ask: csQ.ask },
      { label: 'CL', bid: clQ.bid, ask: clQ.ask },
    ],
    rawCost,
    entryCredit ?? 0,
  )

  // Always return cost_to_close_mid (mark price) for P&L display — even when
  // bid/ask validation fails due to wide spreads on wing strikes.
  // The mid price is still a reliable estimate and matches Tradier's portfolio.
  // Only cost_to_close (worst-case bid/ask) is unreliable with wide spreads.
  const cost = validation.pass
    ? Math.min(Math.max(0, rawCost), spreadWidth)
    : costMark  // Fallback: use mid for PT/SL too when bid/ask is unreliable

  // Detect quote staleness: compare most recent trade/bid timestamp to now.
  // Tradier returns trade_date (last fill) and bid_date (last bid update) as epoch ms.
  let quoteAgeSeconds: number | undefined
  try {
    const now = Date.now()
    const timestamps: number[] = []
    for (const raw of [psRaw, plRaw, csRaw, clRaw, spotRaw]) {
      if (!raw) continue
      // Tradier returns bid_date/ask_date as epoch milliseconds, or trade_date as ISO string
      for (const field of ['bid_date', 'ask_date', 'trade_date']) {
        const v = raw[field]
        if (!v) continue
        const ts = typeof v === 'number' ? v : new Date(v).getTime()
        if (ts > 0 && ts < now + 86400000) timestamps.push(ts)
      }
    }
    if (timestamps.length > 0) {
      const newest = Math.max(...timestamps)
      quoteAgeSeconds = Math.round((now - newest) / 1000)
    }
  } catch { /* non-fatal */ }

  if (quoteAgeSeconds != null && quoteAgeSeconds > 300) {
    console.warn(
      `[tradier] MTM quotes are ${quoteAgeSeconds}s old (${Math.round(quoteAgeSeconds / 60)}min) — ` +
      `API may be returning delayed data. Base URL: ${TRADIER_BASE_URL}`,
    )
  }

  return {
    cost_to_close: Math.round(cost * 10000) / 10000,
    cost_to_close_mid: Math.round(costMark * 10000) / 10000,
    cost_to_close_last: Math.round(costLast * 10000) / 10000,
    put_short_ask: psQ.ask,
    put_long_bid: plQ.bid,
    call_short_ask: csQ.ask,
    call_long_bid: clQ.bid,
    spot_price: spotRaw ? parse(spotRaw.last) : null,
    validation_issues: validation.pass ? undefined : validation.issues,
    quote_age_seconds: quoteAgeSeconds,
    api_source: TRADIER_BASE_URL,
    last_prices: { ps: psLast, pl: plLast, cs: csLast, cl: clLast },
  }
}

/**
 * Shared unrealized P&L calculation for an Iron Condor position.
 * Ensures consistent formula, capping, and rounding across all endpoints.
 *
 * @param entryCredit  Per-contract credit received at open
 * @param costToClose  Per-contract cost to close (already capped by getIcMarkToMarket)
 * @param contracts    Number of contracts
 * @param spreadWidth  Width of the spread (e.g. 5.0 for $5 wide)
 * @returns Unrealized P&L in dollars, rounded to 2 decimals
 */
export function calculateIcUnrealizedPnl(
  entryCredit: number,
  costToClose: number,
  contracts: number,
  spreadWidth: number,
): number {
  // Cap cost at [0, spreadWidth] — theoretical bounds for an IC
  const cappedCost = Math.min(Math.max(0, costToClose), spreadWidth)
  return Math.round((entryCredit - cappedCost) * 100 * contracts * 100) / 100
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

/** Whether the Tradier API key is configured (env var or DB). */
export function isConfigured(): boolean {
  return !!_tradierApiKey
}

/** Async version — ensures DB key is loaded before checking. */
export async function isConfiguredAsync(): Promise<boolean> {
  await ensureQuoteApiKey()
  return !!_tradierApiKey
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

/**
 * Bot → sandbox account mapping.
 *
 * FLAME:   User only — 1:1 sandbox mirror for unrealized P&L comparison.
 *          Paper position = 85% of paper_account BP (contracts) + Tradier fill price.
 *          User sandbox account sizes at 85% of its own BP.
 * SPARK:   Paper-only — NO sandbox orders. Sizes from paper_account × 85%.
 * INFERNO: Paper-only — NO sandbox orders. Sizes from paper_account × 85%.
 *          Can hold multiple simultaneous positions (max 20 contracts).
 *
 * Formula: usableBP = accountBP × bpShare × 0.85
 * Contract counts always floor() to whole numbers — no fractional contracts.
 */
interface BotAccountConfig {
  accounts: string[]
  /** BP share per account name (0-1). Applied before the 0.85 BP usage cap. */
  bpShare: Record<string, number>
}

const BOT_ACCOUNTS: Record<string, BotAccountConfig> = {
  flame: {
    accounts: ['User'],
    bpShare:  { User: 1.0 },
  },
  spark: {
    accounts: [],  // Paper-only — no sandbox orders
    bpShare:  {},
  },
  inferno: {
    accounts: [],  // Paper-only — no sandbox orders
    bpShare:  {},
  },
}

/** Get sandbox accounts that a specific bot trades on. */
export function getAccountsForBot(botName: string): string[] {
  return BOT_ACCOUNTS[botName]?.accounts ?? ['User']
}

/** Get this bot's BP share for a specific account (0-1). */
export function getBpShareForBot(botName: string, accountName: string): number {
  return BOT_ACCOUNTS[botName]?.bpShare[accountName] ?? 1.0
}

/** Load all configured sandbox accounts from env vars. */
function getSandboxAccountsFromEnv(): SandboxAccount[] {
  const accounts: SandboxAccount[] = []
  const userKey = process.env.TRADIER_SANDBOX_KEY_USER || ''
  const mattKey = process.env.TRADIER_SANDBOX_KEY_MATT || ''
  const loganKey = process.env.TRADIER_SANDBOX_KEY_LOGAN || ''

  if (userKey) accounts.push({ name: 'User', apiKey: userKey })
  if (mattKey) accounts.push({ name: 'Matt', apiKey: mattKey })
  if (loganKey) accounts.push({ name: 'Logan', apiKey: loganKey })
  return accounts
}

let _sandboxAccounts = getSandboxAccountsFromEnv()
let _sandboxAccountsLoadedFromDb = false

/**
 * Load sandbox accounts from the ironforge_accounts database table.
 * Called once on first use if env vars yielded zero accounts.
 * This bridges the gap: accounts added via the UI (/accounts page)
 * are stored in the DB, not in env vars.
 */
async function ensureSandboxAccountsLoaded(): Promise<void> {
  if (_sandboxAccounts.length > 0 || _sandboxAccountsLoadedFromDb) return
  _sandboxAccountsLoadedFromDb = true

  try {
    // Dynamic import to avoid circular dependency (db.ts imports nothing from tradier)
    const { query: dbq } = await import('./db')

    // Try sandbox-type accounts first; if none, try all accounts.
    // IronForge sends all orders to sandbox.tradier.com regardless of type,
    // so production-type keys stored here are still sandbox keys
    // (the "type" field just indicates how the user categorized them).
    let rows = await dbq(
      `SELECT person, api_key, account_id FROM ironforge_accounts
       WHERE is_active = TRUE AND type = 'sandbox' ORDER BY person`,
    )
    if (rows.length === 0) {
      rows = await dbq(
        `SELECT person, api_key, account_id FROM ironforge_accounts
         WHERE is_active = TRUE ORDER BY person`,
      )
    }
    if (rows.length > 0) {
      const seen = new Set<string>()
      let isFirst = true
      for (const row of rows) {
        const key = row.api_key?.trim()
        if (!key || seen.has(key)) continue
        seen.add(key)
        // First account gets name 'User' so FLAME fill-only mode works
        // (FLAME requires sandboxOrderIds['User'] to be present)
        const name = isFirst ? 'User' : (row.person || 'DB')
        _sandboxAccounts.push({ name, apiKey: key })
        isFirst = false
      }
      if (_sandboxAccounts.length > 0) {
        console.log(
          `[tradier] Loaded ${_sandboxAccounts.length} sandbox account(s) from DB: ` +
          _sandboxAccounts.map(a => `${a.name} (${a.apiKey.slice(0, 4)}...)`).join(', '),
        )
      }
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[tradier] Failed to load sandbox accounts from DB: ${msg}`)
  }
}

async function sandboxPost(
  endpoint: string,
  body: Record<string, string>,
  apiKey: string,
): Promise<any> {
  if (!apiKey) return null

  const url = `${SANDBOX_URL}${endpoint}`

  let res: Response
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        Accept: 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams(body).toString(),
      cache: 'no-store',
      signal: timeoutSignal(),
    })
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      console.error(`Tradier sandbox: ${endpoint} timed out after ${API_TIMEOUT_MS}ms`)
    } else {
      const msg = err instanceof Error ? err.message : String(err)
      console.error(`Tradier sandbox: ${endpoint} fetch failed: ${msg}`)
    }
    return null
  }

  if (!res.ok) {
    const status = res.status
    let errorBody = ''
    try { errorBody = await res.text() } catch { /* ignore */ }
    if (status === 401 || status === 403) {
      console.error(`Tradier sandbox POST: AUTH FAILURE ${status} on ${endpoint} — check API key. Body: ${errorBody}`)
    } else {
      console.error(`Tradier sandbox POST: ${endpoint} returned HTTP ${status} (${res.statusText}) — Body: ${errorBody}`)
    }
    return null
  }
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

  let res: Response
  try {
    res = await fetch(url.toString(), {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        Accept: 'application/json',
      },
      cache: 'no-store',
      signal: timeoutSignal(),
    })
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      console.error(`Tradier sandbox: ${endpoint} timed out after ${API_TIMEOUT_MS}ms`)
    } else {
      const msg = err instanceof Error ? err.message : String(err)
      console.error(`Tradier sandbox: ${endpoint} fetch failed: ${msg}`)
    }
    return null
  }

  if (!res.ok) {
    const status = res.status
    let errorBody = ''
    try { errorBody = await res.text() } catch { /* ignore */ }
    if (status === 401 || status === 403) {
      console.error(`Tradier sandbox GET: AUTH FAILURE ${status} on ${endpoint} — check API key. Body: ${errorBody}`)
    } else {
      console.error(`Tradier sandbox GET: ${endpoint} returned HTTP ${status} (${res.statusText}) — Body: ${errorBody}`)
    }
    return null
  }
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

/** Get available Option Buying Power for a sandbox account.
 *
 * Tradier API balances response (per docs):
 *   - margin.option_buying_power  = Option B.P. (1x, real collateral limit)
 *   - margin.stock_buying_power   = Stock B.P.  (2x margin)
 *   - pdt.option_buying_power     = Option B.P. for PDT accounts
 *   - pdt.day_trade_buying_power  = Day Trade B.P. (4x leverage — NOT for sizing)
 *   - total_equity                = Total account value (includes positions)
 *
 * The correct field for option order sizing is margin.option_buying_power
 * (or pdt.option_buying_power for PDT accounts). This matches the
 * "Option B.P." shown on the Tradier website UI.
 *
 * See: https://documentation.tradier.com/brokerage-api/reference/response/balances
 */
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
  const pdt = balances.pdt || {}
  const margin = balances.margin || {}
  const cash = balances.cash || {}

  // Log ALL balance fields so we can verify which field is correct
  console.log(
    `getSandboxBuyingPower [${accountId}]: RAW ` +
    `account_type=${balances.account_type ?? 'N/A'}, ` +
    `total_equity=${balances.total_equity ?? 'N/A'}, ` +
    `total_cash=${balances.total_cash ?? 'N/A'}, ` +
    `margin.obp=${margin.option_buying_power ?? 'N/A'}, ` +
    `margin.sbp=${margin.stock_buying_power ?? 'N/A'}, ` +
    `pdt.obp=${pdt.option_buying_power ?? 'N/A'}, ` +
    `pdt.sbp=${pdt.stock_buying_power ?? 'N/A'}, ` +
    `pdt.dtbp=${pdt.day_trade_buying_power ?? 'N/A'}, ` +
    `cash.available=${cash.cash_available ?? 'N/A'}`,
  )

  // Per Tradier docs: option_buying_power is the real Option B.P. (1x).
  // Use margin.option_buying_power or pdt.option_buying_power depending on account type.
  // Fallback chain: margin OBP → pdt OBP → total_cash → cash_available → total_equity
  const optionBp =
    margin.option_buying_power ??
    pdt.option_buying_power ??
    balances.total_cash ??
    cash.cash_available ??
    balances.total_equity

  if (optionBp != null) {
    const parsed = parseFloat(optionBp)
    console.log(`getSandboxBuyingPower [${accountId}]: Using option_buying_power=$${parsed.toFixed(0)}`)
    return parsed
  }

  console.warn(
    `getSandboxBuyingPower [${accountId}]: No balance data found. ` +
    `Keys: ${JSON.stringify(Object.keys(balances))}`,
  )
  return null
}

/* ------------------------------------------------------------------ */
/*  Sandbox account balance details (for Accounts page)                */
/* ------------------------------------------------------------------ */

export interface SandboxAccountBalance {
  name: string
  account_id: string | null
  total_equity: number | null
  option_buying_power: number | null
  day_pnl: number | null
  open_positions_count: number
}

/**
 * Fetch full balance + position count for all configured sandbox accounts.
 * Returns one entry per account. Values are null when Tradier API is unreachable.
 */
export async function getSandboxAccountBalances(): Promise<SandboxAccountBalance[]> {
  await ensureSandboxAccountsLoaded()
  const results: SandboxAccountBalance[] = []

  await Promise.all(
    _sandboxAccounts.map(async (acct) => {
      const accountId = await getAccountIdForKey(acct.apiKey)
      if (!accountId) {
        results.push({
          name: acct.name,
          account_id: null,
          total_equity: null,
          option_buying_power: null,
          day_pnl: null,
          open_positions_count: 0,
        })
        return
      }

      // Fetch balances and positions in parallel
      const [balData, posData] = await Promise.all([
        sandboxGet(`/accounts/${accountId}/balances`, undefined, acct.apiKey),
        sandboxGet(`/accounts/${accountId}/positions`, undefined, acct.apiKey),
      ])

      const bal = balData?.balances || {}
      const pdt = bal.pdt || {}
      const margin = bal.margin || {}
      const equity = bal.total_equity != null ? parseFloat(bal.total_equity) : null
      // Per Tradier docs: margin.option_buying_power (or pdt.option_buying_power)
      // is the real Option B.P. — matches what the Tradier UI shows as "Option B.P."
      const rawObp = margin.option_buying_power ?? pdt.option_buying_power
      const optionBp = rawObp != null ? parseFloat(rawObp) : equity

      // Tradier doesn't provide day P&L directly — compute from total_equity - close_pl - open_pl
      // Use pending_cash or option_short_value as proxy; safest: just report null if unavailable
      // Actually Tradier balances include `close_pl` which is realized day P&L
      const closePl = bal.close_pl != null ? parseFloat(bal.close_pl) : null
      const openPl = bal.pending_cash != null ? parseFloat(bal.pending_cash) : null
      const dayPnl = closePl != null ? closePl + (openPl || 0) : null

      // Count open positions
      let posCount = 0
      if (posData?.positions?.position) {
        const pos = posData.positions.position
        posCount = Array.isArray(pos) ? pos.length : 1
      }

      results.push({
        name: acct.name,
        account_id: accountId,
        total_equity: equity,
        option_buying_power: optionBp,
        day_pnl: dayPnl,
        open_positions_count: posCount,
      })
    }),
  )

  return results
}

/**
 * Get all open position OCC symbols for a sandbox account.
 * Used by the accounts page to cross-reference against bot positions.
 */
export async function getSandboxPositionSymbols(
  apiKey: string,
): Promise<string[]> {
  const accountId = await getAccountIdForKey(apiKey)
  if (!accountId) return []

  const data = await sandboxGet(
    `/accounts/${accountId}/positions`,
    undefined,
    apiKey,
  )
  if (!data?.positions?.position) return []

  let positions = data.positions.position
  if (!Array.isArray(positions)) positions = [positions]

  return positions.map((p: any) => p.symbol || '').filter(Boolean)
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
  maxPollMs: number = 90_000,
): Promise<number | null> {
  // Aggressive polling for fills. Market orders WILL fill — poll until they do.
  //
  // Behavior by status:
  //   pending / open / partially_filled → keep polling (no limit, these WILL fill)
  //   filled → return the fill price
  //   rejected / canceled / expired → confirm 5x then give up (genuinely terminal)
  //   API failure (null data) → retry indefinitely (transient network issue)
  //
  // maxPollMs: 0 = no cap (poll forever until fill or terminal status).
  // Default 90s for opens. Pass 0 for close orders where we MUST get the fill.
  // Backoff: 1s for first 10 polls, 2s for 10-20, 3s after that.
  const startMs = Date.now()
  const MAX_POLL_MS = maxPollMs
  let attempt = 0
  let terminalConfirmations = 0 // count consecutive rejected/canceled/expired reads

  while (MAX_POLL_MS === 0 || Date.now() - startMs < MAX_POLL_MS) {
    attempt++
    const delay = attempt <= 10 ? 1000 : attempt <= 20 ? 2000 : 3000

    const data = await sandboxGet(
      `/accounts/${accountId}/orders/${orderId}`,
      undefined,
      apiKey,
    )
    if (!data) {
      // API call failed — transient, keep retrying
      terminalConfirmations = 0
      await new Promise((r) => setTimeout(r, delay))
      continue
    }

    const order = data.order || {}
    const status = order.status || ''

    if (status === 'filled') {
      // avg_fill_price on order level for multileg
      if (order.avg_fill_price != null) {
        console.log(`[tradier] Order ${orderId} filled after ${attempt} polls (${((Date.now() - startMs) / 1000).toFixed(1)}s)`)
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
        if (total !== 0) {
          console.log(`[tradier] Order ${orderId} filled (leg calc) after ${attempt} polls (${((Date.now() - startMs) / 1000).toFixed(1)}s)`)
          return Math.abs(total)
        }
      }
      // filled but no price yet — keep polling (Tradier may populate price on next read)
      terminalConfirmations = 0
      await new Promise((r) => setTimeout(r, delay))
      continue
    }

    if (['pending', 'open', 'partially_filled'].includes(status)) {
      // Normal pre-fill states — poll indefinitely (within safety cap)
      terminalConfirmations = 0
      if (attempt % 10 === 0) {
        console.log(`[tradier] Order ${orderId} still ${status} after ${attempt} polls (${((Date.now() - startMs) / 1000).toFixed(1)}s) — continuing...`)
      }
      await new Promise((r) => setTimeout(r, delay))
      continue
    }

    // rejected / canceled / expired — these are genuinely terminal on Tradier.
    // Confirm 5 consecutive reads to be sure (in case of API glitch).
    terminalConfirmations++
    if (terminalConfirmations >= 5) {
      // Log the full rejection reason from Tradier so we can debug
      const reason = order.reason_description || order.reject_reason || order.reason || 'no reason provided'
      const tag = order.tag || ''
      console.error(
        `[tradier] Order ${orderId} confirmed ${status} after ${terminalConfirmations} consecutive reads ` +
        `(${attempt} total polls, ${((Date.now() - startMs) / 1000).toFixed(1)}s) — REASON: "${reason}" ` +
        `[tag=${tag}, qty=${order.quantity || 'N/A'}, class=${order.class || 'N/A'}]`,
      )
      // Log full order object for debugging (first rejection only)
      if (terminalConfirmations === 5) {
        console.error(`[tradier] Order ${orderId} FULL RESPONSE: ${JSON.stringify(order)}`)
      }
      return null
    }
    console.warn(`[tradier] Order ${orderId} shows ${status} at poll ${attempt} (confirmation ${terminalConfirmations}/5) — re-checking...`)
    await new Promise((r) => setTimeout(r, delay))
  }

  // Safety cap reached — should never happen for market orders
  console.error(
    `[tradier] Order ${orderId} polling safety cap reached after ${attempt} polls ` +
    `(${((Date.now() - startMs) / 1000).toFixed(1)}s) — returning null`,
  )
  return null
}

/**
 * Place an Iron Condor in ALL configured sandbox accounts.
 *
 * Sizing: uses the SMALLER of the paper-sized contract count and
 * what the sandbox account's buying power supports.
 * This keeps sandbox trades aligned with the paper account's capital.
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
  paperContracts: number,
  totalCredit: number,
  tag?: string,
  botName?: string,
): Promise<Record<string, SandboxOrderInfo>> {
  await ensureSandboxAccountsLoaded()
  const results: Record<string, SandboxOrderInfo> = {}

  // Filter accounts by bot (FLAME=User+Matt+Logan, SPARK+INFERNO=paper-only/none)
  const allowedAccounts = botName ? getAccountsForBot(botName) : null
  const eligibleAccounts = allowedAccounts
    ? _sandboxAccounts.filter((a) => allowedAccounts.includes(a.name))
    : _sandboxAccounts

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
  const userAccts = eligibleAccounts.filter((a) => a.name === 'User')
  const otherAccts = eligibleAccounts.filter((a) => a.name !== 'User')

  async function placeForAccount(acct: SandboxAccount) {
    try {
      const accountId = await getAccountIdForKey(acct.apiKey)
      if (!accountId) return

      // Query this account's OPTION buying power (not stock/day-trade BP)
      const bp = await getSandboxBuyingPower(acct.apiKey, accountId)
      const brokerMarginCheck = spreadWidth * 100  // $500 for $5 spread
      if (bp == null || bp < brokerMarginCheck) {
        console.warn(
          `Sandbox [${acct.name}]: optionBP=$${bp} insufficient (need $${brokerMarginCheck.toFixed(0)}/contract)`,
        )
        return
      }

      // Size to ~85% of this account's buying power.
      // FLAME: all 3 accounts (fill-only). SPARK+INFERNO: paper-only (no sandbox).
      // Math.floor guarantees whole contracts — no fractional orders.
      //
      // CRITICAL: Use BROKER margin (spread_width * 100), NOT net collateral.
      // Tradier requires margin = spread_width * 100 per contract (ignores credit offset).
      // Using net collateral (spread_width - credit) * 100 oversizes by ~40-60%.
      const SANDBOX_MAX_CONTRACTS = 200
      const brokerMarginPer = spreadWidth * 100  // Tradier margin: $500 for $5 spread
      const botShare = botName ? getBpShareForBot(botName, acct.name) : 1.0
      const usableBP = bp * botShare * 0.85
      const bpContracts = Math.max(1, Math.floor(usableBP / brokerMarginPer))
      // Size to 85% of account's option buying power. No paperContracts cap —
      // sandbox accounts size independently based on their own BP.
      // Safety cap at 200 contracts to prevent runaway orders.
      const acctContracts = Math.min(SANDBOX_MAX_CONTRACTS, bpContracts)

      const totalMargin = acctContracts * brokerMarginPer
      console.log(
        `Sandbox [${acct.name}]: optionBP=$${bp.toFixed(0)}, ` +
        `usable=$${usableBP.toFixed(0)} (${(botShare * 100).toFixed(0)}% × 85%), ` +
        `margin/contract=$${brokerMarginPer}, ` +
        `contracts=${acctContracts} (bp_calc=${bpContracts}, paperCap=${paperContracts}, hardCap=${SANDBOX_MAX_CONTRACTS}), ` +
        `totalMargin=$${totalMargin.toFixed(0)} (paper=${paperContracts})`,
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
      if (!result) {
        console.error(`Sandbox [${acct.name}]: Order POST returned null (HTTP error) — check logs above`)
        return
      }
      // Tradier may return errors at the order level (e.g., insufficient BP)
      if (result.errors) {
        console.error(`Sandbox [${acct.name}]: Order REJECTED at POST: ${JSON.stringify(result.errors)}`)
        return
      }
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
/**
 * Fetch raw Tradier quote data for multiple symbols, preserving all fields
 * (bid, ask, last, bid_date, ask_date, trade_date, etc.) for diagnostics.
 */
export async function getRawQuotes(
  symbols: string[],
): Promise<Record<string, Record<string, unknown>>> {
  await ensureQuoteApiKey()
  if (!_tradierApiKey || symbols.length === 0) return {}

  const data = await tradierGet('/markets/quotes', {
    symbols: symbols.join(','),
  })
  if (!data) return {}

  const results: Record<string, Record<string, unknown>> = {}
  let quotes = data.quotes?.quote
  if (!quotes) return results
  if (!Array.isArray(quotes)) quotes = [quotes]

  for (const q of quotes) {
    if (!q?.symbol) continue
    results[q.symbol] = q
  }
  return results
}

/** Returns the Tradier API base URL currently in use (for diagnostics). */
export function getTradierBaseUrl(): string {
  return TRADIER_BASE_URL
}

/**
 * Fetch Tradier timesales (minute bars) for a symbol.
 * Returns the last `minutes` candles for intraday comparison.
 */
export async function getTimesales(
  symbol: string,
  minutes: number = 10,
): Promise<Array<{ time: string; open: number; high: number; low: number; close: number; volume: number }>> {
  await ensureQuoteApiKey()
  if (!_tradierApiKey) return []

  const data = await tradierGet('/markets/timesales', {
    symbol,
    interval: '1min',
    session_filter: 'all',
  })
  if (!data) return []

  let series = data.series?.data
  if (!series) return []
  if (!Array.isArray(series)) series = [series]

  // Return last N candles
  return series.slice(-minutes).map((d: any) => ({
    time: d.time || d.timestamp,
    open: parseFloat(d.open || '0'),
    high: parseFloat(d.high || '0'),
    low: parseFloat(d.low || '0'),
    close: parseFloat(d.close || '0'),
    volume: parseInt(d.volume || '0', 10),
  }))
}

export async function getBatchOptionQuotes(
  occSymbols: string[],
): Promise<Record<string, LegQuote>> {
  await ensureQuoteApiKey()
  if (!_tradierApiKey || occSymbols.length === 0) return {}

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

/** Async version that ensures DB accounts are loaded first. */
export async function getLoadedSandboxAccountsAsync(): Promise<Array<{ name: string; apiKey: string }>> {
  await ensureSandboxAccountsLoaded()
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
 * Cascade close strategy (matches Databricks scanner):
 *   1. 4-leg multileg close (2 attempts)
 *   2. 2 × 2-leg spread close (put spread + call spread)
 *   3. 4 individual leg closes
 *
 * Reads per-account contract counts from sandboxOpenInfo (stored at open time).
 * Falls back to the paper position's contracts if legacy format.
 *
 * Returns Record<accountName, SandboxCloseInfo> for successful closes.
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
  await ensureSandboxAccountsLoaded()
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

        // Query Tradier for ACTUAL position quantities (not paper count).
        // This prevents quantity mismatches from pileup (multiple opens without closes).
        let closeQty = paperContracts
        try {
          const positions = await getSandboxAccountPositions(acct.apiKey)
          // Find the short put leg to determine actual quantity
          const shortPutPos = positions.find(p => p.symbol === occPs && p.quantity < 0)
          if (shortPutPos) {
            const actualQty = Math.abs(shortPutPos.quantity)
            if (actualQty !== closeQty) {
              console.warn(
                `[tradier] ${acct.name}: Tradier has ${actualQty} contracts (paper=${paperContracts}) ` +
                `for ${occPs} — using Tradier quantity`,
              )
              closeQty = actualQty
            }
          }
        } catch (posErr: unknown) {
          // Fall back to paper count / sandbox open info
          const acctInfo = sandboxOpenInfo?.[acct.name]
          if (acctInfo && typeof acctInfo === 'object' && 'contracts' in acctInfo) {
            closeQty = acctInfo.contracts
          }
          const msg = posErr instanceof Error ? posErr.message : String(posErr)
          console.warn(`[tradier] ${acct.name}: Position query failed, using paper count ${closeQty}: ${msg}`)
        }

        const tagStr = tag ? tag.slice(0, 255) : ''

        // --- Stage 1: 4-leg multileg close (2 attempts) ---
        const body4leg: Record<string, string> = {
          class: 'multileg',
          symbol: ticker,
          type: 'market',
          duration: 'day',
          'option_symbol[0]': occPs, 'side[0]': 'buy_to_close',  'quantity[0]': String(closeQty),
          'option_symbol[1]': occPl, 'side[1]': 'sell_to_close', 'quantity[1]': String(closeQty),
          'option_symbol[2]': occCs, 'side[2]': 'buy_to_close',  'quantity[2]': String(closeQty),
          'option_symbol[3]': occCl, 'side[3]': 'sell_to_close', 'quantity[3]': String(closeQty),
        }
        if (tagStr) body4leg.tag = tagStr

        let result = await sandboxPost(`/accounts/${accountId}/orders`, body4leg, acct.apiKey)
        if (result?.order?.id) {
          let fillPrice: number | null = null
          try { fillPrice = await getOrderFillPrice(acct.apiKey, accountId, result.order.id, 0) } catch { /* non-fatal */ }
          results[acct.name] = { order_id: result.order.id, contracts: closeQty, fill_price: fillPrice }
          return
        }

        // Retry 4-leg after 1s
        await new Promise((r) => setTimeout(r, 1000))
        result = await sandboxPost(`/accounts/${accountId}/orders`, body4leg, acct.apiKey)
        if (result?.order?.id) {
          let fillPrice: number | null = null
          try { fillPrice = await getOrderFillPrice(acct.apiKey, accountId, result.order.id, 0) } catch { /* non-fatal */ }
          results[acct.name] = { order_id: result.order.id, contracts: closeQty, fill_price: fillPrice }
          return
        }

        // --- Stage 2: 2 × 2-leg spread close ---
        console.warn(`Sandbox IC close 4-leg FAILED [${acct.name}] — falling back to 2x 2-leg spreads`)
        const putSpreadBody: Record<string, string> = {
          class: 'multileg', symbol: ticker, type: 'market', duration: 'day',
          'option_symbol[0]': occPs, 'side[0]': 'buy_to_close',  'quantity[0]': String(closeQty),
          'option_symbol[1]': occPl, 'side[1]': 'sell_to_close', 'quantity[1]': String(closeQty),
        }
        const callSpreadBody: Record<string, string> = {
          class: 'multileg', symbol: ticker, type: 'market', duration: 'day',
          'option_symbol[0]': occCs, 'side[0]': 'buy_to_close',  'quantity[0]': String(closeQty),
          'option_symbol[1]': occCl, 'side[1]': 'sell_to_close', 'quantity[1]': String(closeQty),
        }
        if (tagStr) { putSpreadBody.tag = tagStr; callSpreadBody.tag = tagStr }

        const [putResult, callResult] = await Promise.all([
          sandboxPost(`/accounts/${accountId}/orders`, putSpreadBody, acct.apiKey),
          sandboxPost(`/accounts/${accountId}/orders`, callSpreadBody, acct.apiKey),
        ])
        const putId = putResult?.order?.id
        const callId = callResult?.order?.id

        if (putId && callId) {
          // Poll BOTH spread orders for fill prices and combine them.
          // Each 2-leg close returns the net debit for that half of the IC.
          // Combined = put spread debit + call spread debit = total IC close cost.
          let fillPrice: number | null = null
          try {
            const [putFill, callFill] = await Promise.all([
              getOrderFillPrice(acct.apiKey, accountId, putId, 0),
              getOrderFillPrice(acct.apiKey, accountId, callId, 0),
            ])
            if (putFill != null && callFill != null) {
              fillPrice = putFill + callFill
              console.log(
                `[tradier] ${acct.name}: 2x2-leg close fills: put=$${putFill.toFixed(4)} + call=$${callFill.toFixed(4)} = $${fillPrice.toFixed(4)}`,
              )
            } else if (putFill != null) {
              fillPrice = putFill
              console.warn(`[tradier] ${acct.name}: 2x2-leg close: only put fill available ($${putFill.toFixed(4)}), call fill missing`)
            } else if (callFill != null) {
              fillPrice = callFill
              console.warn(`[tradier] ${acct.name}: 2x2-leg close: only call fill available ($${callFill.toFixed(4)}), put fill missing`)
            }
          } catch { /* non-fatal — fillPrice stays null, scanner uses estimated price */ }
          results[acct.name] = { order_id: putId, contracts: closeQty, fill_price: fillPrice }
          return
        }

        // --- Stage 3: 4 individual leg closes ---
        console.warn(
          `Sandbox IC close 2-leg FAILED [${acct.name}] ` +
          `(put=${putId ? 'OK' : 'FAIL'}, call=${callId ? 'OK' : 'FAIL'}) — ` +
          `falling back to individual legs`,
        )
        const legs: Array<{ occ: string; side: string; label: string }> = [
          { occ: occPs, side: 'buy_to_close',  label: 'put_short' },
          { occ: occPl, side: 'sell_to_close', label: 'put_long' },
          { occ: occCs, side: 'buy_to_close',  label: 'call_short' },
          { occ: occCl, side: 'sell_to_close', label: 'call_long' },
        ]
        let anyOk = false
        // Track individual leg order IDs for fill polling
        const legOrders: Array<{ orderId: number; side: string; label: string }> = []

        for (const leg of legs) {
          // Skip legs already closed by partial 2-leg success
          if (leg.label.startsWith('put') && putId) continue
          if (leg.label.startsWith('call') && callId) continue

          const legBody: Record<string, string> = {
            class: 'option', symbol: ticker, option_symbol: leg.occ,
            side: leg.side, quantity: String(closeQty), type: 'market', duration: 'day',
          }
          if (tagStr) legBody.tag = tagStr

          const legResult = await sandboxPost(`/accounts/${accountId}/orders`, legBody, acct.apiKey)
          if (legResult?.order?.id) {
            anyOk = true
            legOrders.push({ orderId: legResult.order.id, side: leg.side, label: leg.label })
          } else {
            console.error(`Sandbox leg CLOSE FAILED [${acct.name}]: ${leg.label}`)
          }
        }

        if (anyOk) {
          // Poll each individual leg for fill prices and combine.
          // buy_to_close legs = debit (cost), sell_to_close legs = credit (offset).
          // Net close cost = sum(buy_to_close fills) - sum(sell_to_close fills).
          let fillPrice: number | null = null
          try {
            const legFills = await Promise.all(
              legOrders.map(async (lo) => {
                const fp = await getOrderFillPrice(acct.apiKey, accountId, lo.orderId, 0)
                return { ...lo, fill: fp }
              }),
            )
            let totalDebit = 0
            let totalCredit = 0
            let allFilled = true
            for (const lf of legFills) {
              if (lf.fill == null) {
                allFilled = false
                console.warn(`[tradier] ${acct.name}: Individual leg ${lf.label} fill missing`)
                continue
              }
              if (lf.side === 'buy_to_close') {
                totalDebit += lf.fill
              } else {
                totalCredit += lf.fill
              }
            }
            if (allFilled || totalDebit > 0) {
              fillPrice = totalDebit - totalCredit
              console.log(
                `[tradier] ${acct.name}: Individual leg close fills: debit=$${totalDebit.toFixed(4)} - credit=$${totalCredit.toFixed(4)} = net $${fillPrice.toFixed(4)}` +
                (allFilled ? '' : ' (partial — some legs missing)'),
              )
            }
          } catch { /* non-fatal — fillPrice stays null, scanner uses estimated price */ }
          results[acct.name] = { order_id: legOrders[0]?.orderId ?? -1, contracts: closeQty, fill_price: fillPrice }
        } else {
          console.error(`Sandbox IC close ALL strategies FAILED [${acct.name}] — orphan likely`)
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err)
        console.warn(`Sandbox IC close failed [${acct.name}]: ${msg}`)
      }
    }),
  )

  return results
}

/**
 * Emergency close all open option positions on a sandbox account.
 * Queries Tradier for current positions and market-sells each one.
 * Used by post-EOD verification as a last resort.
 */
export async function emergencyCloseSandboxPositions(
  apiKey: string,
  accountName: string,
): Promise<{ closed: number; failed: number; details: string[] }> {
  const details: string[] = []
  let closed = 0
  let failed = 0

  try {
    const accountId = await getAccountIdForKey(apiKey)
    if (!accountId) {
      details.push(`No account ID found for ${accountName}`)
      return { closed, failed: 1, details }
    }

    const positions = await getSandboxAccountPositions(apiKey)
    const openPositions = positions.filter(p => p.quantity !== 0)

    if (openPositions.length === 0) {
      details.push(`${accountName}: No open positions`)
      return { closed, failed, details }
    }

    details.push(`${accountName}: Found ${openPositions.length} open positions to close`)

    for (const pos of openPositions) {
      const qty = Math.abs(pos.quantity)
      const side = pos.quantity > 0 ? 'sell_to_close' : 'buy_to_close'

      try {
        const body: Record<string, string> = {
          class: 'option',
          symbol: pos.symbol.slice(0, 3), // ticker from OCC
          option_symbol: pos.symbol,
          side,
          quantity: String(qty),
          type: 'market',
          duration: 'day',
        }
        const result = await sandboxPost(`/accounts/${accountId}/orders`, body, apiKey)
        if (result?.errors) {
          failed++
          details.push(`${accountName}: ORDER REJECTED ${pos.symbol} x${qty}: ${JSON.stringify(result.errors)}`)
          continue
        }
        if (result?.order?.id) {
          // VERIFY the close order actually filled — don't fire-and-forget.
          // Old behavior just counted order ID as "closed" but the order
          // could be rejected by Tradier, leaving the position open.
          const orderId = result.order.id
          const fillPrice = await getOrderFillPrice(apiKey, accountId, orderId, 15_000) // 15s timeout
          if (fillPrice != null) {
            closed++
            details.push(`${accountName}: Closed ${pos.symbol} x${qty} → order ${orderId} filled @ $${fillPrice.toFixed(4)}`)
          } else {
            // Order was placed but rejected/expired — position still open
            failed++
            details.push(`${accountName}: Close order ${orderId} for ${pos.symbol} x${qty} was REJECTED/EXPIRED (position still open)`)
          }
        } else {
          failed++
          details.push(`${accountName}: FAILED to close ${pos.symbol} x${qty} (no order ID)`)
        }
      } catch (err: unknown) {
        failed++
        const msg = err instanceof Error ? err.message : String(err)
        details.push(`${accountName}: ERROR closing ${pos.symbol}: ${msg}`)
      }
    }
  } catch (err: unknown) {
    failed++
    const msg = err instanceof Error ? err.message : String(err)
    details.push(`${accountName}: Fatal error: ${msg}`)
  }

  return { closed, failed, details }
}

// Expose for scanner re-poll and testing
export { getOrderFillPrice, getAccountIdForKey }

export const _testing = {
  getOrderFillPrice,
}
