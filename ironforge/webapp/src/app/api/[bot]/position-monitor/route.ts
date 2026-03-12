import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/databricks-sql'
import { getIcMarkToMarket, isConfigured, calculateIcUnrealizedPnl } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

  try {
    const positionRows = await dbQuery(
      `SELECT position_id, ticker, expiration,
             put_short_strike, put_long_strike, put_credit,
             call_short_strike, call_long_strike, call_credit,
             contracts, spread_width, total_credit, max_loss, max_profit,
             underlying_at_entry, vix_at_entry, collateral_required,
             wings_adjusted, open_time, sandbox_order_id
      FROM ${botTable(bot, 'positions')}
      WHERE status = 'open' ${dteFilter}
      ORDER BY open_time DESC`,
    )

    if (!positionRows.length) {
      return NextResponse.json({
        positions: [],
        total_unrealized_pnl: 0,
        spot_price: null,
        tradier_connected: isConfigured(),
        pnl_source: 'none',
      })
    }

    let anyLiveQuoteSucceeded = false

    const positions = await Promise.all(
      positionRows.map(async (r) => {
        const ps = num(r.put_short_strike)
        const pl = num(r.put_long_strike)
        const cs = num(r.call_short_strike)
        const cl = num(r.call_long_strike)
        const contracts = int(r.contracts)
        const entryCredit = num(r.total_credit)
        const ticker = r.ticker || 'SPY'
        const expiration = r.expiration ? String(r.expiration).slice(0, 10) : ''

        const profitTargetPrice = Math.round(entryCredit * 0.7 * 10000) / 10000
        const stopLossPrice = Math.round(entryCredit * 2.0 * 10000) / 10000

        let mtm: number | null = null
        let unrealizedPnl: number | null = null
        let unrealizedPnlPct: number | null = null
        let spotPrice: number | null = null
        let distanceToPt: number | null = null
        let distanceToSl: number | null = null

        if (isConfigured()) {
          const mtmResult = await getIcMarkToMarket(
            ticker, expiration, ps, pl, cs, cl, entryCredit,
          )
          if (mtmResult) {
            anyLiveQuoteSucceeded = true
            mtm = mtmResult.cost_to_close
            spotPrice = mtmResult.spot_price
            const spreadWidth = num(r.spread_width) || (ps - pl)
            unrealizedPnl = calculateIcUnrealizedPnl(entryCredit, mtm, contracts, spreadWidth)
            unrealizedPnlPct =
              entryCredit > 0
                ? Math.round(((entryCredit - Math.min(Math.max(0, mtm), spreadWidth)) / entryCredit) * 10000) / 100
                : 0
            distanceToPt = Math.round((mtm - profitTargetPrice) * 10000) / 10000
            distanceToSl = Math.round((stopLossPrice - mtm) * 10000) / 10000
          }
        }

        return {
          position_id: r.position_id,
          ticker,
          expiration,
          put_short_strike: ps, put_long_strike: pl,
          put_credit: num(r.put_credit),
          call_short_strike: cs, call_long_strike: cl,
          call_credit: num(r.call_credit),
          contracts,
          spread_width: num(r.spread_width),
          total_credit: entryCredit,
          max_loss: num(r.max_loss),
          max_profit: num(r.max_profit),
          underlying_at_entry: num(r.underlying_at_entry),
          vix_at_entry: num(r.vix_at_entry),
          collateral_required: num(r.collateral_required),
          wings_adjusted: r.wings_adjusted === true || r.wings_adjusted === 'true',
          open_time: r.open_time || null,
          current_cost_to_close: mtm,
          spot_price: spotPrice,
          unrealized_pnl: unrealizedPnl,
          unrealized_pnl_pct: unrealizedPnlPct,
          profit_target_price: profitTargetPrice,
          stop_loss_price: stopLossPrice,
          distance_to_pt: distanceToPt,
          distance_to_sl: distanceToSl,
          sandbox_order_ids: r.sandbox_order_id ? (() => { try { return JSON.parse(r.sandbox_order_id) } catch { return null } })() : null,
        }
      }),
    )

    // If live Tradier quotes passed validation, use them
    if (anyLiveQuoteSucceeded) {
      const totalUnrealizedPnl = positions.reduce(
        (sum, p) => sum + (p.unrealized_pnl || 0), 0,
      )
      return NextResponse.json({
        positions,
        total_unrealized_pnl: Math.round(totalUnrealizedPnl * 100) / 100,
        spot_price: positions[0]?.spot_price ?? null,
        tradier_connected: isConfigured(),
        pnl_source: 'live',
      })
    }

    // Fallback: use the scanner's latest equity snapshot for unrealized P&L.
    // The scanner runs every 5 min with its own validated MTM — more reliable
    // than stale/wide-spread Tradier quotes from the webapp.
    const snapshotRows = await dbQuery(
      `SELECT unrealized_pnl, snapshot_time
       FROM ${botTable(bot, 'equity_snapshots')}
       ${dte ? `WHERE dte_mode = '${escapeSql(dte)}'` : ''}
       ORDER BY snapshot_time DESC
       LIMIT 1`,
    )

    const scannerPnl = snapshotRows.length > 0 ? num(snapshotRows[0].unrealized_pnl) : 0
    const snapshotTime = snapshotRows.length > 0 ? snapshotRows[0].snapshot_time : null

    return NextResponse.json({
      positions,
      total_unrealized_pnl: Math.round(scannerPnl * 100) / 100,
      spot_price: positions[0]?.spot_price ?? null,
      tradier_connected: isConfigured(),
      pnl_source: 'scanner_snapshot',
      scanner_snapshot_time: snapshotTime,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
