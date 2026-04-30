import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, sharedTable, num, int, escapeSql, validateBot, heartbeatName, dteMode, CT_TODAY } from '@/lib/db'
import { getIcMarkToMarket, isConfigured, calculateIcUnrealizedPnl, getSandboxAccountBalances, getAccountsForBot, PRODUCTION_BOT, getProductionAccountsForBot, getTradierBalanceDetail, getTradierOrders, getSandboxAccountPositions, getLoadedSandboxAccountsAsync, getAccountIdForKey } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const personParam = req.nextUrl.searchParams.get('person')
  const filterByPerson = personParam && personParam !== 'all'

  try {
    const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
    const personFilter = filterByPerson ? `AND person = '${escapeSql(personParam)}'` : ''
    const accountTypeParam = req.nextUrl.searchParams.get('account_type')
    const accountTypeFilter = accountTypeParam
      ? `AND COALESCE(account_type, 'sandbox') = '${escapeSql(accountTypeParam)}'`
      : ''

    const accountQuery = dbQuery(
      `SELECT starting_capital, current_balance, cumulative_pnl,
              total_trades, collateral_in_use, buying_power,
              high_water_mark, max_drawdown, is_active
       FROM ${botTable(bot, 'paper_account')}
       WHERE is_active = TRUE ${dteFilter} ${accountTypeFilter} ${personFilter}
       ORDER BY id DESC LIMIT 1`,
    )

    const positionCountQuery = dbQuery(
      `SELECT COUNT(*) as cnt
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter} ${personFilter} ${accountTypeFilter}`,
    )

    // Live reconciliation: compute realized P&L and trade count from actual closed positions
    // This is the source of truth — paper_account can drift out of sync
    const liveStatsQuery = dbQuery(
      `SELECT
        COALESCE(SUM(realized_pnl), 0) as actual_realized_pnl,
        COUNT(*) as actual_total_trades
       FROM ${botTable(bot, 'positions')}
       WHERE status IN ('closed', 'expired')
         AND realized_pnl IS NOT NULL
         ${dteFilter} ${personFilter} ${accountTypeFilter}`,
    )

    // Today's realized P&L (trades closed today in CT)
    const todayRealizedQuery = dbQuery(
      `SELECT
        COALESCE(SUM(realized_pnl), 0) as today_realized_pnl,
        COUNT(*) as today_trades_closed
       FROM ${botTable(bot, 'positions')}
       WHERE status IN ('closed', 'expired')
         AND realized_pnl IS NOT NULL
         AND (close_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
         ${dteFilter} ${personFilter} ${accountTypeFilter}`,
    )

    // Today's close reason breakdown (which PT tiers hit, with IC return data)
    const todayCloseReasonsQuery = dbQuery(
      `SELECT close_reason, realized_pnl, total_credit, contracts, close_price
       FROM ${botTable(bot, 'positions')}
       WHERE status IN ('closed', 'expired')
         AND realized_pnl IS NOT NULL
         AND (close_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
         ${dteFilter} ${personFilter} ${accountTypeFilter}
       ORDER BY close_time ASC`,
    )

    // Actual collateral from open positions (not stale paper_account value)
    const liveCollateralQuery = dbQuery(
      `SELECT COALESCE(SUM(collateral_required), 0) as actual_collateral
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter} ${personFilter} ${accountTypeFilter}`,
    )

    const hbName = heartbeatName(bot)
    const heartbeatQuery = dbQuery(
      `SELECT scan_count, last_heartbeat, status, details
       FROM ${sharedTable('bot_heartbeats')}
       WHERE bot_name = '${escapeSql(hbName)}'`,
    )

    const snapshotQuery = dbQuery(
      `SELECT unrealized_pnl, open_positions, snapshot_time
       FROM ${botTable(bot, 'equity_snapshots')}
       WHERE 1=1 ${dteFilter} ${personFilter} ${accountTypeFilter}
       ORDER BY snapshot_time DESC
       LIMIT 1`,
    )

    const scansTodayQuery = dbQuery(
      `SELECT COUNT(*) as cnt
       FROM ${botTable(bot, 'logs')}
       WHERE level = 'SCAN'
         AND (log_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
         ${dteFilter}`,
    )

    const lastErrorQuery = dbQuery(
      `SELECT log_time, message
       FROM ${botTable(bot, 'logs')}
       WHERE level = 'ERROR' ${dteFilter}
       ORDER BY log_time DESC LIMIT 1`,
    )

    const openPositionsQuery = dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts, total_credit, spread_width
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter} ${personFilter} ${accountTypeFilter}`,
    )

    // Pending order count (production bot only — graceful fallback if table doesn't exist).
    // The schema only guarantees id, position_id, ticker, expiration, strikes,
    // contracts, total_credit, status, created_at, updated_at, dte_mode — so we
    // filter on created_at (not the optional created_date column).
    const pendingCountQuery = bot === PRODUCTION_BOT
      ? dbQuery(
          `SELECT COUNT(*) as cnt
           FROM ${botTable(bot, 'pending_orders')}
           WHERE status = 'pending'
             AND (created_at AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
             ${dteFilter}`,
        ).catch(() => [{ cnt: 0 }])
      : Promise.resolve([{ cnt: 0 }])

    // Account balances — fetch real Tradier data, filtered by bot assignment
    const sandboxBalancesQuery = getSandboxAccountBalances().catch(() => [])

    // Fetch person aliases for sandbox account display names
    const aliasQuery = dbQuery(
      `SELECT person, alias FROM ${sharedTable('ironforge_person_aliases')}`,
    ).catch(() => [])

    // Which persons are assigned to this bot? Filter accounts to only show relevant ones.
    const botAssignmentQuery = dbQuery(
      `SELECT person, type FROM ${sharedTable('ironforge_accounts')}
       WHERE is_active = TRUE AND bot ILIKE $1`,
      [`%${bot}%`],
    ).catch(() => [])

    const [accountRows, positionCountRows, heartbeatRows, snapshotRows, scansTodayRows, lastErrorRows, openPositionRows, liveStatsRows, liveCollateralRows, pendingCountRows, todayRealizedRows, sandboxBalances, todayCloseReasonRows, aliasRows, botAssignmentRows] =
      await Promise.all([accountQuery, positionCountQuery, heartbeatQuery, snapshotQuery, scansTodayQuery, lastErrorQuery, openPositionsQuery, liveStatsQuery, liveCollateralQuery, pendingCountQuery, todayRealizedQuery, sandboxBalancesQuery, todayCloseReasonsQuery, aliasQuery, botAssignmentQuery])

    // Build person → alias lookup
    const aliasMap: Record<string, string> = {}
    for (const r of aliasRows) {
      if (r.alias) aliasMap[r.person as string] = r.alias as string
    }

    const acct = accountRows[0]
    let startingCapital = num(acct?.starting_capital) || 10000

    // Use LIVE stats from actual positions (source of truth), not stale paper_account
    const liveStats = liveStatsRows[0]
    let realizedPnl = Math.round(num(liveStats?.actual_realized_pnl) * 100) / 100
    let totalTrades = int(liveStats?.actual_total_trades)
    let liveCollateral = num(liveCollateralRows[0]?.actual_collateral)
    let balance = Math.round((startingCapital + realizedPnl) * 100) / 100
    let buyingPower = Math.round((balance - liveCollateral) * 100) / 100
    let productionPositionsCountOverride: number | null = null
    let todayRealizedOverride: number | null = null
    let todayTradesClosedOverride: number | null = null

    // Live-trading FULL MIRROR: when the production bot is viewed in production
    // mode, every displayed number comes from the Tradier Iron Viper account.
    // Source of truth = the broker. The DB ledger is kept as a fallback only.
    //
    // Overrides applied (all sourced from Tradier when source='tradier'):
    //   balance              = sum(total_equity)        across prod accounts
    //   buying_power         = sum(option_buying_power) across prod accounts
    //   collateral_in_use    = max(0, total_equity - option_buying_power)
    //   unrealized_pnl       = sum(open_pl)
    //   cumulative_pnl       = sum(close_pl)            (realized — Tradier-day)
    //   today_realized_pnl   = sum(close_pl)            (Tradier close_pl is per-day)
    //   total_trades         = count of filled orders (trailing 30d)
    //   today_trades_closed  = count of filled orders dated today (CT)
    //   open_positions       = ceil(non-zero position legs / 4) — 1 IC = 4 legs
    //   starting_capital     = balance - cumulative_pnl (back-compute so the
    //                          "balance = start + realized" math reconciles)
    //
    // Fallback: any helper failure (missing creds, Tradier 5xx, no prod account
    // assigned) drops us back to the paper_account-derived values and sets
    // `account.source = 'paper_account'` with `source_error` populated — no
    // fabrication, operator sees exactly where the numbers came from.
    let accountSource: 'tradier' | 'paper_account' = 'paper_account'
    let tradierBalanceFetchError: string | null = null
    let tradierOpenPlOverride: number | null = null
    if (accountTypeParam === 'production' && bot === PRODUCTION_BOT) {
      try {
        const prodAccts = await getProductionAccountsForBot(bot)
        let tradierEquity = 0
        let tradierBp = 0
        let tradierOpenPl = 0
        let tradierClosePl = 0
        let haveTradierData = false
        for (const pa of prodAccts) {
          if (!pa.accountId) continue
          const bal = await getTradierBalanceDetail(pa.apiKey, pa.accountId, pa.baseUrl)
          if (!bal || bal.total_equity == null || bal.option_buying_power == null) continue
          haveTradierData = true
          tradierEquity += bal.total_equity
          tradierBp += bal.option_buying_power
          tradierOpenPl += bal.open_pl ?? 0
          tradierClosePl += bal.close_pl ?? 0
        }
        if (haveTradierData) {
          balance = Math.round(tradierEquity * 100) / 100
          buyingPower = Math.round(tradierBp * 100) / 100
          liveCollateral = Math.round(Math.max(0, tradierEquity - tradierBp) * 100) / 100
          tradierOpenPlOverride = Math.round(tradierOpenPl * 100) / 100
          // Realized = Tradier close_pl (day-scoped per Tradier spec). Both
          // cumulative_pnl and today_realized_pnl mirror this number in Live
          // mode so the top card matches Iron Viper's day P&L exactly.
          realizedPnl = Math.round(tradierClosePl * 100) / 100
          todayRealizedOverride = realizedPnl
          // Back-compute starting_capital so balance = startingCapital + realizedPnl holds
          startingCapital = Math.round((balance - realizedPnl) * 100) / 100
          accountSource = 'tradier'

          // Second + third pass: query orders and positions for trade counts
          // and open-position count. These are independent API calls; a
          // failure in either leaves balance/BP/unrealized as already
          // overridden and just skips the count mirror (keeps DB count).
          try {
            const cutoff30d = Date.now() - 30 * 24 * 60 * 60 * 1000
            // CT "today" string in YYYY-MM-DD, matching transaction_date format
            const ctNow = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
            const ctToday =
              `${ctNow.getFullYear()}-${String(ctNow.getMonth() + 1).padStart(2, '0')}-${String(ctNow.getDate()).padStart(2, '0')}`
            let filledTotal = 0
            let filledToday = 0
            let nonZeroPositions = 0
            for (const pa of prodAccts) {
              if (!pa.accountId) continue
              // Orders
              try {
                const orders = await getTradierOrders(pa.apiKey, pa.accountId, pa.baseUrl, 'filled')
                for (const o of orders) {
                  const txTs = o.transaction_date ? Date.parse(o.transaction_date) : NaN
                  if (Number.isFinite(txTs) && txTs >= cutoff30d) {
                    filledTotal += 1
                    // Compare CT date strings to avoid TZ drift
                    const txDate = new Date(txTs).toLocaleString('en-US', {
                      timeZone: 'America/Chicago',
                      year: 'numeric', month: '2-digit', day: '2-digit',
                    })
                    const [mm, dd, yyyy] = txDate.split(/[\/,\s]+/).filter(Boolean)
                    const txCtKey = `${yyyy}-${mm}-${dd}`
                    if (txCtKey === ctToday) filledToday += 1
                  }
                }
              } catch { /* orders fetch failed — leave count at 0 for this account */ }
              // Positions — count non-zero legs
              try {
                const positions = await getSandboxAccountPositions(pa.apiKey, undefined, pa.baseUrl)
                nonZeroPositions += positions.filter(p => p.quantity !== 0).length
              } catch { /* positions fetch failed — leave at 0 */ }
            }
            totalTrades = filledTotal
            todayTradesClosedOverride = filledToday
            // One IC has 4 legs; round up so 1 orphan leg still counts as 1
            productionPositionsCountOverride = Math.ceil(nonZeroPositions / 4)
          } catch { /* count mirror is best-effort — never fail the whole route */ }
        } else {
          tradierBalanceFetchError = 'no_production_balance_returned'
        }
      } catch (err: unknown) {
        tradierBalanceFetchError = err instanceof Error ? err.message : String(err)
        console.warn(`[status] ${bot}: production balance fetch failed (${tradierBalanceFetchError}) — falling back to paper_account`)
      }
    }

    // FLAME sandbox mirror: balance/BP/P&L come from the Tradier User sandbox
    // account, not the DB paper_account. The scanner re-seeds paper_account
    // with DEFAULT_CONFIG.starting_capital each cycle, so paper_account alone
    // would never reflect the real Tradier balance. This mirrors the SPARK
    // Live-mode override pattern but scoped to User sandbox.
    //
    // On any Tradier failure we keep the paper_account-derived values already
    // computed above and set source_error — no fabrication.
    if (bot === 'flame') {
      try {
        const accts = await getLoadedSandboxAccountsAsync()
        const userAcct = accts.find((a) => a.name === 'User' && a.type === 'sandbox')
        if (userAcct) {
          const accountId = await getAccountIdForKey(userAcct.apiKey, userAcct.baseUrl)
          if (accountId) {
            const bal = await getTradierBalanceDetail(userAcct.apiKey, accountId, userAcct.baseUrl)
            if (bal && bal.total_equity != null) {
              balance = Math.round(bal.total_equity * 100) / 100
              if (bal.option_buying_power != null) {
                buyingPower = Math.round(bal.option_buying_power * 100) / 100
                liveCollateral = Math.round(Math.max(0, bal.total_equity - bal.option_buying_power) * 100) / 100
              }
              if (bal.open_pl != null) {
                tradierOpenPlOverride = Math.round(bal.open_pl * 100) / 100
              }
              // FLAME is PAPER ONLY — no orders are placed against the User
              // sandbox, so Tradier's close_pl on that account reflects non-
              // FLAME activity (manual trades, other operators, settled stale
              // positions). Mirroring it here makes "Realized Today" diverge
              // from FLAME's actual paper P&L: the equity chart and close-
              // reason breakdown both read flame_positions.realized_pnl and
              // showed +$432 from the day's PT trade while the top card said
              // -$386 from the shared sandbox's day P&L.
              //
              // Keep balance/BP/unrealized mirrored to Tradier (the operator
              // wants to see the live dollar balance on the User account),
              // but leave realizedPnl/todayRealizedPnl on the flame_positions
              // values already computed above. Back-compute starting_capital
              // off that same realized number so the card math stays
              // consistent (balance = starting_capital + realizedPnl).
              startingCapital = Math.round((balance - realizedPnl) * 100) / 100
              accountSource = 'tradier'
            } else {
              tradierBalanceFetchError = 'no_user_sandbox_balance_returned'
            }
          } else {
            tradierBalanceFetchError = 'no_account_id_for_user_sandbox_key'
          }
        } else {
          tradierBalanceFetchError = 'no_user_sandbox_account_loaded'
        }
      } catch (err: unknown) {
        tradierBalanceFetchError = err instanceof Error ? err.message : String(err)
        console.warn(`[status] flame: User sandbox balance fetch failed (${tradierBalanceFetchError}) — falling back to paper_account`)
      }
    }

    // Compute live unrealized P&L from open positions via Tradier
    let unrealizedPnl: number | null = null
    if (openPositionRows.length > 0 && isConfigured()) {
      let anyMtmSucceeded = false
      const mtmResults = await Promise.all(
        openPositionRows.map(async (pos) => {
          try {
            const entryCredit = num(pos.total_credit)
            const mtm = await getIcMarkToMarket(
              pos.ticker || 'SPY',
              pos.expiration?.toISOString?.()?.slice(0, 10) || String(pos.expiration).slice(0, 10),
              num(pos.put_short_strike),
              num(pos.put_long_strike),
              num(pos.call_short_strike),
              num(pos.call_long_strike),
              entryCredit,
            )
            if (!mtm) return null
            anyMtmSucceeded = true
            const contracts = int(pos.contracts)
            const spreadWidth = num(pos.spread_width) || (num(pos.put_short_strike) - num(pos.put_long_strike))
            // Use last trade prices — matches Tradier portfolio Gain/Loss calculation
            return calculateIcUnrealizedPnl(entryCredit, mtm.cost_to_close_last, contracts, spreadWidth)
          } catch (err: unknown) {
            console.error(`[${bot}] MTM failed for position ${pos.position_id}:`, err instanceof Error ? err.message : err)
            return null
          }
        }),
      )
      if (anyMtmSucceeded) {
        unrealizedPnl = mtmResults.reduce((a: number, b) => a + (b ?? 0), 0)
      }
      // else: unrealizedPnl stays null — frontend should show "—"
    } else if (openPositionRows.length > 0) {
      // Tradier not configured but positions exist — unrealized PnL unavailable
      unrealizedPnl = null
    } else {
      unrealizedPnl = 0
    }

    // Live-trading override: prefer Tradier-reported open_pl over per-leg MTM
    // when we successfully fetched the production balance above. Tradier's
    // open_pl already reflects the broker's mark and matches what the operator
    // sees on tradier.com, which is the authoritative number for a live account.
    if (accountSource === 'tradier' && tradierOpenPlOverride !== null) {
      unrealizedPnl = tradierOpenPlOverride
    }

    // Live-mode overrides (set above when accountSource === 'tradier') take
    // precedence over the DB-ledger values. Paper/Sandbox mode is unaffected.
    const todayRealizedPnl = todayRealizedOverride != null
      ? todayRealizedOverride
      : Math.round(num(todayRealizedRows[0]?.today_realized_pnl) * 100) / 100
    const todayTradesClosed = todayTradesClosedOverride != null
      ? todayTradesClosedOverride
      : int(todayRealizedRows[0]?.today_trades_closed)

    // Weighted IC return %: average of (credit - close_price) / credit
    // Weight by credit × contracts (larger positions count more)
    let totalWeight = 0
    let weightedReturnSum = 0
    for (const r of todayCloseReasonRows) {
      const credit = num(r.total_credit)
      const closePrice = num(r.close_price)
      const contracts = int(r.contracts) || 1
      if (credit > 0) {
        const weight = credit * contracts
        const icReturn = (credit - closePrice) / credit
        weightedReturnSum += icReturn * weight
        totalWeight += weight
      }
    }
    const todayIcReturnPct = totalWeight > 0
      ? Math.round((weightedReturnSum / totalWeight) * 10000) / 100
      : null

    // For PRODUCTION mode: detect orphan positions (Tradier has positions DB doesn't track).
    // Do NOT substitute Tradier data into the scorecard — the DB is the source of truth.
    // If positions are missing from DB, that's a data integrity error to surface, not mask.
    let dataIntegrityWarning: string | null = null
    if (accountTypeParam === 'production') {
      const prodBrokerData = sandboxBalances.find((s: any) => s.account_type === 'production')
      if (prodBrokerData) {
        const brokerPosCount = prodBrokerData.open_positions_count || 0
        const dbPosCount = int(positionCountRows[0]?.cnt)
        if (brokerPosCount > dbPosCount) {
          dataIntegrityWarning = `Tradier has ${brokerPosCount} open legs but DB tracks ${dbPosCount}. ` +
            `${brokerPosCount - dbPosCount} orphan leg(s) not tracked by IronForge.`
        }
      }
    }

    const totalPnl = realizedPnl + (unrealizedPnl ?? 0)
    const returnPct = startingCapital > 0 ? (totalPnl / startingCapital) * 100 : 0

    const hb = heartbeatRows[0]
    const lastErr = lastErrorRows[0]

    // Parse heartbeat details JSON for SPY/VIX and bot state
    let hbDetails: { action?: string; reason?: string; spot?: number; vix?: number } = {}
    if (hb?.details) {
      try { hbDetails = typeof hb.details === 'string' ? JSON.parse(hb.details) : hb.details } catch {
        // Malformed JSON in heartbeat details — ignore
      }
    }

    const pendingOrderCount = int(pendingCountRows[0]?.cnt)

    // Derive bot_state from heartbeat status + action
    const hbStatus = hb?.status || 'unknown'
    const hbAction = hbDetails.action || ''
    const botState =
      hbStatus === 'error' ? 'error'
      : hbAction === 'pending_fill' ? 'pending_fill'
      : hbAction === 'awaiting_fill' ? 'awaiting_fill'
      : hbAction === 'monitoring' ? 'monitoring'
      : hbAction === 'traded' || hbAction === 'closed' ? 'traded'
      : hbAction === 'outside_window' || hbAction === 'outside_entry_window' ? 'market_closed'
      : hbStatus === 'idle' ? 'idle'
      : hbStatus === 'active' ? 'scanning'
      : 'unknown'

    const dteNum = bot === 'flame' ? 2 : bot === 'spark' ? 1 : 0
    const tradeMode = bot === PRODUCTION_BOT ? 'Live' : 'Paper'
    const strategyName = bot === 'flame' ? 'Put Credit Spread' : 'Iron Condor'
    const strategy = `${dteNum}DTE ${tradeMode} ${strategyName}`

    return NextResponse.json({
      bot_name: bot.toUpperCase(),
      strategy,
      dte: dteNum,
      ticker: 'SPY',
      is_active: acct?.is_active === true || acct?.is_active === 'true',
      account: {
        starting_capital: startingCapital,
        balance,
        cumulative_pnl: realizedPnl,
        unrealized_pnl: unrealizedPnl,
        today_realized_pnl: todayRealizedPnl,
        today_trades_closed: todayTradesClosed,
        today_ic_return_pct: todayIcReturnPct,
        total_pnl: Math.round(totalPnl * 100) / 100,
        return_pct: Math.round(returnPct * 100) / 100,
        total_trades: totalTrades,
        collateral_in_use: liveCollateral,
        buying_power: buyingPower,
        high_water_mark: num(acct?.high_water_mark),
        max_drawdown: num(acct?.max_drawdown),
        // Diagnostic: 'tradier' = balance/BP/unrealized came from the live broker;
        // 'paper_account' = fell back to the DB-seeded paper account row.
        // UI does not render this; use `curl ... | jq .account.source` to verify.
        source: accountSource,
        source_error: tradierBalanceFetchError,
      },
      open_positions: productionPositionsCountOverride != null
        ? productionPositionsCountOverride
        : int(positionCountRows[0]?.cnt),
      data_integrity_warning: dataIntegrityWarning,
      pending_order_count: pendingOrderCount,
      last_scan: hb?.last_heartbeat || null,
      last_snapshot: snapshotRows[0]?.snapshot_time || null,
      scan_count: int(hb?.scan_count),
      scans_today: int(scansTodayRows[0]?.cnt),
      spot_price: hbDetails.spot || null,
      vix: hbDetails.vix || null,
      bot_state: botState,
      last_scan_reason: hbDetails.reason || null,
      last_error: lastErr ? {
        time: lastErr.log_time || null,
        message: lastErr.message || null,
      } : null,
      today_close_reasons: todayCloseReasonRows.map((r) => {
        const pnl = Math.round(num(r.realized_pnl) * 100) / 100
        const credit = num(r.total_credit)
        const closePrice = num(r.close_price)
        // IC return %: how much of the credit premium was kept
        // Formula: (credit_received - close_price) / credit_received × 100
        // This is the TRUE IC win % — matches the PT tier targets (30%, 20%, 15%)
        const icReturnPct = credit > 0
          ? Math.round(((credit - closePrice) / credit) * 10000) / 100
          : 0
        return {
          close_reason: r.close_reason || '',
          realized_pnl: pnl,
          ic_return_pct: icReturnPct,
        }
      }),
      sandbox_accounts: sandboxBalances
        .filter((s) => {
          // Paper-only bots never show broker accounts (SPARK, INFERNO have no Tradier orders)
          if (getAccountsForBot(bot).length === 0) return false
          // Only show accounts assigned to this bot
          const assignedToBot = botAssignmentRows.some(
            (r) => r.person === s.name && r.type === s.account_type,
          )
          if (botAssignmentRows.length > 0 && !assignedToBot) return false

          if (accountTypeParam) {
            // Show only accounts matching the selected type
            if (s.account_type !== accountTypeParam) return false
          }
          if (filterByPerson) {
            // Match by person name OR alias
            const alias = aliasMap[s.name]
            if (s.name !== personParam && alias !== personParam) return false
          }
          return true
        })
        .map((s) => ({
          name: aliasMap[s.name] || s.name,
          account_id: s.account_id,
          total_equity: s.total_equity,
          option_buying_power: s.option_buying_power,
          day_pnl: s.day_pnl,
          unrealized_pnl: s.unrealized_pnl,
          unrealized_pnl_pct: s.unrealized_pnl_pct,
          open_positions: s.open_positions_count,
          account_type: s.account_type,
        })),
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
