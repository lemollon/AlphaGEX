import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, validateBot } from '@/lib/db'
import { getIcMarkToMarket, isConfigured, closeIcOrderAllAccounts } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * POST /api/[bot]/force-close
 *
 * Force-close an open Iron Condor position.
 * Uses Tradier MTM for close price, or accepts an override.
 *
 * Body: { "position_id": string, "close_price"?: number }
 */
export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = bot === 'flame' ? '2DTE' : '1DTE'
  const botName = bot.toUpperCase()

  try {
    const body = await req.json()
    const { position_id, close_price: overridePrice } = body

    if (!position_id) {
      return NextResponse.json(
        { error: 'position_id is required' },
        { status: 400 },
      )
    }

    // 1. Look up the open position
    const rows = await query(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike, put_credit,
              call_short_strike, call_long_strike, call_credit,
              contracts, spread_width, total_credit, max_loss,
              collateral_required
       FROM ${botTable(bot, 'positions')}
       WHERE position_id = $1 AND status = 'open' AND dte_mode = $2
       LIMIT 1`,
      [position_id, dte],
    )

    if (rows.length === 0) {
      return NextResponse.json(
        { error: `No open position found: ${position_id}` },
        { status: 404 },
      )
    }

    const pos = rows[0]
    const totalCredit = num(pos.total_credit)
    const contracts = num(pos.contracts)
    const collateral = num(pos.collateral_required)

    // 2. Determine close price
    let closePrice: number
    if (overridePrice != null && overridePrice >= 0) {
      closePrice = overridePrice
    } else if (isConfigured()) {
      const mtm = await getIcMarkToMarket(
        pos.ticker,
        String(pos.expiration).slice(0, 10),
        num(pos.put_short_strike),
        num(pos.put_long_strike),
        num(pos.call_short_strike),
        num(pos.call_long_strike),
      )
      closePrice = mtm?.cost_to_close ?? 0
    } else {
      // Market closed / no API — close at zero (full credit kept)
      closePrice = 0
    }

    // 3. Calculate P&L
    const pnlPerContract = (totalCredit - closePrice) * 100
    const realizedPnl = Math.round(pnlPerContract * contracts * 100) / 100

    // 4. Close the position
    await query(
      `UPDATE ${botTable(bot, 'positions')}
       SET status = 'closed', close_time = NOW(),
           close_price = $1, realized_pnl = $2,
           close_reason = 'manual_close', updated_at = NOW()
       WHERE position_id = $3 AND status = 'open' AND dte_mode = $4`,
      [closePrice, realizedPnl, position_id, dte],
    )

    // 5. Update paper account (add realized P&L, refund collateral)
    await query(
      `UPDATE ${botTable(bot, 'paper_account')}
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
      [realizedPnl, collateral, dte],
    )

    // 6. Update PDT log
    await query(
      `UPDATE ${botTable(bot, 'pdt_log')}
       SET closed_at = NOW(), exit_cost = $1, pnl = $2,
           close_reason = 'manual_close',
           is_day_trade = (opened_at::date = CURRENT_DATE)
       WHERE position_id = $3 AND dte_mode = $4`,
      [closePrice, realizedPnl, position_id, dte],
    )

    // 7. Save equity snapshot
    const acctRows = await query(
      `SELECT current_balance, cumulative_pnl FROM ${botTable(bot, 'paper_account')}
       WHERE dte_mode = $1 ORDER BY id DESC LIMIT 1`,
      [dte],
    )
    const bal = num(acctRows[0]?.current_balance)
    const openCount = await query(
      `SELECT COUNT(*) as cnt FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' AND dte_mode = $1`,
      [dte],
    )
    const cumPnl = num(acctRows[0]?.cumulative_pnl)
    await query(
      `INSERT INTO ${botTable(bot, 'equity_snapshots')}
       (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
       VALUES ($1, $2, 0, $3, $4, $5)`,
      [bal, cumPnl, num(openCount[0]?.cnt), `force_close:${position_id}`, dte],
    )

    // 8. Mirror close to all Tradier sandbox accounts (both FLAME and SPARK)
    let sandboxCloseIds: Record<string, number> = {}
    try {
      sandboxCloseIds = await closeIcOrderAllAccounts(
        pos.ticker,
        String(pos.expiration).slice(0, 10),
        num(pos.put_short_strike),
        num(pos.put_long_strike),
        num(pos.call_short_strike),
        num(pos.call_long_strike),
        contracts,
        closePrice,
        position_id,
      )
    } catch (sbErr: any) {
      console.warn(`Sandbox close mirror failed for ${position_id}: ${sbErr.message}`)
    }

    // 9. Log
    await query(
      `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
       VALUES ($1, $2, $3, $4)`,
      [
        'TRADE_CLOSE',
        `FORCE CLOSE: ${position_id} @ $${closePrice.toFixed(4)} P&L=$${realizedPnl.toFixed(2)}`,
        JSON.stringify({
          position_id,
          close_price: closePrice,
          realized_pnl: realizedPnl,
          close_reason: 'manual_close',
          entry_credit: totalCredit,
          source: 'force_close_api',
          sandbox_close_ids: sandboxCloseIds,
        }),
        dte,
      ],
    )

    // 10. Update daily_perf
    await query(
      `INSERT INTO ${botTable(bot, 'daily_perf')} (trade_date, trades_executed, positions_closed, realized_pnl)
       VALUES (CURRENT_DATE, 0, 1, $1)
       ON CONFLICT (trade_date) DO UPDATE SET
         positions_closed = ${botTable(bot, 'daily_perf')}.positions_closed + 1,
         realized_pnl = ${botTable(bot, 'daily_perf')}.realized_pnl + $1`,
      [realizedPnl],
    )

    return NextResponse.json({
      success: true,
      position_id,
      close_price: closePrice,
      realized_pnl: realizedPnl,
      entry_credit: totalCredit,
      contracts,
      sandbox_close_ids: sandboxCloseIds,
    })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
