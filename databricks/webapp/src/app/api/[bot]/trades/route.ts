import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, int, validateBot } from '@/lib/databricks'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = bot === 'flame' ? '2DTE' : '1DTE'

  try {
    // Query closed trades and close-log details (scanner/sandbox price) in parallel
    const [posRows, logRows] = await Promise.all([
      query(`
        SELECT
          position_id, ticker, expiration,
          put_short_strike, put_long_strike,
          call_short_strike, call_long_strike,
          contracts, spread_width, total_credit,
          close_price, close_reason, realized_pnl,
          open_time, close_time,
          underlying_at_entry, vix_at_entry,
          wings_adjusted, sandbox_order_id
        FROM ${botTable(bot, 'positions')}
        WHERE status IN ('closed', 'expired') AND dte_mode = '${dte}'
        ORDER BY close_time DESC
        LIMIT 50
      `),
      // Get close-log details containing scanner/sandbox price info
      query(`
        SELECT
          get_json_object(details, '$.position_id') AS pid,
          get_json_object(details, '$.scanner_close_price') AS scanner_close_price,
          get_json_object(details, '$.sandbox_fill_price') AS sandbox_fill_price,
          get_json_object(details, '$.fill_delta_pct') AS fill_delta_pct
        FROM ${botTable(bot, 'logs')}
        WHERE dte_mode = '${dte}'
          AND details IS NOT NULL
          AND details LIKE '%scanner_close_price%'
        ORDER BY log_time DESC
        LIMIT 100
      `),
    ])

    // Build lookup map: position_id -> close log details
    const closeLogMap: Record<string, {
      scanner_close_price: number | null
      sandbox_fill_price: number | null
      fill_delta_pct: number | null
    }> = {}
    for (const l of logRows) {
      const pid = (l as Record<string, string | null>).pid
      if (pid && !closeLogMap[pid]) {
        const scp = (l as Record<string, string | null>).scanner_close_price
        const sfp = (l as Record<string, string | null>).sandbox_fill_price
        const fdp = (l as Record<string, string | null>).fill_delta_pct
        closeLogMap[pid] = {
          scanner_close_price: scp ? parseFloat(scp) : null,
          sandbox_fill_price: sfp ? parseFloat(sfp) : null,
          fill_delta_pct: fdp ? parseFloat(fdp) : null,
        }
      }
    }

    const trades = posRows.map((r: Record<string, string | null>) => {
      const posId = r.position_id || ''
      const logDetail = closeLogMap[posId]
      return {
        position_id: posId,
        ticker: r.ticker,
        expiration: r.expiration,
        put_short_strike: num(r.put_short_strike),
        put_long_strike: num(r.put_long_strike),
        call_short_strike: num(r.call_short_strike),
        call_long_strike: num(r.call_long_strike),
        contracts: int(r.contracts),
        spread_width: num(r.spread_width),
        total_credit: num(r.total_credit),
        close_price: num(r.close_price),
        close_reason: r.close_reason || '',
        realized_pnl: num(r.realized_pnl),
        open_time: r.open_time,
        close_time: r.close_time,
        underlying_at_entry: num(r.underlying_at_entry),
        vix_at_entry: num(r.vix_at_entry),
        wings_adjusted: r.wings_adjusted === 'true' || r.wings_adjusted === '1',
        sandbox_order_id: r.sandbox_order_id || null,
        // New: scanner vs sandbox price data (null for older trades)
        scanner_close_price: logDetail?.scanner_close_price ?? null,
        sandbox_fill_price: logDetail?.sandbox_fill_price ?? null,
        fill_delta_pct: logDetail?.fill_delta_pct ?? null,
      }
    })

    return NextResponse.json({ trades })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
