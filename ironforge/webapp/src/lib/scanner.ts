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
  getLoadedSandboxAccounts,
  getLoadedSandboxAccountsAsync,
  getSandboxAccountPositions,
  emergencyCloseSandboxPositions,
  type SandboxOrderInfo,
  type SandboxCloseInfo,
} from './tradier'

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const SCAN_INTERVAL_MS = 60 * 1000 // 1 minute
const MAX_CONSECUTIVE_MTM_FAILURES = 10

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
}

/** Hardcoded defaults matching Python BOT_CONFIG */
const DEFAULT_CONFIG: Record<string, BotConfig> = {
  flame:   { sd: 1.2, pt_pct: 0.30, sl_mult: 2.0, entry_end: 1400, max_trades: 1, max_contracts: 0, bp_pct: 0.85, starting_capital: 10000 },
  spark:   { sd: 1.2, pt_pct: 0.30, sl_mult: 2.0, entry_end: 1400, max_trades: 1, max_contracts: 0, bp_pct: 0.85, starting_capital: 10000 },
  inferno: { sd: 1.0, pt_pct: 0.50, sl_mult: 3.0, entry_end: 1430, max_trades: 0, max_contracts: 20, bp_pct: 0.85, starting_capital: 10000 },
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
 * Read {bot}_config tables from PostgreSQL and merge into _botConfig.
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

      _botConfig[bot.name] = merged
      console.log(
        `[scanner] ${bot.name.toUpperCase()} config loaded: sd=${merged.sd}, pt=${merged.pt_pct}, ` +
        `sl=${merged.sl_mult}, entry_end=${merged.entry_end}, max_contracts=${merged.max_contracts}, ` +
        `max_trades=${merged.max_trades}, bp_pct=${merged.bp_pct}`,
      )
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      console.warn(`[scanner] ${bot.name.toUpperCase()} config load failed (using defaults): ${msg}`)
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

let _sandboxPaperOnly = false
let _lastSandboxCleanupDate: string | null = null

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
 * INFERNO    (base=0.50): MORNING 50% → MIDDAY 30% → AFTERNOON 10%
 */
function getSlidingProfitTarget(ct: Date, basePt: number, botName: string): [number, string] {
  const timeMinutes = ct.getHours() * 60 + ct.getMinutes()
  const isInferno = botName === 'inferno'

  if (timeMinutes < 630) { // before 10:30 AM CT
    return [basePt, 'MORNING']
  } else if (timeMinutes < 780) { // before 1:00 PM CT
    if (isInferno) return [0.30, 'MIDDAY']
    return [Math.max(0.10, basePt - 0.10), 'MIDDAY']
  } else {
    if (isInferno) return [0.10, 'AFTERNOON']
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

  const dow = new Date().getDay()
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
  const now = new Date()
  const target = new Date(now)
  let counted = 0
  while (counted < minDte) {
    target.setDate(target.getDate() + 1)
    const dow = target.getDay()
    if (dow !== 0 && dow !== 6) counted++
  }
  return target.toISOString().slice(0, 10)
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
            collateral_required, open_time
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

  const costToClose = mtm.cost_to_close

  // Profit target: cost_to_close <= PT threshold (sliding)
  if (costToClose <= profitTargetPrice) {
    await closePosition(bot, pid, ticker, expiration,
      num(pos.put_short_strike), num(pos.put_long_strike),
      num(pos.call_short_strike), num(pos.call_long_strike),
      contracts, entryCredit, collateral, `profit_target_${ptTier}`, costToClose)
    return { status: `closed:profit_target@${costToClose.toFixed(4)}(${ptTier})`, unrealizedPnl: 0 }
  }

  // Stop loss: cost_to_close >= SL multiplier * entry credit
  if (costToClose >= stopLossPrice) {
    await closePosition(bot, pid, ticker, expiration,
      num(pos.put_short_strike), num(pos.put_long_strike),
      num(pos.call_short_strike), num(pos.call_long_strike),
      contracts, entryCredit, collateral, 'stop_loss', costToClose)
    return { status: `closed:stop_loss@${costToClose.toFixed(4)}`, unrealizedPnl: 0 }
  }

  const unrealizedPnl = Math.round((entryCredit - costToClose) * 100 * contracts * 100) / 100
  return {
    status: `monitoring:mtm=${costToClose.toFixed(4)} uPnL=$${unrealizedPnl.toFixed(2)} PT=${ptTier}(${(ptFraction * 100).toFixed(0)}%)`,
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
): Promise<void> {
  // Determine estimated close price if not provided
  let estimatedPrice = closePrice ?? 0
  if (closePrice === undefined && isConfigured()) {
    const mtm = await getIcMarkToMarket(ticker, expiration, putShort, putLong, callShort, callLong)
    estimatedPrice = mtm?.cost_to_close ?? 0
  }

  // Mirror close to sandbox — FLAME requires sandbox close to succeed (1:1 sync).
  // SPARK + INFERNO: paper-only, no sandbox positions to close.
  let sandboxCloseInfo: Record<string, SandboxCloseInfo> = {}
  const isFlameBotClose = bot.name === 'flame'

  // Only FLAME has real sandbox positions. SPARK/INFERNO are paper-only.
  const shouldCloseSandbox = isFlameBotClose

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
        )

        // Check if primary account actually closed (FLAME requirement)
        if (isFlameBotClose && !sandboxCloseInfo['User']?.order_id) {
          console.error(
            `[scanner] FLAME SANDBOX CLOSE: User account missing from results ` +
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
          `[scanner] ${isFlameBotClose ? 'FLAME' : bot.name.toUpperCase()} ` +
          `SANDBOX CLOSE FAILED (attempt ${attempt}/${MAX_CLOSE_ATTEMPTS}): ${positionId} — ${msg}`,
        )
        if (attempt < MAX_CLOSE_ATTEMPTS) {
          await new Promise(r => setTimeout(r, 2000 * attempt))
        }
      }
    }

    // FLAME: log critical error if sandbox close still failed
    if (isFlameBotClose && !sandboxCloseInfo['User']?.order_id) {
      console.error(
        `[scanner] *** FLAME SANDBOX CLOSE FAILED AFTER ${MAX_CLOSE_ATTEMPTS} ATTEMPTS *** ` +
        `Position ${positionId} closed on paper but Tradier positions may still be open!`,
      )
      await query(
        `INSERT INTO ${botTable('flame', 'logs')} (level, message, details, dte_mode)
         VALUES ($1, $2, $3, $4)`,
        [
          'CRITICAL',
          `SANDBOX CLOSE FAILED: ${positionId} — paper closed but Tradier may be open`,
          JSON.stringify({
            position_id: positionId, reason, attempts: MAX_CLOSE_ATTEMPTS,
            sandbox_close_info: sandboxCloseInfo,
            sandbox_paper_only: _sandboxPaperOnly,
          }),
          bot.dte,
        ],
      )
    }
  }

  // Use User's actual fill price if available
  let effectivePrice = estimatedPrice
  const userClose = sandboxCloseInfo['User']
  if (userClose?.fill_price != null && userClose.fill_price > 0) {
    console.log(
      `[scanner] ${bot.name.toUpperCase()}: Actual close fill=$${userClose.fill_price.toFixed(4)} ` +
      `(estimated=$${estimatedPrice.toFixed(4)}, diff=${(userClose.fill_price - estimatedPrice).toFixed(4)})`,
    )
    effectivePrice = userClose.fill_price
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

  // Update paper account
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
     WHERE is_active IS NOT NULL AND dte_mode = $3`,
    [realizedPnl, collateral, bot.dte],
  )

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
    `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode)
     VALUES ($1, $2, $3, $4)`,
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
      bot.dte,
    ],
  )

  // Daily perf
  await query(
    `INSERT INTO ${botTable(bot.name, 'daily_perf')} (trade_date, trades_executed, positions_closed, realized_pnl)
     VALUES (${CT_TODAY}, 0, 1, $1)
     ON CONFLICT (trade_date) DO UPDATE SET
       positions_closed = ${botTable(bot.name, 'daily_perf')}.positions_closed + 1,
       realized_pnl = ${botTable(bot.name, 'daily_perf')}.realized_pnl + $1`,
    [realizedPnl],
  )

  console.log(`[scanner] ${bot.name.toUpperCase()} CLOSED ${positionId}: $${realizedPnl.toFixed(2)} [${reason}]${fillNote}`)

  // Post-close: if same-day open+close = day trade, increment PDT counter
  try {
    const posRow = await query(
      `SELECT open_time FROM ${botTable(bot.name, 'positions')}
       WHERE position_id = $1 AND dte_mode = $2 LIMIT 1`,
      [positionId, bot.dte],
    )
    const openDate = posRow[0]?.open_time
      ? new Date(posRow[0].open_time).toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
      : null
    const closeDate = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
    if (openDate === closeDate) {
      const pdtRow = await query(
        `SELECT day_trade_count FROM ${botTable(bot.name, 'pdt_config')}
         WHERE bot_name = $1 LIMIT 1`,
        [bot.name.toUpperCase()],
      )
      const oldCount = int(pdtRow[0]?.day_trade_count)
      const newCount = oldCount + 1
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
      console.log(`[scanner] ${bot.name.toUpperCase()} PDT: day trade recorded, count ${oldCount}→${newCount}`)
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

  // PDT config check
  const pdtConfigRows = await query(
    `SELECT pdt_enabled, max_day_trades, max_trades_per_day, last_reset_at
     FROM ${botTable(bot.name, 'pdt_config')}
     WHERE bot_name = $1 LIMIT 1`,
    [bot.name.toUpperCase()],
  )
  const pdtCfg = pdtConfigRows[0]
  const pdtEnabled = pdtCfg ? ![false, 'false', 'f', 0, '0'].includes(pdtCfg.pdt_enabled) : true
  const maxDayTrades = pdtCfg?.max_day_trades != null ? int(pdtCfg.max_day_trades) : 4
  const maxTradesPerDay = pdtCfg?.max_trades_per_day != null ? int(pdtCfg.max_trades_per_day) : botCfg.max_trades
  const lastResetAt = pdtCfg?.last_reset_at ?? null

  // Already traded today? (0 = unlimited, also unlimited when PDT is off)
  if (pdtEnabled && maxTradesPerDay > 0) {
    const todayTrades = await query(
      `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'pdt_log')}
       WHERE trade_date = ${CT_TODAY} AND dte_mode = $1`,
      [bot.dte],
    )
    if (int(todayTrades[0]?.cnt) >= maxTradesPerDay) return 'skip:already_traded_today'
  }

  // PDT rolling window check
  if (pdtEnabled && maxDayTrades > 0) {
    let pdtSql = `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'pdt_log')}
       WHERE is_day_trade = TRUE AND dte_mode = $1
         AND trade_date >= ${CT_TODAY} - INTERVAL '6 days'
         AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5`
    const pdtParams: any[] = [bot.dte]
    if (lastResetAt) {
      pdtSql += ` AND created_at > $2`
      pdtParams.push(lastResetAt)
    }
    const liveCountRows = await query(pdtSql, pdtParams)
    const pdtCount = int(liveCountRows[0]?.cnt)
    if (pdtCount >= maxDayTrades) {
      return `skip:pdt_blocked(${pdtCount}/${maxDayTrades})`
    }
  }

  // Get account
  const accountRows = await query(
    `SELECT id, current_balance, buying_power FROM ${botTable(bot.name, 'paper_account')}
     WHERE is_active = TRUE AND dte_mode = $1 ORDER BY id DESC LIMIT 1`,
    [bot.dte],
  )
  if (accountRows.length === 0) return 'skip:no_paper_account'
  const acct = accountRows[0]

  // Fix 10: Derive buying power from LIVE open position collateral (not cached paper_account)
  const balance = num(acct.current_balance)
  const liveCollRows = await query(
    `SELECT COALESCE(SUM(collateral_required), 0) AS total_collateral
     FROM ${botTable(bot.name, 'positions')}
     WHERE status = 'open' AND dte_mode = $1`,
    [bot.dte],
  )
  const liveCollateral = num(liveCollRows[0]?.total_collateral)
  const buyingPower = balance - liveCollateral

  if (buyingPower < 200) return `skip:low_bp($${buyingPower.toFixed(0)})`

  const expectedMove = (vix / 100 / Math.sqrt(252)) * spot

  // Advisor
  const adv = evaluateAdvisor(vix, spot, expectedMove, bot.dte)
  if (adv.advice === 'SKIP') return `skip:advisor(${adv.reasoning})`

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

  // Strikes + credits — dynamic SD walk-in
  // Start at configured SD, step down by 0.1 until we get viable credit or hit floor.
  const SD_STEP = 0.1
  const SD_FLOOR = 0.5
  let usedSd = botCfg.sd
  let strikes = calculateStrikes(spot, expectedMove, usedSd)
  let credits = await getIcEntryCredit(
    'SPY', expiration,
    strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
  )

  while ((!credits || credits.totalCredit < 0.05) && usedSd - SD_STEP >= SD_FLOOR) {
    usedSd = Math.round((usedSd - SD_STEP) * 10) / 10  // avoid float drift
    strikes = calculateStrikes(spot, expectedMove, usedSd)
    credits = await getIcEntryCredit(
      'SPY', expiration,
      strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
    )
    console.log(
      `[scanner] ${bot.name.toUpperCase()} SD walk-in: sd=${usedSd.toFixed(1)} → credit=$${credits?.totalCredit?.toFixed(4) ?? '0'}`,
    )
  }

  if (!credits || credits.totalCredit < 0.05) {
    return `skip:credit_too_low($${credits?.totalCredit?.toFixed(4) ?? '0'} after SD walk-in to ${usedSd.toFixed(1)})`
  }

  // Sizing (Fix 1: per-bot max_contracts and bp_pct)
  const spreadWidth = strikes.putShort - strikes.putLong
  const collateralPer = Math.max(0, (spreadWidth - credits.totalCredit) * 100)
  if (collateralPer <= 0) return 'skip:bad_collateral'
  const usableBP = buyingPower * botCfg.bp_pct
  const bpContracts = Math.max(1, Math.floor(usableBP / collateralPer))
  // max_contracts=0 means unlimited (sized by BP only)
  const maxContracts = botCfg.max_contracts > 0
    ? Math.min(botCfg.max_contracts, bpContracts)
    : bpContracts
  const totalCollateral = collateralPer * maxContracts
  const maxProfit = credits.totalCredit * 100 * maxContracts
  const maxLoss = totalCollateral

  // Position ID
  const now = new Date()
  const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '')
  const hex = Math.random().toString(16).slice(2, 8).toUpperCase()
  const botName = bot.name.toUpperCase()
  const positionId = `${botName}-${dateStr}-${hex}`

  // ── FLAME Tradier-fill-only mode ──────────────────────────────────
  // FLAME only records trades that Tradier actually fills.
  // Place sandbox order FIRST; if User's account doesn't fill, reject.
  // Use actual fill price + actual contract count as the paper position.
  // SPARK/INFERNO still use paper-first (traditional) mode.
  const FLAME_PRIMARY_ACCOUNT = 'User' // Primary fill account for FLAME (100% of 85% BP)
  const isFlameFillOnly = bot.name === 'flame'

  let sandboxOrderIds: Record<string, SandboxOrderInfo> = {}
  let effectiveCredit = credits.totalCredit
  let effectiveContracts = maxContracts
  let effectiveCollateral = totalCollateral

  if (isFlameFillOnly) {
    // FLAME: place sandbox order first — paper position depends on fill
    if (_sandboxPaperOnly) {
      return 'skip:flame_requires_tradier(paper_only_mode)'
    }

    // Attempt sandbox order — if User doesn't fill, try cleaning up
    // stale positions and retry once before giving up.
    let attempts = 0
    const MAX_FLAME_ATTEMPTS = 2
    while (attempts < MAX_FLAME_ATTEMPTS) {
      attempts++

      try {
        sandboxOrderIds = await placeIcOrderAllAccounts(
          'SPY', expiration,
          strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
          maxContracts, credits.totalCredit, positionId, bot.name,
        )
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e)
        console.warn(`[scanner] FLAME sandbox order failed (attempt ${attempts}): ${msg}`)
        if (attempts < MAX_FLAME_ATTEMPTS) {
          // Try emergency cleanup of stale positions blocking buying power
          console.log('[scanner] FLAME: Attempting sandbox cleanup before retry...')
          const accounts = await getLoadedSandboxAccountsAsync()
          for (const acct of accounts) {
            await emergencyCloseSandboxPositions(acct.apiKey, acct.name)
          }
          await new Promise((r) => setTimeout(r, 2000))
          continue
        }
        // Log the rejected signal after all attempts
        await query(
          `INSERT INTO ${botTable(bot.name, 'signals')} (
            spot_price, vix, expected_move, call_wall, put_wall,
            gex_regime, put_short, put_long, call_short, call_long,
            total_credit, confidence, was_executed, skip_reason, reasoning,
            wings_adjusted, dte_mode
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)`,
          [
            spot, vix, expectedMove, 0, 0,
            'UNKNOWN', strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
            credits.totalCredit, adv.confidence, false, 'sandbox_order_failed', `Auto scan | ${adv.reasoning}`,
            false, bot.dte,
          ],
        )
        return `skip:flame_sandbox_failed(${msg})`
      }

      // Check primary account fill — FLAME requires it
      const primaryFill = sandboxOrderIds[FLAME_PRIMARY_ACCOUNT]
      if (!primaryFill || !primaryFill.fill_price || primaryFill.fill_price <= 0) {
        console.warn(
          `[scanner] FLAME: ${FLAME_PRIMARY_ACCOUNT} sandbox did not fill (attempt ${attempts}) — got: ${JSON.stringify(primaryFill)}`,
        )
        if (attempts < MAX_FLAME_ATTEMPTS) {
          // Stale positions likely consuming all buying power — clean up and retry
          console.log('[scanner] FLAME: Cleaning up stale sandbox positions before retry...')
          const accounts = await getLoadedSandboxAccountsAsync()
          for (const acct of accounts) {
            await emergencyCloseSandboxPositions(acct.apiKey, acct.name)
          }
          await new Promise((r) => setTimeout(r, 2000))
          sandboxOrderIds = {}  // Reset for retry
          continue
        }
        await query(
          `INSERT INTO ${botTable(bot.name, 'signals')} (
            spot_price, vix, expected_move, call_wall, put_wall,
            gex_regime, put_short, put_long, call_short, call_long,
            total_credit, confidence, was_executed, skip_reason, reasoning,
            wings_adjusted, dte_mode
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)`,
          [
            spot, vix, expectedMove, 0, 0,
            'UNKNOWN', strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
            credits.totalCredit, adv.confidence, false, 'primary_no_fill', `Auto scan | ${adv.reasoning}`,
            false, bot.dte,
          ],
        )
        return 'skip:flame_primary_no_fill'
      }

      // Primary account filled — break out of retry loop
      break
    }

    // Use Tradier's actual fill values
    const primaryFillFinal = sandboxOrderIds[FLAME_PRIMARY_ACCOUNT]!
    if (!primaryFillFinal || !primaryFillFinal.fill_price || primaryFillFinal.fill_price <= 0) {
      return 'skip:flame_primary_no_fill'
    }

    // Use Tradier's actual fill values
    effectiveCredit = primaryFillFinal.fill_price
    effectiveContracts = primaryFillFinal.contracts
    effectiveCollateral = Math.max(0, (spreadWidth - effectiveCredit) * 100) * effectiveContracts
    console.log(
      `[scanner] FLAME Tradier-fill-only: ${FLAME_PRIMARY_ACCOUNT} filled ${effectiveContracts} contracts @ $${effectiveCredit.toFixed(4)} ` +
      `(estimated was $${credits.totalCredit.toFixed(4)}, diff=${(effectiveCredit - credits.totalCredit).toFixed(4)})`,
    )
  }

  const effectiveMaxLoss = effectiveCollateral
  const effectiveMaxProfit = effectiveCredit * 100 * effectiveContracts

  // Insert position (FLAME uses Tradier fill values, others use paper estimates)
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
      status, open_time, open_date, dte_mode
    ) VALUES (
      $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
      $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
      $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
      $31, $32, $33, $34, $35, NOW(), ${CT_TODAY}, $36
    )`,
    [
      positionId, 'SPY', expiration,
      strikes.putShort, strikes.putLong, isFlameFillOnly ? effectiveCredit / 2 : credits.putCredit,
      strikes.callShort, strikes.callLong, isFlameFillOnly ? effectiveCredit / 2 : credits.callCredit,
      effectiveContracts, spreadWidth, effectiveCredit, effectiveMaxLoss, effectiveMaxProfit,
      effectiveCollateral,
      spot, vix, expectedMove,
      0, 0, 'UNKNOWN',
      0, 0,
      adv.confidence, adv.winProbability, adv.advice,
      adv.reasoning, JSON.stringify(adv.topFactors), false,
      false, spreadWidth, spreadWidth,
      'PAPER', 'PAPER',
      'open', bot.dte,
    ],
  )

  // SPARK + INFERNO: paper-only, no sandbox orders (getAccountsForBot returns [] → skip)
  if (!isFlameFillOnly && !_sandboxPaperOnly) {
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

  // Store sandbox order IDs on position
  if (Object.keys(sandboxOrderIds).length > 0) {
    await query(
      `UPDATE ${botTable(bot.name, 'positions')}
       SET sandbox_order_id = $1, updated_at = NOW()
       WHERE position_id = $2`,
      [JSON.stringify(sandboxOrderIds), positionId],
    )
  }

  // Deduct collateral
  await query(
    `UPDATE ${botTable(bot.name, 'paper_account')}
     SET collateral_in_use = collateral_in_use + $1,
         buying_power = buying_power - $1,
         updated_at = NOW()
     WHERE id = $2`,
    [effectiveCollateral, acct.id],
  )

  // Signal log
  await query(
    `INSERT INTO ${botTable(bot.name, 'signals')} (
      spot_price, vix, expected_move, call_wall, put_wall,
      gex_regime, put_short, put_long, call_short, call_long,
      total_credit, confidence, was_executed, reasoning,
      wings_adjusted, dte_mode
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)`,
    [
      spot, vix, expectedMove, 0, 0,
      'UNKNOWN', strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
      effectiveCredit, adv.confidence, true,
      `Auto scan${isFlameFillOnly ? ' [Tradier-fill]' : ''} | ${adv.reasoning}`,
      false, bot.dte,
    ],
  )

  // Trade log
  await query(
    `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode)
     VALUES ($1, $2, $3, $4)`,
    [
      'TRADE_OPEN',
      `AUTO TRADE: ${positionId} ${strikes.putLong}/${strikes.putShort}P-${strikes.callShort}/${strikes.callLong}C x${effectiveContracts} @ $${effectiveCredit.toFixed(4)}${isFlameFillOnly ? ' [Tradier-fill]' : ''}`,
      JSON.stringify({
        position_id: positionId, contracts: effectiveContracts,
        credit: effectiveCredit, collateral: effectiveCollateral,
        source: isFlameFillOnly ? 'tradier_fill' : 'scanner',
        estimated_credit: credits.totalCredit,
        sandbox_order_ids: sandboxOrderIds,
        config: { sd: botCfg.sd, used_sd: usedSd, pt_pct: botCfg.pt_pct, sl_mult: botCfg.sl_mult },
      }),
      bot.dte,
    ],
  )

  // PDT log
  await query(
    `INSERT INTO ${botTable(bot.name, 'pdt_log')} (
      trade_date, symbol, position_id, opened_at,
      contracts, entry_credit, dte_mode
    ) VALUES (${CT_TODAY}, $1, $2, NOW(), $3, $4, $5)`,
    ['SPY', positionId, effectiveContracts, effectiveCredit, bot.dte],
  )

  // Equity snapshot
  const updatedAcct = await query(
    `SELECT current_balance, cumulative_pnl FROM ${botTable(bot.name, 'paper_account')}
     WHERE id = $1`, [acct.id],
  )
  await query(
    `INSERT INTO ${botTable(bot.name, 'equity_snapshots')}
     (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
     VALUES ($1, $2, 0, 1, $3, $4)`,
    [num(updatedAcct[0]?.current_balance), num(updatedAcct[0]?.cumulative_pnl), `auto:${positionId}`, bot.dte],
  )

  // Daily perf
  await query(
    `INSERT INTO ${botTable(bot.name, 'daily_perf')} (trade_date, trades_executed, positions_closed, realized_pnl)
     VALUES (${CT_TODAY}, 1, 0, 0)
     ON CONFLICT (trade_date) DO UPDATE SET
       trades_executed = ${botTable(bot.name, 'daily_perf')}.trades_executed + 1`,
  )

  console.log(`[scanner] ${botName} OPENED ${positionId} ${strikes.putLong}/${strikes.putShort}P-${strikes.callShort}/${strikes.callLong}C x${effectiveContracts} @ $${effectiveCredit.toFixed(4)} [sandbox:${JSON.stringify(sandboxOrderIds)}]${isFlameFillOnly ? ' [Tradier-fill-only]' : ''}`)
  return `traded:${positionId}`
}

/* ------------------------------------------------------------------ */
/*  Collateral reconciliation (Fix 4)                                  */
/* ------------------------------------------------------------------ */

async function reconcileCollateral(bot: BotDef): Promise<void> {
  try {
    const posTable = botTable(bot.name, 'positions')
    const acctTable = botTable(bot.name, 'paper_account')

    const liveColl = await query(
      `SELECT COALESCE(SUM(collateral_required), 0) AS total_collateral
       FROM ${posTable}
       WHERE status = 'open' AND dte_mode = $1`,
      [bot.dte],
    )
    const actualColl = num(liveColl[0]?.total_collateral)

    const storedAcct = await query(
      `SELECT collateral_in_use, current_balance
       FROM ${acctTable}
       WHERE is_active = TRUE AND dte_mode = $1
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
         WHERE is_active = TRUE AND dte_mode = $3`,
        [actualColl, newBp, bot.dte],
      )
      console.log(
        `[scanner] ${bot.name.toUpperCase()} COLLATERAL RECONCILED: ` +
        `$${storedColl.toFixed(2)} → $${actualColl.toFixed(2)} ` +
        `(BP: $${(storedBal - storedColl).toFixed(2)} → $${newBp.toFixed(2)})`,
      )
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] ${bot.name.toUpperCase()} collateral reconciliation error: ${msg}`)
  }
}

/* ------------------------------------------------------------------ */
/*  Daily sandbox cleanup (Fix 7)                                      */
/* ------------------------------------------------------------------ */

async function dailySandboxCleanup(ct: Date): Promise<void> {
  const todayStr = ct.toISOString().slice(0, 10)

  // Run once per day at market open, OR re-run if stale positions were found
  // but not successfully closed on the first attempt.
  if (_lastSandboxCleanupDate === todayStr) return
  const hhmm = ctHHMM(ct)
  if (hhmm < 830 || hhmm > 900) return

  console.log('[scanner] DAILY SANDBOX CLEANUP: Starting stale position scan...')

  try {
    const accounts = await getLoadedSandboxAccountsAsync()
    if (accounts.length === 0) {
      _lastSandboxCleanupDate = todayStr
      console.log('[scanner] DAILY SANDBOX CLEANUP: No sandbox accounts configured, skipping')
      return
    }

    let totalStale = 0
    let totalClosed = 0
    let totalFailed = 0
    const cleanupDetails: Record<string, { stale: number; closed: number; failed: number }> = {}

    for (const acct of accounts) {
      const positions = await getSandboxAccountPositions(acct.apiKey)
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
        const result = await emergencyCloseSandboxPositions(acct.apiKey, acct.name)
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

    // Only mark cleanup as done if all stale positions were handled.
    // If some failed, allow retry on next scan cycle.
    if (totalFailed === 0) {
      _lastSandboxCleanupDate = todayStr
    } else {
      console.warn(
        `[scanner] SANDBOX CLEANUP: ${totalFailed} positions failed to close — will retry next cycle`,
      )
    }

    if (totalStale > 0) {
      await query(
        `INSERT INTO ${botTable('flame', 'logs')} (level, message, details, dte_mode)
         VALUES ($1, $2, $3, $4)`,
        [
          'SANDBOX_CLEANUP',
          `Daily sandbox cleanup: ${totalStale} stale, ${totalClosed} closed, ${totalFailed} failed`,
          JSON.stringify({ event: 'daily_sandbox_cleanup', date: todayStr, totalStale, totalClosed, totalFailed, perAccount: cleanupDetails }),
          '2DTE',
        ],
      )
    }

    console.log(`[scanner] DAILY SANDBOX CLEANUP COMPLETE: ${totalStale} stale, ${totalClosed} closed, ${totalFailed} failed`)
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
      const positions = await getSandboxAccountPositions(acct.apiKey)
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

  if (negativeCount > 0 && negativeCount >= totalChecked) {
    if (!_sandboxPaperOnly) {
      _sandboxPaperOnly = true
      console.error('[scanner] SANDBOX HEALTH CRITICAL: ALL sandbox accounts unreachable — switching to paper-only mode')
      await query(
        `INSERT INTO ${botTable('flame', 'logs')} (level, message, details, dte_mode)
         VALUES ($1, $2, $3, $4)`,
        [
          'SANDBOX_HEALTH',
          'CRITICAL: ALL sandbox accounts unreachable — auto-switched to paper-only',
          JSON.stringify({ action: 'auto_paper_only', source: 'prescan_health_check', negativeCount, totalChecked }),
          '2DTE',
        ],
      )
    }
  } else if (negativeCount === 0 && _sandboxPaperOnly) {
    _sandboxPaperOnly = false
    console.log('[scanner] SANDBOX HEALTH: All accounts healthy — re-enabling sandbox mirroring')
    await query(
      `INSERT INTO ${botTable('flame', 'logs')} (level, message, details, dte_mode)
       VALUES ($1, $2, $3, $4)`,
      [
        'SANDBOX_HEALTH',
        'RECOVERED: All sandbox accounts healthy — re-enabling sandbox',
        JSON.stringify({ source: 'prescan_health_check', action: 're_enable_sandbox' }),
        '2DTE',
      ],
    )
  }
}

/* ------------------------------------------------------------------ */
/*  Post-EOD sandbox verification (Fix 9)                              */
/* ------------------------------------------------------------------ */

async function postEodSandboxVerify(ct: Date): Promise<void> {
  const hhmm = ctHHMM(ct)
  // Only run in the 2:50-3:10 PM CT window
  if (hhmm < 1450 || hhmm > 1510) return

  const accounts = await getLoadedSandboxAccountsAsync()
  if (accounts.length === 0) return

  const todayYYMMDD = ct.toISOString().slice(2, 10).replace(/-/g, '') // YYMMDD

  for (const acct of accounts) {
    try {
      const positions = await getSandboxAccountPositions(acct.apiKey)
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
        const result = await emergencyCloseSandboxPositions(acct.apiKey, acct.name)

        await query(
          `INSERT INTO ${botTable('flame', 'logs')} (level, message, details, dte_mode)
           VALUES ($1, $2, $3, $4)`,
          [
            result.failed > 0 ? 'CRITICAL' : 'POST_EOD_CHECK',
            `POST-EOD EMERGENCY CLOSE [${acct.name}]: ${result.closed} closed, ${result.failed} failed`,
            JSON.stringify({
              account: acct.name,
              positions: todayPositions.map(p => ({ symbol: p.symbol, qty: p.quantity })),
              close_result: result,
            }),
            '2DTE',
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

    // Auto-decrement PDT counter
    try {
      const pdtCfgRow = await query(
        `SELECT day_trade_count, last_reset_at FROM ${botTable(bot.name, 'pdt_config')}
         WHERE bot_name = $1 LIMIT 1`,
        [bot.name.toUpperCase()],
      )
      const storedCount = int(pdtCfgRow[0]?.day_trade_count)
      const syncResetAt = pdtCfgRow[0]?.last_reset_at ?? null

      let pdtCountSql = `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'pdt_log')}
         WHERE is_day_trade = TRUE AND dte_mode = $1
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

    // Count open positions
    const openRows = await query(
      `SELECT position_id FROM ${botTable(bot.name, 'positions')}
       WHERE status = 'open' AND dte_mode = $1`,
      [bot.dte],
    )
    const openCount = openRows.length
    const hasOpenPosition = openCount > 0

    // Step 1: Always monitor open positions first
    if (hasOpenPosition) {
      const monitorResult = await monitorPosition(bot, ct)
      action = monitorResult.status.startsWith('closed:') ? 'closed' : 'monitoring'
      reason = monitorResult.status
      unrealizedPnl = monitorResult.unrealizedPnl
    }

    // Post-EOD sandbox verification (Fix 9)
    if (action === 'closed' && isAfterEodCutoff(ct)) {
      try {
        await postEodSandboxVerify(ct)
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err)
        console.warn(`[scanner] Post-EOD sandbox verification error: ${msg}`)
      }
    }

    // Step 2: If market closed, just log and return
    if (!isMarketOpen(ct)) {
      if (!hasOpenPosition) {
        action = 'outside_window'
        reason = `Market closed (${ct.getHours()}:${String(ct.getMinutes()).padStart(2, '0')} CT)`
      }
    }
    // Step 3: If in entry window and can open → try to trade
    // max_trades: 0 = unlimited, 1 = single trade only, >1 = multi-trade with cap
    else if (isInEntryWindow(ct, bot)) {
      const maxTrades = botCfg.max_trades
      const canOpenMore = (maxTrades === 0) ||
        (maxTrades > 1 && openCount < maxTrades) ||
        (maxTrades === 1 && !hasOpenPosition)

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
        // No position, but max_trades hit for today (shouldn't happen with proper PDT check)
        action = 'no_trade'
        reason = `max_trades_reached(${openCount}/${maxTrades})`
      }
      // else: has position + monitoring already happened above
    } else if (!hasOpenPosition) {
      action = 'outside_entry_window'
      reason = `Past entry cutoff (${ct.getHours()}:${String(ct.getMinutes()).padStart(2, '0')} CT, cutoff ${botCfg.entry_end})`
    }

    // Take equity snapshot every cycle
    try {
      const acctRows = await query(
        `SELECT current_balance, cumulative_pnl FROM ${botTable(bot.name, 'paper_account')}
         WHERE dte_mode = $1 ORDER BY id DESC LIMIT 1`, [bot.dte],
      )
      const openPosCount = await query(
        `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'positions')}
         WHERE status = 'open' AND dte_mode = $1`, [bot.dte],
      )
      if (acctRows.length > 0) {
        await query(
          `INSERT INTO ${botTable(bot.name, 'equity_snapshots')}
           (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
           VALUES ($1, $2, $3, $4, $5, $6)`,
          [num(acctRows[0]?.current_balance), num(acctRows[0]?.cumulative_pnl),
           unrealizedPnl, int(openPosCount[0]?.cnt), `scan:${action}`, bot.dte],
        )
      }
    } catch (snapErr: unknown) {
      const msg = snapErr instanceof Error ? snapErr.message : String(snapErr)
      console.warn(`[scanner] ${botName} snapshot error: ${msg}`)
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

async function runAllScans(): Promise<void> {
  _scanCount++
  const start = Date.now()
  console.log(`[scanner] === scan cycle #${_scanCount} starting ===`)

  // Load config overrides from DB (Fix 1)
  try {
    await loadConfigOverrides()
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] Config override load failed (using defaults): ${msg}`)
  }

  // Daily sandbox cleanup at market open (Fix 7)
  const ct = getCentralTime()
  try {
    await dailySandboxCleanup(ct)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[scanner] Daily sandbox cleanup failed (non-fatal): ${msg}`)
  }

  // Pre-scan sandbox health check (Fix 8)
  try {
    await prescanSandboxHealthCheck()
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] Sandbox health check failed (non-fatal): ${msg}`)
  }

  // Skip scanning entirely after 3:10 PM CT — market closed, no work to do.
  // Safety net runs in the 2:55-3:05 window, so we keep scanning until 3:10.
  const hhmm = ctHHMM(ct)
  if (hhmm > 1510) {
    const elapsed = ((Date.now() - start) / 1000).toFixed(1)
    console.log(`[scanner] === scan cycle #${_scanCount} skipped (${elapsed}s) — market closed (${hhmm} CT) ===`)
    return
  }

  // Run all bots in parallel
  await Promise.allSettled(
    BOTS.map(bot =>
      scanBot(bot).catch(err => {
        console.error(`[scanner] ${bot.name.toUpperCase()} fatal error:`, err)
      }),
    ),
  )

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
