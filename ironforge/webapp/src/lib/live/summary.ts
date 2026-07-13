import { dbQuery, botTable, sharedTable, num, int, escapeSql, heartbeatName, dteMode, CT_TODAY } from '@/lib/db'
import {
  getProductionPauseState,
  getSandboxAccountBalances,
  getSpark2ProductionBalance,
  getQuoteDetail,
  getIcMarkToMarket,
  calculateIcUnrealizedPnl,
  isConfigured,
} from '@/lib/tradier'
import { isMarketOpen, DEFAULT_EOD_CUTOFF_MIN, formatCTClock } from '@/lib/pt-tiers'
import { deriveCustomerState, getMarketSession } from './state'
import type { LiveSummary, LiveTrade } from './types'

/**
 * Server-side assembly for the customer Live page. Everything is scoped to
 * SPARK production — the one live-money agent. All queries are the same ones
 * the operator dashboard routes use (status, equity-curve/intraday,
 * position-monitor); this module only reshapes them into the narrow,
 * jargon-free customer payload. Honest-data rule: when a source is
 * unavailable, fields are null (the UI renders "—"), never fabricated.
 */

import type { LiveBot } from './viewer'

interface HeartbeatDetails {
  action?: string
  reason?: string
  spot?: number
  vix?: number
}

function parseHeartbeatDetails(raw: unknown): HeartbeatDetails {
  if (!raw) return {}
  try {
    return typeof raw === 'string' ? JSON.parse(raw) : (raw as HeartbeatDetails)
  } catch {
    return {}
  }
}

/** Same bot_state ternary chain as /api/[bot]/status. */
function deriveBotState(hbStatus: string, hbAction: string): string {
  return hbStatus === 'error' ? 'error'
    : hbAction === 'pending_fill' ? 'pending_fill'
    : hbAction === 'awaiting_fill' ? 'awaiting_fill'
    : hbAction === 'monitoring' ? 'monitoring'
    : hbAction === 'traded' || hbAction === 'closed' ? 'traded'
    : hbAction === 'outside_window' || hbAction === 'outside_entry_window' ? 'market_closed'
    : hbStatus === 'idle' ? 'idle'
    : hbStatus === 'active' ? 'scanning'
    : 'unknown'
}

export async function getLiveSummary(BOT: LiveBot = 'spark'): Promise<LiveSummary> {
  const dte = dteMode(BOT)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const prodFilter = `AND COALESCE(account_type, 'sandbox') = 'production'`

  const [
    heartbeatRows,
    accountRows,
    positionCountRows,
    liveStatsRows,
    todayRealizedRows,
    latestSnapshotRows,
    intradayRows,
    pauseState,
    balances,
    spyQuote,
  ] = await Promise.all([
    dbQuery(
      `SELECT scan_count, last_heartbeat, status, details
       FROM ${sharedTable('bot_heartbeats')}
       WHERE bot_name = '${escapeSql(heartbeatName(BOT))}'`,
    ),
    dbQuery(
      `SELECT starting_capital, is_active
       FROM ${botTable(BOT, 'paper_account')}
       WHERE is_active = TRUE ${dteFilter} ${prodFilter}
       ORDER BY id DESC LIMIT 1`,
    ),
    dbQuery(
      `SELECT COUNT(*) as cnt
       FROM ${botTable(BOT, 'positions')}
       WHERE status = 'open' ${dteFilter} ${prodFilter}`,
    ),
    dbQuery(
      `SELECT COALESCE(SUM(realized_pnl), 0) as actual_realized_pnl
       FROM ${botTable(BOT, 'positions')}
       WHERE status IN ('closed', 'expired')
         AND realized_pnl IS NOT NULL
         ${dteFilter} ${prodFilter}`,
    ),
    dbQuery(
      `SELECT COALESCE(SUM(realized_pnl), 0) as today_realized_pnl,
              COUNT(*) as today_trades_closed
       FROM ${botTable(BOT, 'positions')}
       WHERE status IN ('closed', 'expired')
         AND realized_pnl IS NOT NULL
         AND (close_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
         ${dteFilter} ${prodFilter}`,
    ),
    dbQuery(
      `SELECT unrealized_pnl, snapshot_time
       FROM ${botTable(BOT, 'equity_snapshots')}
       WHERE 1=1 ${dteFilter} ${prodFilter}
       ORDER BY snapshot_time DESC LIMIT 1`,
    ),
    // Minute-bucketed intraday equity — same shape as /api/[bot]/equity-curve/intraday.
    dbQuery(
      `SELECT bucket AS snapshot_time,
              SUM(balance) AS balance,
              SUM(unrealized_pnl) AS unrealized_pnl
       FROM (
         SELECT date_trunc('minute', snapshot_time) AS bucket,
                balance, unrealized_pnl,
                ROW_NUMBER() OVER (
                  PARTITION BY date_trunc('minute', snapshot_time),
                               person, COALESCE(account_type, 'sandbox')
                  ORDER BY snapshot_time DESC
                ) AS rn
         FROM ${botTable(BOT, 'equity_snapshots')}
         WHERE (snapshot_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
           ${dteFilter} ${prodFilter}
       ) s
       WHERE rn = 1
       GROUP BY bucket
       ORDER BY bucket ASC`,
    ),
    getProductionPauseState(BOT),
    getSandboxAccountBalances().catch(() => []),
    getQuoteDetail('SPY').catch(() => null),
  ])

  const hb = heartbeatRows[0]
  const hbDetails = parseHeartbeatDetails(hb?.details)
  const botState = deriveBotState(String(hb?.status || 'unknown'), hbDetails.action || '')
  const heartbeatAgeMin = hb?.last_heartbeat
    ? Math.round((Date.now() - new Date(hb.last_heartbeat as string).getTime()) / 60_000)
    : null

  const session = getMarketSession()
  const openPositions = int(positionCountRows[0]?.cnt)
  const todayTradesClosed = int(todayRealizedRows[0]?.today_trades_closed)

  const state = deriveCustomerState({
    botState,
    lastScanReason: hbDetails.reason || null,
    paused: pauseState.paused,
    isActive: accountRows[0]?.is_active === true || accountRows[0]?.is_active === 'true',
    openPositions,
    todayTradesClosed,
    sessionOpen: session.open,
    heartbeatAgeMin,
  })

  // --- Account value + today's result -----------------------------------
  // Primary: the live Tradier production account (pause-independent — same
  // path the status route uses so pausing never blanks the balance).
  // Fallback: DB ledger (starting_capital + Σ realized) with source flagged.
  // Bot-aware balance source: SPARK's production account rows come from
  // ironforge_accounts; SPARK2's single live account lives in env creds and is
  // read directly (never SPARK's rows — accounts must not cross-leak).
  const prodBals = BOT === 'spark'
    ? balances.filter((b) => b.account_type === 'production' && b.total_equity != null)
    : []
  let accountValue: number | null = null
  let todayPnl: number | null = null
  let source: 'tradier' | 'paper_account' = 'paper_account'
  if (BOT === 'spark2') {
    const det = await getSpark2ProductionBalance().catch(() => null)
    if (det?.total_equity != null) {
      accountValue = Math.round(num(det.total_equity) * 100) / 100
      todayPnl = Math.round((num(det.close_pl) + num(det.open_pl)) * 100) / 100
      source = 'tradier'
    }
  }
  if (source !== 'tradier' && prodBals.length > 0) {
    accountValue = Math.round(prodBals.reduce((a, b) => a + num(b.total_equity), 0) * 100) / 100
    // Today's result = broker day realized (close_pl) + open unrealized (open_pl).
    todayPnl = Math.round(
      prodBals.reduce((a, b) => a + num(b.day_pnl) + num(b.unrealized_pnl), 0) * 100,
    ) / 100
    source = 'tradier'
  } else if (source !== 'tradier') {
    const startingCapital = num(accountRows[0]?.starting_capital)
    if (startingCapital > 0) {
      accountValue = Math.round((startingCapital + num(liveStatsRows[0]?.actual_realized_pnl)) * 100) / 100
      todayPnl = Math.round(
        (num(todayRealizedRows[0]?.today_realized_pnl) + num(latestSnapshotRows[0]?.unrealized_pnl)) * 100,
      ) / 100
    }
  }
  const todayPnlPct =
    accountValue != null && todayPnl != null && accountValue - todayPnl > 0
      ? Math.round((todayPnl / (accountValue - todayPnl)) * 10000) / 100
      : null

  // --- Market conditions (derived labels, not a data feed) ---------------
  const vix = typeof hbDetails.vix === 'number' ? hbDetails.vix : null
  const spyChangePct = spyQuote?.change_percentage ?? null
  const trend: LiveSummary['market']['trend'] =
    spyChangePct == null ? null
    : spyChangePct > 0.15 ? 'Bullish'
    : spyChangePct < -0.15 ? 'Bearish'
    : 'Holding Steady'

  // Bands follow SPARK's live gates: the scanner skips entries above VIX 40
  // (the customer-facing "No Trading" line), and 20+ reads as elevated.
  const blocked = state.key === 'BLOCKED' || (vix != null && vix > 40)
  const caution = !blocked && vix != null && vix >= 20
  const condition: LiveSummary['market']['condition'] =
    blocked ? 'no_trading' : caution ? 'caution' : 'good'
  const conditionLine =
    blocked ? 'Conditions do not meet your protection standards today.'
    : caution ? 'Conditions are mixed — Spark is being extra selective.'
    : 'Conditions are favorable for your strategy.'
  const outlook = blocked ? 'Protective' : caution ? 'Cautious' : 'Favorable'

  const intraday = intradayRows.map((r) => ({
    timestamp: String(r.snapshot_time),
    equity: Math.round((num(r.balance) + num(r.unrealized_pnl)) * 100) / 100,
  }))

  return {
    state,
    market: {
      ...session,
      condition,
      condition_line: conditionLine,
      spy_price: spyQuote?.last ?? null,
      spy_change_pct: spyChangePct,
      vix,
      vix_as_of: hb?.last_heartbeat ? String(hb.last_heartbeat) : null,
      trend,
      outlook,
      derived: true,
    },
    account: {
      value: accountValue,
      today_pnl: todayPnl,
      today_pnl_pct: todayPnlPct,
      source,
    },
    intraday,
    membership: {
      plan: 'Forge Automate',
      badge: 'Early Access',
      // Static placeholder matching the approved Home design — no billing/trial
      // state exists in the DB yet (same precedent as plan/badge above).
      trial: { label: '5 Day Free Trial', day: 2, total_days: 5, ends_label: 'Ends May 25, 2025' },
    },
    as_of: new Date().toISOString(),
  }
}

export async function getLiveTrade(BOT: LiveBot = 'spark'): Promise<LiveTrade> {
  const dte = dteMode(BOT)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const prodFilter = `AND COALESCE(account_type, 'sandbox') = 'production'`

  const [positionRows, sparkSeriesRows] = await Promise.all([
    dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts, total_credit, spread_width, open_time
       FROM ${botTable(BOT, 'positions')}
       WHERE status = 'open' ${dteFilter} ${prodFilter}
       ORDER BY open_time DESC`,
    ),
    // Today's unrealized-P&L stream for the mini chart — real scanner
    // snapshots, minute-bucketed like the intraday equity curve.
    dbQuery(
      `SELECT bucket AS snapshot_time, SUM(unrealized_pnl) AS unrealized_pnl
       FROM (
         SELECT date_trunc('minute', snapshot_time) AS bucket,
                unrealized_pnl,
                ROW_NUMBER() OVER (
                  PARTITION BY date_trunc('minute', snapshot_time),
                               person, COALESCE(account_type, 'sandbox')
                  ORDER BY snapshot_time DESC
                ) AS rn
         FROM ${botTable(BOT, 'equity_snapshots')}
         WHERE (snapshot_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
           ${dteFilter} ${prodFilter}
       ) s
       WHERE rn = 1
       GROUP BY bucket
       ORDER BY bucket ASC`,
    ),
  ])

  const sparkSeries = sparkSeriesRows.map((r) => ({
    timestamp: String(r.snapshot_time),
    pnl: Math.round(num(r.unrealized_pnl) * 100) / 100,
  }))

  if (positionRows.length === 0) {
    // No open trade — surface today's realized result when trading is done.
    const todaysClosed = await dbQuery(
      `SELECT COALESCE(SUM(realized_pnl), 0) as pnl,
              COALESCE(SUM(total_credit * contracts * 100), 0) as credit_dollars,
              COUNT(*) as cnt
       FROM ${botTable(BOT, 'positions')}
       WHERE status IN ('closed', 'expired')
         AND realized_pnl IS NOT NULL
         AND (close_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
         ${dteFilter} ${prodFilter}`,
    )
    const closedCount = int(todaysClosed[0]?.cnt)
    const pnl = Math.round(num(todaysClosed[0]?.pnl) * 100) / 100
    const creditDollars = num(todaysClosed[0]?.credit_dollars)
    return {
      active: false,
      opened_at: null,
      expires_label: null,
      time_in_trade_min: null,
      unrealized_pnl: null,
      unrealized_pnl_pct: null,
      pnl_source: 'none',
      spark_series: sparkSeries,
      today_result: closedCount > 0
        ? {
            pnl,
            pct: creditDollars > 0 ? Math.round((pnl / creditDollars) * 10000) / 100 : null,
          }
        : null,
    }
  }

  // SPARK opens at most one trade a day — describe the most recent open position.
  const pos = positionRows[0]
  const contracts = int(pos.contracts)
  const entryCredit = num(pos.total_credit)
  const expiration =
    pos.expiration?.toISOString?.()?.slice(0, 10) ||
    (pos.expiration ? String(pos.expiration).slice(0, 10) : '')

  let unrealizedPnl: number | null = null
  let unrealizedPnlPct: number | null = null
  let pnlSource: LiveTrade['pnl_source'] = 'none'

  if (isConfigured()) {
    try {
      const mtm = await getIcMarkToMarket(
        pos.ticker || 'SPY',
        expiration,
        num(pos.put_short_strike),
        num(pos.put_long_strike),
        num(pos.call_short_strike),
        num(pos.call_long_strike),
        entryCredit,
      )
      if (mtm) {
        const spreadWidth = num(pos.spread_width) || (num(pos.put_short_strike) - num(pos.put_long_strike))
        const mtmLast = mtm.cost_to_close_last
        unrealizedPnl = calculateIcUnrealizedPnl(entryCredit, mtmLast, contracts, spreadWidth)
        unrealizedPnlPct = entryCredit > 0
          ? Math.round(((entryCredit - Math.min(Math.max(0, mtmLast), spreadWidth)) / entryCredit) * 10000) / 100
          : null
        pnlSource = 'live'
      }
    } catch {
      // fall through to the scanner-snapshot fallback below
    }
  }

  if (unrealizedPnl == null && sparkSeries.length > 0) {
    // Scanner's own validated MTM — more reliable than stale webapp quotes.
    unrealizedPnl = sparkSeries[sparkSeries.length - 1].pnl
    pnlSource = 'scanner_snapshot'
  }

  // Live point keeps the sparkline current while the market is open.
  if (pnlSource === 'live' && unrealizedPnl != null && isMarketOpen() && sparkSeries.length > 0) {
    sparkSeries.push({ timestamp: new Date().toISOString(), pnl: unrealizedPnl })
  }

  const openedAt = pos.open_time ? new Date(pos.open_time as string) : null
  const timeInTradeMin = openedAt
    ? Math.max(0, Math.round((Date.now() - openedAt.getTime()) / 60_000))
    : null

  // Plain-English auto-close label: expiring today → the EOD safety cutoff
  // time; otherwise the expiration date (SPARK's 1DTE swing holds overnight).
  const ctToday = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
  const expiresLabel = expiration === ctToday
    ? `Today ${formatCTClock(DEFAULT_EOD_CUTOFF_MIN)} CT`
    : new Date(`${expiration}T12:00:00`).toLocaleDateString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric',
      })

  return {
    active: true,
    opened_at: openedAt ? openedAt.toISOString() : null,
    expires_label: expiresLabel,
    time_in_trade_min: timeInTradeMin,
    unrealized_pnl: unrealizedPnl,
    unrealized_pnl_pct: unrealizedPnlPct,
    pnl_source: pnlSource,
    spark_series: sparkSeries,
    today_result: null,
  }
}
