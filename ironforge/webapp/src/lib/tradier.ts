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
       WHERE is_active = TRUE AND type = 'sandbox' ORDER BY id LIMIT 1`,
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

/* ------------------------------------------------------------------ */
/*  Circuit Breaker — stops hammering Tradier when it's down           */
/* ------------------------------------------------------------------ */

let _circuitOpenUntil = 0           // epoch ms; 0 = circuit closed
let _consecutiveFailures = 0
const CIRCUIT_BREAKER_THRESHOLD = 5
const CIRCUIT_BREAKER_COOLDOWN_MS = 5 * 60 * 1000 // 5 min

function recordTradierSuccess(): void {
  _consecutiveFailures = 0
  _circuitOpenUntil = 0
}

function recordTradierFailure(): void {
  _consecutiveFailures++
  if (_consecutiveFailures >= CIRCUIT_BREAKER_THRESHOLD) {
    _circuitOpenUntil = Date.now() + CIRCUIT_BREAKER_COOLDOWN_MS
    console.warn(
      `[tradier] Circuit breaker OPEN — ${_consecutiveFailures} consecutive failures. ` +
      `Cooling off for ${CIRCUIT_BREAKER_COOLDOWN_MS / 60_000} min.`,
    )
  }
}

function isCircuitOpen(): boolean {
  if (_circuitOpenUntil === 0) return false
  if (Date.now() > _circuitOpenUntil) {
    // Half-open: allow one retry
    _circuitOpenUntil = 0
    _consecutiveFailures = 0
    return false
  }
  return true
}

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
  // Circuit breaker: skip API call if Tradier is known to be down
  if (isCircuitOpen()) {
    return null
  }

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
    recordTradierFailure()
    if (err instanceof Error && err.name === 'AbortError') {
      console.error(`Tradier: ${endpoint} timed out after ${API_TIMEOUT_MS}ms`)
    } else {
      const msg = err instanceof Error ? err.message : String(err)
      console.error(`Tradier: ${endpoint} fetch failed: ${msg}`)
    }
    return null
  }

  if (!res.ok) {
    recordTradierFailure()
    console.error(`Tradier: ${endpoint} returned HTTP ${res.status} (${res.statusText})`)
    return null
  }
  recordTradierSuccess()
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

// Sandbox URL for paper trading orders.
// Production URL for live trading orders.
const SANDBOX_URL = 'https://sandbox.tradier.com/v1'
const PRODUCTION_URL = 'https://api.tradier.com/v1'

interface SandboxAccount {
  name: string
  apiKey: string
  cachedAccountId?: string
  baseUrl: string   // SANDBOX_URL or PRODUCTION_URL
  type: 'sandbox' | 'production'
}

/**
 * Bot → sandbox account mapping.
 *
 * SPARK:   User only — 1DTE real-money production bot. Trades on the User
 *          production account via api.tradier.com and is mirrored to the User
 *          sandbox for unrealized P&L comparison.
 * FLAME:   Paper-only — NO sandbox orders. Sizes from paper_account × 85%.
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
    accounts: [],  // Paper-only — no sandbox orders
    bpShare:  {},
  },
  spark: {
    accounts: ['User'],
    bpShare:  { User: 1.0 },
  },
  inferno: {
    accounts: [],  // Paper-only — no sandbox orders
    bpShare:  {},
  },
}

/**
 * Bot allowed to place real-money production orders.
 * SPARK is the sole production bot; everyone else is strictly paper/sandbox.
 */
export const PRODUCTION_BOT = 'spark'

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

  if (userKey) accounts.push({ name: 'User', apiKey: userKey, baseUrl: SANDBOX_URL, type: 'sandbox' })
  if (mattKey) accounts.push({ name: 'Matt', apiKey: mattKey, baseUrl: SANDBOX_URL, type: 'sandbox' })
  if (loganKey) accounts.push({ name: 'Logan', apiKey: loganKey, baseUrl: SANDBOX_URL, type: 'sandbox' })
  return accounts
}

let _sandboxAccounts = getSandboxAccountsFromEnv()
let _sandboxAccountsLoadedFromDb = false

/**
 * Load trading accounts from the ironforge_accounts database table.
 * Loads both sandbox and production accounts — production accounts route
 * orders to api.tradier.com (real money), sandbox to sandbox.tradier.com.
 * Called once on first use if env vars yielded zero accounts.
 */
let _dbLoadAttempts = 0
let _dbLoadLastAttemptTime = 0
const DB_LOAD_MAX_RETRIES = 5
// Cooldown after max retries exhausted — reduced from 60s to 15s so concurrent
// bot scans aren't blocked for a full minute by one bot's DB failure.
const DB_LOAD_COOLDOWN_MS = 15_000

async function ensureSandboxAccountsLoaded(): Promise<void> {
  // ALWAYS check DB — env vars only provide sandbox accounts, production accounts
  // live exclusively in the DB. The old check `if (_sandboxAccounts.length > 0) return`
  // caused production accounts to NEVER load when env vars were set.
  if (_sandboxAccountsLoadedFromDb) return

  // Cap retries to avoid infinite DB queries on persistent failures.
  // Auto-reset after 60s cooldown so the system self-heals without a redeploy
  // (e.g., DB was slow on Render cold start but is now ready).
  if (_dbLoadAttempts >= DB_LOAD_MAX_RETRIES) {
    if (Date.now() - _dbLoadLastAttemptTime > DB_LOAD_COOLDOWN_MS) {
      console.log('[tradier] DB load retry counter reset after 60s cooldown — retrying production account load')
      _dbLoadAttempts = 0
    } else {
      return
    }
  }
  _dbLoadAttempts++
  _dbLoadLastAttemptTime = Date.now()

  try {
    const { query: dbq } = await import('./db')

    // Load ALL active accounts (sandbox + production)
    const rows = await dbq(
      `SELECT person, api_key, account_id, type FROM ironforge_accounts
       WHERE is_active = TRUE ORDER BY type, person`,
    )
    if (rows.length > 0) {
      // Build a NEW array atomically — prevents race conditions where a concurrent
      // reader iterates _sandboxAccounts while we're mutating it via .push().
      // Start with existing env-var accounts, then merge DB accounts.
      const merged: typeof _sandboxAccounts = [..._sandboxAccounts]
      const seen = new Set<string>(merged.map(a => a.apiKey))
      for (const row of rows) {
        const key = row.api_key?.trim()
        if (!key || seen.has(key)) continue
        seen.add(key)
        const name = row.person || 'User'
        const acctType = row.type === 'production' ? 'production' as const : 'sandbox' as const
        const baseUrl = acctType === 'production' ? PRODUCTION_URL : SANDBOX_URL
        merged.push({ name, apiKey: key, baseUrl, type: acctType })
      }
      // Atomic replacement — any concurrent reader sees either the old or new array, never a partial state
      _sandboxAccounts = merged
      const sandboxCount = _sandboxAccounts.filter(a => a.type === 'sandbox').length
      const prodCount = _sandboxAccounts.filter(a => a.type === 'production').length
      console.log(
        `[tradier] Loaded ${_sandboxAccounts.length} trading account(s) ` +
        `(${sandboxCount} sandbox, ${prodCount} production): ` +
        _sandboxAccounts.map(a => `${a.name}[${a.type}] (${a.apiKey.slice(0, 4)}...)`).join(', '),
      )
      // Only mark as loaded once we successfully loaded accounts (including production)
      _sandboxAccountsLoadedFromDb = true
    } else {
      console.warn(`[tradier] DB returned 0 active accounts (attempt ${_dbLoadAttempts}/${DB_LOAD_MAX_RETRIES}) — will retry next call`)
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[tradier] FAILED to load trading accounts from DB (attempt ${_dbLoadAttempts}/${DB_LOAD_MAX_RETRIES}): ${msg} — production accounts UNAVAILABLE, will retry next call`)
  }
}

async function sandboxPost(
  endpoint: string,
  body: Record<string, string>,
  apiKey: string,
  baseUrl: string = SANDBOX_URL,
): Promise<any> {
  if (!apiKey) return null

  const url = `${baseUrl}${endpoint}`

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
  baseUrl: string = SANDBOX_URL,
): Promise<any> {
  if (!apiKey) return null

  const url = new URL(`${baseUrl}${endpoint}`)
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

async function getAccountIdForKey(apiKey: string, baseUrl: string = SANDBOX_URL): Promise<string | null> {
  if (_accountIdCache[apiKey]) return _accountIdCache[apiKey]

  const data = await sandboxGet('/user/profile', undefined, apiKey, baseUrl)
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
export async function getSandboxBuyingPower(
  apiKey: string,
  accountId: string,
  baseUrl: string = SANDBOX_URL,
): Promise<number | null> {
  const data = await sandboxGet(
    `/accounts/${accountId}/balances`,
    undefined,
    apiKey,
    baseUrl,
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
  unrealized_pnl: number | null
  unrealized_pnl_pct: number | null
  open_positions_count: number
  account_type: 'sandbox' | 'production'
}

// Cache sandbox balances for 30s to avoid hammering Tradier on every SWR refresh
let _sbBalanceCache: { data: SandboxAccountBalance[]; fetchedAt: number } | null = null
const SB_BALANCE_CACHE_TTL = 30_000

/**
 * Fetch full balance + position count for all configured sandbox accounts.
 * Returns one entry per account. Values are null when Tradier API is unreachable.
 * Results are cached for 30s and sorted by name for stable display order.
 */
export async function getSandboxAccountBalances(): Promise<SandboxAccountBalance[]> {
  if (_sbBalanceCache && Date.now() - _sbBalanceCache.fetchedAt < SB_BALANCE_CACHE_TTL) {
    return _sbBalanceCache.data
  }
  await ensureSandboxAccountsLoaded()

  // Use Promise.all on mapped array to preserve stable order (matches _sandboxAccounts order)
  const results = await Promise.all(
    _sandboxAccounts.map(async (acct): Promise<SandboxAccountBalance> => {
      const accountId = await getAccountIdForKey(acct.apiKey, acct.baseUrl)
      if (!accountId) {
        return {
          name: acct.name,
          account_id: null,
          total_equity: null,
          option_buying_power: null,
          day_pnl: null,
          unrealized_pnl: null,
          unrealized_pnl_pct: null,
          open_positions_count: 0,
          account_type: acct.type,
        }
      }

      // Fetch balances and positions in parallel
      const [balData, posData] = await Promise.all([
        sandboxGet(`/accounts/${accountId}/balances`, undefined, acct.apiKey, acct.baseUrl),
        sandboxGet(`/accounts/${accountId}/positions`, undefined, acct.apiKey, acct.baseUrl),
      ])

      const bal = balData?.balances || {}
      const pdt = bal.pdt || {}
      const margin = bal.margin || {}
      const equity = bal.total_equity != null ? parseFloat(bal.total_equity) : null
      // Per Tradier docs: margin.option_buying_power (or pdt.option_buying_power)
      // is the real Option B.P. — matches what the Tradier UI shows as "Option B.P."
      const rawObp = margin.option_buying_power ?? pdt.option_buying_power
      const optionBp = rawObp != null ? parseFloat(rawObp) : equity

      // Tradier balances include `close_pl` (realized day P&L) and `open_pl` (unrealized P&L)
      const closePl = bal.close_pl != null ? parseFloat(bal.close_pl) : null
      const openPl = bal.pending_cash != null ? parseFloat(bal.pending_cash) : null
      const dayPnl = closePl != null ? closePl + (openPl || 0) : null

      // Count open positions and compute unrealized P&L
      // Sandbox API may not return gain_loss on positions, so we use multiple fallbacks:
      // 1. Sum gain_loss from positions (production API)
      // 2. Use open_pl from balances
      // 3. Compute from balance market_value minus net cost basis
      let posCount = 0
      let unrealizedPnl: number | null = null
      let totalAbsCostBasis = 0
      let netCostBasis = 0
      if (posData?.positions?.position) {
        const posList = Array.isArray(posData.positions.position)
          ? posData.positions.position
          : [posData.positions.position]
        posCount = posList.length
        let gainSum = 0
        let hasGainLoss = false
        for (const p of posList) {
          if (p.cost_basis != null) {
            const cb = parseFloat(p.cost_basis)
            totalAbsCostBasis += Math.abs(cb)
            netCostBasis += cb
          }
          if (p.gain_loss != null) {
            gainSum += parseFloat(p.gain_loss)
            hasGainLoss = true
          }
        }
        if (hasGainLoss) {
          unrealizedPnl = gainSum
        }
      }
      // Fallback 1: use open_pl from balances
      if (unrealizedPnl == null && bal.open_pl != null) {
        unrealizedPnl = parseFloat(bal.open_pl)
      }
      // Fallback 2: compute from balance market_value - net cost basis
      // market_value = net value of all options (long_market_value + short_market_value)
      if (unrealizedPnl == null && posCount > 0 && bal.market_value != null) {
        unrealizedPnl = parseFloat(bal.market_value) - netCostBasis
      }
      // Unrealized % relative to abs(net cost basis) to match Tradier's portfolio display
      // Tradier: Gain/Loss % = total_gain_loss / abs(net_cost_basis)
      // e.g. $3,234 gain / abs(-$7,795 net cost) = 41.49%
      const absNetCb = Math.abs(netCostBasis)
      const unrealizedPct = unrealizedPnl != null && absNetCb > 0
        ? (unrealizedPnl / absNetCb) * 100
        : null

      return {
        name: acct.name,
        account_id: accountId,
        total_equity: equity,
        option_buying_power: optionBp,
        day_pnl: dayPnl,
        unrealized_pnl: unrealizedPnl != null ? Math.round(unrealizedPnl * 100) / 100 : null,
        unrealized_pnl_pct: unrealizedPct != null ? Math.round(unrealizedPct * 10) / 10 : null,
        open_positions_count: posCount,
        account_type: acct.type,
      }
    }),
  )

  // Sort by person name for stable display order
  results.sort((a, b) => a.name.localeCompare(b.name))
  _sbBalanceCache = { data: results, fetchedAt: Date.now() }
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
  account_type?: 'sandbox' | 'production'
}

export interface SandboxCloseInfo {
  order_id: number
  contracts: number
  fill_price?: number | null
  account_type?: 'sandbox' | 'production'
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
  baseUrl: string = SANDBOX_URL,
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
      baseUrl,
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
  opts?: { sandboxOnly?: boolean; productionOnly?: boolean },
): Promise<Record<string, SandboxOrderInfo>> {
  await ensureSandboxAccountsLoaded()
  const results: Record<string, SandboxOrderInfo> = {}

  // Filter accounts by bot — reads from ironforge_accounts DB.
  // Must check BOTH person AND account type (sandbox/production) to prevent
  // placing orders on accounts that don't have this bot assigned.
  // e.g., Logan has sandbox with FLAME but production WITHOUT FLAME — production should NOT get FLAME orders.
  let eligibleAccounts = _sandboxAccounts
  if (botName) {
    try {
      const { query: dbq } = await import('./db')
      const botUpper = botName.toUpperCase()
      const allowedRows = await dbq(
        `SELECT DISTINCT person, type FROM ironforge_accounts
         WHERE is_active = TRUE AND type IN ('sandbox', 'production')
           AND (bot = $1 OR bot LIKE '%' || $1 || '%' OR bot = 'BOTH'
                OR bot = 'FLAME,SPARK,INFERNO')
         ORDER BY person, type`,
        [botUpper],
      )
      // Build a set of "person:type" keys for efficient matching
      const allowedKeys = new Set(allowedRows.map((r: any) => `${r.person}:${r.type}`))
      eligibleAccounts = _sandboxAccounts.filter((a) => {
        const key = `${a.name}:${a.type ?? 'sandbox'}`
        return allowedKeys.has(key)
      })
    } catch {
      // Fallback: use getAccountsForBotAsync (person-only matching)
      const allowedPersons = await getAccountsForBotAsync(botName)
      eligibleAccounts = _sandboxAccounts.filter((a) => allowedPersons.includes(a.name))
    }
  }
  console.log(
    `[tradier] placeIcOrderAllAccounts: bot=${botName ?? 'ALL'}, ` +
    `eligible=[${eligibleAccounts.map(a => `${a.name}:${a.type}`).join(', ')}]`,
  )

  // Shared OCC symbols — same strikes for all accounts
  const occPs = buildOccSymbol(ticker, expiration, putShort, 'P')
  const occPl = buildOccSymbol(ticker, expiration, putLong, 'P')
  const occCs = buildOccSymbol(ticker, expiration, callShort, 'C')
  const occCl = buildOccSymbol(ticker, expiration, callLong, 'C')

  // Collateral per contract
  const spreadWidth = putShort - putLong
  const collateralPer = Math.max(0, (spreadWidth - totalCredit) * 100)
  if (collateralPer <= 0) return results

  // Separate sandbox and production accounts.
  // Flow: User sandbox first → other sandbox in parallel → production independently.
  const sandboxAccts = eligibleAccounts.filter((a) => a.type !== 'production')
  let productionAccts = eligibleAccounts.filter((a) => a.type === 'production')
  const userAccts = sandboxAccts.filter((a) => a.name === 'User')
  const otherSandboxAccts = sandboxAccts.filter((a) => a.name !== 'User')

  // SAFETY (defense in depth): drop production accounts when the bot has
  // explicitly paused production trading. `getProductionAccountsForBot`
  // already returns [] when paused, but this path can be reached via
  // `eligibleAccounts` composed upstream from _sandboxAccounts directly —
  // we check the pause flag here too so no production order can slip
  // through after an operator hits the Pause button.
  if (productionAccts.length > 0 && botName) {
    try {
      const pause = await getProductionPauseState(botName)
      if (pause.paused) {
        console.warn(
          `[tradier] ${botName.toUpperCase()} production trading PAUSED ` +
          `(reason=${pause.paused_reason ?? 'n/a'}) — removing ${productionAccts.length} ` +
          `production account(s) from this order. Sandbox/paper unaffected.`,
        )
        productionAccts = []
      }
    } catch { /* pre-migration deploy — fall through to the primary gate below */ }
  }

  // SAFETY: Only SPARK is allowed to place production orders.
  // FLAME and INFERNO are paper-only bots — they must NEVER place real money orders.
  const productionBotUc = PRODUCTION_BOT.toUpperCase()
  const botUc = (botName || '').toUpperCase()
  if (productionAccts.length > 0 && botUc !== productionBotUc) {
    console.warn(
      `[tradier] BLOCKED: ${botUc} attempted production orders on ${productionAccts.length} account(s). ` +
      `Only ${productionBotUc} can trade production. Removing production accounts from this order.`,
    )
    productionAccts = []
  }

  // Load the PRODUCTION-scope config row ONCE per order so every production
  // account in this call sizes off the same knobs. We load it lazily (only
  // when production accounts are actually in scope) so sandbox-only paths
  // never touch the production config row.
  //   bp_pct      → deployment fraction of Tradier OBP (default 0.15)
  //   max_contracts → 0 = unlimited (bp_pct is the real cap)
  // If the production row is missing or malformed, we log + skip all
  // production accounts rather than falling back to paper values — matches
  // the plan's "no silent drop" requirement.
  let prodBpPct = 0
  let prodMaxContracts = 0
  let productionConfigOk = false
  if (productionAccts.length > 0 && botName) {
    try {
      const { loadProductionConfigFor } = await import('./scanner')
      const prodCfg = await loadProductionConfigFor(botName)
      if (prodCfg && prodCfg.bp_pct > 0 && prodCfg.bp_pct <= 1) {
        prodBpPct = prodCfg.bp_pct
        prodMaxContracts = Math.max(0, prodCfg.max_contracts)
        productionConfigOk = true
      } else {
        console.error(
          `[tradier] PRODUCTION_SIZE_DROP: no valid production config row for ${botName.toUpperCase()} ` +
          `(bp_pct=${prodCfg?.bp_pct ?? 'null'}). SKIPPING production accounts to prevent wrong-size orders.`,
        )
        // Also write to spark_logs so the failure has a durable audit trail
        try {
          const { dbExecute, botTable } = await import('./db')
          await dbExecute(
            `INSERT INTO ${botTable(botName, 'logs')} (level, message, details, dte_mode)
             VALUES ($1, $2, $3, $4)`,
            [
              'ERROR',
              `PRODUCTION_SIZE_DROP: production config missing or invalid (bp_pct=${prodCfg?.bp_pct ?? 'null'})`,
              JSON.stringify({ event: 'production_size_drop', bot: botName, cfg: prodCfg }),
              '1DTE',
            ],
          )
        } catch { /* audit write is best-effort; console is the canonical trace */ }
        productionAccts = []
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      console.error(`[tradier] PRODUCTION_SIZE_DROP: config load threw (${msg}) — SKIPPING production accounts`)
      productionAccts = []
    }
  }

  async function placeForAccount(acct: SandboxAccount) {
    try {
      const accountId = await getAccountIdForKey(acct.apiKey, acct.baseUrl)
      if (!accountId) {
        const label = acct.type === 'production' ? `PRODUCTION [${acct.name}]` : `Sandbox [${acct.name}]`
        console.error(`${label}: getAccountIdForKey returned null — API key invalid or Tradier unreachable. SKIPPING order.`)
        return
      }

      // Query this account's OPTION buying power (not stock/day-trade BP)
      const bp = await getSandboxBuyingPower(acct.apiKey, accountId, acct.baseUrl)
      const brokerMarginCheck = spreadWidth * 100  // $500 for $5 spread
      if (bp == null || bp < brokerMarginCheck) {
        console.warn(
          `Sandbox [${acct.name}]: optionBP=$${bp} insufficient (need $${brokerMarginCheck.toFixed(0)}/contract)`,
        )
        return
      }

      // Sizing model (one bp_pct per scope, no double-dip):
      //
      //   Paper/Sandbox: usableBP = bp × botShare × 0.85           (85% hardcoded,
      //                                                             matches paper
      //                                                             ledger semantics)
      //   Live/Production: usableBP = bp × botShare × prodBpPct    (0.15 from
      //                                                             spark_config's
      //                                                             production row)
      //
      // Contract count is floor(usableBP / broker_margin_per_contract). Tradier
      // requires margin = spread_width * 100 per contract (NOT net collateral).
      //
      // Production is NOT capped by paperContracts — production is sized
      // independently from the live Tradier account per operator's 15% rule.
      // The scanner's paper-sized paperContracts is only a cap for sandbox/paper
      // mirror orders (which must match paper contract count 1:1).
      const SANDBOX_MAX_CONTRACTS = 200
      const brokerMarginPer = spreadWidth * 100  // Tradier margin: $500 for $5 spread
      const sameTypeCount = eligibleAccounts.filter(a => a.type === acct.type).length
      const botShare = botName && sameTypeCount > 1
        ? 1.0 / sameTypeCount
        : 1.0

      // Per-scope bp_pct. Production reads from the siloed config row loaded
      // above; sandbox is hardcoded 0.85 (matches paper ledger).
      const bpPct = acct.type === 'production'
        ? prodBpPct  // 0.15 default; refuses to size if productionConfigOk=false
                     // (productionAccts was cleared above in that case, so we
                     // never reach here for prod without valid config)
        : 0.85

      if (acct.type === 'production' && !productionConfigOk) {
        // Defensive — should have been filtered out already
        console.error(`PRODUCTION [${acct.name}]: no valid production config, refusing to size`)
        return
      }

      const usableBP = bp * botShare * bpPct
      const bpContracts = Math.floor(usableBP / brokerMarginPer)
      if (bpContracts < 1) {
        const bpLabel = acct.type === 'production' ? `PRODUCTION [${acct.name}]` : `Sandbox [${acct.name}]`
        console.warn(
          `${bpLabel}: bp_pct=${(bpPct * 100).toFixed(1)}% → usableBP=$${usableBP.toFixed(0)} insufficient for 1 contract ($${brokerMarginPer}/ea)`,
        )
        return
      }

      // Contract-count cap depends on scope:
      //   Sandbox: min(hardCap, bpContracts, paperContracts) — must mirror paper
      //   Production: min(hardCap, bpContracts, spark_config.production.max_contracts)
      //               where max_contracts=0 means unlimited (bp_pct is the real cap)
      let acctContracts: number
      if (acct.type === 'production') {
        const prodCeiling = prodMaxContracts > 0 ? prodMaxContracts : Number.POSITIVE_INFINITY
        acctContracts = Math.min(SANDBOX_MAX_CONTRACTS, bpContracts, prodCeiling)
      } else {
        acctContracts = Math.min(SANDBOX_MAX_CONTRACTS, bpContracts, paperContracts)
      }

      const totalMargin = acctContracts * brokerMarginPer
      const sizeLabel = acct.type === 'production' ? `PRODUCTION [${acct.name}]` : `Sandbox [${acct.name}]`
      const capsDetail = acct.type === 'production'
        ? `bp_calc=${bpContracts}, prodMax=${prodMaxContracts > 0 ? prodMaxContracts : '∞'}, hardCap=${SANDBOX_MAX_CONTRACTS}`
        : `bp_calc=${bpContracts}, paperCap=${paperContracts}, hardCap=${SANDBOX_MAX_CONTRACTS}`
      console.log(
        `${sizeLabel}: optionBP=$${bp.toFixed(0)}, bp_pct=${(bpPct * 100).toFixed(1)}%, ` +
        `usable=$${usableBP.toFixed(0)} (${(bpPct * 100).toFixed(1)}% × ${(botShare * 100).toFixed(0)}%), ` +
        `margin/contract=$${brokerMarginPer}, ` +
        `contracts=${acctContracts} (${capsDetail}), ` +
        `totalMargin=$${totalMargin.toFixed(0)}`,
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

      const label = acct.type === 'production' ? `PRODUCTION [${acct.name}]` : `Sandbox [${acct.name}]`
      const result = await sandboxPost(
        `/accounts/${accountId}/orders`,
        orderBody,
        acct.apiKey,
        acct.baseUrl,
      )
      if (!result) {
        console.error(`${label}: Order POST returned null (HTTP error) — check logs above`)
        return
      }
      // Tradier may return errors at the order level (e.g., insufficient BP)
      if (result.errors) {
        console.error(`${label}: Order REJECTED at POST: ${JSON.stringify(result.errors)}`)
        return
      }
      if (result?.order?.id) {
        // Read back actual fill price.
        // Production market orders WILL fill — poll forever (maxPollMs=0) until Tradier confirms.
        // Sandbox uses 90s cap since sandbox fills are less critical.
        let fillPrice: number | null = null
        const pollTimeout = acct.type === 'production' ? 0 : 90_000
        const maxRetries = acct.type === 'production' ? 3 : 0
        for (let attempt = 0; attempt <= maxRetries; attempt++) {
          try {
            fillPrice = await getOrderFillPrice(acct.apiKey, accountId, result.order.id, pollTimeout, acct.baseUrl)
            break // Success — exit retry loop
          } catch (pollErr: unknown) {
            const pollMsg = pollErr instanceof Error ? pollErr.message : String(pollErr)
            if (acct.type === 'production') {
              console.error(
                `${label}: Fill poll FAILED (attempt ${attempt + 1}/${maxRetries + 1}): ${pollMsg}`,
              )
              if (attempt < maxRetries) {
                await new Promise((r) => setTimeout(r, 5000)) // 5s backoff before retry
              }
            }
            // For sandbox: single attempt, no retry
          }
        }

        // SAFETY: If fill price is null, check whether the order was rejected.
        // Tradier accepts orders (returns order ID) then rejects them asynchronously
        // (e.g., "Not enough day trading buying power"). A null fill price after
        // polling means either timeout or rejection. For PRODUCTION accounts, verify
        // the actual order status before recording — rejected orders must NOT be
        // recorded as positions.
        if (fillPrice == null) {
          try {
            const orderCheck = await sandboxGet(
              `/accounts/${accountId}/orders/${result.order.id}`,
              undefined,
              acct.apiKey,
              acct.baseUrl,
            )
            const orderStatus = orderCheck?.order?.status || 'unknown'
            const rejectReason = orderCheck?.order?.reason_description
              || orderCheck?.order?.reject_reason
              || orderCheck?.order?.reason
              || ''
            if (['rejected', 'canceled', 'expired'].includes(orderStatus)) {
              console.error(
                `${label}: Order ${result.order.id} was ${orderStatus.toUpperCase()} by Tradier: "${rejectReason}" — NOT recording position`,
              )
              return // Do NOT add to results — order never filled
            }
            // If status is still pending/open after timeout, log warning but still record
            // (for sandbox this is acceptable; for production it means something unusual)
            if (acct.type === 'production') {
              console.warn(
                `${label}: Order ${result.order.id} status="${orderStatus}" with no fill price after polling — recording with estimated credit`,
              )
            }
          } catch (checkErr: unknown) {
            const checkMsg = checkErr instanceof Error ? checkErr.message : String(checkErr)
            console.warn(`${label}: Could not verify order status: ${checkMsg}`)
          }
        }

        // Use composite key to avoid collision when same person has sandbox + production
        const resultKey = `${acct.name}:${acct.type ?? 'sandbox'}`
        results[resultKey] = {
          order_id: result.order.id,
          contracts: acctContracts,
          fill_price: fillPrice,
          account_type: acct.type ?? 'sandbox',
        }
      } else {
        console.error(`${label}: Order POST returned response but NO order.id — full response: ${JSON.stringify(result).slice(0, 500)}`)
      }
    } catch (err: any) {
      const errLabel = acct.type === 'production' ? `PRODUCTION [${acct.name}]` : `Sandbox [${acct.name}]`
      console.error(`${errLabel}: IC order FAILED: ${err.message}`)
    }
  }

  // Step 1: User sandbox first (sequential) — must fill before other sandbox accounts
  // Skip sandbox steps in productionOnly mode (used when sandbox already traded today)
  if (!opts?.productionOnly) {
    for (const acct of userAccts) await placeForAccount(acct)

    // Step 2: Other sandbox accounts in parallel (mirror trades)
    await Promise.all(otherSandboxAccts.map(placeForAccount))
  }

  // Step 3: Production accounts — run independently of sandbox fills.
  // Production and sandbox are separate systems; a sandbox rejection should
  // never prevent a production order from being placed.
  // Skip production on sandboxOnly mode (used by retry to prevent duplicate production orders).
  if (productionAccts.length > 0 && !opts?.sandboxOnly) {
    console.log(
      `[tradier] Placing orders on ${productionAccts.length} production account(s) independently`,
    )
    await Promise.all(productionAccts.map(placeForAccount))

    // Summary: how many production accounts got orders vs silently dropped
    const prodResults = Object.entries(results).filter(([, v]) => v.account_type === 'production')
    const prodFilled = prodResults.filter(([, v]) => v.fill_price && v.fill_price > 0)
    const prodNoFill = prodResults.filter(([, v]) => !v.fill_price || v.fill_price <= 0)
    const prodDropped = productionAccts.length - prodResults.length
    console.log(
      `[tradier] PRODUCTION SUMMARY: ${productionAccts.length} eligible, ` +
      `${prodFilled.length} filled, ${prodNoFill.length} no-fill, ` +
      `${prodDropped} silently dropped (never reached results)`,
    )
    if (prodDropped > 0) {
      const resultKeys = new Set(Object.keys(results))
      for (const acct of productionAccts) {
        const key = `${acct.name}:production`
        if (!resultKeys.has(key)) {
          console.error(`[tradier] PRODUCTION DROPPED: ${acct.name} — order never recorded. Check logs above for the cause.`)
        }
      }
    }
  } else if (eligibleAccounts.some(a => a.type === 'production')) {
    // Shouldn't happen — production accounts in eligible but not in productionAccts
    console.error(`[tradier] BUG: Production accounts exist in eligible but were filtered out of productionAccts`)
  }

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

/**
 * LegQuote + greeks, used by the Builder tab's leg breakdown.
 * Greeks come from Tradier's `/markets/quotes?greeks=true` — same endpoint
 * as getBatchOptionQuotes, one extra query param. Separate helper so
 * existing callers that only need price data aren't forced to pay the
 * tiny extra payload cost (and don't get potentially-null greeks fields
 * in their LegQuote typing).
 */
export interface LegQuoteWithGreeks extends LegQuote {
  delta: number | null
  gamma: number | null
  theta: number | null
  vega: number | null
  mid_iv: number | null
}

export async function getBatchOptionQuotesWithGreeks(
  occSymbols: string[],
): Promise<Record<string, LegQuoteWithGreeks>> {
  await ensureQuoteApiKey()
  if (!_tradierApiKey || occSymbols.length === 0) return {}

  const data = await tradierGet('/markets/quotes', {
    symbols: occSymbols.join(','),
    greeks: 'true',
  })
  if (!data) return {}

  const results: Record<string, LegQuoteWithGreeks> = {}
  let quotes = data.quotes?.quote
  if (!quotes) return results
  if (!Array.isArray(quotes)) quotes = [quotes]

  const numOrNull = (v: unknown): number | null => {
    if (v == null || v === '') return null
    const n = typeof v === 'number' ? v : parseFloat(String(v))
    return Number.isFinite(n) ? n : null
  }

  for (const q of quotes) {
    if (!q?.symbol || q.bid == null) continue
    const bid = parseFloat(q.bid || '0')
    const ask = parseFloat(q.ask || '0')
    const g = q.greeks || {}
    results[q.symbol] = {
      symbol: q.symbol,
      bid,
      ask,
      mid: Math.round(((bid + ask) / 2) * 10000) / 10000,
      last: parseFloat(q.last || '0'),
      delta: numOrNull(g.delta),
      gamma: numOrNull(g.gamma),
      theta: numOrNull(g.theta),
      vega: numOrNull(g.vega),
      mid_iv: numOrNull(g.mid_iv),
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
export async function getLoadedSandboxAccountsAsync(): Promise<Array<{ name: string; apiKey: string; baseUrl: string; type: 'sandbox' | 'production' }>> {
  await ensureSandboxAccountsLoaded()
  return _sandboxAccounts.map((a) => ({ name: a.name, apiKey: a.apiKey, baseUrl: a.baseUrl, type: a.type }))
}

/**
 * Force-reload sandbox accounts from DB and clear API key cache.
 * Call this after any account CRUD (create, update, delete) to ensure
 * the scanner picks up changes immediately instead of on next restart.
 */
export async function reloadSandboxAccounts(): Promise<void> {
  // Clear caches — including the retry counter so DB load actually happens
  _sandboxAccounts = []
  _sandboxAccountsLoadedFromDb = false
  _dbLoadAttempts = 0
  for (const key of Object.keys(_accountIdCache)) {
    delete _accountIdCache[key]
  }
  // Re-load from DB
  await ensureSandboxAccountsLoaded()
  console.log(`[tradier] Sandbox accounts reloaded (${_sandboxAccounts.length} account(s))`)
}

/**
 * Get the configured capital percentage for a specific account (by person name).
 * Reads from ironforge_accounts table. Defaults to 100 (%).
 *
 * IMPORTANT: capital_pct only applies to PRODUCTION accounts.
 * Sandbox/paper accounts always use 100% so the paper account gets
 * the full Tradier equity as its starting capital.
 */
export async function getCapitalPctForAccount(person: string, accountType?: 'sandbox' | 'production'): Promise<number> {
  // Sandbox accounts always use 100% — capital_pct is a production-only safety cap
  if (accountType !== 'production') return 100

  try {
    const { query: dbq } = await import('./db')
    const rows = await dbq(
      `SELECT capital_pct FROM ironforge_accounts
       WHERE person = '${person.replace(/'/g, "''")}' AND type = 'production' AND is_active = TRUE
       LIMIT 1`,
    )
    if (rows.length > 0 && rows[0].capital_pct != null) {
      const pct = parseInt(rows[0].capital_pct)
      return (pct >= 1 && pct <= 100) ? pct : 100
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[tradier] getCapitalPctForAccount('${person}') DB query failed: ${msg} — defaulting to 100%`)
  }
  return 100
}

/**
 * Get the allocated capital for a specific account.
 * = real Tradier total_equity × capital_pct / 100
 * Falls back to $10,000 × pct if Tradier is unreachable.
 */
export async function getAllocatedCapitalForAccount(person: string, accountType: 'sandbox' | 'production' = 'sandbox'): Promise<number> {
  const pct = await getCapitalPctForAccount(person, accountType)

  // Find the account's API key from DB and fetch total_equity (not OBP)
  // CRITICAL: Filter by BOTH person AND type to avoid returning the wrong account.
  // Without the type filter, ORDER BY type DESC returns 'sandbox' (s > p alphabetically),
  // causing production paper_account to sync with sandbox Tradier balance.
  try {
    const { query: dbq } = await import('./db')
    const rows = await dbq(
      `SELECT api_key, type FROM ironforge_accounts
       WHERE person = '${person.replace(/'/g, "''")}' AND type = '${accountType}' AND is_active = TRUE
       LIMIT 1`,
    )
    if (rows.length > 0 && rows[0].api_key) {
      const apiKey = rows[0].api_key.trim()
      const acctType = rows[0].type || 'sandbox'
      const baseUrl = acctType === 'production' ? PRODUCTION_URL : SANDBOX_URL
      const accountId = await getAccountIdForKey(apiKey, baseUrl)
      if (accountId) {
        const equity = await getSandboxTotalEquity(apiKey, accountId, baseUrl)
        if (equity != null) {
          const allocated = Math.round(equity * pct / 100 * 100) / 100
          console.log(`[tradier] getAllocatedCapital: ${person}[${accountType}] → equity=$${equity.toLocaleString()}, pct=${pct}%, allocated=$${allocated.toLocaleString()}`)
          return allocated
        }
      }
    }
  } catch { /* fallback */ }

  // Fallback: return a default
  return Math.round(10000 * pct / 100)
}

/**
 * Fetch total equity for a sandbox account (consistent with frontend display).
 * Uses total_equity, NOT option_buying_power.
 */
async function getSandboxTotalEquity(apiKey: string, accountId: string, baseUrl: string = SANDBOX_URL): Promise<number | null> {
  const data = await sandboxGet(`/accounts/${accountId}/balances`, undefined, apiKey, baseUrl)
  const equity = data?.balances?.total_equity
  return equity != null ? parseFloat(equity) : null
}

/**
 * Get the PDT enabled flag for a specific account (by person name).
 * Reads from ironforge_accounts table. Defaults to true.
 */
export async function getPdtEnabledForAccount(person: string, accountType?: 'sandbox' | 'production'): Promise<boolean> {
  try {
    const { query: dbq } = await import('./db')
    // Filter by type when provided to avoid returning wrong account's PDT setting.
    // Without this, a person with sandbox pdt_enabled=false + production pdt_enabled=true
    // would always return the sandbox value.
    const typeFilter = accountType ? `AND type = '${accountType}'` : ''
    const rows = await dbq(
      `SELECT pdt_enabled FROM ironforge_accounts
       WHERE person = '${person.replace(/'/g, "''")}' ${typeFilter} AND is_active = TRUE
       LIMIT 1`,
    )
    if (rows.length > 0 && rows[0].pdt_enabled != null) {
      return rows[0].pdt_enabled === true || rows[0].pdt_enabled === 'true'
    }
  } catch { /* fallback */ }
  return true
}

/**
 * Get sandbox accounts that a specific bot should trade on (DB-backed).
 * Queries ironforge_accounts for accounts assigned to this bot.
 * The bot field can be a single bot name or comma-separated (e.g. "FLAME,SPARK").
 * Falls back to the hardcoded BOT_ACCOUNTS if DB query fails.
 */
export async function getAccountsForBotAsync(botName: string): Promise<string[]> {
  try {
    const { query: dbq } = await import('./db')
    const botUpper = botName.toUpperCase()
    // Match accounts where the bot field contains this bot name
    // Handles: exact match ("FLAME"), comma-separated ("FLAME,SPARK"), or legacy "BOTH"
    // Match both sandbox and production accounts for trading.
    // Production accounts route orders to api.tradier.com (real money).
    const rows = await dbq(
      `SELECT DISTINCT person FROM ironforge_accounts
       WHERE is_active = TRUE AND type IN ('sandbox', 'production')
         AND (bot = $1 OR bot LIKE '%' || $1 || '%' OR bot = 'BOTH'
              OR bot = 'FLAME,SPARK,INFERNO')
       ORDER BY person`,
      [botUpper],
    )
    if (rows.length > 0) {
      return rows.map((r: any) => r.person)
    }
  } catch { /* fallback to hardcoded */ }
  return BOT_ACCOUNTS[botName]?.accounts ?? ['User']
}

/**
 * Fetch positions from a sandbox account and filter to the given OCC symbols.
 */
export async function getSandboxAccountPositions(
  apiKey: string,
  filterSymbols?: string[],
  baseUrl: string = SANDBOX_URL,
): Promise<SandboxPosition[]> {
  const accountId = await getAccountIdForKey(apiKey, baseUrl)
  if (!accountId) return []

  const data = await sandboxGet(
    `/accounts/${accountId}/positions`,
    undefined,
    apiKey,
    baseUrl,
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
  orderType?: 'market' | 'debit',
  limitPrice?: number,
  accountType?: 'sandbox' | 'production',
): Promise<Record<string, SandboxCloseInfo>> {
  await ensureSandboxAccountsLoaded()
  const results: Record<string, SandboxCloseInfo> = {}

  const occPs = buildOccSymbol(ticker, expiration, putShort, 'P')
  const occPl = buildOccSymbol(ticker, expiration, putLong, 'P')
  const occCs = buildOccSymbol(ticker, expiration, callShort, 'C')
  const occCl = buildOccSymbol(ticker, expiration, callLong, 'C')

  // Filter accounts by type: sandbox closes only go to sandbox, production only to production.
  // Without this filter, closing a sandbox position cascades to production (and vice versa).
  const accounts = accountType
    ? _sandboxAccounts.filter(a => (a.type ?? 'sandbox') === accountType)
    : _sandboxAccounts

  await Promise.all(
    accounts.map(async (acct) => {
      try {
        const accountId = await getAccountIdForKey(acct.apiKey, acct.baseUrl)
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
          // Try composite key first, then legacy plain name key
          const compositeKey = `${acct.name}:${acct.type ?? 'sandbox'}`
          const acctInfo = sandboxOpenInfo?.[compositeKey] ?? sandboxOpenInfo?.[acct.name]
          if (acctInfo && typeof acctInfo === 'object' && 'contracts' in acctInfo) {
            closeQty = acctInfo.contracts
          }
          const msg = posErr instanceof Error ? posErr.message : String(posErr)
          console.warn(`[tradier] ${acct.name}: Position query failed, using paper count ${closeQty}: ${msg}`)
        }

        const tagStr = tag ? tag.slice(0, 255) : ''

        // --- Stage 1: 4-leg multileg close (2 attempts) ---
        const effectiveOrderType = orderType ?? 'market'
        const body4leg: Record<string, string> = {
          class: 'multileg',
          symbol: ticker,
          type: effectiveOrderType,
          duration: 'day',
          'option_symbol[0]': occPs, 'side[0]': 'buy_to_close',  'quantity[0]': String(closeQty),
          'option_symbol[1]': occPl, 'side[1]': 'sell_to_close', 'quantity[1]': String(closeQty),
          'option_symbol[2]': occCs, 'side[2]': 'buy_to_close',  'quantity[2]': String(closeQty),
          'option_symbol[3]': occCl, 'side[3]': 'sell_to_close', 'quantity[3]': String(closeQty),
        }
        // For debit limit orders, set the max debit price (guarantees minimum return)
        if (effectiveOrderType === 'debit' && limitPrice != null) {
          body4leg.price = limitPrice.toFixed(2)
        }
        if (tagStr) body4leg.tag = tagStr

        // Limit orders may not fill immediately — poll for 60s vs unlimited for market
        const pollMs = effectiveOrderType === 'debit' ? 60_000 : 0

        // Composite key avoids collision when same person has sandbox + production
        const resultKey = `${acct.name}:${acct.type ?? 'sandbox'}`

        let result = await sandboxPost(`/accounts/${accountId}/orders`, body4leg, acct.apiKey, acct.baseUrl)
        if (result?.order?.id) {
          let fillPrice: number | null = null
          try { fillPrice = await getOrderFillPrice(acct.apiKey, accountId, result.order.id, pollMs, acct.baseUrl) } catch { /* non-fatal */ }
          results[resultKey] = { order_id: result.order.id, contracts: closeQty, fill_price: fillPrice, account_type: acct.type ?? 'sandbox' }
          return
        }

        // Retry 4-leg after 1s
        await new Promise((r) => setTimeout(r, 1000))
        result = await sandboxPost(`/accounts/${accountId}/orders`, body4leg, acct.apiKey, acct.baseUrl)
        if (result?.order?.id) {
          let fillPrice: number | null = null
          try { fillPrice = await getOrderFillPrice(acct.apiKey, accountId, result.order.id, pollMs, acct.baseUrl) } catch { /* non-fatal */ }
          results[resultKey] = { order_id: result.order.id, contracts: closeQty, fill_price: fillPrice, account_type: acct.type ?? 'sandbox' }
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
          sandboxPost(`/accounts/${accountId}/orders`, putSpreadBody, acct.apiKey, acct.baseUrl),
          sandboxPost(`/accounts/${accountId}/orders`, callSpreadBody, acct.apiKey, acct.baseUrl),
        ])
        const putId = putResult?.order?.id
        const callId = callResult?.order?.id

        if (putId && callId) {
          let fillPrice: number | null = null
          try {
            const [putFill, callFill] = await Promise.all([
              getOrderFillPrice(acct.apiKey, accountId, putId, 0, acct.baseUrl),
              getOrderFillPrice(acct.apiKey, accountId, callId, 0, acct.baseUrl),
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
          results[resultKey] = { order_id: putId, contracts: closeQty, fill_price: fillPrice, account_type: acct.type ?? 'sandbox' }
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

          const legResult = await sandboxPost(`/accounts/${accountId}/orders`, legBody, acct.apiKey, acct.baseUrl)
          if (legResult?.order?.id) {
            anyOk = true
            legOrders.push({ orderId: legResult.order.id, side: leg.side, label: leg.label })
          } else {
            console.error(`${acct.type === 'production' ? 'PRODUCTION' : 'Sandbox'} leg CLOSE FAILED [${acct.name}]: ${leg.label}`)
          }
        }

        if (anyOk) {
          let fillPrice: number | null = null
          try {
            const legFills = await Promise.all(
              legOrders.map(async (lo) => {
                const fp = await getOrderFillPrice(acct.apiKey, accountId, lo.orderId, 0, acct.baseUrl)
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
          results[resultKey] = { order_id: legOrders[0]?.orderId ?? -1, contracts: closeQty, fill_price: fillPrice, account_type: acct.type ?? 'sandbox' }
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
 * Cancel an open order on a Tradier sandbox account.
 * Used to cancel pending limit orders (e.g., unfilled profit target debit closes)
 * so the position can be re-evaluated or closed with a market order.
 */
export async function cancelSandboxOrder(
  orderId: number,
  apiKey?: string,
  baseUrl?: string,
): Promise<boolean> {
  // Find the right API key — try all sandbox accounts if not provided
  const accounts = apiKey ? [{ name: 'direct', apiKey, baseUrl: baseUrl || SANDBOX_URL }] : await getLoadedSandboxAccountsAsync()
  for (const acct of accounts) {
    try {
      const acctBaseUrl = ('baseUrl' in acct ? acct.baseUrl : SANDBOX_URL) as string
      const accountId = await getAccountIdForKey(acct.apiKey, acctBaseUrl)
      if (!accountId) continue

      const url = `${acctBaseUrl}/accounts/${accountId}/orders/${orderId}`
      const res = await fetch(url, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${acct.apiKey}`,
          Accept: 'application/json',
        },
        cache: 'no-store',
        signal: timeoutSignal(),
      })

      if (res.ok) {
        console.log(`[tradier] Order ${orderId} canceled on account ${acct.name}`)
        return true
      }

      // 404 = order already filled/canceled/expired — not an error
      if (res.status === 404) {
        console.log(`[tradier] Order ${orderId} not found (already filled/canceled) on ${acct.name}`)
        return true
      }

      const body = await res.text().catch(() => '')
      console.warn(`[tradier] Cancel order ${orderId} returned ${res.status} on ${acct.name}: ${body}`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      console.warn(`[tradier] Cancel order ${orderId} failed on ${acct.name}: ${msg}`)
    }
  }
  return false
}

/**
 * Emergency close all open option positions on a sandbox account.
 * Queries Tradier for current positions and market-sells each one.
 * Used by post-EOD verification as a last resort.
 */
export async function emergencyCloseSandboxPositions(
  apiKey: string,
  accountName: string,
  baseUrl: string = SANDBOX_URL,
): Promise<{ closed: number; failed: number; details: string[] }> {
  const details: string[] = []
  let closed = 0
  let failed = 0

  try {
    const accountId = await getAccountIdForKey(apiKey, baseUrl)
    if (!accountId) {
      details.push(`No account ID found for ${accountName}`)
      return { closed, failed: 1, details }
    }

    const positions = await getSandboxAccountPositions(apiKey, undefined, baseUrl)
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
        const result = await sandboxPost(`/accounts/${accountId}/orders`, body, apiKey, baseUrl)
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
          const fillPrice = await getOrderFillPrice(apiKey, accountId, orderId, 15_000, baseUrl) // 15s timeout
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

/**
 * Close only specific orphan positions (by OCC symbol) — leaves matching positions untouched.
 * Unlike emergencyCloseSandboxPositions which nukes ALL positions, this only closes
 * the symbols in the orphanSymbols set.
 */
export async function closeOrphanSandboxPositions(
  apiKey: string,
  accountName: string,
  orphanSymbols: Set<string>,
  baseUrl: string = SANDBOX_URL,
): Promise<{ closed: number; failed: number; details: string[] }> {
  const details: string[] = []
  let closed = 0
  let failed = 0

  try {
    const accountId = await getAccountIdForKey(apiKey, baseUrl)
    if (!accountId) {
      details.push(`No account ID found for ${accountName}`)
      return { closed, failed: 1, details }
    }

    const positions = await getSandboxAccountPositions(apiKey, undefined, baseUrl)
    const toClose = positions.filter(p => p.quantity !== 0 && orphanSymbols.has(p.symbol))

    if (toClose.length === 0) {
      details.push(`${accountName}: No orphan positions to close`)
      return { closed, failed, details }
    }

    details.push(`${accountName}: Closing ${toClose.length} orphan positions (preserving ${positions.filter(p => p.quantity !== 0).length - toClose.length} matched)`)

    for (const pos of toClose) {
      const qty = Math.abs(pos.quantity)
      const side = pos.quantity > 0 ? 'sell_to_close' : 'buy_to_close'

      try {
        const body: Record<string, string> = {
          class: 'option',
          symbol: pos.symbol.slice(0, 3),
          option_symbol: pos.symbol,
          side,
          quantity: String(qty),
          type: 'market',
          duration: 'day',
        }
        const result = await sandboxPost(`/accounts/${accountId}/orders`, body, apiKey, baseUrl)
        if (result?.errors) {
          failed++
          details.push(`${accountName}: ORPHAN CLOSE REJECTED ${pos.symbol} x${qty}: ${JSON.stringify(result.errors)}`)
          continue
        }
        if (result?.order?.id) {
          const orderId = result.order.id
          const fillPrice = await getOrderFillPrice(apiKey, accountId, orderId, 15_000, baseUrl)
          if (fillPrice != null) {
            closed++
            details.push(`${accountName}: Orphan closed ${pos.symbol} x${qty} → order ${orderId} filled @ $${fillPrice.toFixed(4)}`)
          } else {
            failed++
            details.push(`${accountName}: Orphan close ${orderId} for ${pos.symbol} x${qty} REJECTED/EXPIRED`)
          }
        } else {
          failed++
          details.push(`${accountName}: No order ID returned for orphan ${pos.symbol}`)
        }
      } catch (err: unknown) {
        failed++
        const msg = err instanceof Error ? err.message : String(err)
        details.push(`${accountName}: ERROR closing orphan ${pos.symbol}: ${msg}`)
      }
    }
  } catch (err: unknown) {
    failed++
    const msg = err instanceof Error ? err.message : String(err)
    details.push(`${accountName}: Fatal error: ${msg}`)
  }

  return { closed, failed, details }
}

/**
 * Close ALL open positions for a sandbox account via market orders.
 * Used when an account is deactivated to prevent orphaned positions.
 * Returns the number of positions successfully closed.
 */
export async function closeAllSandboxPositions(apiKey: string): Promise<number> {
  const accountId = await getAccountIdForKey(apiKey)
  if (!accountId) return 0

  const positions = await getSandboxAccountPositions(apiKey)
  const openPositions = positions.filter(p => p.quantity !== 0)
  if (openPositions.length === 0) return 0

  let closed = 0
  for (const pos of openPositions) {
    const qty = Math.abs(pos.quantity)
    const side = pos.quantity > 0 ? 'sell_to_close' : 'buy_to_close'
    try {
      const result = await sandboxPost(`/accounts/${accountId}/orders`, {
        class: 'option',
        symbol: pos.symbol.slice(0, 3),
        option_symbol: pos.symbol,
        side,
        quantity: String(qty),
        type: 'market',
        duration: 'day',
      }, apiKey)
      if (result?.order?.id) closed++
    } catch { /* best-effort */ }
  }
  return closed
}

/* ------------------------------------------------------------------ */
/*  Production account helpers (Production tab)                        */
/* ------------------------------------------------------------------ */

export interface ProductionAccount {
  name: string
  apiKey: string
  baseUrl: string
  accountId: string | null
}

export interface ProductionPauseState {
  bot_name: string
  paused: boolean
  paused_at: string | null
  paused_by: string | null
  paused_reason: string | null
  updated_at: string | null
}

/**
 * Read the production-pause flag for a bot from ironforge_production_pause.
 * When `paused=true`, the scanner MUST skip all production order placement
 * for that bot — paper/sandbox continue untouched. This is the canonical
 * source of truth; the scanner, balance helpers, and preflight all check
 * the same row so pausing is a single operator action.
 */
export async function getProductionPauseState(botName: string): Promise<ProductionPauseState> {
  try {
    const { query: dbq } = await import('./db')
    const rows = await dbq(
      `SELECT bot_name, paused, paused_at, paused_by, paused_reason, updated_at
       FROM ironforge_production_pause
       WHERE bot_name = $1
       LIMIT 1`,
      [botName.toUpperCase()],
    )
    if (rows.length > 0) {
      const r = rows[0] as {
        bot_name: string
        paused: boolean | string
        paused_at: Date | string | null
        paused_by: string | null
        paused_reason: string | null
        updated_at: Date | string | null
      }
      const toIso = (v: Date | string | null): string | null =>
        v == null ? null : v instanceof Date ? v.toISOString() : String(v)
      return {
        bot_name: r.bot_name,
        paused: r.paused === true || r.paused === 'true' || r.paused === 't',
        paused_at: toIso(r.paused_at),
        paused_by: r.paused_by,
        paused_reason: r.paused_reason,
        updated_at: toIso(r.updated_at),
      }
    }
  } catch {
    // Table may not exist yet on pre-migration deploys — treat as unpaused
    // (default safe behavior is "no pause active").
  }
  return {
    bot_name: botName.toUpperCase(),
    paused: false,
    paused_at: null,
    paused_by: null,
    paused_reason: null,
    updated_at: null,
  }
}

/**
 * Resolve the production-type broker accounts assigned to a bot.
 * Returns the live production accounts (api.tradier.com) this bot is
 * authorized to trade on. Filters out sandbox accounts.
 *
 * When production trading is paused for this bot, returns an empty array
 * so no code path can place real-money orders. The `getProductionPauseState`
 * reader is called by the API/UI/preflight to display pause status — so
 * this function staying empty is the single load-bearing behavior of the
 * pause flag on the trade side.
 */
export async function getProductionAccountsForBot(botName: string): Promise<ProductionAccount[]> {
  if (botName !== PRODUCTION_BOT) return []
  const pauseState = await getProductionPauseState(botName)
  if (pauseState.paused) {
    console.warn(
      `[tradier] ${botName.toUpperCase()} production trading PAUSED ` +
      `(reason=${pauseState.paused_reason ?? 'n/a'}, since=${pauseState.paused_at ?? 'n/a'}) — ` +
      `returning zero production accounts. Scanner will skip production orders; sandbox/paper unaffected.`,
    )
    return []
  }
  const allowedNames = new Set(await getAccountsForBotAsync(botName))
  const loaded = await getLoadedSandboxAccountsAsync()
  const prod = loaded.filter(a => a.type === 'production' && allowedNames.has(a.name))
  const result: ProductionAccount[] = []
  for (const a of prod) {
    const accountId = await getAccountIdForKey(a.apiKey, a.baseUrl)
    result.push({ name: a.name, apiKey: a.apiKey, baseUrl: a.baseUrl, accountId })
  }
  return result
}

export interface TradierBalanceDetail {
  account_id: string | null
  account_number: string | null
  total_equity: number | null
  total_cash: number | null
  option_buying_power: number | null
  stock_buying_power: number | null
  day_trade_buying_power: number | null
  cash_available: number | null
  open_pl: number | null
  close_pl: number | null
  market_value: number | null
}

/** Fetch Tradier /accounts/{id}/balances and normalize the fields the UI cares about. */
export async function getTradierBalanceDetail(
  apiKey: string,
  accountId: string,
  baseUrl: string,
): Promise<TradierBalanceDetail | null> {
  const data = await sandboxGet(`/accounts/${accountId}/balances`, undefined, apiKey, baseUrl)
  if (!data) return null
  const b = data.balances || {}
  const margin = b.margin || {}
  const pdt = b.pdt || {}
  const cash = b.cash || {}
  const numOrNull = (v: unknown): number | null => {
    if (v == null || v === '') return null
    const n = typeof v === 'number' ? v : parseFloat(String(v))
    return Number.isFinite(n) ? n : null
  }
  return {
    account_id: accountId,
    account_number: b.account_number ?? accountId,
    total_equity: numOrNull(b.total_equity),
    total_cash: numOrNull(b.total_cash),
    option_buying_power: numOrNull(margin.option_buying_power ?? pdt.option_buying_power),
    stock_buying_power: numOrNull(margin.stock_buying_power ?? pdt.stock_buying_power),
    day_trade_buying_power: numOrNull(pdt.day_trade_buying_power),
    cash_available: numOrNull(cash.cash_available),
    open_pl: numOrNull(b.open_pl),
    close_pl: numOrNull(b.close_pl),
    market_value: numOrNull(b.market_value),
  }
}

export interface TradierOrderLeg {
  option_symbol: string | null
  side: string | null
  quantity: number | null
  exec_quantity: number | null
  last_fill_price: number | null
  type: string | null
}

export interface TradierOrder {
  id: number | string
  status: string
  type: string | null
  duration: string | null
  side: string | null
  symbol: string | null
  quantity: number | null
  price: number | null
  avg_fill_price: number | null
  exec_quantity: number | null
  last_fill_price: number | null
  class: string | null
  create_date: string | null
  transaction_date: string | null
  tag: string | null
  reason_description: string | null
  legs: TradierOrderLeg[]
}

/**
 * List orders for a Tradier account. `status` filters server-side.
 * Typical values: 'open' (unfilled/working), 'filled', 'canceled', 'all'.
 */
export async function getTradierOrders(
  apiKey: string,
  accountId: string,
  baseUrl: string,
  status: 'open' | 'filled' | 'canceled' | 'all' = 'all',
): Promise<TradierOrder[]> {
  const params: Record<string, string> = { includeTags: 'true' }
  // Tradier supports ?status=open / filled / canceled. 'all' means omit the filter.
  if (status !== 'all') params.status = status
  const data = await sandboxGet(`/accounts/${accountId}/orders`, params, apiKey, baseUrl)
  if (!data) return []
  let orders = data.orders?.order
  if (!orders) return []
  if (!Array.isArray(orders)) orders = [orders]
  const numOrNull = (v: unknown): number | null => {
    if (v == null || v === '') return null
    const n = typeof v === 'number' ? v : parseFloat(String(v))
    return Number.isFinite(n) ? n : null
  }
  return orders.map((o: any): TradierOrder => {
    let legs = o.leg
    if (legs && !Array.isArray(legs)) legs = [legs]
    const legArr: TradierOrderLeg[] = Array.isArray(legs)
      ? legs.map((l: any) => ({
          option_symbol: l.option_symbol ?? null,
          side: l.side ?? null,
          quantity: numOrNull(l.quantity),
          exec_quantity: numOrNull(l.exec_quantity),
          last_fill_price: numOrNull(l.last_fill_price),
          type: l.type ?? null,
        }))
      : []
    return {
      id: o.id,
      status: String(o.status ?? ''),
      type: o.type ?? null,
      duration: o.duration ?? null,
      side: o.side ?? null,
      symbol: o.symbol ?? null,
      quantity: numOrNull(o.quantity),
      price: numOrNull(o.price),
      avg_fill_price: numOrNull(o.avg_fill_price),
      exec_quantity: numOrNull(o.exec_quantity),
      last_fill_price: numOrNull(o.last_fill_price),
      class: o.class ?? null,
      create_date: o.create_date ?? null,
      transaction_date: o.transaction_date ?? null,
      tag: o.tag ?? null,
      reason_description: o.reason_description ?? null,
      legs: legArr,
    }
  })
}

// Expose for scanner re-poll and testing
export { getOrderFillPrice, getAccountIdForKey }

/**
 * Single-order detail fetch. Returns the broker's current view of a
 * specific order — status, fill price, exec qty — in one call. Used by
 * the scanner's broker-gone recovery path (scanner.ts) and by the
 * fix-zero-pnl-trades backfill endpoint to recover the real close price
 * when the re-poll path bailed out too early.
 *
 * Returns null on network failure or if the response is unparseable —
 * caller decides the fallback.
 */
export interface TradierOrderDetails {
  order_id: number | string
  status: string | null
  type: string | null
  avg_fill_price: number | null
  last_fill_price: number | null
  exec_quantity: number | null
  quantity: number | null
  create_date: string | null
  transaction_date: string | null
}

export async function getTradierOrderDetails(
  apiKey: string,
  accountId: string,
  orderId: number | string,
  baseUrl: string,
): Promise<TradierOrderDetails | null> {
  const data = await sandboxGet(`/accounts/${accountId}/orders/${orderId}`, undefined, apiKey, baseUrl)
  if (!data) return null
  const o = data.order
  if (!o) return null
  const numOrNull = (v: unknown): number | null => {
    if (v == null || v === '') return null
    const n = typeof v === 'number' ? v : parseFloat(String(v))
    return Number.isFinite(n) ? n : null
  }
  return {
    order_id: o.id,
    status: o.status ?? null,
    type: o.type ?? null,
    avg_fill_price: numOrNull(o.avg_fill_price),
    last_fill_price: numOrNull(o.last_fill_price),
    exec_quantity: numOrNull(o.exec_quantity),
    quantity: numOrNull(o.quantity),
    create_date: o.create_date ?? null,
    transaction_date: o.transaction_date ?? null,
  }
}

export const _testing = {
  getOrderFillPrice,
  // Circuit breaker internals
  get _circuitOpenUntil() { return _circuitOpenUntil },
  set _circuitOpenUntil(v: number) { _circuitOpenUntil = v },
  get _consecutiveFailures() { return _consecutiveFailures },
  set _consecutiveFailures(v: number) { _consecutiveFailures = v },
  CIRCUIT_BREAKER_THRESHOLD,
  CIRCUIT_BREAKER_COOLDOWN_MS,
  recordTradierSuccess,
  recordTradierFailure,
  isCircuitOpen,
}
