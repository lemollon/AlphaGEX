/**
 * SPARK market-risk brief generator (Commit Q1 — foundation).
 *
 * Informational only — does NOT affect trading behavior. Produces a
 * beginner-friendly plain-English summary of what could challenge a 1DTE
 * Iron Condor today, plus a 0-10 risk score and ranked factor list.
 *
 * Pipeline:
 *   1. gatherInputs(briefType)
 *        — fetches SPY + VIX family + VVIX via Tradier quotes
 *        — reads today's open SPARK position (if any) + last 7 days of
 *          closed SPARK trades from the DB
 *        — computes VIX term structure (vix3m / vix - 1)
 *        — returns a compact JSON object
 *
 *   2. buildPrompt(inputs, briefType)
 *        — produces a system + user prompt pair optimized for a beginner
 *          audience (jargon gets inline definitions, every factor is tied
 *          back to the open IC position)
 *
 *   3. callClaude(messages)
 *        — uses `process.env.CLAUDE_API_KEY` (same key AlphaGEX uses)
 *        — model: claude-sonnet-4-6 (latest Sonnet)
 *        — ~800 max output tokens per brief
 *
 *   4. parseResponse(text)
 *        — extracts RISK_SCORE + FACTORS + SUMMARY + WATCH_NEXT_HOUR
 *          via regex. Falls back to storing raw text if parsing fails.
 *
 *   5. storeBrief(parsed, inputs)
 *        — INSERT into spark_market_briefs; returns the new row id.
 *
 * Used by:
 *   - POST /api/spark/briefs/generate (manual trigger, Q1)
 *   - scanner.ts cron hooks (auto-generation, Q2, not yet)
 */
import { dbQuery, dbExecute, num, botTable, dteMode } from './db'
import { getRawQuotes, isConfigured as isTradierConfigured } from './tradier'
import { fetchGexSnapshot } from './blaze/gex-client'
import { formatVolRegime, type AdvisorReport } from './volatility'

const ALPHAGEX_API_BASE = (process.env.ALPHAGEX_API_BASE || 'https://alphagex-api.onrender.com').replace(/\/$/, '')

// ── Constants ──────────────────────────────────────────────────────────

const ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
const ANTHROPIC_MODEL = 'claude-sonnet-4-6'
const ANTHROPIC_MAX_TOKENS = 1400
const ANTHROPIC_VERSION = '2023-06-01'

// SPY underlying + VIX family — all free via Tradier /markets/quotes.
const QUOTE_SYMBOLS = ['SPY', 'VIX', 'VVIX', 'VIX9D', 'VIX3M', 'VIX6M']

// ── Types ──────────────────────────────────────────────────────────────

export type BriefType = 'morning' | 'intraday' | 'eod_debrief'

export interface MarketState {
  spy_price: number | null
  vix: number | null
  vvix: number | null
  vix9d: number | null
  vix3m: number | null
  vix6m: number | null
  /** vix3m / vix - 1. Positive = contango (calm); negative = backwardation (stress). */
  term_structure: number | null
  /** Convenience: label the structure regime in plain English for the prompt. */
  term_structure_label: 'contango' | 'backwardation' | 'flat' | 'unknown'
  /** One-line volatility-regime advisory (from AlphaGEX /api/vix/regime-advisor),
   * e.g. "Exhaustion — lean long / buy the bounce, ~13 DTE over 3–8 trading days".
   * Optional — omitted when the advisor is unreachable AND no local fallback applies. */
  vol_regime?: string
}

/**
 * GEX (gamma-exposure) profile snapshot from the AlphaGEX backend — the same
 * feed BLAZE/FLARE trade off. Used by every brief so the language reflects
 * where dealer gamma is pinning or accelerating SPY today.
 *
 *   positive gamma  → dealers dampen moves  → range-bound / mean-reverting
 *                     (friendly to Iron Condors / premium selling,
 *                      hostile to directional debit spreads — they pin)
 *   negative gamma  → dealers amplify moves → trending / momentum
 *                     (dangerous for ICs, friendly to directional breakouts)
 */
export interface GexState {
  available: boolean
  spot: number | null
  net_gex: number | null
  flip_point: number | null
  call_wall: number | null
  put_wall: number | null
  /** raw upstream regime label, e.g. MODERATE_POSITIVE / HIGH_NEGATIVE / NEUTRAL */
  regime: string | null
  /** collapsed sign of the regime for prompt/footer logic */
  regime_kind: 'positive' | 'negative' | 'neutral' | 'unknown'
  /** 1-day 1-sigma expected move in dollars */
  sigma_1d: number | null
  /** (call_wall - spot) / spot * 100 — how much room up to the call wall */
  pct_to_call_wall: number | null
  /** (spot - put_wall) / spot * 100 — how much room down to the put wall */
  pct_to_put_wall: number | null
  /** where spot sits relative to the gamma flip point */
  spot_vs_flip: 'above' | 'below' | 'at' | 'unknown'
}

export interface PositionState {
  has_open_ic: boolean
  ticker: string | null
  expiration: string | null
  put_long: number | null
  put_short: number | null
  call_short: number | null
  call_long: number | null
  contracts: number | null
  entry_credit: number | null
  open_time: string | null
  person: string | null
  account_type: string | null
  /** distance from spot to short put as % of spot */
  pct_to_short_put: number | null
  /** distance from spot to short call as % of spot */
  pct_to_short_call: number | null

  // ── Directional debit-spread fields (BLAZE / FLARE only) ──────────────
  /** true when the open position is a directional vertical debit spread */
  is_directional: boolean
  /** which GEX setup fired the trade: wall_fade | wall_break | flip_cross */
  setup_type: string | null
  /** 'call' = bull call debit (bullish), 'put' = bear put debit (bearish) */
  spread_side: 'call' | 'put' | null
  /** plain-English directional bias */
  bias: 'bullish' | 'bearish' | null
  long_strike: number | null
  short_strike: number | null
  /** debit paid per contract (this IS the max loss for a debit spread) */
  debit: number | null
}

export interface RecentTrade {
  closed_at: string
  realized_pnl: number
  close_reason: string
  contracts: number
  credit: number
}

export interface BriefInputs {
  brief_type: BriefType
  ct_timestamp: string
  ct_hhmm: string
  market_state: MarketState
  gex_state: GexState
  position_state: PositionState
  recent_trades: RecentTrade[]
}

export interface ParsedBrief {
  risk_score: number | null
  factors: Array<{ title: string; detail: string }>
  summary: string
  watch_next_hour: string | null
  raw_text: string
}

// ── Input gathering ────────────────────────────────────────────────────

function ctNow(): Date {
  return new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
}
function ctHHMM(): string {
  return ctNow().toTimeString().slice(0, 5)
}

async function gatherMarketState(): Promise<MarketState> {
  if (!isTradierConfigured()) {
    return {
      spy_price: null, vix: null, vvix: null, vix9d: null,
      vix3m: null, vix6m: null, term_structure: null, term_structure_label: 'unknown',
    }
  }
  const quotes = await getRawQuotes(QUOTE_SYMBOLS).catch(() => ({} as Record<string, Record<string, unknown>>))
  const p = (sym: string): number | null => {
    const q = quotes[sym]
    if (!q) return null
    const rawLast = q.last
    const last = typeof rawLast === 'number'
      ? rawLast
      : (typeof rawLast === 'string' ? parseFloat(rawLast) : NaN)
    return Number.isFinite(last) ? last : null
  }
  const spy = p('SPY')
  const vix = p('VIX')
  const vix3m = p('VIX3M')
  const termStructure = (vix != null && vix3m != null && vix > 0)
    ? Math.round(((vix3m / vix) - 1) * 10000) / 10000
    : null
  const termLabel: MarketState['term_structure_label'] =
    termStructure == null ? 'unknown'
    : termStructure > 0.01 ? 'contango'
    : termStructure < -0.01 ? 'backwardation'
    : 'flat'
  return {
    spy_price: spy,
    vix,
    vvix: p('VVIX'),
    vix9d: p('VIX9D'),
    vix3m,
    vix6m: p('VIX6M'),
    term_structure: termStructure,
    term_structure_label: termLabel,
  }
}

function emptyGexState(): GexState {
  return {
    available: false, spot: null, net_gex: null, flip_point: null,
    call_wall: null, put_wall: null, regime: null, regime_kind: 'unknown',
    sigma_1d: null, pct_to_call_wall: null, pct_to_put_wall: null, spot_vs_flip: 'unknown',
  }
}

/** Collapse the upstream regime string (MODERATE_POSITIVE, HIGH_NEGATIVE, …)
 * into a plain sign the prompt and footer can reason about. */
function regimeKind(regime: string | null): GexState['regime_kind'] {
  if (!regime) return 'unknown'
  const u = regime.toUpperCase()
  if (u.includes('POSITIVE')) return 'positive'
  if (u.includes('NEGATIVE')) return 'negative'
  if (u.includes('NEUTRAL')) return 'neutral'
  return 'unknown'
}

/**
 * Fetch the SPY GEX profile. Uses a generous 30-min freshness window (vs the
 * live trader's strict 90s) because a brief only needs a recent-ish picture,
 * not a tick-accurate one. Any fetch/stale/parse error degrades gracefully to
 * an "unavailable" GexState so the brief still generates.
 */
async function gatherGexState(): Promise<GexState> {
  try {
    const s = await fetchGexSnapshot('SPY', 1800)
    const spot = Number.isFinite(s.spot) && s.spot > 0 ? s.spot : null
    const callWall = Number.isFinite(s.call_wall) && s.call_wall > 0 ? s.call_wall : null
    const putWall = Number.isFinite(s.put_wall) && s.put_wall > 0 ? s.put_wall : null
    const flip = Number.isFinite(s.flip_point) && s.flip_point > 0 ? s.flip_point : null
    const pctToCall = spot && callWall ? Math.round(((callWall - spot) / spot) * 10000) / 100 : null
    const pctToPut = spot && putWall ? Math.round(((spot - putWall) / spot) * 10000) / 100 : null
    const spotVsFlip: GexState['spot_vs_flip'] =
      spot && flip ? (spot > flip * 1.0005 ? 'above' : spot < flip * 0.9995 ? 'below' : 'at') : 'unknown'
    return {
      available: true,
      spot,
      net_gex: Number.isFinite(s.net_gex) ? s.net_gex : null,
      flip_point: flip,
      call_wall: callWall,
      put_wall: putWall,
      regime: s.regime || null,
      regime_kind: regimeKind(s.regime),
      sigma_1d: Number.isFinite(s.sigma_1d_band_width) && s.sigma_1d_band_width > 0 ? s.sigma_1d_band_width : null,
      pct_to_call_wall: pctToCall,
      pct_to_put_wall: pctToPut,
      spot_vs_flip: spotVsFlip,
    }
  } catch {
    return emptyGexState()
  }
}

/**
 * Fetch the AlphaGEX volatility-regime advisor and format its one-line summary.
 * Graceful + total: returns null on any failure (timeout, non-200, no usable
 * report) so the brief still generates. NEVER throws.
 */
async function gatherVolRegime(market: MarketState): Promise<string | null> {
  // 1) Try the advisor endpoint with a short timeout.
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)
    try {
      const resp = await fetch(`${ALPHAGEX_API_BASE}/api/vix/regime-advisor`, {
        signal: controller.signal,
      })
      if (resp.ok) {
        const data = await resp.json().catch(() => null)
        const report = (data?.report ?? null) as Partial<AdvisorReport> | null
        const line = formatVolRegime(report)
        if (line) return line
      }
    } finally {
      clearTimeout(timeout)
    }
  } catch {
    /* fall through to local fallback */
  }
  // 2) Local fallback from the already-fetched VIX family.
  const { vix, vix3m } = market
  if (vix != null && vix3m != null) {
    return vix > vix3m ? 'Backwardation (stressed)' : 'Contango'
  }
  // 3) Nothing usable — omit the line entirely.
  return null
}

async function gatherPositionState(bot: string, spotPrice: number | null): Promise<PositionState> {
  const profile = botProfile(bot)
  if (profile.kind === 'debit_spread') {
    return gatherDirectionalPositionState(bot, spotPrice)
  }
  // Production positions only — paper/sandbox contract counts don't represent
  // real-money risk and were polluting the brief (e.g. brief warned about a
  // 143-contract sandbox position when production held far less).
  // FLAME and INFERNO are paper-only so the account_type filter falls
  // through to whatever rows they have.
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${dte}'` : ''
  const accountFilter = bot === 'spark' ? `AND account_type = 'production'` : ''
  const rows = await dbQuery(
    `SELECT position_id, ticker, expiration,
            put_long_strike, put_short_strike,
            call_short_strike, call_long_strike,
            contracts, total_credit, open_time, person, account_type
     FROM ${botTable(bot, 'positions')}
     WHERE status = 'open' ${dteFilter} ${accountFilter}
     ORDER BY open_time DESC NULLS LAST`,
  )
  if (rows.length === 0) {
    return {
      has_open_ic: false,
      ticker: null, expiration: null,
      put_long: null, put_short: null, call_short: null, call_long: null,
      contracts: null, entry_credit: null,
      open_time: null, person: null, account_type: null,
      pct_to_short_put: null, pct_to_short_call: null,
      is_directional: false, setup_type: null, spread_side: null, bias: null,
      long_strike: null, short_strike: null, debit: null,
    }
  }
  const r = rows[0]
  const exp = r.expiration instanceof Date
    ? r.expiration.toISOString().slice(0, 10)
    : String(r.expiration).slice(0, 10)
  // Aggregate contracts across all open production ICs (multiple persons /
  // accounts can hold simultaneous production positions).
  const totalContracts = rows.reduce((sum, row) => sum + (Number(row.contracts) || 0), 0)
  // Credit-weighted average so the prompt sees a representative per-contract credit.
  const totalCreditDollars = rows.reduce(
    (sum, row) => sum + (num(row.total_credit) * (Number(row.contracts) || 0)),
    0,
  )
  const avgCredit = totalContracts > 0 ? totalCreditDollars / totalContracts : num(r.total_credit)
  const pctToShortPut = (spotPrice && r.put_short_strike)
    ? Math.round(((spotPrice - num(r.put_short_strike)) / spotPrice) * 10000) / 100
    : null
  const pctToShortCall = (spotPrice && r.call_short_strike)
    ? Math.round(((num(r.call_short_strike) - spotPrice) / spotPrice) * 10000) / 100
    : null
  return {
    has_open_ic: true,
    ticker: r.ticker || 'SPY',
    expiration: exp,
    put_long: num(r.put_long_strike),
    put_short: num(r.put_short_strike),
    call_short: num(r.call_short_strike),
    call_long: num(r.call_long_strike),
    contracts: totalContracts,
    entry_credit: avgCredit,
    open_time: r.open_time ? new Date(r.open_time).toISOString() : null,
    person: r.person ?? null,
    account_type: r.account_type ?? null,
    pct_to_short_put: pctToShortPut,
    pct_to_short_call: pctToShortCall,
    is_directional: false, setup_type: null, spread_side: null, bias: null,
    long_strike: null, short_strike: null, debit: null,
  }
}

/**
 * Position gatherer for the directional debit-spread bots (BLAZE / FLARE).
 * Their {bot}_positions rows reuse the IC schema with the unused side zeroed;
 * the live spread lives in the directional columns (setup_type, direction,
 * long_strike, short_strike, debit). BLAZE/FLARE are paper-only, so we scope
 * to the sandbox account (matching their own db reader).
 */
async function gatherDirectionalPositionState(bot: string, spotPrice: number | null): Promise<PositionState> {
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${dte}'` : ''
  const rows = await dbQuery(
    `SELECT setup_type, direction, long_strike, short_strike, debit,
            contracts, ticker, expiration, open_time, person, account_type
     FROM ${botTable(bot, 'positions')}
     WHERE status = 'open' ${dteFilter}
       AND COALESCE(account_type, 'sandbox') = 'sandbox'
     ORDER BY open_time DESC NULLS LAST`,
  )
  if (rows.length === 0) {
    return {
      has_open_ic: false,
      ticker: null, expiration: null,
      put_long: null, put_short: null, call_short: null, call_long: null,
      contracts: null, entry_credit: null,
      open_time: null, person: null, account_type: null,
      pct_to_short_put: null, pct_to_short_call: null,
      is_directional: true, setup_type: null, spread_side: null, bias: null,
      long_strike: null, short_strike: null, debit: null,
    }
  }
  const r = rows[0]
  const exp = r.expiration instanceof Date
    ? r.expiration.toISOString().slice(0, 10)
    : String(r.expiration).slice(0, 10)
  const side: 'call' | 'put' = r.direction === 'put' ? 'put' : 'call'
  const totalContracts = rows.reduce((sum, row) => sum + (Number(row.contracts) || 0), 0)
  const totalDebitWeighted = rows.reduce(
    (sum, row) => sum + (num(row.debit) * (Number(row.contracts) || 0)),
    0,
  )
  const avgDebit = totalContracts > 0 ? totalDebitWeighted / totalContracts : num(r.debit)
  const longStrike = num(r.long_strike)
  // % move still needed for the spread to push the long leg in-the-money.
  // Bull call: needs spot to rise toward the long strike; bear put: needs spot
  // to fall toward it. Expressed as signed distance in the favorable direction.
  return {
    has_open_ic: true,
    ticker: r.ticker || 'SPY',
    expiration: exp,
    put_long: null, put_short: null, call_short: null, call_long: null,
    contracts: totalContracts,
    entry_credit: null,
    open_time: r.open_time ? new Date(r.open_time).toISOString() : null,
    person: r.person ?? null,
    account_type: r.account_type ?? null,
    pct_to_short_put: null, pct_to_short_call: null,
    is_directional: true,
    setup_type: r.setup_type ? String(r.setup_type) : null,
    spread_side: side,
    bias: side === 'call' ? 'bullish' : 'bearish',
    long_strike: longStrike || null,
    short_strike: num(r.short_strike) || null,
    debit: avgDebit || null,
  }
}

async function gatherRecentTrades(bot: string): Promise<RecentTrade[]> {
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${dte}'` : ''
  const accountFilter = bot === 'spark' ? `AND account_type = 'production'` : ''
  // Directional bots (BLAZE/FLARE) record the size as `debit`, not `total_credit`.
  const sizeCol = botProfile(bot).kind === 'debit_spread' ? 'debit' : 'total_credit'
  const rows = await dbQuery(
    `SELECT close_time, realized_pnl, close_reason, contracts, ${sizeCol} AS size_amt
     FROM ${botTable(bot, 'positions')}
     WHERE status IN ('closed', 'expired')
       ${dteFilter}
       ${accountFilter}
       AND close_time >= NOW() - INTERVAL '7 days'
       AND realized_pnl IS NOT NULL
     ORDER BY close_time DESC
     LIMIT 10`,
  )
  return rows.map((r) => ({
    closed_at: r.close_time instanceof Date ? r.close_time.toISOString() : String(r.close_time),
    realized_pnl: num(r.realized_pnl),
    close_reason: r.close_reason || 'unknown',
    contracts: Number(r.contracts) || 0,
    credit: num(r.size_amt),
  }))
}

export async function gatherInputs(bot: string, briefType: BriefType): Promise<BriefInputs> {
  const marketState = await gatherMarketState()
  const gexState = await gatherGexState()
  // Best-effort vol-regime advisory line (never throws; null → omitted).
  marketState.vol_regime = (await gatherVolRegime(marketState).catch(() => null)) ?? undefined
  // GEX carries a fresher spot than Tradier's last when SPY quote is stale/null.
  const spotForPosition = marketState.spy_price ?? gexState.spot
  const positionState = await gatherPositionState(bot, spotForPosition)
  const recentTrades = await gatherRecentTrades(bot)
  return {
    brief_type: briefType,
    ct_timestamp: ctNow().toISOString(),
    ct_hhmm: ctHHMM(),
    market_state: marketState,
    gex_state: gexState,
    position_state: positionState,
    recent_trades: recentTrades,
  }
}

// ── Prompt builders ────────────────────────────────────────────────────

/**
 * kind drives the entire framing of the brief:
 *   - iron_condor / put_credit_spread → PREMIUM-SELLING bots. They WANT SPY to
 *     stay in a range (or not drop hard). Risk = a big move. Positive-gamma GEX
 *     is friendly (dealers pin); negative-gamma is dangerous.
 *   - debit_spread → DIRECTIONAL bots (BLAZE/FLARE). They WANT a move in their
 *     favor. Risk = chop / pinning / reversal. Negative-gamma GEX is friendly
 *     (dealers amplify); positive-gamma pins them and is hostile.
 */
type BotKind = 'iron_condor' | 'put_credit_spread' | 'debit_spread'

interface BotProfile {
  name: string
  strategy: string
  dte_label: string
  kind: BotKind
}

const BOT_PROFILES: Record<string, BotProfile> = {
  spark: {
    name: 'SPARK',
    strategy: '1DTE Iron Condor on SPY',
    dte_label: '1DTE',
    kind: 'iron_condor',
  },
  flame: {
    name: 'FLAME',
    strategy: '2DTE Put Credit Spread on SPY',
    dte_label: '2DTE',
    kind: 'put_credit_spread',
  },
  inferno: {
    name: 'INFERNO',
    strategy: '0DTE Iron Condor on SPY (FORTRESS-style aggressive)',
    dte_label: '0DTE',
    kind: 'iron_condor',
  },
  blaze: {
    name: 'BLAZE',
    strategy: '1DTE directional vertical DEBIT spread on SPY (bull-call or bear-put)',
    dte_label: '1DTE',
    kind: 'debit_spread',
  },
  flare: {
    name: 'FLARE',
    strategy: '0DTE directional vertical DEBIT spread on SPY (bull-call or bear-put)',
    dte_label: '0DTE',
    kind: 'debit_spread',
  },
}

function botProfile(bot: string): BotProfile {
  return BOT_PROFILES[bot] ?? BOT_PROFILES.spark
}

function buildSystemPrompt(bot: string): string {
  const p = botProfile(bot)
  const directional = p.kind === 'debit_spread'

  const accountScope = bot === 'spark'
    ? `ACCOUNT SCOPE: The "OPEN POSITION" and "RECENT TRADES" sections describe the LIVE PRODUCTION (real-money) account only. Do NOT speculate about, mention, or include contract counts from paper, sandbox, or any other account. If the prompt says no open position, do not invent one.`
    : `ACCOUNT SCOPE: ${p.name} is paper-only. The "OPEN POSITION" and "RECENT TRADES" sections describe the paper account. Do not speculate about a real-money account.`

  // What does the bot WANT, and what does the 0-10 score mean for it?
  const goalAndScore = directional
    ? `WHAT ${p.name} WANTS: ${p.name} buys a directional debit spread — a bet that SPY MOVES in one direction (a bull-call spread profits if SPY rises, a bear-put spread profits if SPY falls). It WANTS a clean move in its favor; it gets hurt by chop, pinning, or a reversal.
RISK_SCORE MEANING (0-10): how HOSTILE the tape is to today's directional setup. 0 = clean trend with a clear gamma edge in the bot's favor; 10 = choppy/pinned tape likely to stall or reverse the trade. Higher = worse.`
    : `WHAT ${p.name} WANTS: ${p.name} sells premium — it WANTS SPY to stay calm and ${p.kind === 'put_credit_spread' ? 'not drop hard' : 'stay inside a range'}. It gets hurt by a big move (in either direction for an iron condor; a sharp drop for a put credit spread).
RISK_SCORE MEANING (0-10): how much today's conditions THREATEN that calm. 0 = quiet, range-bound, friendly; 10 = a big move looks likely. Higher = worse.`

  // How to read the GEX profile for THIS kind of bot.
  const gexGuidance = directional
    ? `HOW TO READ GEX FOR A DIRECTIONAL BOT:
- "Negative gamma" = dealers amplify moves = trending/momentum tape = GOOD for a directional bet (it can run). "Positive gamma" = dealers dampen moves = range-bound/pinning tape = BAD (the move stalls and the spread bleeds out).
- The call wall acts as a ceiling/magnet above price; the put wall acts as a floor/magnet below. A bull-call spread wants room UP to the call wall; a bear-put spread wants room DOWN to the put wall. If price is pinned right at a wall, the directional move is unlikely.
- The flip point is the bull/bear pivot: above it leans positive-gamma (calmer), below it leans negative-gamma (more volatile).`
    : `HOW TO READ GEX FOR A PREMIUM-SELLING BOT:
- "Positive gamma" = dealers dampen moves = range-bound/mean-reverting tape = GOOD (SPY stays pinned, premium decays safely). "Negative gamma" = dealers amplify moves = trending tape = DANGEROUS (a move can run through your strikes).
- The call wall and put wall are the natural guardrails of the range — they often act as the edges SPY respects. If your short strikes sit beyond the walls, that's safer; inside them is more exposed.
- The flip point is where dealer hedging flips from dampening to amplifying. SPY sitting comfortably in positive-gamma territory (above the flip) is the calmest backdrop for selling premium.`

  return `You are a market advisor for ${p.name}, a ${p.strategy} bot. Write a SHORT, plain-English brief that a complete beginner can understand at a glance, while still giving a trader the key numbers. Be concise — make every sentence earn its place. Do not pad.

${accountScope}

${goalAndScore}

${gexGuidance}

OUTPUT FORMATTING — STRICT:
- Plain text only. NO markdown: no **bold**, *italics*, _underscores_, backticks, or "---" lines.
- Use a plain hyphen or em dash ( — ) between a factor title and its detail.

SUMMARY — REQUIRED, in this exact order:
PLAIN ENGLISH:
<2-3 short sentences, ZERO jargon. No "iron condor", "debit spread", "delta", "VIX", "gamma", "GEX", "flip point", "strike". Translate everything: a directional debit spread becomes "a bet that the market moves ${directional ? 'in our chosen direction' : '...'}"; selling premium becomes "a bet the market stays calm"; negative gamma becomes "conditions that let moves run"; positive gamma becomes "conditions that keep the market pinned in place"; high VIX becomes "the market expects bigger swings". Say what the bot is doing today, and the single biggest thing that could help or hurt it.>
FOR TRADERS:
<ONE tight sentence (two only if truly needed) with the precise read — name the regime/net-gamma, flip point, the relevant wall, VIX/term-structure, and tie it to the open position's strikes when one exists.>

FACTORS — the 2-3 things that matter most today (most important first):
1. <plain-language title> — <one-sentence why it matters; define any term inline; tie to the open position when there is one and to the GEX profile when relevant>
2. <title> — <detail>
3. <title> — <detail>   (only if it genuinely adds something)

WATCH_NEXT_HOUR:
<one sentence, understandable to a beginner, on the single thing to watch next.>

Your response MUST follow this exact structure:

RISK_SCORE: <integer 0-10>

FACTORS:
1. <title> — <detail>
2. <title> — <detail>

SUMMARY:
PLAIN ENGLISH:
<...>

FOR TRADERS:
<...>

WATCH_NEXT_HOUR:
<...>

Keep the whole thing under 320 words. Plain text only.`
}

function formatInputsForPrompt(bot: string, i: BriefInputs): string {
  const profile = botProfile(bot)
  const directional = profile.kind === 'debit_spread'
  const structureLabel = directional
    ? 'DIRECTIONAL DEBIT SPREAD'
    : profile.kind === 'put_credit_spread' ? 'PUT CREDIT SPREAD' : 'IRON CONDOR'
  const tradesLabel = directional ? 'spread' : (profile.kind === 'put_credit_spread' ? 'spread' : 'IC')
  const m = i.market_state
  const g = i.gex_state
  const p = i.position_state
  const lines: string[] = []
  lines.push(`BRIEF TYPE: ${i.brief_type}`)
  lines.push(`CURRENT TIME (CT): ${i.ct_hhmm} on ${i.ct_timestamp.slice(0, 10)}`)
  lines.push('')
  lines.push('MARKET STATE:')
  lines.push(`  SPY: ${m.spy_price != null ? `$${m.spy_price.toFixed(2)}` : 'n/a'}`)
  lines.push(`  VIX: ${m.vix != null ? m.vix.toFixed(2) : 'n/a'}`)
  lines.push(`  VVIX: ${m.vvix != null ? m.vvix.toFixed(2) : 'n/a'} (vol of vol)`)
  lines.push(`  VIX9D: ${m.vix9d != null ? m.vix9d.toFixed(2) : 'n/a'}  VIX3M: ${m.vix3m != null ? m.vix3m.toFixed(2) : 'n/a'}`)
  lines.push(`  Term structure: ${m.term_structure != null ? (m.term_structure * 100).toFixed(2) + '%' : 'n/a'} (${m.term_structure_label})`)
  if (m.vol_regime) lines.push(`  Volatility regime: ${m.vol_regime}`)
  lines.push('')

  // GEX PROFILE — fed to every bot; framing differs by kind (see system prompt).
  lines.push('GEX PROFILE (SPY dealer gamma):')
  if (!g.available) {
    lines.push('  (GEX feed unavailable right now — do not invent gamma levels; note the gap briefly and lean on VIX/term-structure instead.)')
  } else {
    const regimeWord =
      g.regime_kind === 'positive' ? 'POSITIVE gamma (dealers dampen moves → range-bound / pinning)'
      : g.regime_kind === 'negative' ? 'NEGATIVE gamma (dealers amplify moves → trending / momentum)'
      : g.regime_kind === 'neutral' ? 'NEUTRAL gamma (no strong dealer bias)'
      : 'unknown gamma regime'
    lines.push(`  Regime: ${g.regime ?? 'n/a'} — ${regimeWord}`)
    lines.push(`  Net GEX: ${g.net_gex != null ? (g.net_gex / 1e9).toFixed(2) + ' Bn' : 'n/a'}`)
    lines.push(`  Flip point: ${g.flip_point != null ? '$' + g.flip_point.toFixed(2) : 'n/a'} (spot is ${g.spot_vs_flip} the flip)`)
    lines.push(`  Call wall: ${g.call_wall != null ? '$' + g.call_wall.toFixed(2) : 'n/a'}${g.pct_to_call_wall != null ? ` (${g.pct_to_call_wall >= 0 ? '+' : ''}${g.pct_to_call_wall.toFixed(2)}% from spot)` : ''}`)
    lines.push(`  Put wall: ${g.put_wall != null ? '$' + g.put_wall.toFixed(2) : 'n/a'}${g.pct_to_put_wall != null ? ` (${g.pct_to_put_wall.toFixed(2)}% below spot)` : ''}`)
    lines.push(`  1-sigma 1-day move: ${g.sigma_1d != null ? '$' + g.sigma_1d.toFixed(2) : 'n/a'}`)
  }
  lines.push('')

  if (p.has_open_ic && directional) {
    lines.push(`OPEN ${structureLabel}:`)
    lines.push(`  ${p.contracts}x ${p.ticker} exp ${p.expiration} — ${p.bias?.toUpperCase()} (${p.spread_side === 'call' ? 'bull-call' : 'bear-put'} debit)`)
    if (p.setup_type) lines.push(`  Setup: ${p.setup_type}`)
    lines.push(`  Long ${p.long_strike} / Short ${p.short_strike}  (width $${p.long_strike != null && p.short_strike != null ? Math.abs(p.long_strike - p.short_strike).toFixed(0) : '?'})`)
    lines.push(`  Debit paid: $${(p.debit ?? 0).toFixed(2)}/contract (this is the max loss per contract)`)
    lines.push(`  Account: ${p.person ?? '?'} / ${p.account_type ?? 'sandbox'} (paper)`)
  } else if (p.has_open_ic) {
    lines.push(`OPEN ${structureLabel}:`)
    lines.push(`  ${p.contracts}x ${p.ticker} exp ${p.expiration}`)
    if (profile.kind === 'put_credit_spread') {
      lines.push(`  Put wing: ${p.put_long} / ${p.put_short}`)
    } else {
      lines.push(`  Put wing: ${p.put_long} / ${p.put_short}  Call wing: ${p.call_short} / ${p.call_long}`)
    }
    lines.push(`  Entry credit: $${(p.entry_credit ?? 0).toFixed(2)}/contract`)
    if (p.pct_to_short_put != null && (profile.kind === 'put_credit_spread' || p.pct_to_short_call != null)) {
      const callPart = profile.kind === 'put_credit_spread'
        ? ''
        : `  Distance to short call: ${(p.pct_to_short_call ?? 0).toFixed(2)}%`
      lines.push(`  Distance to short put: ${p.pct_to_short_put.toFixed(2)}%${callPart}`)
    }
    lines.push(`  Account: ${p.person ?? '?'} / ${p.account_type ?? '?'}`)
  } else if (directional) {
    lines.push(`OPEN ${structureLabel}: none right now. ${profile.name} is scanning for a directional setup today — describe what the GEX profile implies it would be hunting (a bullish bet if there's room up to the call wall in a momentum/negative-gamma tape, a bearish bet if there's room down to the put wall), and how favorable conditions look.`)
  } else {
    lines.push(`OPEN ${structureLabel}: none (no open ${profile.name} position right now)`)
  }
  lines.push('')
  lines.push(`RECENT ${profile.name} TRADES (last 7 days):`)
  if (i.recent_trades.length === 0) {
    lines.push('  (no closed trades in last 7 days)')
  } else {
    for (const t of i.recent_trades.slice(0, 7)) {
      const date = t.closed_at.slice(0, 10)
      const sizeNote = directional
        ? `debit $${t.credit.toFixed(2)}`
        : `credit $${t.credit.toFixed(2)}`
      lines.push(`  ${date}: ${t.contracts}x ${tradesLabel}, ${sizeNote} → ${t.realized_pnl >= 0 ? '+' : ''}$${t.realized_pnl.toFixed(2)} (${t.close_reason})`)
    }
  }
  lines.push('')
  lines.push(`STRATEGY REMINDER: ${profile.name} runs the ${profile.strategy} strategy. The brief must highlight what a beginner needs to watch today for THIS specific structure, using the GEX profile above through the right lens (${directional ? 'directional: it wants a move, negative-gamma helps, pinning hurts' : 'premium-selling: it wants calm, positive-gamma helps, a big move hurts'}).`)
  return lines.join('\n')
}

// ── Claude API ─────────────────────────────────────────────────────────

interface ClaudeAPIMessage {
  role: 'user' | 'assistant'
  content: string
}

async function callClaude(bot: string, messages: ClaudeAPIMessage[]): Promise<{ text: string; model: string }> {
  const apiKey = process.env.CLAUDE_API_KEY || process.env.ANTHROPIC_API_KEY
  if (!apiKey) {
    throw new Error('CLAUDE_API_KEY env var is not set — add it to IronForge Render environment.')
  }
  const body = {
    model: ANTHROPIC_MODEL,
    max_tokens: ANTHROPIC_MAX_TOKENS,
    system: buildSystemPrompt(bot),
    messages,
  }
  const resp = await fetch(ANTHROPIC_API_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'anthropic-version': ANTHROPIC_VERSION,
      'x-api-key': apiKey,
    },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    const errText = await resp.text().catch(() => '<unreadable>')
    throw new Error(`Claude API ${resp.status}: ${errText.slice(0, 500)}`)
  }
  const data = await resp.json()
  const textBlocks = Array.isArray(data?.content) ? data.content : []
  const text = textBlocks.map((b: any) => b?.text ?? '').join('').trim()
  const model = String(data?.model ?? ANTHROPIC_MODEL)
  if (!text) throw new Error('Claude API returned empty content')
  return { text, model }
}

// ── Response parsing ───────────────────────────────────────────────────

/** Strip markdown emphasis so it doesn't render as raw `**foo**` in the UI.
 * Scrubs asterisks unconditionally — Claude sometimes returns unbalanced
 * markers like `**Title*` which a paired-only regex would miss. The brief
 * body is plain English narrative, so there is no legitimate asterisk to
 * preserve. */
function stripMarkdown(s: string): string {
  return s
    .replace(/\*+/g, '')                          // ALL asterisks (paired or stray)
    .replace(/__([^_]+)__/g, '$1')                 // __bold__
    .replace(/(?<!\w)_([^_\n]+)_(?!\w)/g, '$1')    // _italic_ (preserve snake_case)
    .replace(/`([^`]+)`/g, '$1')                   // `code`
    .replace(/^\s*-{3,}\s*$/gm, '')                // --- separator lines
    .replace(/\s+-{3,}\s*$/g, '')                  // trailing " ---" on a line
    .trim()
}

export function parseResponse(raw: string): ParsedBrief {
  const scoreMatch = raw.match(/RISK_SCORE:\s*(\d+)/i)
  const risk = scoreMatch ? Math.max(0, Math.min(10, parseInt(scoreMatch[1], 10))) : null

  const factorsBlockMatch = raw.match(/FACTORS:\s*([\s\S]*?)(?:SUMMARY:|WATCH_NEXT_HOUR:|$)/i)
  const factors: Array<{ title: string; detail: string }> = []
  if (factorsBlockMatch) {
    const lines = factorsBlockMatch[1].split('\n').map((l) => l.trim()).filter(Boolean)
    for (const ln of lines) {
      // expected: "1. Title - detail" or "- Title: detail"
      const m = ln.match(/^(?:\d+[\.\)]|-|\*)\s*([^-:]{1,80})[-:]\s*(.+)$/)
      if (m) {
        factors.push({ title: stripMarkdown(m[1]), detail: stripMarkdown(m[2]) })
      } else if (factors.length > 0) {
        // continuation line — append to previous detail
        factors[factors.length - 1].detail = stripMarkdown(
          factors[factors.length - 1].detail + ' ' + ln,
        )
      }
    }
  }

  const summaryMatch = raw.match(/SUMMARY:\s*([\s\S]*?)(?:WATCH_NEXT_HOUR:|$)/i)
  const summary = stripMarkdown((summaryMatch ? summaryMatch[1] : raw))

  const watchMatch = raw.match(/WATCH_NEXT_HOUR:\s*([\s\S]*?)$/i)
  const watch = watchMatch ? stripMarkdown(watchMatch[1]) : null

  return {
    risk_score: risk,
    factors,
    summary,
    watch_next_hour: watch,
    raw_text: raw,
  }
}

// ── Storage ────────────────────────────────────────────────────────────

export async function storeBrief(bot: string, parsed: ParsedBrief, inputs: BriefInputs, model: string): Promise<number> {
  const ct = new Date(inputs.ct_timestamp)
  const briefDate = new Date(ct.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
    .toISOString().slice(0, 10)
  const g = inputs.gex_state
  const rows = await dbQuery(
    `INSERT INTO ${botTable(bot, 'market_briefs')}
      (brief_date, brief_type, risk_score, summary, factors_json, raw_inputs_json,
       spy_price, vix, vix3m, term_structure, model,
       gex_regime, gex_flip, gex_call_wall, gex_put_wall, gex_net_gex)
     VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10, $11,
             $12, $13, $14, $15, $16)
     RETURNING id`,
    [
      briefDate,
      inputs.brief_type,
      parsed.risk_score,
      parsed.summary,
      JSON.stringify({ factors: parsed.factors, watch_next_hour: parsed.watch_next_hour, raw: parsed.raw_text }),
      JSON.stringify(inputs),
      inputs.market_state.spy_price,
      inputs.market_state.vix,
      inputs.market_state.vix3m,
      inputs.market_state.term_structure,
      model,
      g.available ? g.regime : null,
      g.available ? g.flip_point : null,
      g.available ? g.call_wall : null,
      g.available ? g.put_wall : null,
      g.available ? g.net_gex : null,
    ],
  )
  return Number(rows[0]?.id ?? 0)
}

// ── Public orchestrator ────────────────────────────────────────────────

export async function generateBrief(bot: string, briefType: BriefType): Promise<{
  id: number
  brief: ParsedBrief
  inputs: BriefInputs
  model: string
}> {
  const inputs = await gatherInputs(bot, briefType)
  const userContent = formatInputsForPrompt(bot, inputs)
  const { text, model } = await callClaude(bot, [{ role: 'user', content: userContent }])
  const parsed = parseResponse(text)
  const id = await storeBrief(bot, parsed, inputs, model)
  // Audit log (best effort) — store source marker so we can trace cost later.
  const dte = dteMode(bot) ?? 'unknown'
  try {
    await dbExecute(
      `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
       VALUES ($1, $2, $3, $4)`,
      [
        'MARKET_BRIEF',
        `Brief #${id} (${briefType}) generated — risk_score=${parsed.risk_score ?? '?'}`,
        JSON.stringify({
          brief_id: id,
          brief_type: briefType,
          model,
          risk_score: parsed.risk_score,
          factor_count: parsed.factors.length,
        }),
        dte,
      ],
    )
  } catch { /* best-effort */ }
  return { id, brief: parsed, inputs, model }
}
