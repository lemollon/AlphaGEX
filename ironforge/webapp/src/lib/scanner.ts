/**
 * IronForge Scan Loop — runs INSIDE the Next.js process on Render.
 *
 * Every 1 minute, for FLAME (2DTE), SPARK (1DTE), and INFERNO (0DTE):
 *   1. If position is open → monitor MTM, check PT/SL/EOD
 *   2. If no position + within entry window + not traded today → try opening
 *   3. Log every scan, update heartbeat, take equity snapshot
 *
 * All trading logic mirrors force-trade/force-close route handlers exactly.
 * This module has ZERO Next.js dependencies — pure Node.js + pg + fetch.
 *
 * Production fixes ported from ironforge_scanner.py:
 *   1.  Per-bot config loading from DB (SD, PT%, SL%, entry_end, max_contracts, bp_pct)
 *   2.  Sliding profit target by time of day (MORNING/MIDDAY/AFTERNOON)
 *   3.  Consecutive MTM failure tracking + force-close at 10 failures
 *   4.  Collateral reconciliation every scan cycle
 *   5.  Double-close guard (check rowCount before updating paper_account)
 *   6.  EOD cutoff corrected: 15:45→14:45
 *   7.  Daily sandbox cleanup at market open
 *   8.  Pre-scan sandbox health check (paper-only fallback)
 *   9.  Post-EOD sandbox verification + emergency close
 *   10. Live buying power from open positions (not cached paper_account)
 *   11. Per-bot entry window (INFERNO=1430, others=1400)
 */

import { query, dbExecute, botTable, num, int, CT_TODAY } from './db'
import {
  getQuote,
  getOptionExpirations,
  getIcEntryCredit,
  getIcMarkToMarket,
  isConfigured,
  isConfiguredAsync,
  placeIcOrderAllAccounts,
  closeIcOrderAllAccounts,
  cancelSandboxOrder,
  getLoadedSandboxAccounts,
  getLoadedSandboxAccountsAsync,
  getSandboxAccountPositions,
  emergencyCloseSandboxPositions,
  closeOrphanSandboxPositions,
  getOrderFillPrice,
  getAccountIdForKey,
  buildOccSymbol,
  getAccountsForBot,
  getAccountsForBotAsync,
  getAllocatedCapitalForAccount,
  getPdtEnabledForAccount,
  getSandboxAccountBalances,
  type SandboxOrderInfo,
  type SandboxCloseInfo,
} from './tradier'

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const SCAN_INTERVAL_MS = 60 * 1000 // 1 minute
const MAX_CONSECUTIVE_MTM_FAILURES = 10

/**
 * Bot that owns real-money production trading.
 * Kept in sync with `PRODUCTION_BOT` in tradier.ts (safety gate).
 * SPARK is the sole production bot — paper-only for everyone else.
 */
const PRODUCTION_BOT = 'spark'
const PRODUCTION_BOT_DTE = '1DTE' // Matches BOTS[] entry for PRODUCTION_BOT

// Per-bot consecutive sandbox rejection tracking to avoid spamming Tradier
// with 1500+ rejected orders per day. After N consecutive rejections,
// back off exponentially (skip cycles) before retrying.
const _consecutiveRejects: Record<string, number> = { flame: 0, spark: 0, inferno: 0 }
const MAX_REJECTS_BEFORE_BACKOFF = 5  // After 5 rejections, start backing off
const BACKOFF_CYCLES = 10             // Skip 10 cycles (~10 min) between retries

// Per-bot sandbox cleanup verification gates.
// Each bot tracks its own cleanup state so one bot's failure doesn't block others.
const _sandboxCleanupVerified: Record<string, boolean> = { flame: false, spark: false, inferno: false }
const _sandboxCleanupVerifiedDate: Record<string, string> = { flame: '', spark: '', inferno: '' }

const BOTS = [
  { name: 'flame', dte: '2DTE', minDte: 2 },
  { name: 'spark', dte: '1DTE', minDte: 1 },
  { name: 'inferno', dte: '0DTE', minDte: 0 },
] as const

type BotDef = (typeof BOTS)[number]

/* ------------------------------------------------------------------ */
/*  Per-bot config — loaded from DB each cycle, falls back to defaults */
/* ------------------------------------------------------------------ */

interface BotConfig {
  sd: number
  pt_pct: number    // fraction, e.g. 0.30 = 30%
  sl_mult: number   // fraction, e.g. 2.0 = 200%
  entry_end: number // HHMM, e.g. 1400
  max_trades: number // 0 = unlimited
  max_contracts: number
  bp_pct: number
  starting_capital: number
  min_credit: number // minimum credit per contract to open a trade
}

/** Hardcoded defaults matching Python BOT_CONFIG */
const DEFAULT_CONFIG: Record<string, BotConfig> = {
  flame:   { sd: 1.2, pt_pct: 0.30, sl_mult: 2.0, entry_end: 1400, max_trades: 1, max_contracts: 0, bp_pct: 0.85, starting_capital: 10000, min_credit: 0.05 },
  spark:   { sd: 1.2, pt_pct: 0.30, sl_mult: 2.0, entry_end: 1400, max_trades: 1, max_contracts: 0, bp_pct: 0.85, starting_capital: 10000, min_credit: 0.05 },
  inferno: { sd: 1.0, pt_pct: 0.50, sl_mult: 2.0, entry_end: 1430, max_trades: 0, max_contracts: 9999, bp_pct: 0.85, starting_capital: 10000, min_credit: 0.15 },
}

/** DB column → config key mapping (with optional transform) */
const DB_TO_CFG: Record<string, { key: keyof BotConfig; transform?: (v: number) => number }> = {
  sd_multiplier:        { key: 'sd' },
  profit_target_pct:    { key: 'pt_pct', transform: (v) => v / 100 },    // DB stores 30.0 → 0.30
  stop_loss_pct:        { key: 'sl_mult', transform: (v) => v / 100 },   // DB stores 200.0 → 2.0
  max_contracts:        { key: 'max_contracts' },
  max_trades_per_day:   { key: 'max_trades' },
  buying_power_usage_pct: { key: 'bp_pct' },
  starting_capital:     { key: 'starting_capital' },
  min_credit:           { key: 'min_credit' },
}

/** Runtime config — mutated by loadConfigOverrides() each cycle */
const _botConfig: Record<string, BotConfig> = {
  flame:   { ...DEFAULT_CONFIG.flame },
  spark:   { ...DEFAULT_CONFIG.spark },
  inferno: { ...DEFAULT_CONFIG.inferno },
}

function cfg(bot: BotDef): BotConfig {
  return _botConfig[bot.name] ?? DEFAULT_CONFIG[bot.name]
}

/**
 * Look up the allocated capital for this bot from ironforge_accounts.
 * Uses the primary sandbox account (from BOT_ACCOUNTS hardcoded config,
 * typically 'User') to determine starting capital for the shared paper account.
 * Falls back to DEFAULT_CONFIG starting_capital if no accounts found.
 */
async function getStartingCapitalForBot(botName: string): Promise<number> {
  try {
    // Only fetch Tradier balance for bots that actually have sandbox accounts (FLAME).
    // Paper-only bots (SPARK, INFERNO) have no accounts — use configured default.
    const primaryAccounts = getAccountsForBot(botName)
    if (primaryAccounts.length === 0) {
      // Paper-only bot — no Tradier account, use config starting_capital
      return DEFAULT_CONFIG[botName]?.starting_capital ?? 10000
    }
    const primaryPerson = primaryAccounts[0]
    const allocated = await getAllocatedCapitalForAccount(primaryPerson, 'sandbox')
    if (allocated > 0) {
      console.log(
        `[scanner] ${botName.toUpperCase()} capital from sandbox account (${primaryPerson}): $${allocated.toLocaleString()}`,
      )
      return allocated
    }
  } catch { /* fallback */ }
  return DEFAULT_CONFIG[botName]?.starting_capital ?? 10000
}

/**
 * Read {bot}_config tables from PostgreSQL and merge into _botConfig.
 * Also reads allocated capital from ironforge_accounts (capital_pct × real balance).
 * Runs once per scan cycle. Falls back silently to defaults if table
 * doesn't exist or query fails.
 */
async function loadConfigOverrides(): Promise<void> {
  for (const bot of BOTS) {
    try {
      const rows = await query(
        `SELECT * FROM ${botTable(bot.name, 'config')} WHERE dte_mode = $1 LIMIT 1`,
        [bot.dte],
      )
      if (rows.length === 0) continue
      const row = rows[0]

      // Start from defaults so missing DB columns don't wipe config
      const merged: BotConfig = { ...DEFAULT_CONFIG[bot.name] }
      for (const [dbCol, mapping] of Object.entries(DB_TO_CFG)) {
        const val = row[dbCol]
        if (val == null) continue
        const n = Number(val)
        if (isNaN(n)) continue
        merged[mapping.key] = mapping.transform ? mapping.transform(n) : n
      }

      // entry_end from config table is stored as "14:00" string — parse to HHMM int
      const entryEndStr = row.entry_end
      if (entryEndStr && typeof entryEndStr === 'string' && entryEndStr.includes(':')) {
        const [h, m] = entryEndStr.split(':').map(Number)
        if (!isNaN(h) && !isNaN(m)) merged.entry_end = h * 100 + m
      }

      // Override starting_capital from ironforge_accounts (capital_pct × real balance)
      // Only for bots with Tradier accounts (FLAME). Paper-only bots (SPARK, INFERNO)
      // use the starting_capital from their DB config table — not Tradier.
      const botAccounts = getAccountsForBot(bot.name)
      if (botAccounts.length > 0) {
        try {
          const allocatedCap = await getStartingCapitalForBot(bot.name)
          if (allocatedCap > 0) {
            merged.starting_capital = allocatedCap
          }
        } catch { /* keep config default */ }
      }

      _botConfig[bot.name] = merged
      console.log(
        `[scanner] ${bot.name.toUpperCase()} config loaded: sd=${merged.sd}, pt=${merged.pt_pct}, ` +
        `sl=${merged.sl_mult}, entry_end=${merged.entry_end}, max_contracts=${merged.max_contracts}, ` +
        `max_trades=${merged.max_trades}, bp_pct=${merged.bp_pct}, starting_capital=$${merged.starting_capital.toLocaleString()}`,
      )
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      console.warn(`[scanner] ${bot.name.toUpperCase()} config load failed (using defaults): ${msg}`)
    }
  }

  // Sync paper_account starting_capital if it changed
  await syncPaperAccountCapital()
}

/**
 * Update paper_account.starting_capital when allocated capital changes.
 * Recalculates balance and buying_power to keep accounting consistent.
 */
async function syncPaperAccountCapital(): Promise<void> {
  for (const bot of BOTS) {
    const botCfg = cfg(bot)
    try {
      // Sync SANDBOX paper_account
      const rows = await query(
        `SELECT id, starting_capital, cumulative_pnl, collateral_in_use
         FROM ${botTable(bot.name, 'paper_account')}
         WHERE is_active = TRUE AND dte_mode = $1 AND COALESCE(account_type, 'sandbox') = 'sandbox'
         ORDER BY id DESC LIMIT 1`,
        [bot.dte],
      )
      if (rows.length > 0) {
        const current = num(rows[0].starting_capital)
        const target = botCfg.starting_capital

        // Only update if meaningful change (>$1 difference)
        if (Math.abs(current - target) >= 1) {
          const pnl = num(rows[0].cumulative_pnl)
          const collateral = num(rows[0].collateral_in_use)
          const newBalance = target + pnl
          const newBp = newBalance - collateral

          await query(
            `UPDATE ${botTable(bot.name, 'paper_account')}
             SET starting_capital = $1,
                 current_balance = $2,
                 buying_power = $3,
                 high_water_mark = GREATEST(high_water_mark, $2),
                 updated_at = NOW()
             WHERE id = $4`,
            [target, newBalance, newBp, rows[0].id],
          )
          console.log(
            `[scanner] ${bot.name.toUpperCase()} SANDBOX CAPITAL SYNCED: ` +
            `$${current.toLocaleString()} → $${target.toLocaleString()} ` +
            `(balance=$${newBalance.toLocaleString()}, BP=$${newBp.toLocaleString()})`,
          )
        }
      }

      // Sync PRODUCTION paper_accounts (each person independently)
      const prodRows = await query(
        `SELECT pa.id, pa.person, pa.starting_capital, pa.cumulative_pnl, pa.collateral_in_use
         FROM ${botTable(bot.name, 'paper_account')} pa
         WHERE pa.is_active = TRUE AND pa.dte_mode = $1 AND pa.account_type = 'production'`,
        [bot.dte],
      )
      for (const pa of prodRows) {
        try {
          const target = await getAllocatedCapitalForAccount(pa.person, 'production')
          const current = num(pa.starting_capital)
          if (Math.abs(current - target) < 1) continue

          const pnl = num(pa.cumulative_pnl)
          const collateral = num(pa.collateral_in_use)
          const newBalance = target + pnl
          const newBp = newBalance - collateral

          await query(
            `UPDATE ${botTable(bot.name, 'paper_account')}
             SET starting_capital = $1,
                 current_balance = $2,
                 buying_power = $3,
                 high_water_mark = GREATEST(high_water_mark, $2),
                 updated_at = NOW()
             WHERE id = $4`,
            [target, newBalance, newBp, pa.id],
          )
          console.log(
            `[scanner] ${bot.name.toUpperCase()} PRODUCTION CAPITAL SYNCED (${pa.person}): ` +
            `$${current.toLocaleString()} → $${target.toLocaleString()} ` +
            `(balance=$${newBalance.toLocaleString()}, BP=$${newBp.toLocaleString()})`,
          )
        } catch { /* non-critical — sandbox is the primary account */ }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      console.warn(`[scanner] ${bot.name.toUpperCase()} capital sync error: ${msg}`)
    }
  }
}

/* ------------------------------------------------------------------ */
/*  Consecutive MTM failure tracking (Fix 3)                           */
/* ------------------------------------------------------------------ */

const _mtmFailureCounts: Map<string, number> = new Map()

/* ------------------------------------------------------------------ */
/*  Sandbox health state (Fix 8)                                       */
/* ------------------------------------------------------------------ */

// Per-bot paper-only mode: when a bot's sandbox accounts are unreachable,
// only that bot switches to paper-only — other bots continue normally.
const _sandboxPaperOnly: Record<string, boolean> = { flame: false, spark: false, inferno: false }
// Per-bot daily cleanup tracking: prevents cleanup from running >1x per day per bot.
const _lastSandboxCleanupDate: Record<string, string | null> = { flame: null, spark: null, inferno: null }

/* ------------------------------------------------------------------ */
/*  Market hours (Central Time)                                        */
/* ------------------------------------------------------------------ */

function getCentralTime(): Date {
  const str = new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' })
  return new Date(str)
}

function ctHHMM(ct: Date): number {
  return ct.getHours() * 100 + ct.getMinutes()
}

function isMarketOpen(ct: Date): boolean {
  const dow = ct.getDay()
  if (dow === 0 || dow === 6) return false
  const hhmm = ctHHMM(ct)
  return hhmm >= 830 && hhmm <= 1500 // Fix: was 1530, market closes at 3:00 PM CT
}

/** Per-bot entry window using config entry_end (Fix 11) */
function isInEntryWindow(ct: Date, bot: BotDef): boolean {
  const dow = ct.getDay()
  if (dow === 0 || dow === 6) return false
  const hhmm = ctHHMM(ct)
  const entryEnd = cfg(bot).entry_end
  return hhmm >= 830 && hhmm <= entryEnd
}

/** EOD cutoff at 2:50 PM CT (was 2:45, originally 3:45 PM) */
function isAfterEodCutoff(ct: Date): boolean {
  return ctHHMM(ct) >= 1450
}

/* ------------------------------------------------------------------ */
/*  Sliding Profit Target (Fix 2)                                      */
/* ------------------------------------------------------------------ */

/**
 * Returns [profitTargetFraction, tierLabel] based on current CT time.
 * PT slides DOWN as the day progresses.
 *
 * FLAME/SPARK (base=0.30): MORNING 30% → MIDDAY 20% → AFTERNOON 15%
 * INFERNO    (0DTE):      MORNING 20% → MIDDAY 30% → AFTERNOON 50%
 *   Reversed for 0DTE: exit quickly in morning (direction uncertain, IV high),
 *   let theta work in afternoon (decay accelerates into close).
 */
function getSlidingProfitTarget(ct: Date, basePt: number, botName: string): [number, string] {
  const timeMinutes = ct.getHours() * 60 + ct.getMinutes()
  const isInferno = botName === 'inferno'

  if (timeMinutes < 630) { // before 10:30 AM CT
    if (isInferno) return [0.20, 'MORNING']
    return [basePt, 'MORNING']
  } else if (timeMinutes < 780) { // before 1:00 PM CT
    if (isInferno) return [0.30, 'MIDDAY']
    return [Math.max(0.10, basePt - 0.10), 'MIDDAY']
  } else {
    if (isInferno) return [0.50, 'AFTERNOON']
    return [Math.max(0.10, basePt - 0.15), 'AFTERNOON']
  }
}

/* ------------------------------------------------------------------ */
/*  Advisor (copied from force-trade — DO NOT CHANGE)                  */
/* ------------------------------------------------------------------ */

function evaluateAdvisor(vix: number, spot: number, expectedMove: number, dteMode: string) {
  const BASE_WP = 0.65
  let winProb = BASE_WP
  const factors: [string, number][] = []

  if (vix >= 15 && vix <= 22) { const a = 0.10; winProb += a; factors.push(['VIX_IDEAL', a]) }
  else if (vix < 15) { const a = -0.05; winProb += a; factors.push(['VIX_LOW_PREMIUMS', a]) }
  else if (vix <= 28) { const a = -0.05; winProb += a; factors.push(['VIX_ELEVATED', a]) }
  else { const a = -0.15; winProb += a; factors.push(['VIX_HIGH_RISK', a]) }

  const dow = getCentralTime().getDay()
  if (dow >= 2 && dow <= 4) { const a = 0.08; winProb += a; factors.push(['DAY_OPTIMAL', a]) }
  else if (dow === 1) { const a = 0.03; winProb += a; factors.push(['DAY_MONDAY', a]) }
  else if (dow === 5) { const a = -0.10; winProb += a; factors.push(['DAY_FRIDAY_RISK', a]) }
  else { const a = -0.20; winProb += a; factors.push(['DAY_WEEKEND', a]) }

  const emRatio = spot > 0 ? (expectedMove / spot * 100) : 1.0
  if (emRatio < 1.0) { const a = 0.08; winProb += a; factors.push(['EM_TIGHT', a]) }
  else if (emRatio <= 2.0) { factors.push(['EM_NORMAL', 0]) }
  else { const a = -0.08; winProb += a; factors.push(['EM_WIDE', a]) }

  if (dteMode === '2DTE') { const a = 0.03; winProb += a; factors.push(['DTE_2DAY_DECAY', a]) }
  else if (dteMode === '0DTE') { const a = -0.05; winProb += a; factors.push(['DTE_0DAY_AGGRESSIVE', a]) }
  else { const a = -0.02; winProb += a; factors.push(['DTE_1DAY_TIGHT', a]) }

  winProb = Math.max(0.10, Math.min(0.95, winProb))

  const pos = factors.filter(([, a]) => a > 0).length
  const neg = factors.filter(([, a]) => a < 0).length
  let confidence = pos === factors.length ? 0.85
    : neg === factors.length ? 0.25
    : pos > neg ? 0.60 + (pos / factors.length) * 0.20
    : 0.40
  confidence = Math.max(0.10, Math.min(0.95, confidence))

  const advice = winProb >= 0.60 && confidence >= 0.50 ? 'TRADE_FULL'
    : winProb >= 0.42 && confidence >= 0.35 ? 'TRADE_REDUCED'
    : 'SKIP'

  return {
    advice,
    winProbability: Math.round(winProb * 10000) / 10000,
    confidence: Math.round(confidence * 10000) / 10000,
    topFactors: factors,
    reasoning: `Advisor: ${advice} WP=${winProb.toFixed(2)} conf=${confidence.toFixed(2)}`,
  }
}

/* ------------------------------------------------------------------ */
/*  Strike calculation — now takes sdMult from config (Fix 1)          */
/* ------------------------------------------------------------------ */

function calculateStrikes(spot: number, expectedMove: number, sdMult: number) {
  const WIDTH = 5

  const minEM = spot * 0.005
  const em = Math.max(expectedMove, minEM)

  let putShort = Math.floor(spot - sdMult * em)
  let callShort = Math.ceil(spot + sdMult * em)
  let putLong = putShort - WIDTH
  let callLong = callShort + WIDTH

  if (callShort <= putShort) {
    putShort = Math.floor(spot - spot * 0.02)
    callShort = Math.ceil(spot + spot * 0.02)
    putLong = putShort - WIDTH
    callLong = callShort + WIDTH
  }

  return { putShort, putLong, callShort, callLong }
}

function getTargetExpiration(minDte: number): string {
  const now = getCentralTime()
  const target = new Date(now)
  let counted = 0
  while (counted < minDte) {
    target.setDate(target.getDate() + 1)
    const dow = target.getDay()
    if (dow !== 0 && dow !== 6) counted++
  }
  // Format as YYYY-MM-DD from the CT-based date (avoid toISOString which converts back to UTC)
  const y = target.getFullYear()
  const m = String(target.getMonth() + 1).padStart(2, '0')
  const d = String(target.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/* ------------------------------------------------------------------ */
/*  Position monitoring — PT / SL / EOD close                          */
/* ------------------------------------------------------------------ */

async function monitorPosition(bot: BotDef, ct: Date): Promise<{ status: string; unrealizedPnl: number }> {
  const positions = await query(
    `SELECT position_id, ticker, expiration,
            put_short_strike, put_long_strike,
            call_short_strike, call_long_strike,
            contracts, total_credit, max_loss,
            collateral_required, open_time,
            sandbox_close_order_id,
            COALESCE(account_type, 'sandbox') as account_type,
            person
     FROM ${botTable(bot.name, 'positions')}
     WHERE status = 'open' AND dte_mode = $1
     ORDER BY open_time DESC`,
    [bot.dte],
  )

  if (positions.length === 0) return { status: 'no_position', unrealizedPnl: 0 }

  // Monitor ALL positions in PARALLEL (multi-position for INFERNO)
  // This eliminates the sequential-per-position latency bottleneck.
  const results = await Promise.allSettled(
    positions.map(pos => monitorSinglePosition(bot, ct, pos)),
  )

  let totalUnrealized = 0
  let anyAction = 'monitoring'
  for (const r of results) {
    if (r.status === 'fulfilled') {
      totalUnrealized += r.value.unrealizedPnl
      if (r.value.status.startsWith('closed:')) anyAction = r.value.status
    } else {
      console.error(`[scanner] ${bot.name.toUpperCase()}: position monitor error:`, r.reason)
    }
  }
  return { status: anyAction, unrealizedPnl: totalUnrealized }
}

async function monitorSinglePosition(
  bot: BotDef, ct: Date, pos: Record<string, any>,
): Promise<{ status: string; unrealizedPnl: number }> {
  const botCfg = cfg(bot)
  const entryCredit = num(pos.total_credit)
  const contracts = int(pos.contracts)
  const collateral = num(pos.collateral_required)
  const ticker = pos.ticker || 'SPY'
  const expiration = pos.expiration?.toISOString?.()?.slice(0, 10) || String(pos.expiration).slice(0, 10)
  const pid = pos.position_id

  // --- FLAME pending close re-poll ---
  // If sandbox_close_order_id is set but status is still 'open', a previous close
  // fired on Tradier but the fill price wasn't available. Re-poll for the fill
  // and complete the paper close once we have it.
  if (bot.name === PRODUCTION_BOT && pos.sandbox_close_order_id) {
    let pendingInfo: Record<string, any> = {}
    try { pendingInfo = JSON.parse(pos.sandbox_close_order_id) } catch { /* ignore */ }

    // Find the correct pending order — for sandbox positions use 'User' or 'User:sandbox',
    // for production positions use the production account key (e.g., 'Logan:production')
    const posAccountType = pos.account_type || 'sandbox'
    const posPerson = pos.person || 'User'
    let pendingKey = ''
    let userPending: any = null

    if (posAccountType === 'production') {
      // Production positions: look for person:production key
      pendingKey = `${posPerson}:production`
      userPending = pendingInfo[pendingKey]
    }
    if (!userPending?.order_id) {
      // Sandbox positions (or fallback): try User:sandbox, then User
      pendingKey = 'User:sandbox'
      userPending = pendingInfo['User:sandbox'] ?? pendingInfo['User']
      if (!userPending?.order_id) pendingKey = 'User'
    }

    if (userPending?.order_id && userPending.order_id > 0 && !userPending.fill_price) {
      // If past EOD cutoff, cancel the pending limit order and fall through
      // to the normal EOD market close logic below. A pending limit order
      // should never block the EOD safety close.
      if (isAfterEodCutoff(ct)) {
        console.log(
          `[scanner] ${bot.name.toUpperCase()} ${pid}: Past EOD cutoff with pending order ${userPending.order_id} — ` +
          `canceling limit order and falling through to EOD market close`,
        )
        // Find the correct account to cancel the order
        const cancelAccts = await getLoadedSandboxAccountsAsync()
        const cancelAcct = posAccountType === 'production'
          ? cancelAccts.find(a => a.name === posPerson && a.type === 'production')
          : cancelAccts.find(a => a.name === 'User' && a.type === 'sandbox') ?? cancelAccts.find(a => a.name === 'User')
        if (cancelAcct) {
          try { await cancelSandboxOrder(userPending.order_id, cancelAcct.apiKey, cancelAcct.baseUrl) } catch { /* non-fatal */ }
        } else {
          try { await cancelSandboxOrder(userPending.order_id) } catch { /* non-fatal */ }
        }
        // Clear the pending state so EOD close can proceed cleanly
        await query(
          `UPDATE ${botTable(bot.name, 'positions')}
           SET sandbox_close_order_id = NULL, updated_at = NOW()
           WHERE position_id = $1 AND status = 'open' AND dte_mode = $2`,
          [pid, bot.dte],
        )
        // Fall through — do NOT return; the EOD/stale close logic below will handle it
      } else {
        // Normal re-poll during market hours
        console.log(`[scanner] ${bot.name.toUpperCase()} ${pid}: Pending close — re-polling order ${userPending.order_id} for fill price (${pendingKey})...`)
        try {
          // Find the correct account for re-polling
          const allAccts = await getLoadedSandboxAccountsAsync()
          const pollAcct = posAccountType === 'production'
            ? allAccts.find(a => a.name === posPerson && a.type === 'production')
            : allAccts.find(a => a.name === 'User' && a.type === 'sandbox') ?? allAccts.find(a => a.name === 'User')
          if (pollAcct) {
            const accountId = await getAccountIdForKey(pollAcct.apiKey, pollAcct.baseUrl)
            if (accountId) {
              const fill = await getOrderFillPrice(pollAcct.apiKey, accountId, userPending.order_id, 0)
              if (fill != null && fill > 0) {
                console.log(`[scanner] ${bot.name.toUpperCase()} ${pid}: Pending close fill received! $${fill.toFixed(4)} — completing paper close (${pendingKey})`)
                // Complete the deferred close with actual fill
                const closeReason = pendingInfo._pending_reason || 'deferred_fill'
                const pnlPerContract = (entryCredit - fill) * 100
                const realizedPnl = Math.round(pnlPerContract * contracts * 100) / 100
                // Update the pending info with the fill price
                pendingInfo[pendingKey] = { ...userPending, fill_price: fill }
                delete pendingInfo._pending_reason
                const rowsAffected = await dbExecute(
                  `UPDATE ${botTable(bot.name, 'positions')}
                   SET status = 'closed', close_time = NOW(),
                       close_price = $1, realized_pnl = $2,
                       close_reason = $3, sandbox_close_order_id = $4,
                       updated_at = NOW()
                   WHERE position_id = $5 AND status = 'open' AND dte_mode = $6`,
                  [fill, realizedPnl, closeReason, JSON.stringify(pendingInfo), pid, bot.dte],
                )
                if (rowsAffected > 0) {
                  // Route paper_account update based on position's account_type
                  if (posAccountType === 'production') {
                    await query(
                      `UPDATE ${botTable(bot.name, 'paper_account')}
                       SET current_balance = current_balance + $1,
                           cumulative_pnl = cumulative_pnl + $1,
                           total_trades = total_trades + 1,
                           collateral_in_use = GREATEST(0, collateral_in_use - $2),
                           buying_power = current_balance + $1 - GREATEST(0, collateral_in_use - $2),
                           updated_at = NOW()
                       WHERE account_type = 'production' AND person = $3 AND is_active = TRUE AND dte_mode = $4`,
                      [realizedPnl, collateral, posPerson, bot.dte],
                    )
                  } else {
                    await query(
                      `UPDATE ${botTable(bot.name, 'paper_account')}
                       SET current_balance = current_balance + $1,
                           cumulative_pnl = cumulative_pnl + $1,
                           total_trades = total_trades + 1,
                           collateral_in_use = GREATEST(0, collateral_in_use - $2),
                           buying_power = current_balance + $1 - GREATEST(0, collateral_in_use - $2),
                           updated_at = NOW()
                       WHERE COALESCE(account_type, 'sandbox') = 'sandbox' AND dte_mode = $3`,
                      [realizedPnl, collateral, bot.dte],
                    )
                  }
                  await query(
                    `INSERT INTO ${botTable(bot.name, 'daily_perf')} (trade_date, trades_executed, positions_closed, realized_pnl, person)
                     VALUES (${CT_TODAY}, 0, 1, $1, $2)
                     ON CONFLICT (trade_date, COALESCE(person, '')) DO UPDATE SET
                       positions_closed = ${botTable(bot.name, 'daily_perf')}.positions_closed + 1,
                       realized_pnl = ${botTable(bot.name, 'daily_perf')}.realized_pnl + $1`,
                    [realizedPnl, posPerson],
                  )
                  console.log(`[scanner] ${bot.name.toUpperCase()} DEFERRED CLOSE COMPLETE ${pid}: $${realizedPnl.toFixed(2)} [${closeReason}] (fill=$${fill.toFixed(4)})`)
                }
                _mtmFailureCounts.delete(pid)
                return { status: `closed:deferred_fill@${fill.toFixed(4)}`, unrealizedPnl: 0 }
              } else {
                // Re-poll returned no fill — check if broker position even exists anymore.
                // If the broker legs are gone, the position was closed/expired at the broker
                // and we should close the DB position instead of retrying forever.
                let brokerLegsExist = true
                try {
                  const ticker = pos.ticker || 'SPY'
                  const exp = pos.expiration?.toISOString?.()?.slice(0, 10) || String(pos.expiration).slice(0, 10)
                  const occPs = buildOccSymbol(ticker, exp, num(pos.put_short_strike), 'P')
                  const brokerPositions = await getSandboxAccountPositions(pollAcct.apiKey, undefined, pollAcct.baseUrl)
                  const shortPutLeg = brokerPositions.find((p: any) => p.symbol === occPs && p.quantity !== 0)
                  brokerLegsExist = !!shortPutLeg
                } catch { /* assume legs exist if check fails — don't close on API error */ }

                if (!brokerLegsExist) {
                  // Broker position is gone — close DB at entry credit (0 P&L)
                  console.warn(
                    `[scanner] ${bot.name.toUpperCase()} ${pid}: Re-poll returned no fill AND broker position is gone — ` +
                    `closing DB position at entry credit (0 P&L)`,
                  )
                  const closeReason = pendingInfo._pending_reason || 'deferred_broker_gone'
                  const rowsAffected = await dbExecute(
                    `UPDATE ${botTable(bot.name, 'positions')}
                     SET status = 'closed', close_time = NOW(),
                         close_price = $1, realized_pnl = 0,
                         close_reason = $2, sandbox_close_order_id = $3,
                         updated_at = NOW()
                     WHERE position_id = $4 AND status = 'open' AND dte_mode = $5`,
                    [entryCredit, closeReason, JSON.stringify(pendingInfo), pid, bot.dte],
                  )
                  if (rowsAffected > 0) {
                    if (posAccountType === 'production') {
                      await query(
                        `UPDATE ${botTable(bot.name, 'paper_account')}
                         SET total_trades = total_trades + 1,
                             collateral_in_use = GREATEST(0, collateral_in_use - $1),
                             buying_power = current_balance - GREATEST(0, collateral_in_use - $1),
                             updated_at = NOW()
                         WHERE account_type = 'production' AND person = $2 AND is_active = TRUE AND dte_mode = $3`,
                        [collateral, posPerson, bot.dte],
                      )
                    } else {
                      await query(
                        `UPDATE ${botTable(bot.name, 'paper_account')}
                         SET total_trades = total_trades + 1,
                             collateral_in_use = GREATEST(0, collateral_in_use - $1),
                             buying_power = current_balance - GREATEST(0, collateral_in_use - $1),
                             updated_at = NOW()
                         WHERE COALESCE(account_type, 'sandbox') = 'sandbox' AND dte_mode = $2`,
                        [collateral, bot.dte],
                      )
                    }
                    console.log(`[scanner] ${bot.name.toUpperCase()} DEFERRED BROKER-GONE CLOSE: ${pid} closed at entry credit $${entryCredit.toFixed(4)} (0 P&L)`)
                  }
                  _mtmFailureCounts.delete(pid)
                  return { status: `closed:deferred_broker_gone`, unrealizedPnl: 0 }
                }

                console.warn(`[scanner] ${bot.name.toUpperCase()} ${pid}: Re-poll returned no fill — will retry next cycle`)
                return { status: `monitoring:pending_close_fill(order=${userPending.order_id})`, unrealizedPnl: 0 }
              }
            }
          }
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : String(err)
          console.error(`[scanner] ${bot.name.toUpperCase()} ${pid}: Pending close re-poll failed: ${msg} — will retry next cycle`)
          return { status: `monitoring:pending_close_repoll_error`, unrealizedPnl: 0 }
        }
      }
    }
  }

  // Sliding profit target (Fix 2)
  const [ptFraction, ptTier] = getSlidingProfitTarget(ct, botCfg.pt_pct, bot.name)
  const profitTargetPrice = Math.round(entryCredit * (1 - ptFraction) * 10000) / 10000
  const stopLossPrice = Math.round(entryCredit * botCfg.sl_mult * 10000) / 10000

  // Check if position is from a prior day (stale holdover)
  const openDate = pos.open_time ? new Date(pos.open_time).toISOString().slice(0, 10) : null
  const todayStr = ct.toISOString().slice(0, 10)
  const isStaleHoldover = openDate !== null && openDate < todayStr

  // EOD cutoff or stale holdover → force close
  if (isAfterEodCutoff(ct) || isStaleHoldover) {
    const reason = isStaleHoldover ? 'stale_holdover' : 'eod_cutoff'
    try {
      await closePosition(bot, pid, ticker, expiration,
        num(pos.put_short_strike), num(pos.put_long_strike),
        num(pos.call_short_strike), num(pos.call_long_strike),
        contracts, entryCredit, collateral, reason)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      console.warn(`[scanner] ${bot.name.toUpperCase()}: Force-close failed, retrying at entry credit: ${msg}`)
      await closePosition(bot, pid, ticker, expiration,
        num(pos.put_short_strike), num(pos.put_long_strike),
        num(pos.call_short_strike), num(pos.call_long_strike),
        contracts, entryCredit, collateral, reason, entryCredit)
    }
    _mtmFailureCounts.delete(pid) // Clear on close
    return { status: `closed:${reason}`, unrealizedPnl: 0 }
  }

  // Get MTM
  if (!isConfigured()) return { status: 'monitoring:no_tradier', unrealizedPnl: 0 }

  const mtm = await getIcMarkToMarket(
    ticker, expiration,
    num(pos.put_short_strike), num(pos.put_long_strike),
    num(pos.call_short_strike), num(pos.call_long_strike),
    entryCredit,
  )

  // MTM failure tracking (Fix 3)
  if (!mtm) {
    const failCount = (_mtmFailureCounts.get(pid) ?? 0) + 1
    _mtmFailureCounts.set(pid, failCount)

    if (failCount >= MAX_CONSECUTIVE_MTM_FAILURES) {
      console.error(
        `[scanner] ${bot.name.toUpperCase()} ${pid}: ${failCount} consecutive MTM failures — ` +
        `force-closing at entry credit $${entryCredit.toFixed(4)}`,
      )
      await closePosition(bot, pid, ticker, expiration,
        num(pos.put_short_strike), num(pos.put_long_strike),
        num(pos.call_short_strike), num(pos.call_long_strike),
        contracts, entryCredit, collateral, 'data_feed_failure', entryCredit)
      _mtmFailureCounts.delete(pid)
      return { status: `closed:data_feed_failure(${failCount})`, unrealizedPnl: 0 }
    }

    return { status: `monitoring:mtm_failed(${failCount}/${MAX_CONSECUTIVE_MTM_FAILURES})`, unrealizedPnl: 0 }
  }

  // MTM succeeded — reset failure counter
  _mtmFailureCounts.delete(pid)

  const costToClose = mtm.cost_to_close        // bid/ask worst-case — for stop loss
  const costToCloseMid = mtm.cost_to_close_mid // mark (mid) — fallback reference
  const costToCloseLast = mtm.cost_to_close_last // last trade prices — matches Tradier portfolio

  // Log when quotes have validation issues (wide spreads on wings)
  if (mtm.validation_issues?.length) {
    console.warn(`[scanner] ${bot.name.toUpperCase()} ${pid}: wide bid/ask spreads: ${mtm.validation_issues.join(', ')}`)
  }

  // Profit target uses LAST TRADE prices for the TRIGGER check — best estimate of
  // actual market. But the Tradier close order uses a DEBIT LIMIT at profitTargetPrice
  // to guarantee the minimum return. This prevents slippage from eroding profits
  // (e.g., trigger at 20% based on last trades, but market fill at only 14%).
  // If the limit doesn't fill immediately, the deferred-close mechanism retries next cycle.
  if (costToCloseLast <= profitTargetPrice) {
    await closePosition(bot, pid, ticker, expiration,
      num(pos.put_short_strike), num(pos.put_long_strike),
      num(pos.call_short_strike), num(pos.call_long_strike),
      contracts, entryCredit, collateral, `profit_target_${ptTier}`, costToCloseLast,
      'debit', profitTargetPrice)
    return { status: `closed:profit_target@${costToCloseLast.toFixed(4)}(${ptTier})`, unrealizedPnl: 0 }
  }

  // Stop loss uses BID/ASK (conservative) — better to exit early on losses
  if (costToClose >= stopLossPrice) {
    await closePosition(bot, pid, ticker, expiration,
      num(pos.put_short_strike), num(pos.put_long_strike),
      num(pos.call_short_strike), num(pos.call_long_strike),
      contracts, entryCredit, collateral, 'stop_loss', costToClose)
    return { status: `closed:stop_loss@${costToClose.toFixed(4)}`, unrealizedPnl: 0 }
  }

  // Unrealized P&L uses last trade prices to match Tradier's portfolio Gain/Loss
  const unrealizedPnl = Math.round((entryCredit - costToCloseLast) * 100 * contracts * 100) / 100
  return {
    status: `monitoring:mtm=${costToClose.toFixed(4)} last=${costToCloseLast.toFixed(4)} uPnL=$${unrealizedPnl.toFixed(2)} PT=${ptTier}(${(ptFraction * 100).toFixed(0)}%)`,
    unrealizedPnl,
  }
}

/* ------------------------------------------------------------------ */
/*  Close position (mirrors force-close route exactly)                 */
/*  Fix 5: Double-close guard using dbExecute rowCount                 */
/* ------------------------------------------------------------------ */

async function closePosition(
  bot: BotDef,
  positionId: string,
  ticker: string,
  expiration: string,
  putShort: number, putLong: number,
  callShort: number, callLong: number,
  contracts: number,
  entryCredit: number,
  collateral: number,
  reason: string,
  closePrice?: number,
  orderType?: 'market' | 'debit',
  limitPrice?: number,
): Promise<void> {
  // Read person and account_type from position for daily_perf attribution and close routing
  let posPerson = 'User'
  let posAccountType = 'sandbox'
  try {
    const posMetaRow = await query(
      `SELECT person, COALESCE(account_type, 'sandbox') as account_type
       FROM ${botTable(bot.name, 'positions')} WHERE position_id = $1 AND dte_mode = $2`,
      [positionId, bot.dte],
    )
    if (posMetaRow[0]?.person) posPerson = posMetaRow[0].person
    if (posMetaRow[0]?.account_type) posAccountType = posMetaRow[0].account_type
  } catch { /* default */ }

  // Determine estimated close price if not provided
  let estimatedPrice = closePrice ?? 0
  if (closePrice === undefined && isConfigured()) {
    const mtm = await getIcMarkToMarket(ticker, expiration, putShort, putLong, callShort, callLong)
    estimatedPrice = mtm?.cost_to_close ?? 0
  }

  // Mirror close to Tradier — FLAME requires close to succeed (1:1 sync).
  // SPARK + INFERNO: paper-only, no Tradier positions to close.
  let sandboxCloseInfo: Record<string, SandboxCloseInfo> = {}
  const isProductionBotClose = bot.name === PRODUCTION_BOT

  // Only FLAME has real Tradier positions (sandbox OR production). SPARK/INFERNO are paper-only.
  const shouldCloseSandbox = isProductionBotClose

  if (shouldCloseSandbox) {
    const sbRows = await query(
      `SELECT sandbox_order_id FROM ${botTable(bot.name, 'positions')}
       WHERE position_id = $1 AND dte_mode = $2`,
      [positionId, bot.dte],
    )
    let sandboxOpenInfo: Record<string, any> | null = null
    if (sbRows[0]?.sandbox_order_id) {
      try { sandboxOpenInfo = JSON.parse(sbRows[0].sandbox_order_id) } catch { /* ignore */ }
    }

    // Attempt sandbox close with retries (3 attempts with 2s backoff)
    const MAX_CLOSE_ATTEMPTS = 3
    for (let attempt = 1; attempt <= MAX_CLOSE_ATTEMPTS; attempt++) {
      try {
        sandboxCloseInfo = await closeIcOrderAllAccounts(
          ticker, expiration, putShort, putLong, callShort, callLong,
          contracts, estimatedPrice, positionId, sandboxOpenInfo,
          orderType, limitPrice,
          posAccountType as 'sandbox' | 'production',
        )

        // Check if primary account actually closed (FLAME requirement)
        // Use composite key 'User:sandbox' (closeIcOrderAllAccounts returns composite keys)
        const userCloseInfo = posAccountType === 'production'
          ? sandboxCloseInfo[`${posPerson}:production`]
          : sandboxCloseInfo['User:sandbox'] ?? sandboxCloseInfo['User']
        if (isProductionBotClose && !userCloseInfo?.order_id) {
          console.error(
            `[scanner] ${bot.name.toUpperCase()} SANDBOX CLOSE: User account missing from results ` +
            `(attempt ${attempt}/${MAX_CLOSE_ATTEMPTS}) — ${positionId}`,
          )
          if (attempt < MAX_CLOSE_ATTEMPTS) {
            await new Promise(r => setTimeout(r, 2000 * attempt))
            continue
          }
        } else {
          break // Success
        }
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e)
        console.error(
          `[scanner] ${bot.name.toUpperCase()} ` +
          `SANDBOX CLOSE FAILED (attempt ${attempt}/${MAX_CLOSE_ATTEMPTS}): ${positionId} — ${msg}`,
        )
        if (attempt < MAX_CLOSE_ATTEMPTS) {
          await new Promise(r => setTimeout(r, 2000 * attempt))
        }
      }
    }

    // FLAME: log critical error if sandbox close still failed
    // For production positions, check the production account key; for sandbox, check User
    const primaryCloseKey = posAccountType === 'production'
      ? `${posPerson}:production`
      : null
    const userCloseResult = (primaryCloseKey ? sandboxCloseInfo[primaryCloseKey] : null)
      ?? sandboxCloseInfo['User:sandbox'] ?? sandboxCloseInfo['User']
    if (isProductionBotClose && !userCloseResult?.order_id) {
      console.error(
        `[scanner] *** ${bot.name.toUpperCase()} SANDBOX CLOSE FAILED AFTER ${MAX_CLOSE_ATTEMPTS} ATTEMPTS *** ` +
        `Position ${positionId} closed on paper but Tradier positions may still be open!`,
      )
      await query(
        `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode)
         VALUES ($1, $2, $3, $4)`,
        [
          'CRITICAL',
          `SANDBOX CLOSE FAILED: ${positionId} — paper closed but Tradier may be open`,
          JSON.stringify({
            position_id: positionId, reason, attempts: MAX_CLOSE_ATTEMPTS,
            sandbox_close_info: sandboxCloseInfo,
            sandbox_paper_only: _sandboxPaperOnly[bot.name],
          }),
          bot.dte,
        ],
      )
    }
  }

  // FLAME parity: MUST use actual Tradier fill price for close, just like open.
  // Close polls use maxPollMs=0 (unlimited) so fill_price should always be present
  // for successful closes. If still missing, DEFER the paper close — store the
  // sandbox close info on the position and let next cycle re-poll.
  let effectivePrice = estimatedPrice
  // For production positions, prefer the production account's fill price
  const prodCloseKey = posAccountType === 'production' ? `${posPerson}:production` : null
  const userClose = (prodCloseKey ? sandboxCloseInfo[prodCloseKey] : null)
    ?? sandboxCloseInfo['User:sandbox'] ?? sandboxCloseInfo['User']
  if (userClose?.fill_price != null && userClose.fill_price > 0) {
    console.log(
      `[scanner] ${bot.name.toUpperCase()}: Actual close fill=$${userClose.fill_price.toFixed(4)} ` +
      `(estimated=$${estimatedPrice.toFixed(4)}, diff=${(userClose.fill_price - estimatedPrice).toFixed(4)})`,
    )
    effectivePrice = userClose.fill_price
  } else if (isProductionBotClose && userClose?.order_id && userClose.order_id > 0) {
    // Sandbox close order exists but fill price is missing (should be rare with unlimited polling).
    // DEFER: store the close info on the position so next cycle can re-poll.
    // Do NOT close paper with estimated price — that causes drift.
    console.warn(
      `[scanner] ${bot.name.toUpperCase()} ${positionId}: Close order ${userClose.order_id} placed but no fill price. ` +
      `DEFERRING paper close — will re-poll next cycle.`,
    )
    const pendingInfo = { ...sandboxCloseInfo, _pending_reason: reason }
    await query(
      `UPDATE ${botTable(bot.name, 'positions')}
       SET sandbox_close_order_id = $1, updated_at = NOW()
       WHERE position_id = $2 AND status = 'open' AND dte_mode = $3`,
      [JSON.stringify(pendingInfo), positionId, bot.dte],
    )
    await query(
      `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode)
       VALUES ($1, $2, $3, $4)`,
      [
        'WARNING',
        `DEFERRED CLOSE: ${positionId} — waiting for Tradier fill price (order ${userClose.order_id})`,
        JSON.stringify({ position_id: positionId, reason, sandbox_close_info: sandboxCloseInfo }),
        bot.dte,
      ],
    )
    return // Exit without closing paper — next cycle will re-poll
  } else if (isProductionBotClose) {
    // Sandbox close failed entirely (no order_id). Log critical error.
    // Still close paper to prevent stranded positions, but mark the reason.
    console.error(
      `[scanner] *** ${bot.name.toUpperCase()} CLOSE: NO SANDBOX ORDER *** Position ${positionId} — ` +
      `Tradier close failed. Closing paper with estimated $${estimatedPrice.toFixed(4)}. ` +
      `Check sandbox for orphaned positions.`,
    )
    await query(
      `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode)
       VALUES ($1, $2, $3, $4)`,
      [
        'CRITICAL',
        `SANDBOX CLOSE FAILED: ${positionId} — paper closed at estimated price, Tradier may have orphans`,
        JSON.stringify({ position_id: positionId, reason, sandbox_close_info: sandboxCloseInfo }),
        bot.dte,
      ],
    )
  }

  const pnlPerContract = (entryCredit - effectivePrice) * 100
  const realizedPnl = Math.round(pnlPerContract * contracts * 100) / 100

  // Close position — use dbExecute for rowCount (Fix 5: double-close guard)
  const rowsAffected = await dbExecute(
    `UPDATE ${botTable(bot.name, 'positions')}
     SET status = 'closed', close_time = NOW(),
         close_price = $1, realized_pnl = $2,
         close_reason = $3, sandbox_close_order_id = $4,
         updated_at = NOW()
     WHERE position_id = $5 AND status = 'open' AND dte_mode = $6`,
    [effectivePrice, realizedPnl, reason,
     Object.keys(sandboxCloseInfo).length > 0 ? JSON.stringify(sandboxCloseInfo) : null,
     positionId, bot.dte],
  )

  // Fix 5: If 0 rows affected, position was already closed by another scan — skip paper_account update
  if (rowsAffected === 0) {
    console.warn(
      `[scanner] ${bot.name.toUpperCase()} ${positionId}: position UPDATE matched 0 rows ` +
      `(already closed by another scan). Skipping paper_account update to prevent ` +
      `double-counting. realized_pnl would have been $${realizedPnl.toFixed(2)}`,
    )
    return
  }

  // Update paper account — route to correct row based on account_type
  if (posAccountType === 'production') {
    // Production positions update the production paper_account (filtered by person + account_type)
    await query(
      `UPDATE ${botTable(bot.name, 'paper_account')}
       SET current_balance = current_balance + $1,
           cumulative_pnl = cumulative_pnl + $1,
           total_trades = total_trades + 1,
           collateral_in_use = GREATEST(0, collateral_in_use - $2),
           buying_power = buying_power + $2 + $1,
           high_water_mark = GREATEST(high_water_mark, current_balance + $1),
           max_drawdown = GREATEST(max_drawdown,
             GREATEST(high_water_mark, current_balance + $1) - (current_balance + $1)),
           updated_at = NOW()
       WHERE account_type = 'production' AND person = $3 AND is_active = TRUE AND dte_mode = $4`,
      [realizedPnl, collateral, posPerson, bot.dte],
    )
  } else {
    // Sandbox positions update the shared sandbox paper_account
    await query(
      `UPDATE ${botTable(bot.name, 'paper_account')}
       SET current_balance = current_balance + $1,
           cumulative_pnl = cumulative_pnl + $1,
           total_trades = total_trades + 1,
           collateral_in_use = GREATEST(0, collateral_in_use - $2),
           buying_power = buying_power + $2 + $1,
           high_water_mark = GREATEST(high_water_mark, current_balance + $1),
           max_drawdown = GREATEST(max_drawdown,
             GREATEST(high_water_mark, current_balance + $1) - (current_balance + $1)),
           updated_at = NOW()
       WHERE COALESCE(account_type, 'sandbox') = 'sandbox' AND dte_mode = $3`,
      [realizedPnl, collateral, bot.dte],
    )
  }

  // PDT log
  await query(
    `UPDATE ${botTable(bot.name, 'pdt_log')}
     SET closed_at = NOW(), exit_cost = $1, pnl = $2,
         close_reason = $3,
         is_day_trade = ((opened_at AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY})
     WHERE position_id = $4 AND dte_mode = $5`,
    [effectivePrice, realizedPnl, reason, positionId, bot.dte],
  )

  // Log
  const fillNote = userClose?.fill_price != null && userClose.fill_price !== estimatedPrice
    ? ` (actual fill=$${userClose.fill_price.toFixed(4)})`
    : ''
  await query(
    `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode, person)
     VALUES ($1, $2, $3, $4, $5)`,
    [
      'TRADE_CLOSE',
      `AUTO CLOSE: ${positionId} @ $${effectivePrice.toFixed(4)} P&L=$${realizedPnl.toFixed(2)} [${reason}]${fillNote}`,
      JSON.stringify({
        position_id: positionId,
        close_price_estimated: estimatedPrice,
        close_price_actual: userClose?.fill_price ?? null,
        close_price: effectivePrice,
        realized_pnl: realizedPnl,
        close_reason: reason,
        source: 'scanner',
        sandbox_close_info: sandboxCloseInfo,
      }),
      bot.dte, posPerson,
    ],
  )

  // Daily perf (keyed by trade_date + person so sandbox/production don't overwrite each other)
  await query(
    `INSERT INTO ${botTable(bot.name, 'daily_perf')} (trade_date, trades_executed, positions_closed, realized_pnl, person)
     VALUES (${CT_TODAY}, 0, 1, $1, $2)
     ON CONFLICT (trade_date, COALESCE(person, '')) DO UPDATE SET
       positions_closed = ${botTable(bot.name, 'daily_perf')}.positions_closed + 1,
       realized_pnl = ${botTable(bot.name, 'daily_perf')}.realized_pnl + $1`,
    [realizedPnl, posPerson],
  )

  console.log(`[scanner] ${bot.name.toUpperCase()} CLOSED ${positionId}: $${realizedPnl.toFixed(2)} [${reason}]${fillNote}`)

  // Post-close: if same-day open+close = day trade, update PDT tracking.
  // Production and sandbox PDT are tracked SEPARATELY:
  //   - Sandbox: increments shared ironforge_pdt_config.day_trade_count (used by scanner gate)
  //   - Production: pdt_log is_day_trade flag is set (used by API's dayTradeCountSql query)
  // Both: pdt_log.is_day_trade is set via the UPDATE above (line ~1017-1025)
  try {
    const posRow = await query(
      `SELECT open_time, account_type FROM ${botTable(bot.name, 'positions')}
       WHERE position_id = $1 AND dte_mode = $2 LIMIT 1`,
      [positionId, bot.dte],
    )
    const openDate = posRow[0]?.open_time
      ? new Date(posRow[0].open_time).toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
      : null
    const closeDate = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
    const closedAccountType = posRow[0]?.account_type || 'sandbox'
    if (openDate === closeDate) {
      // Only increment shared ironforge_pdt_config counter for SANDBOX trades.
      // Production PDT is tracked via pdt_log rows with account_type='production' —
      // the API's dayTradeCountSql() reads from pdt_log filtered by account_type,
      // so production PDT displays correctly without touching the shared counter.
      if (closedAccountType !== 'production') {
        // Increment on shared table (ironforge_pdt_config)
        const pdtRow = await query(
          `SELECT day_trade_count FROM ironforge_pdt_config
           WHERE bot_name = $1 LIMIT 1`,
          [bot.name.toUpperCase()],
        )
        const oldCount = int(pdtRow[0]?.day_trade_count)
        const newCount = oldCount + 1
        await query(
          `UPDATE ironforge_pdt_config
           SET day_trade_count = $1, updated_at = NOW()
           WHERE bot_name = $2`,
          [newCount, bot.name.toUpperCase()],
        )
        // Also sync per-bot table for consistency
        await query(
          `UPDATE ${botTable(bot.name, 'pdt_config')}
           SET day_trade_count = $1, updated_at = NOW()
           WHERE bot_name = $2`,
          [newCount, bot.name.toUpperCase()],
        )
        await query(
          `INSERT INTO ${botTable(bot.name, 'pdt_audit_log')}
             (bot_name, action, old_value, new_value, reason, performed_by)
           VALUES ($1, $2, $3, $4, $5, $6)`,
          [
            bot.name.toUpperCase(),
            'day_trade_recorded',
            JSON.stringify({ day_trade_count: oldCount }),
            JSON.stringify({ day_trade_count: newCount }),
            `Day trade: ${positionId} opened+closed on ${closeDate}`,
            'scanner',
          ],
        )
        console.log(`[scanner] ${bot.name.toUpperCase()} PDT: sandbox day trade recorded, count ${oldCount}→${newCount}`)
      } else {
        console.log(`[scanner] ${bot.name.toUpperCase()} PDT: production day trade detected for ${positionId} — tracked via pdt_log (not shared counter)`)
      }
    }
  } catch (pdtErr: unknown) {
    const msg = pdtErr instanceof Error ? pdtErr.message : String(pdtErr)
    console.warn(`[scanner] PDT counter update failed: ${msg}`)
  }
}

/* ------------------------------------------------------------------ */
/*  Open new trade (mirrors force-trade route exactly)                 */
/*  Fix 10: Live buying power from open positions                      */
/* ------------------------------------------------------------------ */

async function tryOpenTrade(bot: BotDef, spot: number, vix: number): Promise<string> {
  const botCfg = cfg(bot)

  // VIX filter
  if (vix > 32) return `skip:vix_too_high(${vix.toFixed(1)})`

  // Friday skip — INFERNO and SPARK (data: INFERNO -$298, SPARK -$735 on Fridays)
  if ((bot.name === 'inferno' || bot.name === 'spark') && getCentralTime().getDay() === 5) {
    return `skip:friday_filter`
  }

  // Resolve the primary person for this bot (used for position attribution)
  let person = 'User'
  try {
    const persons = await getAccountsForBotAsync(bot.name)
    if (persons.length > 0) person = persons[0]
  } catch { /* default to 'User' */ }

  // max_trades_per_day: bot config default (1 for FLAME/SPARK, 0/unlimited for INFERNO)
  // This is a daily safety cap for paper/sandbox trades — uses bot config, NOT PDT config.
  // PDT enforcement for FLAME's production account is handled inside the FLAME block below.
  const maxTradesPerDay = botCfg.max_trades

  // Already traded today? (0 = unlimited, i.e. INFERNO)
  // Counts only sandbox/paper trades — production has its own check inside the FLAME block.
  // For FLAME: if sandbox already traded but production hasn't, we continue in production-only mode.
  // Paper never blocks production. Production never blocks paper.
  let sandboxAlreadyTraded = false
  if (maxTradesPerDay > 0) {
    const todayTradesSql = person && person !== 'all'
      ? `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'pdt_log')}
         WHERE trade_date = ${CT_TODAY} AND dte_mode = $1 AND person = $2
           AND COALESCE(account_type, 'sandbox') = 'sandbox'`
      : `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'pdt_log')}
         WHERE trade_date = ${CT_TODAY} AND dte_mode = $1
           AND COALESCE(account_type, 'sandbox') = 'sandbox'`
    const todayTradesParams: any[] = person && person !== 'all' ? [bot.dte, person] : [bot.dte]
    const todayTrades = await query(todayTradesSql, todayTradesParams)
    if (int(todayTrades[0]?.cnt) >= maxTradesPerDay) {
      // FLAME: check if production still needs to trade before returning
      if (bot.name === PRODUCTION_BOT) {
        let prodNeedsToTrade = false
        try {
          const prodDayCheck = await query(
            `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'positions')}
             WHERE account_type = 'production'
               AND (open_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}`,
            [],
          )
          prodNeedsToTrade = int(prodDayCheck[0]?.cnt) === 0
        } catch { /* assume production doesn't need to trade */ }

        if (prodNeedsToTrade) {
          sandboxAlreadyTraded = true
          console.log(`[scanner] ${bot.name.toUpperCase()}: Sandbox already traded today but production hasn't — continuing in production-only mode`)
        } else {
          return 'skip:already_traded_today'
        }
      } else {
        return 'skip:already_traded_today'
      }
    }
  }

  // Get sandbox paper account (production positions use Tradier fill data, not paper BP)
  // When sandboxAlreadyTraded=true (FLAME production-only mode), paper account/BP checks are skipped.
  const accountRows = await query(
    `SELECT id, current_balance, buying_power FROM ${botTable(bot.name, 'paper_account')}
     WHERE is_active = TRUE AND dte_mode = $1 AND COALESCE(account_type, 'sandbox') = 'sandbox'
     ORDER BY id DESC LIMIT 1`,
    [bot.dte],
  )
  if (accountRows.length === 0 && !sandboxAlreadyTraded) return 'skip:no_paper_account'
  const acct = accountRows[0] ?? { id: null, current_balance: 0, buying_power: 0 }

  // Fix 10: Derive buying power from LIVE open position collateral (not cached paper_account)
  // Filter by sandbox account_type so production collateral doesn't affect sandbox BP
  const balance = num(acct.current_balance)
  const liveCollRows = await query(
    `SELECT COALESCE(SUM(collateral_required), 0) AS total_collateral
     FROM ${botTable(bot.name, 'positions')}
     WHERE status = 'open' AND dte_mode = $1 AND COALESCE(account_type, 'sandbox') = 'sandbox'`,
    [bot.dte],
  )
  const liveCollateral = num(liveCollRows[0]?.total_collateral)
  const buyingPower = balance - liveCollateral

  // Paper BP check — skip in production-only mode (production uses Tradier account equity, not paper BP)
  if (buyingPower < 200 && !sandboxAlreadyTraded) return `skip:low_bp($${buyingPower.toFixed(0)})`

  const expectedMove = (vix / 100 / Math.sqrt(252)) * spot

  // Advisor
  const adv = evaluateAdvisor(vix, spot, expectedMove, bot.dte)
  if (adv.advice === 'SKIP') return `skip:advisor(${adv.reasoning})`

  // GEX data warning — log but don't block (GEX not yet integrated)
  // When GEX is wired up, change this to a hard block
  console.warn(
    `[scanner] ${bot.name.toUpperCase()}: GEX_DATA_MISSING — all GEX fields zero, trading without gamma context`,
  )

  // Expiration
  const targetExp = getTargetExpiration(bot.minDte)
  const expirations = await getOptionExpirations('SPY')
  let expiration = targetExp
  if (expirations.length > 0 && !expirations.includes(targetExp)) {
    const targetDate = new Date(targetExp + 'T12:00:00').getTime()
    let nearest = expirations[0]
    let minDiff = Infinity
    for (const exp of expirations) {
      const diff = Math.abs(new Date(exp + 'T12:00:00').getTime() - targetDate)
      if (diff < minDiff) { minDiff = diff; nearest = exp }
    }
    expiration = nearest
  }

  // Strikes + credits
  // Production bot (SPARK): fixed SD, no walk-in. Walking strikes closer to ATM
  // produced sub-breakeven setups (0.85 SD effective vs 1.2 target) in historical
  // testing and consistently lost money on real capital — removed April 2026.
  // Paper bots (FLAME/INFERNO): keep SD walk-in (step down by 0.1 until viable
  // credit or floor) because they only risk paper balances.
  const SD_STEP = 0.1
  const SD_FLOOR = 0.5
  let usedSd = botCfg.sd
  let strikes = calculateStrikes(spot, expectedMove, usedSd)
  let credits = await getIcEntryCredit(
    'SPY', expiration,
    strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
  )

  if (bot.name !== PRODUCTION_BOT) {
    while ((!credits || credits.totalCredit < botCfg.min_credit) && usedSd - SD_STEP >= SD_FLOOR) {
      usedSd = Math.round((usedSd - SD_STEP) * 10) / 10
      strikes = calculateStrikes(spot, expectedMove, usedSd)
      credits = await getIcEntryCredit(
        'SPY', expiration,
        strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
      )
      console.log(
        `[scanner] ${bot.name.toUpperCase()} SD walk-in: sd=${usedSd.toFixed(1)} → credit=$${credits?.totalCredit?.toFixed(4) ?? '0'}`,
      )
    }
  }

  if (!credits || credits.totalCredit < botCfg.min_credit) {
    return `skip:credit_too_low($${credits?.totalCredit?.toFixed(4) ?? '0'} at sd=${usedSd.toFixed(1)})`
  }

  // Sizing — BP% for all bots. Trade quality filtered by min_credit in config.
  const spreadWidth = strikes.putShort - strikes.putLong
  const collateralPer = Math.max(0, (spreadWidth - credits.totalCredit) * 100)
  if (collateralPer <= 0) return 'skip:bad_collateral'
  const usableBP = buyingPower * botCfg.bp_pct
  const bpContracts = Math.floor(usableBP / collateralPer)
  // Paper BP check — skip in production-only mode (production sizes via Tradier account equity)
  if (bpContracts < 1 && !sandboxAlreadyTraded) return `skip:insufficient_bp($${usableBP.toFixed(0)} < $${collateralPer.toFixed(0)}/contract)`
  const SCANNER_MAX_CONTRACTS = 200
  // In production-only mode, use a nominal maxContracts — placeIcOrderAllAccounts re-sizes
  // based on real Tradier account equity anyway
  const rawMax = bpContracts < 1
    ? SCANNER_MAX_CONTRACTS  // production-only mode fallback
    : botCfg.max_contracts > 0
      ? Math.min(botCfg.max_contracts, bpContracts)
      : bpContracts
  const maxContracts = Math.min(rawMax, SCANNER_MAX_CONTRACTS)

  const totalCollateral = collateralPer * maxContracts
  const maxProfit = credits.totalCredit * 100 * maxContracts
  const maxLoss = totalCollateral

  // Position ID — use Central Time date (not UTC) so IDs stay consistent after 7 PM CT
  const now = new Date()
  const ctStr = now.toLocaleString('en-US', { timeZone: 'America/Chicago' })
  const ctDate = new Date(ctStr)
  const dateStr = `${ctDate.getFullYear()}${String(ctDate.getMonth() + 1).padStart(2, '0')}${String(ctDate.getDate()).padStart(2, '0')}`
  const hex = Math.random().toString(16).slice(2, 8).toUpperCase()
  const botName = bot.name.toUpperCase()
  const positionId = `${botName}-${dateStr}-${hex}`

  // ── FLAME Tradier fill (required for paper) ──────────────────────
  // FLAME paper is a mirror of real Tradier sandbox fills.
  // Paper position REQUIRES a real fill price — no estimated credit fallback.
  // If sandbox can't fill, FLAME paper does NOT trade (unlike SPARK/INFERNO).
  // Production gating (PDT) is handled INSIDE this block — never blocks sandbox.
  // SPARK/INFERNO are paper-only (no sandbox orders, use estimated credit).
  const PRODUCTION_PRIMARY_ACCOUNT = 'User' // Primary fill account for FLAME
  const isProductionFillOnly = bot.name === PRODUCTION_BOT

  let sandboxOrderIds: Record<string, SandboxOrderInfo> = {}
  let effectiveCredit = credits.totalCredit
  let effectiveContracts = maxContracts
  let effectiveCollateral = totalCollateral

  if (isProductionFillOnly) {
    // ── FLAME: Tradier sandbox fill (BEST-EFFORT) ──────────────────────
    // Sandbox fill provides real fill prices for paper P&L accuracy.
    // If sandbox fails for ANY reason, paper uses estimated credit (like SPARK/INFERNO).
    // Production orders are placed alongside sandbox and recorded independently.
    // Paper position INSERT always runs after this block — NEVER blocked by Tradier.

    // ── Production gating (PDT + already-traded check) ──
    // PDT rules only apply to FLAME's production account (<$25K).
    // This determines whether production orders are included in the Tradier call.
    let prodAlreadyTradedToday = false
    try {
      const pdtConfigRows = await query(
        `SELECT pdt_enabled, max_day_trades, last_reset_at
         FROM ironforge_pdt_config
         WHERE bot_name = $1 LIMIT 1`,
        [bot.name.toUpperCase()],
      )
      const pdtCfg = pdtConfigRows[0]
      let pdtEnabled = pdtCfg ? ![false, 'false', 'f', 0, '0'].includes(pdtCfg.pdt_enabled) : false
      if (pdtEnabled) {
        try {
          const acctPdt = await getPdtEnabledForAccount(person)
          if (!acctPdt) {
            pdtEnabled = false
            console.log(`[scanner] ${bot.name.toUpperCase()} PDT disabled by account (${person})`)
          }
        } catch { /* keep bot-level setting */ }
      }
      const maxDayTrades = pdtCfg?.max_day_trades != null ? int(pdtCfg.max_day_trades) : 3
      const lastResetAt: string | null = pdtCfg?.last_reset_at ?? null

      // Production PDT rolling window check
      if (pdtEnabled && maxDayTrades > 0) {
        let prodPdtSql = `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'pdt_log')}
           WHERE is_day_trade = TRUE AND dte_mode = $1
             AND account_type = 'production'
             AND trade_date >= ${CT_TODAY} - INTERVAL '6 days'
             AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5`
        const prodPdtParams: any[] = [bot.dte]
        if (lastResetAt) {
          prodPdtSql += ` AND created_at > $${prodPdtParams.length + 1}`
          prodPdtParams.push(lastResetAt)
        }
        const prodPdtRows = await query(prodPdtSql, prodPdtParams)
        if (int(prodPdtRows[0]?.cnt) >= maxDayTrades) {
          prodAlreadyTradedToday = true
          console.log(`[scanner] ${bot.name.toUpperCase()} PRODUCTION PDT BLOCKED: ${int(prodPdtRows[0]?.cnt)}/${maxDayTrades} day trades in rolling window`)
        }
      }

      // Check if production already traded today
      if (!prodAlreadyTradedToday) {
        const prodDayCheck = await query(
          `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'positions')}
           WHERE account_type = 'production'
             AND (open_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}`,
          [],
        )
        prodAlreadyTradedToday = int(prodDayCheck[0]?.cnt) > 0
      }
      if (prodAlreadyTradedToday) {
        console.log(`[scanner] ${bot.name.toUpperCase()}: Production already traded or PDT blocked — sandboxOnly`)
      }
    } catch (e: unknown) {
      prodAlreadyTradedToday = true
      console.warn(`[scanner] Production status check failed:`, e instanceof Error ? e.message : String(e))
    }

    // ── Production-only mode: sandbox already traded, just need production ──
    if (sandboxAlreadyTraded) {
      if (prodAlreadyTradedToday) {
        return 'skip:already_traded_today'
      }
      // Place production-only order
      try {
        sandboxOrderIds = await placeIcOrderAllAccounts(
          'SPY', expiration,
          strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
          maxContracts, credits.totalCredit, positionId, bot.name,
          { productionOnly: true },
        )
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e)
        console.warn(`[scanner] ${bot.name.toUpperCase()} production-only order failed: ${msg}`)
        return `skip:production_only_order_failed(${msg})`
      }

      // Record production positions (same logic as normal path below)
      const PRODUCTION_MAX_CONTRACTS = 2
      let prodRecorded = false
      for (const [key, info] of Object.entries(sandboxOrderIds)) {
        if (info.account_type !== 'production') continue
        const hasFill = info.fill_price != null && info.fill_price > 0
        if (!hasFill) {
          console.warn(`[scanner] PRODUCTION WARNING: ${key} fill_price is ${info.fill_price} — using estimated credit $${credits.totalCredit.toFixed(4)} as fallback.`)
        }
        const prodPerson = key.split(':')[0]
        const prodContracts = Math.min(info.contracts, PRODUCTION_MAX_CONTRACTS)
        const prodCredit = hasFill ? info.fill_price! : credits.totalCredit
        const prodCollateral = Math.max(0, (spreadWidth - prodCredit) * 100) * prodContracts
        const prodMaxLoss = prodCollateral
        const prodMaxProfit = prodCredit * 100 * prodContracts
        const prodPositionId = `${positionId}-prod-${prodPerson.toLowerCase().replace(/[^a-z0-9]/g, '')}`

        console.log(`[scanner] PRODUCTION-ONLY POSITION: ${prodPerson} ${prodContracts} contracts @ $${prodCredit.toFixed(4)}`)

        try {
          await query(
            `INSERT INTO ${botTable(bot.name, 'positions')} (
              position_id, ticker, expiration,
              put_short_strike, put_long_strike, put_credit,
              call_short_strike, call_long_strike, call_credit,
              contracts, spread_width, total_credit, max_loss, max_profit,
              collateral_required,
              underlying_at_entry, vix_at_entry, expected_move,
              call_wall, put_wall, gex_regime,
              flip_point, net_gex,
              oracle_confidence, oracle_win_probability, oracle_advice,
              oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
              wings_adjusted, original_put_width, original_call_width,
              put_order_id, call_order_id,
              sandbox_order_id,
              status, open_time, open_date, dte_mode, person, account_type
            ) VALUES (
              $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
              $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
              $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
              $31, $32, $33, $34, $35,
              'open', NOW(), ${CT_TODAY}, $36, $37, 'production'
            )`,
            [
              prodPositionId, 'SPY', expiration,
              strikes.putShort, strikes.putLong, prodCredit / 2,
              strikes.callShort, strikes.callLong, prodCredit / 2,
              prodContracts, spreadWidth, prodCredit, prodMaxLoss, prodMaxProfit,
              prodCollateral,
              spot, vix, expectedMove,
              0, 0, 'UNKNOWN',
              0, 0,
              adv.confidence, adv.winProbability, adv.advice,
              adv.reasoning, JSON.stringify(adv.topFactors), false,
              false, spreadWidth, spreadWidth,
              'PRODUCTION', 'PRODUCTION',
              JSON.stringify({ [key]: info }),
              bot.dte, prodPerson,
            ],
          )

          await query(
            `UPDATE ${botTable(bot.name, 'paper_account')}
             SET collateral_in_use = collateral_in_use + $1,
                 buying_power = buying_power - $1,
                 updated_at = NOW()
             WHERE account_type = 'production' AND person = $2 AND is_active = TRUE AND dte_mode = $3`,
            [prodCollateral, prodPerson, bot.dte],
          )

          await query(
            `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode, person)
             VALUES ('PRODUCTION_ORDER', $1, $2, $3, $4)`,
            [
              `PRODUCTION-ONLY: ${prodPerson} ${prodContracts}x SPY IC ${strikes.putShort}/${strikes.putLong}P-${strikes.callShort}/${strikes.callLong}C @ $${prodCredit.toFixed(4)}`,
              JSON.stringify({ position_id: prodPositionId, order_info: info, mode: 'production_only' }),
              bot.dte, prodPerson,
            ],
          )

          await query(
            `INSERT INTO ${botTable(bot.name, 'pdt_log')} (
              trade_date, symbol, position_id, opened_at,
              contracts, entry_credit, dte_mode, person, account_type
            ) VALUES (${CT_TODAY}, $1, $2, NOW(), $3, $4, $5, $6, 'production')`,
            ['SPY', prodPositionId, prodContracts, prodCredit, bot.dte, prodPerson],
          )
          prodRecorded = true
        } catch (prodErr: unknown) {
          const prodErrMsg = prodErr instanceof Error ? prodErr.message : String(prodErr)
          console.error(`[scanner] PRODUCTION-ONLY position creation failed for ${prodPerson}:`, prodErrMsg)
          try {
            await query(
              `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode, person)
               VALUES ('ERROR', $1, $2, $3, $4)`,
              [
                `PRODUCTION-ONLY POSITION RECORD FAILED: ${prodPerson} — ${prodErrMsg}`,
                JSON.stringify({ position_id: prodPositionId, order_info: info, error: prodErrMsg }),
                bot.dte, prodPerson,
              ],
            )
          } catch { /* last resort */ }
        }
      }

      return prodRecorded
        ? `traded:${positionId}(production_only)`
        : 'skip:production_only_no_fills'
    }

    // ── Attempt Tradier sandbox fill ──
    // FLAME paper is a mirror of real Tradier sandbox fills — it MUST use real fill prices.
    // If sandbox can't fill, FLAME paper does NOT trade (unlike SPARK/INFERNO which use estimates).
    // These gates skip the entire trade, not just the Tradier call.

    if (_sandboxPaperOnly[bot.name]) {
      return 'skip:production_requires_tradier(paper_only_mode)'
    }

    // Backoff after consecutive rejections — stop spamming Tradier
    if (_consecutiveRejects[bot.name] >= MAX_REJECTS_BEFORE_BACKOFF) {
      const cyclesSinceLastAttempt = _consecutiveRejects[bot.name] - MAX_REJECTS_BEFORE_BACKOFF
      if (cyclesSinceLastAttempt % BACKOFF_CYCLES !== 0) {
        _consecutiveRejects[bot.name]++
        return `skip:production_backoff(${_consecutiveRejects[bot.name]} consecutive rejects, retrying every ${BACKOFF_CYCLES} cycles)`
      }
      console.log(`[scanner] ${bot.name.toUpperCase()}: ${_consecutiveRejects[bot.name]} consecutive rejects — retrying now (backoff cycle)`)
    }

    // Stale position cleanup gate
    {
      const ctNow = getCentralTime()
      const todayStr = ctNow.toISOString().slice(0, 10)
      if (_sandboxCleanupVerifiedDate[bot.name] !== todayStr) {
        _sandboxCleanupVerified[bot.name] = false
      }

      if (!_sandboxCleanupVerified[bot.name]) {
      // Quick check: are there actually stale positions right now?
      let staleCount = 0
      try {
        const accounts = await getLoadedSandboxAccountsAsync()
        for (const acct of accounts) {
          const positions = await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
          for (const p of positions) {
            if (!p.symbol || p.symbol.length < 15 || p.quantity === 0) continue
            try {
              const datePart = p.symbol.slice(3, 9)
              const expDate = `20${datePart.slice(0, 2)}-${datePart.slice(2, 4)}-${datePart.slice(4, 6)}`
              if (expDate <= todayStr) staleCount++
            } catch { /* ignore */ }
          }
        }
      } catch { /* ignore */ }

      if (staleCount > 0) {
        // Try emergency cleanup right now
        console.warn(`[scanner] ${bot.name.toUpperCase()} PRE-ORDER: ${staleCount} stale positions blocking orders — cleaning up...`)
        try {
          const accounts = await getLoadedSandboxAccountsAsync()
          for (const acct of accounts) {
            const result = await emergencyCloseSandboxPositions(acct.apiKey, acct.name, acct.baseUrl)
            for (const detail of result.details) {
              console.log(`[scanner] ${bot.name.toUpperCase()} PRE-ORDER: ${detail}`)
            }
          }
        } catch { /* ignore */ }

        // Re-check if stale positions remain
        let remaining = 0
        try {
          const accounts = await getLoadedSandboxAccountsAsync()
          for (const acct of accounts) {
            const positions = await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
            for (const p of positions) {
              if (!p.symbol || p.symbol.length < 15 || p.quantity === 0) continue
              try {
                const datePart = p.symbol.slice(3, 9)
                const expDate = `20${datePart.slice(0, 2)}-${datePart.slice(2, 4)}-${datePart.slice(4, 6)}`
                if (expDate <= todayStr) remaining++
              } catch { /* ignore */ }
            }
          }
        } catch { /* ignore */ }

        if (remaining > 0) {
          _consecutiveRejects[bot.name]++
          return `skip:production_stale_positions_blocking(${remaining} stale positions still consuming BP)`
        } else {
          _sandboxCleanupVerified[bot.name] = true
          _sandboxCleanupVerifiedDate[bot.name] = todayStr
          console.log(`[scanner] ${bot.name.toUpperCase()} PRE-ORDER: All stale positions cleared — proceeding with order`)
        }
      } else {
        // No stale positions — mark verified
        _sandboxCleanupVerified[bot.name] = true
        _sandboxCleanupVerifiedDate[bot.name] = todayStr
      }
      }
    }

    // ── Place Tradier orders (sandbox + conditionally production) ──
    try {
      sandboxOrderIds = await placeIcOrderAllAccounts(
        'SPY', expiration,
        strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
        maxContracts, credits.totalCredit, positionId, bot.name,
        prodAlreadyTradedToday ? { sandboxOnly: true } : undefined,
      )
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      console.warn(`[scanner] ${bot.name.toUpperCase()} order placement failed: ${msg}`)
      // Log the rejected signal
      await query(
        `INSERT INTO ${botTable(bot.name, 'signals')} (
          spot_price, vix, expected_move, call_wall, put_wall,
          gex_regime, put_short, put_long, call_short, call_long,
          total_credit, confidence, was_executed, skip_reason, reasoning,
          wings_adjusted, dte_mode, person, account_type
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, 'sandbox')`,
        [
          spot, vix, expectedMove, 0, 0,
          'UNKNOWN', strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
          credits.totalCredit, adv.confidence, false, 'order_failed', `Auto scan | ${adv.reasoning}`,
          false, bot.dte, person,
        ],
      )
      _consecutiveRejects[bot.name]++
      return `skip:production_order_failed(${msg})`
    }

    // ── PRODUCTION FILLS: Process INDEPENDENTLY of sandbox ──
    // Record production positions immediately. These are real money positions
    // that must be tracked regardless of what happens with sandbox.
    const PRODUCTION_MAX_CONTRACTS = 2  // Safety cap
    for (const [key, info] of Object.entries(sandboxOrderIds)) {
      if (info.account_type !== 'production') continue

      // CRITICAL: For production, we MUST record the position even if fill_price is null.
      // The order was already placed on Tradier with REAL MONEY. If we skip recording,
      // the position becomes an orphan — unmonitored, unmanaged, and never closed.
      // Use the estimated credit as fallback when fill price polling fails.
      const hasFill = info.fill_price != null && info.fill_price > 0
      if (!hasFill) {
        console.warn(
          `[scanner] PRODUCTION WARNING: ${key} fill_price is ${info.fill_price} — ` +
          `using estimated credit $${credits.totalCredit.toFixed(4)} as fallback. ` +
          `Order was already placed on Tradier — MUST record position.`,
        )
      }

      const prodPerson = key.split(':')[0]
      const prodContracts = Math.min(info.contracts, PRODUCTION_MAX_CONTRACTS)
      const prodCredit = hasFill ? info.fill_price! : credits.totalCredit
      const prodCollateral = Math.max(0, (spreadWidth - prodCredit) * 100) * prodContracts
      const prodMaxLoss = prodCollateral
      const prodMaxProfit = prodCredit * 100 * prodContracts
      const prodPositionId = `${positionId}-prod-${prodPerson.toLowerCase().replace(/[^a-z0-9]/g, '')}`

      console.log(
        `[scanner] PRODUCTION POSITION: ${prodPerson} ${prodContracts} contracts @ $${prodCredit.toFixed(4)} ` +
        `(collateral=$${prodCollateral.toFixed(0)}, maxLoss=$${prodMaxLoss.toFixed(0)})`,
      )

      try {
        await query(
          `INSERT INTO ${botTable(bot.name, 'positions')} (
            position_id, ticker, expiration,
            put_short_strike, put_long_strike, put_credit,
            call_short_strike, call_long_strike, call_credit,
            contracts, spread_width, total_credit, max_loss, max_profit,
            collateral_required,
            underlying_at_entry, vix_at_entry, expected_move,
            call_wall, put_wall, gex_regime,
            flip_point, net_gex,
            oracle_confidence, oracle_win_probability, oracle_advice,
            oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
            wings_adjusted, original_put_width, original_call_width,
            put_order_id, call_order_id,
            sandbox_order_id,
            status, open_time, open_date, dte_mode, person, account_type
          ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
            $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
            $31, $32, $33, $34, $35,
            'open', NOW(), ${CT_TODAY}, $36, $37, 'production'
          )`,
          [
            prodPositionId, 'SPY', expiration,
            strikes.putShort, strikes.putLong, prodCredit / 2,
            strikes.callShort, strikes.callLong, prodCredit / 2,
            prodContracts, spreadWidth, prodCredit, prodMaxLoss, prodMaxProfit,
            prodCollateral,
            spot, vix, expectedMove,
            0, 0, 'UNKNOWN',
            0, 0,
            adv.confidence, adv.winProbability, adv.advice,
            adv.reasoning, JSON.stringify(adv.topFactors), false,
            false, spreadWidth, spreadWidth,
            'PRODUCTION', 'PRODUCTION',
            JSON.stringify({ [key]: info }),
            bot.dte, prodPerson,
          ],
        )

        // Deduct collateral from the PRODUCTION paper_account
        await query(
          `UPDATE ${botTable(bot.name, 'paper_account')}
           SET collateral_in_use = collateral_in_use + $1,
               buying_power = buying_power - $1,
               updated_at = NOW()
           WHERE account_type = 'production' AND person = $2 AND is_active = TRUE AND dte_mode = $3`,
          [prodCollateral, prodPerson, bot.dte],
        )

        // Log the production order
        await query(
          `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode, person)
           VALUES ('PRODUCTION_ORDER', $1, $2, $3, $4)`,
          [
            `PRODUCTION: ${prodPerson} ${prodContracts}x SPY IC ${strikes.putShort}/${strikes.putLong}P-${strikes.callShort}/${strikes.callLong}C @ $${prodCredit.toFixed(4)}`,
            JSON.stringify({ position_id: prodPositionId, order_info: info }),
            bot.dte, prodPerson,
          ],
        )

        // PDT log for production position (enables production PDT tracking on dashboard)
        await query(
          `INSERT INTO ${botTable(bot.name, 'pdt_log')} (
            trade_date, symbol, position_id, opened_at,
            contracts, entry_credit, dte_mode, person, account_type
          ) VALUES (${CT_TODAY}, $1, $2, NOW(), $3, $4, $5, $6, 'production')`,
          ['SPY', prodPositionId, prodContracts, prodCredit, bot.dte, prodPerson],
        )
      } catch (prodErr: unknown) {
        const prodErrMsg = prodErr instanceof Error ? prodErr.message : String(prodErr)
        console.error(`[scanner] PRODUCTION position creation failed for ${prodPerson}:`, prodErrMsg)
        // Log to DB so it's visible in the dashboard (console.error only goes to server logs)
        try {
          await query(
            `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode, person)
             VALUES ('ERROR', $1, $2, $3, $4)`,
            [
              `PRODUCTION POSITION RECORD FAILED: ${prodPerson} — order was placed on Tradier but DB insert failed: ${prodErrMsg}`,
              JSON.stringify({ position_id: prodPositionId, order_info: info, error: prodErrMsg }),
              bot.dte, prodPerson,
            ],
          )
        } catch { /* last resort — can't even log the error */ }
      }
    }

    // ── PRODUCTION FILL SUMMARY ──
    {
      const allEntries = Object.entries(sandboxOrderIds)
      const prodEntries = allEntries.filter(([, v]) => v.account_type === 'production')
      const prodWithFill = prodEntries.filter(([, v]) => v.fill_price && v.fill_price > 0)
      const prodNoFill = prodEntries.filter(([, v]) => !v.fill_price || v.fill_price <= 0)
      if (prodEntries.length === 0 && allEntries.length > 0) {
        const msg = `PRODUCTION FILL SUMMARY: 0 production entries in sandboxOrderIds (${allEntries.length} total: ${allEntries.map(([k]) => k).join(', ')}). Production account may not have been eligible or order was silently dropped.`
        console.warn(`[scanner] ${msg}`)
        // Log to DB for dashboard visibility
        try {
          await query(
            `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, dte_mode)
             VALUES ('WARN', $1, $2)`,
            [msg, bot.dte],
          )
        } catch { /* non-fatal */ }
      } else if (prodEntries.length > 0) {
        console.log(
          `[scanner] PRODUCTION FILL SUMMARY: ${prodWithFill.length} filled, ${prodNoFill.length} no-fill ` +
          `(entries: ${prodEntries.map(([k, v]) => `${k}=$${v.fill_price ?? 'null'}`).join(', ')})`,
        )
      }
    }

    // ── SANDBOX FILL CHECK: Retry sandbox only if it didn't fill ──
    // Sandbox failure should NOT affect production (already saved above).
    // Retry once after cleaning up stale positions.
    const primaryFill = sandboxOrderIds[`${PRODUCTION_PRIMARY_ACCOUNT}:sandbox`]
    if (!primaryFill || !primaryFill.fill_price || primaryFill.fill_price <= 0) {
      console.warn(
        `[scanner] ${bot.name.toUpperCase()}: ${PRODUCTION_PRIMARY_ACCOUNT} sandbox did not fill — got: ${JSON.stringify(primaryFill)}`,
      )
      // Try emergency cleanup and one retry for sandbox only
      console.log(`[scanner] ${bot.name.toUpperCase()}: Cleaning up stale sandbox positions before retry...`)
      try {
        const retryAccounts = await getLoadedSandboxAccountsAsync()
        for (const a of retryAccounts) {
          if (a.type === 'production') continue
          await emergencyCloseSandboxPositions(a.apiKey, a.name, a.baseUrl)
        }
      } catch { /* ignore cleanup errors */ }
      await new Promise((r) => setTimeout(r, 2000))

      // Retry sandbox order only (production already placed — sandboxOnly prevents duplicate)
      try {
        const retryResults = await placeIcOrderAllAccounts(
          'SPY', expiration,
          strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
          maxContracts, credits.totalCredit, positionId, bot.name,
          { sandboxOnly: true },
        )
        for (const [key, info] of Object.entries(retryResults)) {
          if (info.account_type !== 'production') {
            sandboxOrderIds[key] = info
          }
        }
      } catch { /* ignore retry errors */ }

      const retryFill = sandboxOrderIds[`${PRODUCTION_PRIMARY_ACCOUNT}:sandbox`]
      if (!retryFill || !retryFill.fill_price || retryFill.fill_price <= 0) {
        await query(
          `INSERT INTO ${botTable(bot.name, 'signals')} (
            spot_price, vix, expected_move, call_wall, put_wall,
            gex_regime, put_short, put_long, call_short, call_long,
            total_credit, confidence, was_executed, skip_reason, reasoning,
            wings_adjusted, dte_mode, person, account_type
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, 'sandbox')`,
          [
            spot, vix, expectedMove, 0, 0,
            'UNKNOWN', strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
            credits.totalCredit, adv.confidence, false, 'primary_no_fill', `Auto scan | ${adv.reasoning}`,
            false, bot.dte, person,
          ],
        )
        _consecutiveRejects[bot.name]++
        return 'skip:production_primary_no_fill'
      }
    }

    // Primary account filled — reset rejection counter
    _consecutiveRejects[bot.name] = 0

    // Use Tradier's actual fill PRICE but keep paper-sized contracts.
    // FLAME paper is a mirror of real sandbox — must use real fill price.
    const primaryFillFinal = sandboxOrderIds[`${PRODUCTION_PRIMARY_ACCOUNT}:sandbox`]!
    if (!primaryFillFinal || !primaryFillFinal.fill_price || primaryFillFinal.fill_price <= 0) {
      return 'skip:production_primary_no_fill'
    }

    effectiveCredit = primaryFillFinal.fill_price
    // effectiveContracts stays as maxContracts (85% of paper BP)
    effectiveCollateral = Math.max(0, (spreadWidth - effectiveCredit) * 100) * effectiveContracts
    console.log(
      `[scanner] ${bot.name.toUpperCase()} Tradier-fill: ${PRODUCTION_PRIMARY_ACCOUNT} filled ${primaryFillFinal.contracts} contracts @ $${effectiveCredit.toFixed(4)} ` +
      `(paper=${effectiveContracts} contracts, estimated credit=$${credits.totalCredit.toFixed(4)}, diff=${(effectiveCredit - credits.totalCredit).toFixed(4)})`,
    )
  }

  const effectiveMaxLoss = effectiveCollateral
  const effectiveMaxProfit = effectiveCredit * 100 * effectiveContracts

  // Insert sandbox position (FLAME uses Tradier fill values, others use paper estimates)
  await query(
    `INSERT INTO ${botTable(bot.name, 'positions')} (
      position_id, ticker, expiration,
      put_short_strike, put_long_strike, put_credit,
      call_short_strike, call_long_strike, call_credit,
      contracts, spread_width, total_credit, max_loss, max_profit,
      collateral_required,
      underlying_at_entry, vix_at_entry, expected_move,
      call_wall, put_wall, gex_regime,
      flip_point, net_gex,
      oracle_confidence, oracle_win_probability, oracle_advice,
      oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
      wings_adjusted, original_put_width, original_call_width,
      put_order_id, call_order_id,
      status, open_time, open_date, dte_mode, person, account_type
    ) VALUES (
      $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
      $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
      $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
      $31, $32, $33, $34,
      'open', NOW(), ${CT_TODAY}, $35, $36, 'sandbox'
    )`,
    [
      positionId, 'SPY', expiration,
      strikes.putShort, strikes.putLong, isProductionFillOnly ? effectiveCredit / 2 : credits.putCredit,
      strikes.callShort, strikes.callLong, isProductionFillOnly ? effectiveCredit / 2 : credits.callCredit,
      effectiveContracts, spreadWidth, effectiveCredit, effectiveMaxLoss, effectiveMaxProfit,
      effectiveCollateral,
      spot, vix, expectedMove,
      0, 0, 'UNKNOWN',
      0, 0,
      adv.confidence, adv.winProbability, adv.advice,
      adv.reasoning, JSON.stringify(adv.topFactors), false,
      false, spreadWidth, spreadWidth,
      'PAPER', 'PAPER',
      bot.dte, person,
    ],
  )

  // SPARK + INFERNO: paper-only, no sandbox orders (getAccountsForBot returns [] → skip)
  if (!isProductionFillOnly && !_sandboxPaperOnly[bot.name]) {
    try {
      sandboxOrderIds = await placeIcOrderAllAccounts(
        'SPY', expiration,
        strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
        maxContracts, credits.totalCredit, positionId, bot.name,
      )
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      console.warn(`[scanner] Sandbox open failed for ${positionId}: ${msg}`)
    }
  }

  // Store sandbox order IDs on the sandbox position (filter out production fills)
  const sandboxFills: Record<string, SandboxOrderInfo> = {}
  for (const [key, info] of Object.entries(sandboxOrderIds)) {
    if (info.account_type !== 'production') {
      sandboxFills[key] = info
    }
  }
  if (Object.keys(sandboxFills).length > 0) {
    await query(
      `UPDATE ${botTable(bot.name, 'positions')}
       SET sandbox_order_id = $1, updated_at = NOW()
       WHERE position_id = $2`,
      [JSON.stringify(sandboxFills), positionId],
    )
  }

  // Deduct collateral from the sandbox paper_account
  await query(
    `UPDATE ${botTable(bot.name, 'paper_account')}
     SET collateral_in_use = collateral_in_use + $1,
         buying_power = buying_power - $1,
         updated_at = NOW()
     WHERE id = $2`,
    [effectiveCollateral, acct.id],
  )

  // Record production positions for NON-FLAME bots (FLAME handles this in its own block above).
  // Production positions only exist if placeIcOrderAllAccounts confirmed a Tradier fill
  // (sandbox must fill first — production is only mirrored after sandbox success).
  if (!isProductionFillOnly) {
    const PRODUCTION_MAX_CONTRACTS = 2  // Safety cap for production
    for (const [key, info] of Object.entries(sandboxOrderIds)) {
      if (info.account_type !== 'production') continue
      if (!info.fill_price || info.fill_price <= 0) continue

      const prodPerson = key.split(':')[0]
      const prodContracts = Math.min(info.contracts, PRODUCTION_MAX_CONTRACTS)
      const prodCredit = info.fill_price
      const prodCollateral = Math.max(0, (spreadWidth - prodCredit) * 100) * prodContracts
      const prodMaxLoss = prodCollateral
      const prodMaxProfit = prodCredit * 100 * prodContracts
      const prodPositionId = `${positionId}-prod-${prodPerson.toLowerCase().replace(/[^a-z0-9]/g, '')}`

      console.log(
        `[scanner] ${bot.name.toUpperCase()} PRODUCTION POSITION: ${prodPerson} ${prodContracts} contracts @ $${prodCredit.toFixed(4)} ` +
        `(collateral=$${prodCollateral.toFixed(0)}, maxLoss=$${prodMaxLoss.toFixed(0)})`,
      )

      try {
        await query(
          `INSERT INTO ${botTable(bot.name, 'positions')} (
            position_id, ticker, expiration,
            put_short_strike, put_long_strike, put_credit,
            call_short_strike, call_long_strike, call_credit,
            contracts, spread_width, total_credit, max_loss, max_profit,
            collateral_required,
            underlying_at_entry, vix_at_entry, expected_move,
            call_wall, put_wall, gex_regime,
            flip_point, net_gex,
            oracle_confidence, oracle_win_probability, oracle_advice,
            oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
            wings_adjusted, original_put_width, original_call_width,
            put_order_id, call_order_id,
            sandbox_order_id,
            status, open_time, open_date, dte_mode, person, account_type
          ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
            $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
            $31, $32, $33, $34, $35,
            'open', NOW(), ${CT_TODAY}, $36, $37, 'production'
          )`,
          [
            prodPositionId, 'SPY', expiration,
            strikes.putShort, strikes.putLong, prodCredit / 2,
            strikes.callShort, strikes.callLong, prodCredit / 2,
            prodContracts, spreadWidth, prodCredit, prodMaxLoss, prodMaxProfit,
            prodCollateral,
            spot, vix, expectedMove,
            0, 0, 'UNKNOWN',
            0, 0,
            adv.confidence, adv.winProbability, adv.advice,
            adv.reasoning, JSON.stringify(adv.topFactors), false,
            false, spreadWidth, spreadWidth,
            'PAPER', 'PAPER',
            JSON.stringify({ [key]: info }),
            bot.dte, prodPerson,
          ],
        )

        // Deduct collateral from the PRODUCTION paper_account
        await query(
          `UPDATE ${botTable(bot.name, 'paper_account')}
           SET collateral_in_use = collateral_in_use + $1,
               buying_power = buying_power - $1,
               updated_at = NOW()
           WHERE account_type = 'production' AND person = $2 AND is_active = TRUE AND dte_mode = $3`,
          [prodCollateral, prodPerson, bot.dte],
        )

        await query(
          `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode, person)
           VALUES ('PRODUCTION_ORDER', $1, $2, $3, $4)`,
          [
            `PRODUCTION: ${prodPerson} ${prodContracts}x SPY IC ${strikes.putShort}/${strikes.putLong}P-${strikes.callShort}/${strikes.callLong}C @ $${prodCredit.toFixed(4)}`,
            JSON.stringify({ position_id: prodPositionId, order_info: info }),
            bot.dte, prodPerson,
          ],
        )
      } catch (prodErr: unknown) {
        console.error(`[scanner] ${bot.name.toUpperCase()} PRODUCTION position creation failed for ${prodPerson}:`, prodErr instanceof Error ? prodErr.message : prodErr)
      }
    }
  }

  // Signal log (include person + account_type for per-account attribution)
  await query(
    `INSERT INTO ${botTable(bot.name, 'signals')} (
      spot_price, vix, expected_move, call_wall, put_wall,
      gex_regime, put_short, put_long, call_short, call_long,
      total_credit, confidence, was_executed, reasoning,
      wings_adjusted, dte_mode, person, account_type
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, 'sandbox')`,
    [
      spot, vix, expectedMove, 0, 0,
      'UNKNOWN', strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
      effectiveCredit, adv.confidence, true,
      `Auto scan${isProductionFillOnly ? ' [Tradier-fill]' : ''} | ${adv.reasoning}`,
      false, bot.dte, person,
    ],
  )

  // Trade log
  await query(
    `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode, person)
     VALUES ($1, $2, $3, $4, $5)`,
    [
      'TRADE_OPEN',
      `AUTO TRADE: ${positionId} ${strikes.putLong}/${strikes.putShort}P-${strikes.callShort}/${strikes.callLong}C x${effectiveContracts} @ $${effectiveCredit.toFixed(4)}${isProductionFillOnly ? ' [Tradier-fill]' : ''}`,
      JSON.stringify({
        position_id: positionId, contracts: effectiveContracts,
        credit: effectiveCredit, collateral: effectiveCollateral,
        source: isProductionFillOnly ? 'tradier_fill' : 'scanner',
        estimated_credit: credits.totalCredit,
        sandbox_order_ids: sandboxOrderIds,
        config: { sd: botCfg.sd, used_sd: usedSd, pt_pct: botCfg.pt_pct, sl_mult: botCfg.sl_mult },
      }),
      bot.dte, person,
    ],
  )

  // PDT log (include person + account_type for per-account daily trade tracking)
  await query(
    `INSERT INTO ${botTable(bot.name, 'pdt_log')} (
      trade_date, symbol, position_id, opened_at,
      contracts, entry_credit, dte_mode, person, account_type
    ) VALUES (${CT_TODAY}, $1, $2, NOW(), $3, $4, $5, $6, 'sandbox')`,
    ['SPY', positionId, effectiveContracts, effectiveCredit, bot.dte, person],
  )

  // Equity snapshot
  const updatedAcct = await query(
    `SELECT current_balance, cumulative_pnl FROM ${botTable(bot.name, 'paper_account')}
     WHERE id = $1`, [acct.id],
  )
  await query(
    `INSERT INTO ${botTable(bot.name, 'equity_snapshots')}
     (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode, person, account_type)
     VALUES ($1, $2, 0, 1, $3, $4, $5, 'sandbox')`,
    [num(updatedAcct[0]?.current_balance), num(updatedAcct[0]?.cumulative_pnl), `auto:${positionId}`, bot.dte, person],
  )

  // Daily perf
  await query(
    `INSERT INTO ${botTable(bot.name, 'daily_perf')} (trade_date, trades_executed, positions_closed, realized_pnl, person)
     VALUES (${CT_TODAY}, 1, 0, 0, $1)
     ON CONFLICT (trade_date, COALESCE(person, '')) DO UPDATE SET
       trades_executed = ${botTable(bot.name, 'daily_perf')}.trades_executed + 1`,
    [person],
  )

  console.log(`[scanner] ${botName} OPENED ${positionId} ${strikes.putLong}/${strikes.putShort}P-${strikes.callShort}/${strikes.callLong}C x${effectiveContracts} @ $${effectiveCredit.toFixed(4)} [sandbox:${JSON.stringify(sandboxOrderIds)}]${isProductionFillOnly ? ' [Tradier-fill-only]' : ''}`)
  return `traded:${positionId}`
}

/* ------------------------------------------------------------------ */
/*  Collateral reconciliation (Fix 4)                                  */
/* ------------------------------------------------------------------ */

async function reconcileCollateral(bot: BotDef): Promise<void> {
  try {
    const posTable = botTable(bot.name, 'positions')
    const acctTable = botTable(bot.name, 'paper_account')

    // Reconcile SANDBOX collateral (separate from production)
    const liveColl = await query(
      `SELECT COALESCE(SUM(collateral_required), 0) AS total_collateral
       FROM ${posTable}
       WHERE status = 'open' AND dte_mode = $1 AND COALESCE(account_type, 'sandbox') = 'sandbox'`,
      [bot.dte],
    )
    const actualColl = num(liveColl[0]?.total_collateral)

    const storedAcct = await query(
      `SELECT collateral_in_use, current_balance
       FROM ${acctTable}
       WHERE is_active = TRUE AND dte_mode = $1 AND COALESCE(account_type, 'sandbox') = 'sandbox'
       ORDER BY id DESC LIMIT 1`,
      [bot.dte],
    )
    if (storedAcct.length === 0) return

    const storedColl = num(storedAcct[0].collateral_in_use)
    const storedBal = num(storedAcct[0].current_balance)

    if (Math.abs(storedColl - actualColl) > 0.01) {
      const newBp = storedBal - actualColl
      await query(
        `UPDATE ${acctTable}
         SET collateral_in_use = $1,
             buying_power = $2,
             updated_at = NOW()
         WHERE is_active = TRUE AND dte_mode = $3 AND COALESCE(account_type, 'sandbox') = 'sandbox'`,
        [actualColl, newBp, bot.dte],
      )
      console.log(
        `[scanner] ${bot.name.toUpperCase()} COLLATERAL RECONCILED: ` +
        `$${storedColl.toFixed(2)} → $${actualColl.toFixed(2)} ` +
        `(BP: $${(storedBal - storedColl).toFixed(2)} → $${newBp.toFixed(2)})`,
      )
    }

    // Reconcile PRODUCTION collateral per-person
    const prodAccts = await query(
      `SELECT id, person, collateral_in_use, current_balance
       FROM ${acctTable}
       WHERE is_active = TRUE AND dte_mode = $1 AND account_type = 'production'`,
      [bot.dte],
    )
    for (const pa of prodAccts) {
      const prodColl = await query(
        `SELECT COALESCE(SUM(collateral_required), 0) AS total_collateral
         FROM ${posTable}
         WHERE status = 'open' AND dte_mode = $1 AND account_type = 'production' AND person = $2`,
        [bot.dte, pa.person],
      )
      const prodActual = num(prodColl[0]?.total_collateral)
      const prodStored = num(pa.collateral_in_use)
      if (Math.abs(prodStored - prodActual) > 0.01) {
        const prodBal = num(pa.current_balance)
        const prodNewBp = prodBal - prodActual
        await query(
          `UPDATE ${acctTable}
           SET collateral_in_use = $1, buying_power = $2, updated_at = NOW()
           WHERE id = $3`,
          [prodActual, prodNewBp, pa.id],
        )
        console.log(
          `[scanner] ${bot.name.toUpperCase()} PRODUCTION COLLATERAL RECONCILED (${pa.person}): ` +
          `$${prodStored.toFixed(2)} → $${prodActual.toFixed(2)}`,
        )
      }
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] ${bot.name.toUpperCase()} collateral reconciliation error: ${msg}`)
  }
}

/* ------------------------------------------------------------------ */
/*  Production broker reconciliation                                    */
/*  Detects when production Tradier positions are closed at the broker  */
/*  but the DB still shows them as open. Closes the DB records.         */
/* ------------------------------------------------------------------ */

async function reconcileProductionBrokerPositions(bot: BotDef): Promise<void> {
  try {
    const posTable = botTable(bot.name, 'positions')
    const acctTable = botTable(bot.name, 'paper_account')

    // Get all open production positions from DB
    const openProdPositions = await query(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts, total_credit, collateral_required,
              person, account_type
       FROM ${posTable}
       WHERE status = 'open' AND dte_mode = $1 AND account_type = 'production'`,
      [bot.dte],
    )

    if (openProdPositions.length === 0) return

    // Get all production Tradier accounts
    const allAccounts = await getLoadedSandboxAccountsAsync()
    const prodAccounts = allAccounts.filter(a => a.type === 'production')
    if (prodAccounts.length === 0) return

    // Build a map of broker positions per person
    const brokerPositionsByPerson: Record<string, Array<{ symbol: string; quantity: number }>> = {}
    for (const acct of prodAccounts) {
      try {
        brokerPositionsByPerson[acct.name] = await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
      } catch {
        // If we can't reach the broker, skip reconciliation (don't close DB positions on API failure)
        console.warn(`[scanner] Production reconcile: Can't reach ${acct.name} broker — skipping`)
        return
      }
    }

    // For each open DB position, check if broker still has the legs
    for (const pos of openProdPositions) {
      const person = pos.person || ''
      const brokerPositions = brokerPositionsByPerson[person]
      if (!brokerPositions) continue // No broker data for this person

      const ticker = pos.ticker || 'SPY'
      const exp = pos.expiration?.toISOString?.()?.slice(0, 10) || String(pos.expiration).slice(0, 10)
      const ps = num(pos.put_short_strike)
      const pl = num(pos.put_long_strike)
      const cs = num(pos.call_short_strike)
      const cl = num(pos.call_long_strike)

      // Check if the short put leg exists at the broker (primary indicator)
      const occPs = buildOccSymbol(ticker, exp, ps, 'P')
      const occCs = buildOccSymbol(ticker, exp, cs, 'C')
      const shortPutExists = brokerPositions.some(p => p.symbol === occPs && p.quantity !== 0)
      const shortCallExists = brokerPositions.some(p => p.symbol === occCs && p.quantity !== 0)

      // If BOTH short legs are gone, the position is closed at the broker
      if (!shortPutExists && !shortCallExists) {
        const entryCredit = num(pos.total_credit)
        const contracts = int(pos.contracts)
        const collateral = num(pos.collateral_required)
        const pid = pos.position_id

        console.warn(
          `[scanner] PRODUCTION BROKER RECONCILE: ${pid} — broker (${person}) has NO legs. ` +
          `Closing DB position at entry credit (0 P&L).`,
        )

        // Close the DB position at entry credit (conservative: 0 P&L)
        // We don't know the actual close price since the broker already closed it.
        const rowsAffected = await dbExecute(
          `UPDATE ${posTable}
           SET status = 'closed', close_time = NOW(),
               close_price = $1, realized_pnl = 0,
               close_reason = 'broker_position_gone',
               updated_at = NOW()
           WHERE position_id = $2 AND status = 'open' AND dte_mode = $3`,
          [entryCredit, pid, bot.dte],
        )

        if (rowsAffected > 0) {
          // Release collateral from production paper_account
          await query(
            `UPDATE ${acctTable}
             SET total_trades = total_trades + 1,
                 collateral_in_use = GREATEST(0, collateral_in_use - $1),
                 buying_power = current_balance - GREATEST(0, collateral_in_use - $1),
                 updated_at = NOW()
             WHERE account_type = 'production' AND person = $2 AND is_active = TRUE AND dte_mode = $3`,
            [collateral, person, bot.dte],
          )

          // Log the reconciliation
          await query(
            `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode, person)
             VALUES ($1, $2, $3, $4, $5)`,
            [
              'BROKER_RECONCILE',
              `PRODUCTION POSITION CLOSED (broker gone): ${pid} — ${person} ${contracts}x IC closed at entry credit (0 P&L)`,
              JSON.stringify({
                position_id: pid,
                person,
                entry_credit: entryCredit,
                contracts,
                collateral,
                reason: 'broker_position_gone',
                broker_put_leg: occPs,
                broker_call_leg: occCs,
              }),
              bot.dte,
              person,
            ],
          )

          console.log(
            `[scanner] PRODUCTION BROKER RECONCILE COMPLETE: ${pid} closed (${person}, ` +
            `${contracts}x @ $${entryCredit.toFixed(4)}, collateral $${collateral.toFixed(0)} released)`,
          )
        }
      }
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] ${bot.name.toUpperCase()} production broker reconciliation error: ${msg}`)
  }
}

/* ------------------------------------------------------------------ */
/*  Daily sandbox cleanup (Fix 7)                                      */
/* ------------------------------------------------------------------ */

async function dailySandboxCleanup(ct: Date): Promise<void> {
  const todayStr = ct.toISOString().slice(0, 10)

  // Run once per day, but DON'T restrict to 8:30-9:00 AM.
  // Old behavior: only ran between 8:30-9:00 AM, so if cleanup failed during
  // that window (e.g., Tradier rejects close on expired options), stale
  // positions blocked ALL new orders for the rest of the day.
  // New behavior: keep retrying every cycle until cleanup succeeds.
  // Use FLAME's cleanup date as the global gate — sandbox cleanup is a shared operation
  // that benefits all sandbox-using bots. Per-bot tracking prevents re-running unnecessarily.
  if (_lastSandboxCleanupDate[PRODUCTION_BOT] === todayStr) return
  const hhmm = ctHHMM(ct)
  if (hhmm < 830) return  // Don't run before market open

  console.log('[scanner] DAILY SANDBOX CLEANUP: Starting stale position scan...')

  try {
    const accounts = await getLoadedSandboxAccountsAsync()
    if (accounts.length === 0) {
      for (const b of BOTS) _lastSandboxCleanupDate[b.name] = todayStr
      console.log('[scanner] DAILY SANDBOX CLEANUP: No sandbox accounts configured, skipping')
      return
    }

    let totalStale = 0
    let totalClosed = 0
    let totalFailed = 0
    const cleanupDetails: Record<string, { stale: number; closed: number; failed: number }> = {}

    for (const acct of accounts) {
      const positions = await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
      let acctStale = 0
      let acctClosed = 0
      let acctFailed = 0

      // Count stale positions (expired or expiring today as holdovers)
      const staleSymbols: string[] = []
      for (const pos of positions) {
        const symbol = pos.symbol
        if (!symbol || symbol.length < 15) continue

        // Extract expiration from OCC symbol: SPY260313C00691000 → 2026-03-13
        try {
          const datePart = symbol.slice(3, 9) // YYMMDD
          const expDate = `20${datePart.slice(0, 2)}-${datePart.slice(2, 4)}-${datePart.slice(4, 6)}`
          // Catch BOTH expired (<today) AND today-expiring holdovers (<=today).
          // Today's 0DTE holdovers are from trades opened on previous days
          // (e.g., FLAME 2DTE opened Friday → 0DTE Tuesday). These consume
          // margin and block new orders even though the paper position was
          // already closed at EOD.
          if (expDate <= todayStr) {
            acctStale++
            staleSymbols.push(symbol)
            console.log(`[scanner] SANDBOX CLEANUP [${acct.name}]: Stale position ${symbol} (exp ${expDate})`)
          }
        } catch { /* ignore parse errors */ }
      }

      // Actually close stale positions instead of just logging them.
      // Tradier sandbox does NOT reliably auto-settle expired options.
      if (staleSymbols.length > 0) {
        console.log(
          `[scanner] SANDBOX CLEANUP [${acct.name}]: Closing ${staleSymbols.length} stale positions...`,
        )
        const result = await emergencyCloseSandboxPositions(acct.apiKey, acct.name, acct.baseUrl)
        acctClosed = result.closed
        acctFailed = result.failed
        for (const detail of result.details) {
          console.log(`[scanner] SANDBOX CLEANUP: ${detail}`)
        }
      }

      totalStale += acctStale
      totalClosed += acctClosed
      totalFailed += acctFailed
      cleanupDetails[acct.name] = { stale: acctStale, closed: acctClosed, failed: acctFailed }
    }

    // After emergency close, VERIFY positions are actually gone.
    // emergencyCloseSandboxPositions now polls for fill confirmation,
    // but double-check by re-querying positions.
    if (totalFailed > 0) {
      console.warn(
        `[scanner] SANDBOX CLEANUP: ${totalFailed} close orders failed — re-checking positions...`,
      )
      // Re-query to see if positions are actually gone despite "failed" close orders
      let remainingStale = 0
      for (const acct of accounts) {
        const freshPositions = await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
        for (const pos of freshPositions) {
          if (!pos.symbol || pos.symbol.length < 15 || pos.quantity === 0) continue
          try {
            const datePart = pos.symbol.slice(3, 9)
            const expDate = `20${datePart.slice(0, 2)}-${datePart.slice(2, 4)}-${datePart.slice(4, 6)}`
            if (expDate <= todayStr) {
              remainingStale++
              console.warn(`[scanner] SANDBOX CLEANUP: STILL OPEN after close attempt: ${acct.name} ${pos.symbol} x${pos.quantity}`)
            }
          } catch { /* ignore */ }
        }
      }
      if (remainingStale === 0) {
        console.log('[scanner] SANDBOX CLEANUP: All stale positions verified gone (close orders may have settled)')
        totalFailed = 0  // Override — positions are actually gone
      } else {
        console.error(`[scanner] SANDBOX CLEANUP: ${remainingStale} stale positions STILL OPEN — will retry next cycle`)
      }
    }

    // Mark cleanup complete and set verified flag for all sandbox-using bots
    if (totalFailed === 0) {
      for (const b of BOTS) {
        _lastSandboxCleanupDate[b.name] = todayStr
        _sandboxCleanupVerified[b.name] = true
        _sandboxCleanupVerifiedDate[b.name] = todayStr
      }
    } else {
      // Stale positions remain — sandbox-using bots blocked until next successful cleanup
      for (const b of BOTS) _sandboxCleanupVerified[b.name] = false
      console.warn(
        `[scanner] SANDBOX CLEANUP: ${totalFailed} positions still open — sandbox bots BLOCKED until resolved`,
      )
    }

    if (totalStale > 0) {
      await query(
        `INSERT INTO ${botTable(PRODUCTION_BOT, 'logs')} (level, message, details, dte_mode)
         VALUES ($1, $2, $3, $4)`,
        [
          totalFailed > 0 ? 'CRITICAL' : 'SANDBOX_CLEANUP',
          `Daily sandbox cleanup: ${totalStale} stale, ${totalClosed} closed, ${totalFailed} failed`,
          JSON.stringify({ event: 'daily_sandbox_cleanup', date: todayStr, totalStale, totalClosed, totalFailed, perAccount: cleanupDetails }),
          PRODUCTION_BOT_DTE,
        ],
      )
    }

    // No stale positions found at all — sandbox is clean
    if (totalStale === 0) {
      for (const b of BOTS) {
        _sandboxCleanupVerified[b.name] = true
        _sandboxCleanupVerifiedDate[b.name] = todayStr
      }
    }

    console.log(`[scanner] DAILY SANDBOX CLEANUP COMPLETE: ${totalStale} stale, ${totalClosed} closed, ${totalFailed} failed`)

    // --- Orphan detection: Tradier positions with NO matching open paper position ---
    // This catches the case where FLAME closed paper (e.g., EOD close with sandbox
    // failure) but Tradier positions survived. The stale check above only catches
    // EXPIRED positions; orphans may have future expirations.
    try {
      // Get all open production-bot paper positions
      const openPaperRows = await query(
        `SELECT put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                expiration, ticker
         FROM ${botTable(PRODUCTION_BOT, 'positions')}
         WHERE status = 'open' AND dte_mode = $1`,
        [PRODUCTION_BOT_DTE],
      )
      // Build a set of OCC symbol prefixes from open paper positions
      const paperOccPrefixes = new Set<string>()
      for (const row of openPaperRows) {
        const ticker = row.ticker || 'SPY'
        const exp = row.expiration?.toISOString?.()?.slice(0, 10) || String(row.expiration).slice(0, 10)
        // Add all 4 leg OCC symbols
        for (const [strike, type] of [
          [row.put_short_strike, 'P'], [row.put_long_strike, 'P'],
          [row.call_short_strike, 'C'], [row.call_long_strike, 'C'],
        ] as [number, string][]) {
          paperOccPrefixes.add(buildOccSymbol(ticker, exp, strike, type as 'P' | 'C'))
        }
      }

      // Check each sandbox account for orphans — close ONLY orphans, preserve matched positions.
      // Old behavior: emergencyCloseSandboxPositions closed ALL positions including the matched
      // one, which broke paper↔sandbox 1:1 sync. New behavior: targeted orphan-only close.
      for (const acct of accounts) {
        const positions = await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
        const orphans = positions.filter(p => p.quantity !== 0 && !paperOccPrefixes.has(p.symbol))
        if (orphans.length > 0) {
          const orphanSymbols = new Set(orphans.map(o => o.symbol))
          const matched = positions.filter(p => p.quantity !== 0 && paperOccPrefixes.has(p.symbol)).length
          console.error(
            `[scanner] ORPHAN DETECTION [${acct.name}]: ${orphans.length} orphan positions ` +
            `(${matched} matched positions preserved) — closing orphans only!`,
          )
          for (const o of orphans) {
            console.error(`[scanner]   ORPHAN: ${o.symbol} qty=${o.quantity} cost=${o.cost_basis} mv=${o.market_value}`)
          }
          const result = await closeOrphanSandboxPositions(acct.apiKey, acct.name, orphanSymbols, acct.baseUrl)
          await query(
            `INSERT INTO ${botTable(PRODUCTION_BOT, 'logs')} (level, message, details, dte_mode)
             VALUES ($1, $2, $3, $4)`,
            [
              'CRITICAL',
              `ORPHAN CLEANUP [${acct.name}]: ${result.closed} closed, ${result.failed} failed ` +
              `(${orphans.length} orphans, ${matched} matched preserved)`,
              JSON.stringify({
                account: acct.name,
                orphans: orphans.map(p => ({ symbol: p.symbol, qty: p.quantity, gain_loss: p.gain_loss })),
                matched_preserved: matched,
                close_result: result,
              }),
              PRODUCTION_BOT_DTE,
            ],
          )
        }
      }
    } catch (orphanErr: unknown) {
      const msg = orphanErr instanceof Error ? orphanErr.message : String(orphanErr)
      console.warn(`[scanner] ORPHAN DETECTION ERROR: ${msg}`)
      // Reset so we retry orphan detection next cycle
      for (const b of BOTS) _lastSandboxCleanupDate[b.name] = null
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[scanner] DAILY SANDBOX CLEANUP ERROR: ${msg}`)
  }
}

/* ------------------------------------------------------------------ */
/*  Pre-scan sandbox health check (Fix 8)                              */
/* ------------------------------------------------------------------ */

async function prescanSandboxHealthCheck(): Promise<void> {
  const accounts = await getLoadedSandboxAccountsAsync()
  if (accounts.length === 0) return

  let negativeCount = 0
  let totalChecked = 0

  for (const acct of accounts) {
    try {
      const positions = await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
      // We check positions count as a proxy — if account is accessible, it's alive
      totalChecked++
      // Note: A more thorough check would query balances, but getSandboxBuyingPower
      // requires accountId which needs an extra API call. For the health check,
      // checking accessibility is sufficient since negative BP manifests as 400 errors
      // on order placement, which the cascade close logic already handles.
      void positions // used for accessibility check
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      console.warn(`[scanner] SANDBOX HEALTH: [${acct.name}] check failed: ${msg}`)
      negativeCount++
    }
  }

  // Sandbox health only affects bots that use Tradier sandbox (currently FLAME only).
  // Per-bot scoping prevents FLAME's sandbox failures from blocking SPARK/INFERNO.
  const sandboxBots = BOTS.filter(b => getAccountsForBot(b.name).length > 0)
  for (const sBot of sandboxBots) {
    if (negativeCount > 0 && negativeCount >= totalChecked) {
      if (!_sandboxPaperOnly[sBot.name]) {
        _sandboxPaperOnly[sBot.name] = true
        console.error(`[scanner] SANDBOX HEALTH CRITICAL: ALL sandbox accounts unreachable — switching ${sBot.name.toUpperCase()} to paper-only mode`)
        await query(
          `INSERT INTO ${botTable(sBot.name, 'logs')} (level, message, details, dte_mode)
           VALUES ($1, $2, $3, $4)`,
          [
            'SANDBOX_HEALTH',
            `CRITICAL: ALL sandbox accounts unreachable — auto-switched ${sBot.name.toUpperCase()} to paper-only`,
            JSON.stringify({ action: 'auto_paper_only', source: 'prescan_health_check', negativeCount, totalChecked }),
            sBot.dte,
          ],
        )
      }
    } else if (negativeCount === 0 && _sandboxPaperOnly[sBot.name]) {
      _sandboxPaperOnly[sBot.name] = false
      console.log(`[scanner] SANDBOX HEALTH: All accounts healthy — re-enabling ${sBot.name.toUpperCase()} sandbox mirroring`)
      await query(
        `INSERT INTO ${botTable(sBot.name, 'logs')} (level, message, details, dte_mode)
         VALUES ($1, $2, $3, $4)`,
        [
          'SANDBOX_HEALTH',
          `RECOVERED: All sandbox accounts healthy — re-enabling ${sBot.name.toUpperCase()} sandbox`,
          JSON.stringify({ source: 'prescan_health_check', action: 're_enable_sandbox' }),
          sBot.dte,
        ],
      )
    }
  }
}

/* ------------------------------------------------------------------ */
/*  Post-EOD sandbox verification (Fix 9)                              */
/* ------------------------------------------------------------------ */

async function postEodSandboxVerify(ct: Date): Promise<void> {
  const hhmm = ctHHMM(ct)
  // Run from EOD cutoff (2:45 PM CT) through 3:10 PM CT.
  // Previously 2:50-3:10 PM, but EOD close happens at 2:45 PM CT —
  // if the sandbox close fails at 2:47, we need to catch it immediately.
  if (hhmm < 1445 || hhmm > 1510) return

  const accounts = await getLoadedSandboxAccountsAsync()
  if (accounts.length === 0) return

  const todayYYMMDD = ct.toISOString().slice(2, 10).replace(/-/g, '') // YYMMDD

  for (const acct of accounts) {
    try {
      const positions = await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
      // Filter to today's or future positions
      const todayPositions = positions.filter(p => {
        const symbol = p.symbol
        if (!symbol || symbol.length < 9) return false
        const datePart = symbol.slice(3, 9) // YYMMDD
        return datePart >= todayYYMMDD && p.quantity !== 0
      })

      if (todayPositions.length > 0) {
        console.error(
          `[scanner] POST-EOD SANDBOX CHECK [${acct.name}]: ` +
          `${todayPositions.length} positions still open — EMERGENCY CLOSING!`,
        )

        // Actually close the stranded positions instead of just logging
        const result = await emergencyCloseSandboxPositions(acct.apiKey, acct.name, acct.baseUrl)

        await query(
          `INSERT INTO ${botTable(PRODUCTION_BOT, 'logs')} (level, message, details, dte_mode)
           VALUES ($1, $2, $3, $4)`,
          [
            result.failed > 0 ? 'CRITICAL' : 'POST_EOD_CHECK',
            `POST-EOD EMERGENCY CLOSE [${acct.name}]: ${result.closed} closed, ${result.failed} failed`,
            JSON.stringify({
              account: acct.name,
              positions: todayPositions.map(p => ({ symbol: p.symbol, qty: p.quantity })),
              close_result: result,
            }),
            PRODUCTION_BOT_DTE,
          ],
        )
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      console.warn(`[scanner] Post-EOD sandbox check failed [${acct.name}]: ${msg}`)
    }
  }
}

/* ------------------------------------------------------------------ */
/*  EOD safety net — force-close ALL open positions across ALL bots    */
/*  Runs at 2:55 PM CT as a backstop in case the normal EOD close     */
/*  was missed (scanner restart, MTM failure, etc.)                    */
/* ------------------------------------------------------------------ */

let _lastSafetyNetDate = ''

async function eodSafetyNetSweep(ct: Date): Promise<void> {
  const hhmm = ctHHMM(ct)
  // Only run between 2:55-3:05 PM CT
  if (hhmm < 1455 || hhmm > 1505) return

  // Only run once per day
  const todayStr = ct.toISOString().slice(0, 10)
  if (_lastSafetyNetDate === todayStr) return
  _lastSafetyNetDate = todayStr

  console.log('[scanner] EOD SAFETY NET: Checking all bots for stranded positions...')

  for (const bot of BOTS) {
    try {
      const openRows = await query(
        `SELECT position_id, ticker, expiration,
                put_short_strike, put_long_strike,
                call_short_strike, call_long_strike,
                contracts, total_credit, collateral_required
         FROM ${botTable(bot.name, 'positions')}
         WHERE status = 'open' AND dte_mode = $1`,
        [bot.dte],
      )

      if (openRows.length === 0) continue

      console.error(
        `[scanner] EOD SAFETY NET: ${bot.name.toUpperCase()} has ${openRows.length} ` +
        `open position(s) at ${hhmm} CT — force-closing!`,
      )

      for (const pos of openRows) {
        const expiration = pos.expiration?.toISOString?.()?.slice(0, 10) || String(pos.expiration).slice(0, 10)
        try {
          await closePosition(
            bot,
            pos.position_id,
            pos.ticker || 'SPY',
            expiration,
            num(pos.put_short_strike), num(pos.put_long_strike),
            num(pos.call_short_strike), num(pos.call_long_strike),
            int(pos.contracts),
            num(pos.total_credit),
            num(pos.collateral_required),
            'eod_safety_net',
          )
          console.log(`[scanner] EOD SAFETY NET: Closed ${pos.position_id} [${bot.name}]`)
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : String(err)
          console.error(`[scanner] EOD SAFETY NET: Failed to close ${pos.position_id}: ${msg}`)
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      console.error(`[scanner] EOD SAFETY NET: Error checking ${bot.name}: ${msg}`)
    }
  }
}

/* ------------------------------------------------------------------ */
/*  Single scan cycle for one bot                                      */
/* ------------------------------------------------------------------ */

async function scanBot(bot: BotDef): Promise<void> {
  const ct = getCentralTime()
  const botName = bot.name.toUpperCase()
  const botCfg = cfg(bot)
  let action = 'scan'
  let reason = ''
  let spot = 0
  let vix = 0
  let unrealizedPnl = 0

  try {
    // Collateral reconciliation every cycle (Fix 4)
    await reconcileCollateral(bot)

    // Production broker reconciliation — detect when production Tradier positions
    // are closed at the broker but DB still shows them as open (FLAME only)
    if (bot.name === PRODUCTION_BOT) {
      await reconcileProductionBrokerPositions(bot)
    }

    // Auto-decrement PDT counter — sync SHARED ironforge_pdt_config with live pdt_log count
    try {
      const pdtCfgRow = await query(
        `SELECT day_trade_count, last_reset_at FROM ironforge_pdt_config
         WHERE bot_name = $1 LIMIT 1`,
        [bot.name.toUpperCase()],
      )
      const storedCount = int(pdtCfgRow[0]?.day_trade_count)
      const syncResetAt = pdtCfgRow[0]?.last_reset_at ?? null

      // Count only sandbox PDT trades for the auto-sync (production has separate tracking)
      let pdtCountSql = `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'pdt_log')}
         WHERE is_day_trade = TRUE AND dte_mode = $1
           AND COALESCE(account_type, 'sandbox') = 'sandbox'
           AND trade_date >= ${CT_TODAY} - INTERVAL '6 days'
           AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5`
      const pdtCountParams: any[] = [bot.dte]
      if (syncResetAt) {
        pdtCountSql += ` AND created_at > $2`
        pdtCountParams.push(syncResetAt)
      }

      const pdtActual = await query(pdtCountSql, pdtCountParams)
      const actualCount = int(pdtActual[0]?.cnt)

      if (storedCount !== actualCount) {
        // Update shared table (authoritative)
        await query(
          `UPDATE ironforge_pdt_config
           SET day_trade_count = $1, updated_at = NOW()
           WHERE bot_name = $2`,
          [actualCount, bot.name.toUpperCase()],
        )
        // Also sync per-bot table for consistency
        await query(
          `UPDATE ${botTable(bot.name, 'pdt_config')}
           SET day_trade_count = $1, updated_at = NOW()
           WHERE bot_name = $2`,
          [actualCount, bot.name.toUpperCase()],
        )
        if (actualCount < storedCount) {
          await query(
            `INSERT INTO ${botTable(bot.name, 'pdt_audit_log')}
               (bot_name, action, old_value, new_value, reason, performed_by)
             VALUES ($1, $2, $3, $4, $5, $6)`,
            [
              bot.name.toUpperCase(),
              'auto_decrement',
              JSON.stringify({ day_trade_count: storedCount }),
              JSON.stringify({ day_trade_count: actualCount }),
              `Rolling window update: old trades dropped off (${storedCount}→${actualCount})`,
              'scanner',
            ],
          )
        }
      }
    } catch (pdtSyncErr: unknown) {
      const msg = pdtSyncErr instanceof Error ? pdtSyncErr.message : String(pdtSyncErr)
      console.warn(`[scanner] ${botName} PDT sync error: ${msg}`)
    }

    // Count open SANDBOX positions (production positions are managed independently
    // via placeIcOrderAllAccounts — they should not block sandbox trading)
    const openRows = await query(
      `SELECT position_id FROM ${botTable(bot.name, 'positions')}
       WHERE status = 'open' AND dte_mode = $1 AND COALESCE(account_type, 'sandbox') = 'sandbox'`,
      [bot.dte],
    )
    const openCount = openRows.length
    const hasOpenPosition = openCount > 0

    // Also check for open PRODUCTION positions — these must be monitored independently
    // of sandbox. Previously, production positions were only monitored as a side-effect
    // of sandbox positions being open. If sandbox closed first and the production close
    // was deferred, the production position would never be re-polled/closed.
    const prodOpenRows = await query(
      `SELECT position_id FROM ${botTable(bot.name, 'positions')}
       WHERE status = 'open' AND dte_mode = $1 AND account_type = 'production'`,
      [bot.dte],
    )
    const hasAnyOpenPosition = hasOpenPosition || prodOpenRows.length > 0

    // Step 1: Always monitor open positions first (sandbox OR production)
    if (hasAnyOpenPosition) {
      const monitorResult = await monitorPosition(bot, ct)
      action = monitorResult.status.startsWith('closed:') ? 'closed' : 'monitoring'
      reason = monitorResult.status
      unrealizedPnl = monitorResult.unrealizedPnl
    }

    // Post-EOD sandbox verification (Fix 9) — run on EVERY scan cycle
    // after EOD cutoff, not just when a position was just closed.
    // This catches stranded Tradier positions when the sandbox close fails
    // during the EOD close (e.g., orders rejected near market close).
    if (bot.name === PRODUCTION_BOT && isAfterEodCutoff(ct)) {
      try {
        await postEodSandboxVerify(ct)
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err)
        console.warn(`[scanner] Post-EOD sandbox verification error: ${msg}`)
      }
    }

    // Step 2: If market closed, just log and return
    if (!isMarketOpen(ct)) {
      if (!hasAnyOpenPosition) {
        action = 'outside_window'
        reason = `Market closed (${ct.getHours()}:${String(ct.getMinutes()).padStart(2, '0')} CT)`
      }
    }
    // Step 3: If in entry window and can open → try to trade
    // max_trades: 0 = unlimited, 1 = single trade only, >1 = multi-trade with cap
    else if (isInEntryWindow(ct, bot)) {
      const maxTrades = botCfg.max_trades
      // For bots with a daily cap (maxTrades > 0), count ALL positions opened today
      // (open + closed), not just currently open ones. This prevents reopening
      // after a same-day close (e.g., SPARK hits PT then tries to trade again).
      // FLAME is excluded: its production-only mode (inside tryOpenTrade) handles
      // the case where sandbox traded but production hasn't.
      let tradedTodayCount = 0
      if (maxTrades > 0 && bot.name !== PRODUCTION_BOT) {
        try {
          const todayPosRows = await query(
            `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'positions')}
             WHERE dte_mode = $1 AND COALESCE(account_type, 'sandbox') = 'sandbox'
               AND (open_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}`,
            [bot.dte],
          )
          tradedTodayCount = int(todayPosRows[0]?.cnt)
        } catch { /* non-fatal — tryOpenTrade has its own guard */ }
      }
      const canOpenMore = (maxTrades === 0) ||
        (bot.name === PRODUCTION_BOT && maxTrades === 1 && !hasOpenPosition) ||
        (maxTrades > 0 && tradedTodayCount < maxTrades && !hasOpenPosition)

      if (canOpenMore) {
        if (!(await isConfiguredAsync())) {
          action = 'skip'
          reason = 'tradier_not_configured'
        } else {
          const [spyQuote, vixQuote] = await Promise.all([getQuote('SPY'), getQuote('VIX')])
          spot = spyQuote?.last ?? 0
          vix = vixQuote?.last ?? 20

          if (spot === 0) {
            action = 'skip'
            reason = 'no_spy_quote'
          } else {
            const tradeResult = await tryOpenTrade(bot, spot, vix)
            if (tradeResult.startsWith('traded:')) {
              action = 'traded'
            } else {
              action = 'no_trade'
            }
            reason = tradeResult
          }
        }
      } else if (!hasOpenPosition) {
        // No position, but already traded today
        action = 'no_trade'
        reason = `max_trades_reached(${tradedTodayCount}/${maxTrades})`
      }
      // else: has position + monitoring already happened above
    } else if (!hasOpenPosition) {
      action = 'outside_entry_window'
      reason = `Past entry cutoff (${ct.getHours()}:${String(ct.getMinutes()).padStart(2, '0')} CT, cutoff ${botCfg.entry_end})`
    }

    // Take equity snapshot every cycle — save SEPARATE snapshots for sandbox and production.
    // Gate by isMarketOpen(ct) so snapshots only persist during 8:30 AM - 3:00 PM CT (Mon-Fri).
    // The outer runAllScans() gate runs until 3:10 PM CT to allow EOD safety-net work, but
    // snapshots written after 3:00 PM pollute the intraday equity chart.
    if (isMarketOpen(ct)) {
      try {
        // Sandbox snapshot
        const acctRows = await query(
          `SELECT current_balance, cumulative_pnl FROM ${botTable(bot.name, 'paper_account')}
           WHERE dte_mode = $1 AND COALESCE(account_type, 'sandbox') = 'sandbox'
           ORDER BY id DESC LIMIT 1`, [bot.dte],
        )
        const openPosCount = await query(
          `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'positions')}
           WHERE status = 'open' AND dte_mode = $1 AND COALESCE(account_type, 'sandbox') = 'sandbox'`, [bot.dte],
        )
        // Resolve person for equity snapshot attribution
        let snapPerson = 'User'
        try {
          const snapPersons = await getAccountsForBotAsync(bot.name)
          if (snapPersons.length > 0) snapPerson = snapPersons[0]
        } catch { /* default */ }
        if (acctRows.length > 0) {
          await query(
            `INSERT INTO ${botTable(bot.name, 'equity_snapshots')}
             (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode, person, account_type)
             VALUES ($1, $2, $3, $4, $5, $6, $7, 'sandbox')`,
            [num(acctRows[0]?.current_balance), num(acctRows[0]?.cumulative_pnl),
             unrealizedPnl, int(openPosCount[0]?.cnt), `scan:${action}`, bot.dte, snapPerson],
          )
        }

        // Production snapshots (one per production paper_account)
        const prodAccts = await query(
          `SELECT person, current_balance, cumulative_pnl FROM ${botTable(bot.name, 'paper_account')}
           WHERE dte_mode = $1 AND account_type = 'production' AND is_active = TRUE`, [bot.dte],
        )
        for (const pa of prodAccts) {
          const prodOpenCount = await query(
            `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'positions')}
             WHERE status = 'open' AND dte_mode = $1 AND account_type = 'production' AND person = $2`,
            [bot.dte, pa.person],
          )
          // Calculate production unrealized PNL from open production positions
          let prodUnrealized = 0
          if (int(prodOpenCount[0]?.cnt) > 0 && unrealizedPnl !== 0) {
            // Use same unrealized PNL as sandbox (same IC, same MTM quotes)
            prodUnrealized = unrealizedPnl
          }
          await query(
            `INSERT INTO ${botTable(bot.name, 'equity_snapshots')}
             (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode, person, account_type)
             VALUES ($1, $2, $3, $4, $5, $6, $7, 'production')`,
            [num(pa.current_balance), num(pa.cumulative_pnl),
             prodUnrealized, int(prodOpenCount[0]?.cnt), `scan:${action}`, bot.dte, pa.person],
          )
        }
      } catch (snapErr: unknown) {
        const msg = snapErr instanceof Error ? snapErr.message : String(snapErr)
        console.warn(`[scanner] ${botName} snapshot error: ${msg}`)
      }
    }

  } catch (err: unknown) {
    action = 'error'
    const msg = err instanceof Error ? err.message : String(err)
    reason = msg
    console.error(`[scanner] ${botName} scan error:`, err)
  }

  // Update heartbeat + log
  const status = action === 'error' ? 'error' : isMarketOpen(ct) ? 'active' : 'idle'
  try {
    await query(
      `INSERT INTO bot_heartbeats (bot_name, last_heartbeat, status, scan_count, details)
       VALUES ($1, NOW(), $2, 1, $3)
       ON CONFLICT (bot_name) DO UPDATE SET
         last_heartbeat = NOW(), status = $2,
         scan_count = bot_heartbeats.scan_count + 1,
         details = EXCLUDED.details`,
      [botName, status, JSON.stringify({ action, reason, spot, vix })],
    )
  } catch (hbErr: unknown) {
    const msg = hbErr instanceof Error ? hbErr.message : String(hbErr)
    console.warn(`[scanner] ${botName} heartbeat error: ${msg}`)
  }

  // Log every scan to bot_logs
  try {
    const spotStr = spot > 0 ? ` SPY=$${spot.toFixed(2)}` : ''
    const vixStr = vix > 0 ? ` VIX=${vix.toFixed(1)}` : ''
    await query(
      `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode)
       VALUES ($1, $2, $3, $4)`,
      [
        'SCAN',
        `SCAN: ${action}${spotStr}${vixStr} | ${reason}`,
        JSON.stringify({ action, reason, spot, vix, source: 'scanner' }),
        bot.dte,
      ],
    )
  } catch (logErr: unknown) {
    const msg = logErr instanceof Error ? logErr.message : String(logErr)
    console.warn(`[scanner] ${botName} log error: ${msg}`)
  }

  console.log(`[scanner] ${botName}: ${action} | ${reason}`)
}

/* ------------------------------------------------------------------ */
/*  Main entry point — starts the scan loop                            */
/* ------------------------------------------------------------------ */

let _intervalId: ReturnType<typeof setInterval> | null = null
let _started = false
let _scanCount = 0
let _running = false
let _scanStartedAt: number | null = null

/** Max time a single scan cycle can run before being considered stuck (5 minutes). */
const MAX_SCAN_DURATION_MS = 5 * 60 * 1000

/** Fire-and-forget wrapper — skips if previous cycle still running, detects stuck scans. */
function safeRunAllScans(): void {
  if (_running) {
    // Check if the running scan is stuck (exceeded MAX_SCAN_DURATION_MS)
    if (_scanStartedAt && Date.now() - _scanStartedAt > MAX_SCAN_DURATION_MS) {
      const stuckMinutes = ((Date.now() - _scanStartedAt) / 60_000).toFixed(1)
      console.error(
        `[scanner] STUCK SCAN DETECTED — running for ${stuckMinutes}m (limit: ${MAX_SCAN_DURATION_MS / 60_000}m). ` +
        `Force-resetting _running flag to unblock next cycle.`,
      )
      _running = false
      _scanStartedAt = null
      // Fall through to start a new scan
    } else {
      console.log('[scanner] previous cycle still running, skipping this tick')
      return
    }
  }
  _running = true
  _scanStartedAt = Date.now()
  runAllScans()
    .catch(err => {
      console.error('[scanner] scan cycle error (interval continues):', err)
    })
    .finally(() => {
      _running = false
      _scanStartedAt = null
    })
}

export function startScanner(): void {
  if (_started) return
  _started = true

  console.log('[scanner] IronForge scan loop starting — 1 min interval for all bots')

  // First scan immediately (fire-and-forget)
  safeRunAllScans()

  // Persistent interval
  _intervalId = setInterval(safeRunAllScans, SCAN_INTERVAL_MS)

  console.log('[scanner] setInterval registered, id:', _intervalId)
}

/** Called by db.ts ensureTables to start scanner in the API route process */
export function ensureScannerStarted(): void {
  startScanner()
}

/* ------------------------------------------------------------------ */
/*  Production equity snapshots — real Tradier balance each cycle       */
/* ------------------------------------------------------------------ */

async function saveProductionEquitySnapshots(): Promise<void> {
  try {
    const balances = await getSandboxAccountBalances()
    if (balances.length === 0) return

    for (const acct of balances) {
      if (acct.total_equity == null) continue
      await query(
        `INSERT INTO production_equity_snapshots
         (person, account_id, total_equity, option_buying_power, day_pnl,
          unrealized_pnl, open_positions, note)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
        [
          acct.name,
          acct.account_id || null,
          acct.total_equity,
          acct.option_buying_power,
          acct.day_pnl,
          acct.unrealized_pnl,
          acct.open_positions_count || 0,
          `scan:${_scanCount}`,
        ],
      )
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] saveProductionEquitySnapshots: ${msg}`)
  }
}

/**
 * Write a lightweight liveness heartbeat for every bot when runAllScans is
 * about to early-return (weekend / pre-market / after-market). Without this,
 * the bot_heartbeats row stays frozen at the last in-hours scan, and the
 * /preflight-live check can't distinguish "scanner crashed" from "scanner
 * is idle because markets are closed". We write the ping every cycle
 * (once per minute) so staleness is always sub-minute during off-hours.
 */
async function writeOffHoursHeartbeats(reason: string): Promise<void> {
  for (const bot of BOTS) {
    try {
      await query(
        `INSERT INTO bot_heartbeats (bot_name, last_heartbeat, status, scan_count, details)
         VALUES ($1, NOW(), 'idle', 1, $2)
         ON CONFLICT (bot_name) DO UPDATE SET
           last_heartbeat = NOW(), status = 'idle',
           scan_count = bot_heartbeats.scan_count + 1,
           details = EXCLUDED.details`,
        [bot.name.toUpperCase(), JSON.stringify({ action: 'skip', reason })],
      )
    } catch (err: unknown) {
      // Non-fatal — DB transient errors shouldn't kill the off-hours loop.
      const msg = err instanceof Error ? err.message : String(err)
      console.warn(`[scanner] off-hours heartbeat error [${bot.name}]: ${msg}`)
    }
  }
}

async function runAllScans(): Promise<void> {
  _scanCount++
  const start = Date.now()

  // Skip scanning entirely outside market hours (before 8:30 AM or after 3:10 PM CT,
  // or on weekends). No DB queries, no Tradier API calls, no collateral reconciliation.
  const ct = getCentralTime()
  const hhmm = ctHHMM(ct)
  const dow = ct.getDay()

  if (dow === 0 || dow === 6) {
    // Log once per hour on weekends to avoid log spam
    if (_scanCount === 1 || _scanCount % 60 === 0) {
      console.log(`[scanner] === scan cycle #${_scanCount} skipped — weekend (${dow === 0 ? 'Sun' : 'Sat'}) ===`)
    }
    await writeOffHoursHeartbeats(dow === 0 ? 'idle_weekend_sun' : 'idle_weekend_sat')
    return
  }

  if (hhmm < 830) {
    // Log once per hour before market open to avoid log spam
    if (_scanCount === 1 || _scanCount % 60 === 0) {
      console.log(`[scanner] === scan cycle #${_scanCount} skipped — pre-market (${hhmm} CT, opens 830) ===`)
    }
    await writeOffHoursHeartbeats(`idle_pre_market_${hhmm}`)
    return
  }

  if (hhmm > 1510) {
    // Log once per hour after market close to avoid log spam
    if (_scanCount === 1 || _scanCount % 60 === 0) {
      console.log(`[scanner] === scan cycle #${_scanCount} skipped — market closed (${hhmm} CT) ===`)
    }
    await writeOffHoursHeartbeats(`idle_after_market_${hhmm}`)
    return
  }

  console.log(`[scanner] === scan cycle #${_scanCount} starting ===`)

  // Load config overrides from DB (Fix 1)
  try {
    await loadConfigOverrides()
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] Config override load failed (using defaults): ${msg}`)
  }

  // Daily sandbox cleanup at market open — MUST complete before FLAME can trade.
  // Stale positions from yesterday consume buying power and cause every new order
  // to be rejected (1500+ rejections/day if not cleaned up).
  // This BLOCKS bot scanning until cleanup finishes — getting positions cleared
  // is more important than scanning 1 minute earlier.
  try {
    await dailySandboxCleanup(ct)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[scanner] Daily sandbox cleanup failed: ${msg}`)
  }

  // Pre-scan sandbox health check (Fix 8) — also non-blocking.
  prescanSandboxHealthCheck().catch((err: unknown) => {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] Sandbox health check failed (non-fatal): ${msg}`)
  })

  // Run all bots in parallel
  await Promise.allSettled(
    BOTS.map(bot =>
      scanBot(bot).catch(err => {
        console.error(`[scanner] ${bot.name.toUpperCase()} fatal error:`, err)
      }),
    ),
  )

  // Save production account equity snapshots every cycle (same as paper snapshots).
  // This gives production accounts their own equity curve based on real Tradier balances.
  // Gate by isMarketOpen(ct) — runAllScans() runs until 3:10 PM CT to allow the EOD safety
  // sweep, but snapshots after 3:00 PM pollute the intraday equity chart.
  if (isMarketOpen(ct)) {
    saveProductionEquitySnapshots().catch((err: unknown) => {
      const msg = err instanceof Error ? err.message : String(err)
      console.warn(`[scanner] Production equity snapshot failed (non-fatal): ${msg}`)
    })
  }

  // EOD safety net: at 2:55 PM CT, sweep ALL bots for any stranded positions
  // This catches positions that survived the normal EOD close (scanner restart,
  // MTM failure, etc.). Runs once per day across all bots.
  try {
    await eodSafetyNetSweep(ct)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[scanner] EOD safety net sweep failed: ${msg}`)
  }

  const elapsed = ((Date.now() - start) / 1000).toFixed(1)
  console.log(`[scanner] === scan cycle #${_scanCount} complete (${elapsed}s) ===`)
}

/* ------------------------------------------------------------------ */
/*  @internal — exported for testing only                              */
/* ------------------------------------------------------------------ */

export const _testing = {
  getCentralTime,
  ctHHMM,
  isMarketOpen,
  isInEntryWindow,
  isAfterEodCutoff,
  getSlidingProfitTarget,
  evaluateAdvisor,
  calculateStrikes,
  getTargetExpiration,
  cfg,
  DEFAULT_CONFIG,
  BOTS,
  MAX_CONSECUTIVE_MTM_FAILURES,
  MAX_SCAN_DURATION_MS,
  _botConfig,
  _mtmFailureCounts,
  get _running() { return _running },
  set _running(v: boolean) { _running = v },
  get _scanStartedAt() { return _scanStartedAt },
  set _scanStartedAt(v: number | null) { _scanStartedAt = v },
} as const
