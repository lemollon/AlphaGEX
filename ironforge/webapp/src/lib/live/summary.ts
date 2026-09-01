import { dbQuery, botTable, sharedTable, num, int, escapeSql, heartbeatName, dteMode, CT_TODAY } from '@/lib/db'
import {
  getProductionPauseState,
  getOwnerPauseState,
  getSandboxAccountBalances,
  getFlameProductionBalance,
  getQuoteDetail,
  getIcMarkToMarket,
  calculateIcUnrealizedPnl,
  isConfigured,
} from '@/lib/tradier'
import { isMarketOpen, DEFAULT_EOD_CUTOFF_MIN, formatCTClock } from '@/lib/pt-tiers'
import { deriveCustomerState, getMarketSession } from './state'
import { countProtectiveSkipDays } from './riskProtection'
import type { LiveSummary, LiveTrade, LiveOpenPosition } from './types'

/**
 * Server-side assembly for the customer Live page. Everything is scoped to
 * SPARK production — the one live-money agent. All queries are the same ones
 * the operator dashboard routes use (status, equity-curve/intraday,
 * position-monitor); this module only reshapes them into the narrow,
 * jargon-free customer payload. Honest-data rule: when a source is
 * unavailable, fields are null (the UI renders "—"), never fabricated.
 */

import { resolveAccountMode, scopeFilter, LIVE_BOT_LABEL, paperDisclosure, type LiveBot } from './viewer'
import { deriveSwingMeta } from './swing'
import { sparkRegimeBpCap, isSparkV2SizingBot } from '@/lib/spark-sizing'
import { BACKTEST_ANCHORS, compareToBacktestAnchor } from './backtestAnchor'

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

export async function getLiveSummary(
  BOT: LiveBot = 'spark',
  /**
   * Operators only. Permits summing multiple production accounts into one
   * balance (the fleet view). See the MULTI-ACCOUNT SAFETY note below.
   */
  { allowAggregate = false, person = null, mode }: { allowAggregate?: boolean; person?: string | null; mode?: 'paper' | 'production' } = {},
): Promise<LiveSummary> {
  const dte = dteMode(BOT)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const prodFilter = scopeFilter(BOT, person, allowAggregate, mode)

  const [
    heartbeatRows,
    accountRows,
    positionCountRows,
    liveStatsRows,
    todayRealizedRows,
    latestSnapshotRows,
    intradayRows,
    pauseState,
    ownerPause,
    balances,
    spyQuote,
    protectiveScanRows,
    tradedCtDateRows,
  ] = await Promise.all([
    dbQuery(
      `SELECT scan_count, last_heartbeat, status, details
       FROM ${sharedTable('bot_heartbeats')}
       WHERE bot_name = '${escapeSql(heartbeatName(BOT))}'`,
    ),
    dbQuery(
      // NOT filtered on is_active: the newest row in scope IS this viewer's
      // account, and whether it is switched on is a separate question we have to
      // be able to answer. Filtering here made "row exists but inactive" and "no
      // row at all" indistinguishable — both returned zero rows and both rendered
      // as "trading is temporarily disabled".
      `SELECT starting_capital, is_active
       FROM ${botTable(BOT, 'paper_account')}
       WHERE TRUE ${dteFilter} ${prodFilter}
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
    getOwnerPauseState(BOT),
    getSandboxAccountBalances().catch(() => []),
    getQuoteDetail('SPY').catch(() => null),
    // Risky-setups-skipped counter: this month's SCAN log rows, CT-month
    // boundary computed in SQL so there is no app/DB timezone mismatch.
    // null (not []) on failure — distinguishes "no scans this month" from
    // "the query errored", which risk_protection below must tell apart.
    dbQuery<{ log_time: string | Date; details: string | null }>(
      `SELECT log_time, details
       FROM ${botTable(BOT, 'logs')}
       WHERE level = 'SCAN'
         AND (log_time AT TIME ZONE 'America/Chicago') >= date_trunc('month', (NOW() AT TIME ZONE 'America/Chicago'))
         ${dteFilter}`,
    ).catch(() => null),
    // Same scope (dte_mode + account) as the rest of this page's queries —
    // reuses prodFilter so "traded" means the same account this summary
    // otherwise describes.
    dbQuery<{ d: string | Date }>(
      `SELECT DISTINCT (open_time AT TIME ZONE 'America/Chicago')::date AS d
       FROM ${botTable(BOT, 'positions')}
       WHERE (open_time AT TIME ZONE 'America/Chicago') >= date_trunc('month', (NOW() AT TIME ZONE 'America/Chicago'))
         ${dteFilter} ${prodFilter}`,
    ).catch(() => null),
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

  // The viewer's own account is paused. An operator's fleet view has no single
  // `person`, so it never reports a self-pause — it reports the fleet switch.
  const selfPaused = !!person && ownerPause.paused.has(person)

  const state = deriveCustomerState({
    botState,
    lastScanReason: hbDetails.reason || null,
    // Two layers. The fleet switch is operator-level and the customer's Resume
    // button cannot clear it; their OWN pause is theirs to undo. selfPaused
    // drives that distinction in state.ts.
    paused: pauseState.paused || selfPaused,
    selfPaused,
    accountLinked: accountRows.length > 0,
    isActive: accountRows[0]?.is_active === true || accountRows[0]?.is_active === 'true',
    openPositions,
    todayTradesClosed,
    sessionOpen: session.open,
    heartbeatAgeMin,
    agent: LIVE_BOT_LABEL[BOT],
  })

  // --- Account value + today's result -----------------------------------
  // Primary: the live Tradier production account (pause-independent — same
  // path the status route uses so pausing never blanks the balance).
  // Fallback: DB ledger (starting_capital + Σ realized) with source flagged.
  // Bot-aware balance source: SPARK's production account rows come from
  // ironforge_accounts. Paper bots (FLAME) have no broker account at all: never consult Tradier for
  // them, always derive from the paper ledger below. Guarding explicitly rather
  // than relying on the per-bot branches falling through to the same place.
  const paper = resolveAccountMode(BOT) === 'paper'
  const allProdBals = BOT === 'spark' && !paper
    ? balances.filter((b) =>
        b.account_type === 'production' &&
        b.total_equity != null &&
        // Scope to the owner when the viewer is pinned to one (customers).
        // ironforge_accounts.person is surfaced as SandboxAccountBalance.name.
        (person == null || b.name === person))
    : []
  // MULTI-ACCOUNT SAFETY. The lines below SUM every production account for the bot.
  // That is correct for an operator (it is the fleet total) and catastrophically
  // wrong for a customer the moment a second person's Tradier account exists in
  // ironforge_accounts — every customer's "Your account" would become everyone's
  // money. The scanner already trades each `person` independently
  // (scanner.ts: "Sync PRODUCTION paper_accounts (each person independently)"),
  // so a second account is an expected future state, not a hypothetical.
  //
  // Until ironforge_customer_bots carries the owning `person` and these queries
  // scope to it, refuse to aggregate for a non-operator. Showing an honest empty
  // state beats showing someone else's balance.
  const aggregateBlocked =
    !allowAggregate && (!person || allProdBals.length > 1)
  const prodBals = aggregateBlocked ? [] : allProdBals
  if (aggregateBlocked) {
    console.warn(
      `[live/summary] ${BOT}: ${allProdBals.length} production accounts but viewer is not ` +
      `an operator — refusing to aggregate. Scope by person before onboarding a 2nd account.`,
    )
  }
  let accountValue: number | null = null
  let todayPnl: number | null = null
  let source: 'tradier' | 'paper_account' = 'paper_account'
  // FLAME's live account is credentialed from env. 🚨 Without this branch the
  // customer page derived FLAME's value from the DB ledger while the operator
  // console read Tradier — the same number rendered two different ways, which
  // is the divergence this whole change fixes. The DB fallback below still
  // applies when creds are absent (paper FLAME).
  if (BOT === 'flame' && !paper) {
    const det = await getFlameProductionBalance().catch(() => null)
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
    : caution ? `Conditions are mixed — ${LIVE_BOT_LABEL[BOT]} is being extra selective.`
    : 'Conditions are favorable for your strategy.'
  const outlook = blocked ? 'Protective' : caution ? 'Cautious' : 'Favorable'

  // Day P&L per point = equity − day-open BALANCE (not day-open equity). Balance only
  // moves on closes, so an overnight swing-hold's unrealized carry shows from the first
  // tick and the curve TERMINATES at the same number the "Today's Result" headline shows.
  // (2026-07-17 bug: anchoring at day-open EQUITY baked a −$259 overnight carry
  // into the baseline — a −$208 day rendered as a +$220 green mountain.)
  const dayOpenBalance = intradayRows.length ? num(intradayRows[0].balance) : null
  const intraday = intradayRows.map((r) => ({
    timestamp: String(r.snapshot_time),
    equity: Math.round((num(r.balance) + num(r.unrealized_pnl)) * 100) / 100,
    pnl: dayOpenBalance != null
      ? Math.round((num(r.balance) + num(r.unrealized_pnl) - dayOpenBalance) * 100) / 100
      : null,
  }))

  // --- Risky setups skipped this month --------------------------------
  // Honest-data rule: null (never a fabricated number) when either query
  // above failed. A count of exactly 0 is real and must still render.
  let riskProtection: LiveSummary['risk_protection'] = null
  if (protectiveScanRows !== null && tradedCtDateRows !== null) {
    try {
      const logs = protectiveScanRows.map((r) => {
        let reason: string | null = null
        try {
          // details is a JSON STRING, not JSONB — one malformed row must not
          // break the others, so this parse is per-row.
          const parsed = typeof r.details === 'string' ? JSON.parse(r.details) : r.details
          reason = parsed && typeof parsed.reason === 'string' ? parsed.reason : null
        } catch {
          reason = null
        }
        return { logTime: r.log_time, reason }
      })
      const tradedCtDates = new Set(
        tradedCtDateRows
          .map((r) => (r.d instanceof Date ? r.d.toISOString().slice(0, 10) : String(r.d).slice(0, 10)))
          .filter(Boolean),
      )
      riskProtection = {
        skipped_count: countProtectiveSkipDays({ logs, tradedCtDates }),
        period_label: 'this month',
      }
    } catch {
      riskProtection = null
    }
  }

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
      mode: mode ?? resolveAccountMode(BOT),
      disclosure: paper ? paperDisclosure(BOT) : null,
    },
    intraday,
    membership: {
      plan: 'IronForge Membership',
      badge: 'Early Access',
      // Honest-data rule: no billing/trial state exists in the DB yet, so no
      // fabricated countdown — consumers null-guard and fall back to the badge.
      trial: null,
    },
    risk_protection: riskProtection,
    as_of: new Date().toISOString(),
  }
}

/**
 * P&L as a percentage of the trade's own potential, NOT of buying power.
 *
 * A gain is shown against MAX PROFIT (the credit collected) — "you've captured
 * X% of what this trade can make." A loss is shown against MAX LOSS (the
 * collateral at risk) — "you're X% of the way to the worst case." Both are
 * signed and each is naturally bounded near ±100%, so a winner reads as real
 * profit capture (the old %-of-risk understated it, e.g. +2.10%) while a loser
 * can't blow up to −770% the way a flat %-of-credit did (2026-07-17).
 *
 * Returns null when the relevant basis is unavailable/≤0.
 */
function profitBasisPct(pnl: number, maxProfitDollars: number, maxLossDollars: number): number | null {
  const basis = pnl >= 0 ? maxProfitDollars : maxLossDollars
  if (!(basis > 0)) return null
  return Math.round((pnl / basis) * 10000) / 100
}

export async function getLiveTrade(
  BOT: LiveBot = 'spark',
  person: string | null = null,
  isOperator = false,
): Promise<LiveTrade> {
  const dte = dteMode(BOT)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const prodFilter = scopeFilter(BOT, person, isOperator)

  const [positionRows, sparkSeriesRows] = await Promise.all([
    dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts, total_credit, spread_width, open_time,
              gex_regime, collateral_required
       FROM ${botTable(BOT, 'positions')}
       WHERE status = 'open' ${dteFilter} ${prodFilter}
       ORDER BY open_time DESC`,
    ),
    // Today's day-P&L stream for the mini chart — real scanner snapshots,
    // minute-bucketed like the intraday equity curve. realized_pnl in snapshots
    // is LIFETIME-cumulative, so day-realized = realized − first bucket's realized;
    // adding it keeps the curve continuous through a close instead of snapping to
    // $0 when unrealized zeroes out (the 2026-07-17 "green line ends at $0 on a
    // −$208 day" bug).
    dbQuery(
      `SELECT bucket AS snapshot_time,
              SUM(unrealized_pnl) AS unrealized_pnl,
              SUM(realized_pnl) AS realized_pnl
       FROM (
         SELECT date_trunc('minute', snapshot_time) AS bucket,
                unrealized_pnl, realized_pnl,
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

  const openRealized = sparkSeriesRows.length ? num(sparkSeriesRows[0].realized_pnl) : 0
  const sparkSeries = sparkSeriesRows.map((r) => ({
    timestamp: String(r.snapshot_time),
    pnl: Math.round((num(r.unrealized_pnl) + num(r.realized_pnl) - openRealized) * 100) / 100,
  }))

  if (positionRows.length === 0) {
    // No open trade — surface today's realized result when trading is done.
    const todaysClosed = await dbQuery(
      `SELECT COALESCE(SUM(realized_pnl), 0) as pnl,
              COALESCE(SUM(collateral_required), 0) as risk_dollars,
              COALESCE(SUM(contracts * total_credit * 100), 0) as max_profit_dollars,
              COALESCE(SUM(contracts), 0) as contracts,
              COUNT(*) as cnt
       FROM ${botTable(BOT, 'positions')}
       WHERE status IN ('closed', 'expired')
         AND realized_pnl IS NOT NULL
         AND (close_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
         ${dteFilter} ${prodFilter}`,
    )
    const closedCount = int(todaysClosed[0]?.cnt)
    const pnl = Math.round(num(todaysClosed[0]?.pnl) * 100) / 100
    // % of the trade's own potential: gain vs MAX PROFIT (credit), loss vs MAX
    // LOSS (collateral). collateral_required is the stored max loss per position.
    const riskDollars = num(todaysClosed[0]?.risk_dollars)
    const maxProfitDollars = num(todaysClosed[0]?.max_profit_dollars)
    const todaysContracts = int(todaysClosed[0]?.contracts)
    const todayResult = closedCount > 0
      ? { pnl, pct: profitBasisPct(pnl, maxProfitDollars, riskDollars) }
      : null
    // Advanced/technical-trader only — see backtestAnchor.ts. Never fabricated
    // when there was no trade today, and never computed off a total that has
    // no per-lot denominator. LiveBot is exactly 'spark' | 'flame', so every
    // bot this function can be called with has a validated anchor.
    const anchor = BACKTEST_ANCHORS[BOT]
    const todayResultTechnical = todayResult && todaysContracts > 0
      ? {
          perLot: Math.round((pnl / todaysContracts) * 100) / 100,
          contracts: todaysContracts,
          anchor,
          comparison: compareToBacktestAnchor(pnl, todaysContracts, anchor),
        }
      : null
    return {
      active: false,
      opened_at: null,
      expires_label: null,
      time_in_trade_min: null,
      unrealized_pnl: null,
      unrealized_pnl_pct: null,
      pnl_source: 'none',
      spark_series: sparkSeries,
      positions: [],
      today_result: todayResult,
      today_result_technical: todayResultTechnical,
    }
  }

  // ── Every open position, not just the newest ────────────────────────────────
  //
  // This used to read `positionRows[0]` under the comment "SPARK opens at most one
  // trade a day". True — but SPARK SWINGS: yesterday's condor is held to expiry instead
  // of being stopped out, so on any day it opens a new trade there are TWO open at once.
  // The older one, holding real money, appeared nowhere on the page.
  //
  // Priced in parallel: each position needs its own mark-to-market, and they are
  // independent.
  const ctTodayDate = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })

  // Per-position marks for today, minute-bucketed — the per-trade chart.
  //
  // One query for every open position rather than one per position: this runs on a
  // page poll, and the positions are already being priced against Tradier in parallel
  // just below. Rows only exist from the moment the scanner started recording them,
  // so an older position legitimately comes back empty.
  const openIds = positionRows.map((p) => String(p.position_id ?? '')).filter(Boolean)
  const seriesByPosition = new Map<string, Array<{ timestamp: string; pnl: number }>>()
  if (openIds.length > 0) {
    try {
      const idList = openIds.map((id) => `'${escapeSql(id)}'`).join(',')
      const rows = await dbQuery(
        `SELECT position_id,
                date_trunc('minute', snapshot_time) AS bucket,
                AVG(unrealized_pnl) AS pnl
           FROM ${botTable(BOT, 'position_snapshots')}
          WHERE position_id IN (${idList})
            AND (snapshot_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
            AND unrealized_pnl IS NOT NULL
          GROUP BY position_id, bucket
          ORDER BY bucket ASC`,
      )
      for (const r of rows) {
        const id = String(r.position_id)
        if (!seriesByPosition.has(id)) seriesByPosition.set(id, [])
        seriesByPosition.get(id)!.push({
          timestamp: String(r.bucket),
          pnl: Math.round(num(r.pnl) * 100) / 100,
        })
      }
    } catch {
      // The table is created on first use; a bot that has not scanned since the
      // change simply has no chart yet. An empty series is the correct answer, and
      // it must never take the whole Live page down with it.
    }
  }

  const positions: LiveOpenPosition[] = await Promise.all(
    positionRows.map(async (p): Promise<LiveOpenPosition> => {
      const pContracts = int(p.contracts)
      const pCredit = num(p.total_credit)
      const pExpiration =
        p.expiration?.toISOString?.()?.slice(0, 10) ||
        (p.expiration ? String(p.expiration).slice(0, 10) : '')

      let pnl: number | null = null
      let pnlPct: number | null = null
      let source: LiveTrade['pnl_source'] = 'none'

      if (isConfigured()) {
        try {
          const mtm = await getIcMarkToMarket(
            p.ticker || 'SPY',
            pExpiration,
            num(p.put_short_strike),
            num(p.put_long_strike),
            num(p.call_short_strike),
            num(p.call_long_strike),
            pCredit,
          )
          if (mtm) {
            const width = num(p.spread_width) || (num(p.put_short_strike) - num(p.put_long_strike))
            pnl = calculateIcUnrealizedPnl(pCredit, mtm.cost_to_close_last, pContracts, width)
            const maxProfit = pContracts * pCredit * 100
            const risk = pContracts * (width - pCredit) * 100
            pnlPct = pnl != null ? profitBasisPct(pnl, maxProfit, risk) : null
            source = 'live'
          }
        } catch {
          // Leave null — the card shows "—" rather than a stale or invented number.
        }
      }

      const pOpened = p.open_time ? new Date(p.open_time as string) : null
      const pOpenedCtDate = pOpened
        ? pOpened.toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
        : null
      // Calendar days, so a Friday trade seen on Monday reads Day 4 rather than Day 2.
      // Counting sessions would need the market calendar; the label says "Day N" and
      // calendar days are the honest reading of that.
      const { heldOvernight, dayNumber } = deriveSwingMeta(pOpenedCtDate, ctTodayDate)

      const rawRegime = String(p.gex_regime ?? '').toUpperCase()
      const regimeAtEntry: 'POSITIVE' | 'NEGATIVE' | null =
        rawRegime === 'POSITIVE' || rawRegime === 'NEGATIVE' ? rawRegime : null
      const collateral = num(p.collateral_required)

      return {
        series: seriesByPosition.get(String(p.position_id ?? '')) ?? [],
        position_id: String(p.position_id ?? ''),
        opened_at: pOpened ? pOpened.toISOString() : null,
        opened_date_label: pOpened
          ? pOpened.toLocaleDateString('en-US', {
              timeZone: 'America/Chicago', month: 'short', day: 'numeric',
            })
          : '—',
        expires_label:
          pExpiration === ctTodayDate
            ? `Today ${formatCTClock(DEFAULT_EOD_CUTOFF_MIN)} CT`
            : pExpiration
              ? new Date(`${pExpiration}T12:00:00`).toLocaleDateString('en-US', {
                  weekday: 'short', month: 'short', day: 'numeric',
                })
              : null,
        time_in_trade_min: pOpened
          ? Math.max(0, Math.round((Date.now() - pOpened.getTime()) / 60_000))
          : null,
        unrealized_pnl: pnl,
        unrealized_pnl_pct: pnlPct,
        pnl_source: source,
        held_overnight: heldOvernight,
        day_number: dayNumber,
        // Regime AT ENTRY, straight off the row. It set this trade's strikes and size,
        // so today's reading would describe a different trade. Anything other than the
        // two known values reads as unknown rather than being coerced to POSITIVE.
        gex_regime: regimeAtEntry,
        capital_used: collateral > 0 ? collateral : null,
        // The ceiling that regime authorises. Unknown takes the LOW cap, matching the
        // fail-safe in the sizing path itself.
        regime_cap_pct: isSparkV2SizingBot(BOT)
          ? sparkRegimeBpCap(regimeAtEntry === 'POSITIVE')
          : null,
      }
    }),
  )

  // The scalar fields below still describe the NEWEST position, so every existing
  // reader behaves exactly as before.
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
        // % of the trade's own potential: gain vs MAX PROFIT (credit collected),
        // loss vs MAX LOSS (width − credit collateral). Matches today_result.pct.
        const maxProfitDollars = contracts * entryCredit * 100
        const riskDollars = contracts * (spreadWidth - entryCredit) * 100
        unrealizedPnlPct = unrealizedPnl != null
          ? profitBasisPct(unrealizedPnl, maxProfitDollars, riskDollars)
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
    positions,
  }
}
