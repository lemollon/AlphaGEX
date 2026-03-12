// @ts-nocheck
/**
 * ⚠️ DEAD CODE — DO NOT IMPORT
 * The real scanner runs on Databricks: ironforge/databricks/ironforge_scanner.py
 * This file imports from the dead PostgreSQL client (@/lib/db) and is NOT used.
 *
 * IronForge Scan Loop — runs INSIDE the Next.js process.
 *
 * Every 1 minute, for FLAME (2DTE), SPARK (1DTE), and INFERNO (0DTE):
 *   1. If position is open → monitor MTM, check PT/SL/EOD
 *   2. If no position + within entry window + not traded today → try opening
 *   3. Log every scan, update heartbeat, take equity snapshot
 *
 * All trading logic mirrors force-trade/force-close route handlers exactly.
 * This module has ZERO Next.js dependencies — pure Node.js + pg + fetch.
 */

import { query, botTable, num, int, CT_TODAY } from './db'
import {
  getQuote,
  getOptionExpirations,
  getIcEntryCredit,
  getIcMarkToMarket,
  isConfigured,
  placeIcOrderAllAccounts,
  closeIcOrderAllAccounts,
  type SandboxOrderInfo,
  type SandboxCloseInfo,
} from './tradier'

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const SCAN_INTERVAL_MS = 60 * 1000 // 1 minute
const BOTS = [
  { name: 'flame', dte: '2DTE', minDte: 2, maxTradesPerDay: 1 },
  { name: 'spark', dte: '1DTE', minDte: 1, maxTradesPerDay: 1 },
  { name: 'inferno', dte: '0DTE', minDte: 0, maxTradesPerDay: 3 },
] as const

type BotDef = (typeof BOTS)[number]

/* ------------------------------------------------------------------ */
/*  Market hours (Central Time)                                        */
/* ------------------------------------------------------------------ */

function getCentralTime(): Date {
  // Build a Date that represents "now" in America/Chicago
  const str = new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' })
  return new Date(str)
}

function isMarketOpen(ct: Date): boolean {
  const dow = ct.getDay()
  if (dow === 0 || dow === 6) return false
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  return hhmm >= 830 && hhmm <= 1530
}

function isInEntryWindow(ct: Date): boolean {
  const dow = ct.getDay()
  if (dow === 0 || dow === 6) return false
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  return hhmm >= 830 && hhmm <= 1400
}

function isAfterEodCutoff(ct: Date): boolean {
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  return hhmm >= 1545 // 3:45 PM CT = 15:45
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
/*  Strike calculation (copied from force-trade — DO NOT CHANGE)       */
/* ------------------------------------------------------------------ */

function calculateStrikes(spot: number, expectedMove: number) {
  const SD = 1.2
  const WIDTH = 5

  const minEM = spot * 0.005
  const em = Math.max(expectedMove, minEM)

  let putShort = Math.floor(spot - SD * em)
  let callShort = Math.ceil(spot + SD * em)
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

  // Monitor ALL positions (multi-position for INFERNO)
  let totalUnrealized = 0
  let anyAction = 'monitoring'
  for (const pos of positions) {
    const monResult = await monitorSinglePosition(bot, ct, pos)
    totalUnrealized += monResult.unrealizedPnl
    if (monResult.status.startsWith('closed:')) anyAction = monResult.status
  }
  return { status: anyAction, unrealizedPnl: totalUnrealized }
}

async function monitorSinglePosition(
  bot: BotDef, ct: Date, pos: Record<string, any>,
): Promise<{ status: string; unrealizedPnl: number }> {
  const entryCredit = num(pos.total_credit)
  const contracts = int(pos.contracts)
  const collateral = num(pos.collateral_required)
  const profitTargetPrice = Math.round(entryCredit * 0.7 * 10000) / 10000
  const stopLossPrice = Math.round(entryCredit * 2.0 * 10000) / 10000
  const ticker = pos.ticker || 'SPY'
  const expiration = pos.expiration?.toISOString?.()?.slice(0, 10) || String(pos.expiration).slice(0, 10)

  // Check if position is from a prior day (stale holdover)
  const openDate = pos.open_time ? new Date(pos.open_time).toISOString().slice(0, 10) : null
  const todayStr = ct.toISOString().slice(0, 10)
  const isStaleHoldover = openDate !== null && openDate < todayStr

  // EOD cutoff or stale holdover → force close
  // Use entryCredit as fallback close price when Tradier data is unavailable (pre-market/pending)
  if (isAfterEodCutoff(ct) || isStaleHoldover) {
    const reason = isStaleHoldover ? 'stale_holdover' : 'eod_cutoff'
    try {
      await closePosition(bot, pos.position_id, ticker, expiration,
        num(pos.put_short_strike), num(pos.put_long_strike),
        num(pos.call_short_strike), num(pos.call_long_strike),
        contracts, entryCredit, collateral, reason)
    } catch (err: any) {
      // Fallback: close at entry credit (break-even) if Tradier/sandbox unavailable
      console.warn(`[scanner] ${bot.name.toUpperCase()}: Force-close failed, retrying at entry credit: ${err.message}`)
      await closePosition(bot, pos.position_id, ticker, expiration,
        num(pos.put_short_strike), num(pos.put_long_strike),
        num(pos.call_short_strike), num(pos.call_long_strike),
        contracts, entryCredit, collateral, reason, entryCredit)
    }
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

  if (!mtm) return { status: 'monitoring:mtm_failed', unrealizedPnl: 0 }

  const costToClose = mtm.cost_to_close

  // Profit target: cost_to_close <= 70% of entry credit
  if (costToClose <= profitTargetPrice) {
    await closePosition(bot, pos.position_id, ticker, expiration,
      num(pos.put_short_strike), num(pos.put_long_strike),
      num(pos.call_short_strike), num(pos.call_long_strike),
      contracts, entryCredit, collateral, 'profit_target', costToClose)
    return { status: `closed:profit_target@${costToClose.toFixed(4)}`, unrealizedPnl: 0 }
  }

  // Stop loss: cost_to_close >= 200% of entry credit
  if (costToClose >= stopLossPrice) {
    await closePosition(bot, pos.position_id, ticker, expiration,
      num(pos.put_short_strike), num(pos.put_long_strike),
      num(pos.call_short_strike), num(pos.call_long_strike),
      contracts, entryCredit, collateral, 'stop_loss', costToClose)
    return { status: `closed:stop_loss@${costToClose.toFixed(4)}`, unrealizedPnl: 0 }
  }

  const unrealizedPnl = Math.round((entryCredit - costToClose) * 100 * contracts * 100) / 100
  return { status: `monitoring:mtm=${costToClose.toFixed(4)} uPnL=$${unrealizedPnl.toFixed(2)}`, unrealizedPnl }
}

/* ------------------------------------------------------------------ */
/*  Close position (mirrors force-close route exactly)                 */
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

  // Mirror close to sandbox FIRST so we can read back actual fill prices
  let sandboxCloseInfo: Record<string, SandboxCloseInfo> = {}
  try {
    const sbRows = await query(
      `SELECT sandbox_order_id FROM ${botTable(bot.name, 'positions')}
       WHERE position_id = $1 AND dte_mode = $2`,
      [positionId, bot.dte],
    )
    let sandboxOpenInfo: Record<string, any> | null = null
    if (sbRows[0]?.sandbox_order_id) {
      try { sandboxOpenInfo = JSON.parse(sbRows[0].sandbox_order_id) } catch {}
    }
    sandboxCloseInfo = await closeIcOrderAllAccounts(
      ticker, expiration, putShort, putLong, callShort, callLong,
      contracts, estimatedPrice, positionId, sandboxOpenInfo,
    )
  } catch (e: any) {
    console.warn(`[scanner] Sandbox close failed for ${positionId}: ${e.message}`)
  }

  // Use User's actual fill price if available, otherwise fall back to estimate
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

  // Close position
  await query(
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
      // Same-day round trip = day trade
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
  } catch (pdtErr: any) {
    console.warn(`[scanner] PDT counter update failed: ${pdtErr.message}`)
  }
}

/* ------------------------------------------------------------------ */
/*  Open new trade (mirrors force-trade route exactly)                 */
/* ------------------------------------------------------------------ */

async function tryOpenTrade(bot: BotDef, spot: number, vix: number): Promise<string> {
  // VIX filter
  if (vix > 32) return `skip:vix_too_high(${vix.toFixed(1)})`

  // PDT config check — read enforcement state from pdt_config table
  const pdtConfigRows = await query(
    `SELECT pdt_enabled, max_day_trades, max_trades_per_day, last_reset_at
     FROM ${botTable(bot.name, 'pdt_config')}
     WHERE bot_name = $1 LIMIT 1`,
    [bot.name.toUpperCase()],
  )
  const pdtCfg = pdtConfigRows[0]
  const pdtEnabled = pdtCfg ? ![false, 'false', 'f', 0, '0'].includes(pdtCfg.pdt_enabled) : true
  // 0 = disabled/unlimited, so don't fall back to a positive number
  const maxDayTrades = pdtCfg?.max_day_trades != null ? int(pdtCfg.max_day_trades) : 4
  const maxTradesPerDay = pdtCfg?.max_trades_per_day != null ? int(pdtCfg.max_trades_per_day) : 1
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

  // PDT rolling window check — live COUNT from pdt_log (source of truth)
  // Must match the 6-day window used by the /api/[bot]/pdt route and Python trader
  // Respects last_reset_at: trades created before reset are excluded
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
  const buyingPower = num(acct.buying_power)
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

  // Strikes + credits
  const strikes = calculateStrikes(spot, expectedMove)
  const credits = await getIcEntryCredit(
    'SPY', expiration,
    strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
  )
  if (!credits || credits.totalCredit < 0.05) {
    return `skip:credit_too_low($${credits?.totalCredit?.toFixed(4) ?? '0'})`
  }

  // Sizing
  const spreadWidth = strikes.putShort - strikes.putLong
  const collateralPer = Math.max(0, (spreadWidth - credits.totalCredit) * 100)
  if (collateralPer <= 0) return 'skip:bad_collateral'
  const usableBP = buyingPower * 0.85
  const maxContracts = Math.min(10, Math.max(1, Math.floor(usableBP / collateralPer)))
  const totalCollateral = collateralPer * maxContracts
  const maxProfit = credits.totalCredit * 100 * maxContracts
  const maxLoss = totalCollateral

  // Position ID
  const now = new Date()
  const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '')
  const hex = Math.random().toString(16).slice(2, 8).toUpperCase()
  const botName = bot.name.toUpperCase()
  const positionId = `${botName}-${dateStr}-${hex}`

  // Insert position
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
      strikes.putShort, strikes.putLong, credits.putCredit,
      strikes.callShort, strikes.callLong, credits.callCredit,
      maxContracts, spreadWidth, credits.totalCredit, maxLoss, maxProfit,
      totalCollateral,
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

  // Mirror to sandbox
  let sandboxOrderIds: Record<string, SandboxOrderInfo> = {}
  try {
    sandboxOrderIds = await placeIcOrderAllAccounts(
      'SPY', expiration,
      strikes.putShort, strikes.putLong, strikes.callShort, strikes.callLong,
      maxContracts, credits.totalCredit, positionId,
    )
    if (Object.keys(sandboxOrderIds).length > 0) {
      await query(
        `UPDATE ${botTable(bot.name, 'positions')}
         SET sandbox_order_id = $1, updated_at = NOW()
         WHERE position_id = $2`,
        [JSON.stringify(sandboxOrderIds), positionId],
      )
    }
  } catch (e: any) {
    console.warn(`[scanner] Sandbox open failed for ${positionId}: ${e.message}`)
  }

  // Deduct collateral
  await query(
    `UPDATE ${botTable(bot.name, 'paper_account')}
     SET collateral_in_use = collateral_in_use + $1,
         buying_power = buying_power - $1,
         updated_at = NOW()
     WHERE id = $2`,
    [totalCollateral, acct.id],
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
      credits.totalCredit, adv.confidence, true, `Auto scan | ${adv.reasoning}`,
      false, bot.dte,
    ],
  )

  // Trade log
  await query(
    `INSERT INTO ${botTable(bot.name, 'logs')} (level, message, details, dte_mode)
     VALUES ($1, $2, $3, $4)`,
    [
      'TRADE_OPEN',
      `AUTO TRADE: ${positionId} ${strikes.putLong}/${strikes.putShort}P-${strikes.callShort}/${strikes.callLong}C x${maxContracts} @ $${credits.totalCredit.toFixed(4)}`,
      JSON.stringify({
        position_id: positionId, contracts: maxContracts,
        credit: credits.totalCredit, collateral: totalCollateral,
        source: 'scanner', sandbox_order_ids: sandboxOrderIds,
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
    ['SPY', positionId, maxContracts, credits.totalCredit, bot.dte],
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

  console.log(`[scanner] ${botName} OPENED ${positionId} ${strikes.putLong}/${strikes.putShort}P-${strikes.callShort}/${strikes.callLong}C x${maxContracts} @ $${credits.totalCredit.toFixed(4)} [sandbox:${JSON.stringify(sandboxOrderIds)}]`)
  return `traded:${positionId}`
}

/* ------------------------------------------------------------------ */
/*  Single scan cycle for one bot                                      */
/* ------------------------------------------------------------------ */

async function scanBot(bot: BotDef): Promise<void> {
  const ct = getCentralTime()
  const botName = bot.name.toUpperCase()
  let action = 'scan'
  let reason = ''
  let spot = 0
  let vix = 0
  let unrealizedPnl = 0

  try {
    // Check bot active state
    const configRows = await query(
      `SELECT id FROM ${botTable(bot.name, 'config')}
       WHERE dte_mode = $1 LIMIT 1`, [bot.dte],
    )
    // If config doesn't exist, bot is active by default

    // Step 1: Always monitor open positions first
    // Auto-decrement PDT counter: recount actual day trades in rolling window
    // Runs every scan but is cheap (single COUNT query)
    // Respects last_reset_at: trades before reset are excluded from count
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
    } catch (pdtSyncErr: any) {
      console.warn(`[scanner] ${bot.name.toUpperCase()} PDT sync error: ${pdtSyncErr.message}`)
    }

    const openRows = await query(
      `SELECT position_id FROM ${botTable(bot.name, 'positions')}
       WHERE status = 'open' AND dte_mode = $1 LIMIT 1`, [bot.dte],
    )
    const hasOpenPosition = openRows.length > 0

    if (hasOpenPosition) {
      // Monitor position even outside entry window (but within market hours or for stale detection)
      const monitorResult = await monitorPosition(bot, ct)
      action = monitorResult.status.startsWith('closed:') ? 'closed' : 'monitoring'
      reason = monitorResult.status
      unrealizedPnl = monitorResult.unrealizedPnl
    }

    // Step 2: If market closed, just log and return
    if (!isMarketOpen(ct)) {
      if (!hasOpenPosition) {
        action = 'outside_window'
        reason = `Market closed (${ct.getHours()}:${String(ct.getMinutes()).padStart(2, '0')} CT)`
      }
    }
    // Step 3: If in entry window and no position → try to trade
    else if (!hasOpenPosition && isInEntryWindow(ct)) {
      // Fetch market data
      if (!isConfigured()) {
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
      action = 'outside_entry_window'
      reason = `Past entry cutoff (${ct.getHours()}:${String(ct.getMinutes()).padStart(2, '0')} CT, cutoff 14:00)`
    }

    // Take equity snapshot every cycle
    try {
      const acctRows = await query(
        `SELECT current_balance, cumulative_pnl FROM ${botTable(bot.name, 'paper_account')}
         WHERE dte_mode = $1 ORDER BY id DESC LIMIT 1`, [bot.dte],
      )
      const openCount = await query(
        `SELECT COUNT(*) as cnt FROM ${botTable(bot.name, 'positions')}
         WHERE status = 'open' AND dte_mode = $1`, [bot.dte],
      )
      if (acctRows.length > 0) {
        await query(
          `INSERT INTO ${botTable(bot.name, 'equity_snapshots')}
           (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
           VALUES ($1, $2, $3, $4, $5, $6)`,
          [num(acctRows[0]?.current_balance), num(acctRows[0]?.cumulative_pnl),
           unrealizedPnl, int(openCount[0]?.cnt), `scan:${action}`, bot.dte],
        )
      }
    } catch (snapErr: any) {
      console.warn(`[scanner] ${botName} snapshot error: ${snapErr.message}`)
    }

  } catch (err: any) {
    action = 'error'
    reason = err.message
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
  } catch (hbErr: any) {
    console.warn(`[scanner] ${botName} heartbeat error: ${hbErr.message}`)
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
  } catch (logErr: any) {
    console.warn(`[scanner] ${botName} log error: ${logErr.message}`)
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

/** Fire-and-forget wrapper — skips if previous cycle still running. */
function safeRunAllScans(): void {
  if (_running) {
    console.log('[scanner] previous cycle still running, skipping this tick')
    return
  }
  _running = true
  runAllScans()
    .catch(err => {
      console.error('[scanner] scan cycle error (interval continues):', err)
    })
    .finally(() => {
      _running = false
    })
}

export function startScanner(): void {
  if (_started) return
  _started = true

  console.log('[scanner] IronForge scan loop starting — 1 min interval for all bots')

  // First scan immediately (fire-and-forget)
  safeRunAllScans()

  // Persistent interval — stored in module-level variable so it can never be GC'd
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
  // Run all bots in parallel so slow API calls don't block each other
  await Promise.allSettled(
    BOTS.map(bot =>
      scanBot(bot).catch(err => {
        console.error(`[scanner] ${bot.name.toUpperCase()} fatal error:`, err)
      }),
    ),
  )
  const elapsed = ((Date.now() - start) / 1000).toFixed(1)
  console.log(`[scanner] === scan cycle #${_scanCount} complete (${elapsed}s) ===`)
}
