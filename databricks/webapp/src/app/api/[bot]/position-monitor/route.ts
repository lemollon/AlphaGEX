import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, int, validateBot, dteMode } from '@/lib/databricks'
import { getIcMarkToMarket, isConfigured } from '@/lib/tradier'
import { getCurrentPTTier, getCTNow } from '@/lib/pt-tiers'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)

  try {
    const positionRows = await query(`
      SELECT position_id, ticker, expiration,
             put_short_strike, put_long_strike, put_credit,
             call_short_strike, call_long_strike, call_credit,
             contracts, spread_width, total_credit, max_loss, max_profit,
             underlying_at_entry, vix_at_entry, collateral_required,
             wings_adjusted, sandbox_order_id, open_time
      FROM ${botTable(bot, 'positions')}
      WHERE status = 'open' AND dte_mode = '${dte}'
      ORDER BY open_time DESC
    `)

    if (!positionRows.length) {
      return NextResponse.json({
        positions: [],
        total_unrealized_pnl: 0,
        spot_price: null,
        tradier_connected: isConfigured(),
      })
    }

    const positions = await Promise.all(
      positionRows.map(async (r) => {
        const ps = num(r.put_short_strike)
        const pl = num(r.put_long_strike)
        const cs = num(r.call_short_strike)
        const cl = num(r.call_long_strike)
        const contracts = int(r.contracts)
        const entryCredit = num(r.total_credit)
        const ticker = r.ticker || 'SPY'
        const expiration = r.expiration || ''

        // Sliding profit target based on current CT time
        const ptTier = getCurrentPTTier(getCTNow())
        const profitTargetPct = ptTier.pct
        const profitTargetPrice = Math.round(entryCredit * (1 - profitTargetPct) * 10000) / 10000
        const stopLossPrice = Math.round(entryCredit * 2.0 * 10000) / 10000

        let mtm: number | null = null
        let unrealizedPnl: number | null = null
        let unrealizedPnlPct: number | null = null
        let spotPrice: number | null = null
        let distanceToPt: number | null = null
        let distanceToSl: number | null = null

        if (isConfigured()) {
          const mtmResult = await getIcMarkToMarket(
            ticker, expiration, ps, pl, cs, cl,
          )
          if (mtmResult) {
            mtm = mtmResult.cost_to_close
            spotPrice = mtmResult.spot_price
            unrealizedPnl =
              Math.round((entryCredit - mtm) * 100 * contracts * 100) / 100
            unrealizedPnlPct =
              entryCredit > 0
                ? Math.round(((entryCredit - mtm) / entryCredit) * 10000) / 100
                : 0
            distanceToPt =
              Math.round((mtm - profitTargetPrice) * 10000) / 10000
            distanceToSl =
              Math.round((stopLossPrice - mtm) * 10000) / 10000
          }
        }

        return {
          position_id: r.position_id,
          ticker,
          expiration,
          put_short_strike: ps,
          put_long_strike: pl,
          put_credit: num(r.put_credit),
          call_short_strike: cs,
          call_long_strike: cl,
          call_credit: num(r.call_credit),
          contracts,
          spread_width: num(r.spread_width),
          total_credit: entryCredit,
          max_loss: num(r.max_loss),
          max_profit: num(r.max_profit),
          underlying_at_entry: num(r.underlying_at_entry),
          vix_at_entry: num(r.vix_at_entry),
          collateral_required: num(r.collateral_required),
          wings_adjusted: r.wings_adjusted === 'true' || r.wings_adjusted === '1',
          sandbox_order_id: r.sandbox_order_id || null,
          open_time: r.open_time,
          // Live data
          current_cost_to_close: mtm,
          spot_price: spotPrice,
          unrealized_pnl: unrealizedPnl,
          unrealized_pnl_pct: unrealizedPnlPct,
          profit_target_price: profitTargetPrice,
          profit_target_pct: profitTargetPct,
          profit_target_tier: ptTier.label.toUpperCase(),
          stop_loss_price: stopLossPrice,
          distance_to_pt: distanceToPt,
          distance_to_sl: distanceToSl,
        }
      }),
    )

    const totalUnrealizedPnl = positions.reduce(
      (sum, p) => sum + (p.unrealized_pnl || 0),
      0,
    )

    return NextResponse.json({
      positions,
      total_unrealized_pnl: Math.round(totalUnrealizedPnl * 100) / 100,
      spot_price: positions[0]?.spot_price ?? null,
      tradier_connected: isConfigured(),
    })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
