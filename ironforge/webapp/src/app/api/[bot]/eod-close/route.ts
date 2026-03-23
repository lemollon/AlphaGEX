import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, validateBot, dteMode, CT_TODAY, escapeSql } from '@/lib/db'
import { getIcMarkToMarket, isConfigured, closeIcOrderAllAccounts, type SandboxCloseInfo, type SandboxOrderInfo } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * POST /api/[bot]/eod-close
 *
 * Automatically close ALL open positions at EOD (2:45 PM CT).
 * Called by the frontend position-monitor poll for faster EOD handling
 * than the 5-minute scanner cycle.
 *
 * Returns: { closed: number, results: [...] }
 */
export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Invalid dte' }, { status: 400 })

  // Optional person filter — if provided, only close positions belonging to this person
  const personParam = req.nextUrl.searchParams.get('person')
  const personFilter = personParam && personParam !== 'all' ? `AND person = $2` : ''
  const posParams: any[] = personFilter ? [dte, personParam] : [dte]

  // Verify it's actually past 2:45 PM CT (server-side check to prevent abuse)
  const ctNow = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const ctMins = ctNow.getHours() * 60 + ctNow.getMinutes()
  if (ctMins < 885) { // 14:45 = 885 minutes
    return NextResponse.json({ error: 'Not past EOD cutoff (2:45 PM CT)', ct_minutes: ctMins }, { status: 400 })
  }

  try {
    // 1. Find all open positions (optionally filtered by person)
    const openPositions = await dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike, put_credit,
              call_short_strike, call_long_strike, call_credit,
              contracts, spread_width, total_credit, max_loss,
              collateral_required, sandbox_order_id, account_type, person
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' AND dte_mode = $1 ${personFilter}
       ORDER BY open_time DESC`,
      posParams,
    )

    if (openPositions.length === 0) {
      return NextResponse.json({ closed: 0, results: [], message: 'No open positions to close' })
    }

    const results: Array<{
      position_id: string
      close_price: number
      realized_pnl: number
      sandbox_close_info: Record<string, SandboxCloseInfo>
      account_type?: string
      person?: string
    }> = []

    // 2. Close each position
    for (const pos of openPositions) {
      const positionId = pos.position_id
      const totalCredit = num(pos.total_credit)
      const contracts = int(pos.contracts)
      const ticker = pos.ticker || 'SPY'
      const expiration = pos.expiration?.toISOString?.()?.slice(0, 10) || (pos.expiration ? String(pos.expiration).slice(0, 10) : '')

      // Get MTM close price
      let closePrice = 0
      if (isConfigured()) {
        try {
          const mtm = await getIcMarkToMarket(
            ticker, expiration,
            num(pos.put_short_strike), num(pos.put_long_strike),
            num(pos.call_short_strike), num(pos.call_long_strike),
            totalCredit,
          )
          if (mtm) closePrice = mtm.cost_to_close
        } catch {
          // Use 0 as fallback (expired options worth $0)
        }
      }

      // Mirror close to sandbox accounts
      let sandboxCloseInfo: Record<string, SandboxCloseInfo> = {}
      let sandboxOpenInfo: Record<string, SandboxOrderInfo | number> | null = null
      if (pos.sandbox_order_id) {
        try { sandboxOpenInfo = JSON.parse(pos.sandbox_order_id) } catch { /* ignore */ }
      }
      try {
        sandboxCloseInfo = await closeIcOrderAllAccounts(
          ticker, expiration,
          num(pos.put_short_strike), num(pos.put_long_strike),
          num(pos.call_short_strike), num(pos.call_long_strike),
          contracts, closePrice, positionId, sandboxOpenInfo,
        )
      } catch {
        // Non-fatal — continue with paper close
      }

      // Use User's actual fill price if available
      let effectivePrice = closePrice
      const userClose = sandboxCloseInfo['User']
      if (userClose?.fill_price != null && userClose.fill_price > 0) {
        effectivePrice = userClose.fill_price
      }

      // Calculate P&L
      const pnlPerContract = (totalCredit - effectivePrice) * 100
      const realizedPnl = Math.round(pnlPerContract * contracts * 100) / 100

      // Close the position (atomically — only if still open)
      const sandboxCloseJson = Object.keys(sandboxCloseInfo).length > 0
        ? JSON.stringify(sandboxCloseInfo)
        : null
      const rowsAffected = await dbExecute(
        `UPDATE ${botTable(bot, 'positions')}
         SET status = 'closed', close_time = NOW(),
             close_price = $1, realized_pnl = $2,
             close_reason = 'eod_cutoff', updated_at = NOW(),
             sandbox_close_order_id = $3
         WHERE position_id = $4 AND status = 'open'
           AND dte_mode = $5`,
        [effectivePrice, realizedPnl, sandboxCloseJson, positionId, dte],
      )

      // Guard: skip paper_account update if position was already closed by scanner
      if (rowsAffected === 0) {
        await dbExecute(
          `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
           VALUES ('SKIP', $1, $2, $3)`,
          [
            `EOD SKIP: ${positionId} already closed (would have been $${realizedPnl.toFixed(2)})`,
            JSON.stringify({ position_id: positionId, skipped_pnl: realizedPnl, source: 'webapp_eod_close', skip_reason: 'already_closed' }),
            dte,
          ],
        )
        continue  // Skip to next position — don't double-count P&L
      }

      // Log the close
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
         VALUES ('TRADE_CLOSE', $1, $2, $3)`,
        [
          `EOD CLOSE: ${positionId} @ $${effectivePrice.toFixed(4)} P&L=$${realizedPnl.toFixed(2)}`,
          JSON.stringify({
            position_id: positionId,
            close_price: effectivePrice,
            realized_pnl: realizedPnl,
            close_reason: 'eod_cutoff',
            entry_credit: totalCredit,
            source: 'webapp_eod_close',
            sandbox_close_info: sandboxCloseInfo,
          }),
          dte,
        ],
      )

      // Update PDT log
      await dbExecute(
        `UPDATE ${botTable(bot, 'pdt_log')}
         SET closed_at = NOW(), exit_cost = $1, pnl = $2,
             close_reason = 'eod_cutoff',
             is_day_trade = ((opened_at AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY})
         WHERE position_id = $3 AND dte_mode = $4`,
        [effectivePrice, realizedPnl, positionId, dte],
      )

      results.push({
        position_id: positionId,
        close_price: effectivePrice,
        realized_pnl: realizedPnl,
        sandbox_close_info: sandboxCloseInfo,
        account_type: (pos.account_type || 'sandbox') as string,
        person: (pos.person || '') as string,
      })
    }

    // 3. Update paper account per account_type (after all positions closed)
    const totalRealizedPnl = results.reduce((sum, r) => sum + r.realized_pnl, 0)

    // Group results by account_type to update the correct paper_account row
    const pnlByAccountType: Record<string, { pnl: number; count: number; person: string }> = {}
    for (const r of results) {
      const key = r.account_type || 'sandbox'
      if (!pnlByAccountType[key]) pnlByAccountType[key] = { pnl: 0, count: 0, person: r.person || '' }
      pnlByAccountType[key].pnl += r.realized_pnl
      pnlByAccountType[key].count += 1
    }

    for (const [acctType, { pnl, count, person: acctPerson }] of Object.entries(pnlByAccountType)) {
      // Calculate remaining collateral PER account_type — not globally.
      // Without this filter, production collateral inflates sandbox and vice versa.
      const collFilter = acctType === 'production'
        ? `AND account_type = 'production' AND person = '${escapeSql(acctPerson)}'`
        : `AND COALESCE(account_type, 'sandbox') = 'sandbox'`
      const remainingCollateral = await dbQuery(
        `SELECT COALESCE(SUM(collateral_required), 0) AS total_collateral
         FROM ${botTable(bot, 'positions')}
         WHERE status = 'open' AND dte_mode = $1 ${collFilter}`,
        [dte],
      )
      const actualCollateral = num(remainingCollateral[0]?.total_collateral)

      if (acctType === 'production') {
        await dbExecute(
          `UPDATE ${botTable(bot, 'paper_account')}
           SET current_balance = current_balance + $1,
               cumulative_pnl = cumulative_pnl + $1,
               total_trades = total_trades + $2,
               collateral_in_use = $3,
               buying_power = current_balance + $1 - $3,
               high_water_mark = GREATEST(high_water_mark, current_balance + $1),
               max_drawdown = GREATEST(max_drawdown,
                 GREATEST(high_water_mark, current_balance + $1) - (current_balance + $1)),
               updated_at = NOW()
           WHERE account_type = 'production' AND person = $4 AND is_active = TRUE AND dte_mode = $5`,
          [pnl, count, actualCollateral, acctPerson, dte],
        )
      } else {
        await dbExecute(
          `UPDATE ${botTable(bot, 'paper_account')}
           SET current_balance = current_balance + $1,
               cumulative_pnl = cumulative_pnl + $1,
               total_trades = total_trades + $2,
               collateral_in_use = $3,
               buying_power = current_balance + $1 - $3,
               high_water_mark = GREATEST(high_water_mark, current_balance + $1),
               max_drawdown = GREATEST(max_drawdown,
                 GREATEST(high_water_mark, current_balance + $1) - (current_balance + $1)),
               updated_at = NOW()
           WHERE COALESCE(account_type, 'sandbox') = 'sandbox' AND dte_mode = $4`,
          [pnl, count, actualCollateral, dte],
        )
      }
    }

    // 4. Equity snapshot
    const acctRows = await dbQuery(
      `SELECT current_balance, cumulative_pnl FROM ${botTable(bot, 'paper_account')}
       WHERE dte_mode = $1 ORDER BY id DESC LIMIT 1`,
      [dte],
    )
    const bal = num(acctRows[0]?.current_balance)
    const cumPnl = num(acctRows[0]?.cumulative_pnl)
    await dbExecute(
      `INSERT INTO ${botTable(bot, 'equity_snapshots')}
       (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
       VALUES ($1, $2, 0, 0, $3, $4)`,
      [bal, cumPnl, `webapp_eod_close:${results.length}_positions`, dte],
    )

    // 5. Daily perf upsert
    await dbExecute(
      `INSERT INTO ${botTable(bot, 'daily_perf')} (trade_date, trades_executed, positions_closed, realized_pnl)
       VALUES (${CT_TODAY}, 0, $1, $2)
       ON CONFLICT (trade_date) DO UPDATE SET
         positions_closed = ${botTable(bot, 'daily_perf')}.positions_closed + $1,
         realized_pnl = ${botTable(bot, 'daily_perf')}.realized_pnl + $2`,
      [results.length, totalRealizedPnl],
    )

    return NextResponse.json({
      closed: results.length,
      total_realized_pnl: Math.round(totalRealizedPnl * 100) / 100,
      results,
      source: 'webapp_eod_close',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
