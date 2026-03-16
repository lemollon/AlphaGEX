import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'

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
    const rows = await dbQuery(
      `SELECT
        COUNT(*) as total_trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
        COALESCE(SUM(realized_pnl), 0) as total_pnl,
        COALESCE(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END), 0) as avg_win,
        COALESCE(AVG(CASE WHEN realized_pnl <= 0 THEN realized_pnl END), 0) as avg_loss,
        COALESCE(MAX(realized_pnl), 0) as best_trade,
        COALESCE(MIN(realized_pnl), 0) as worst_trade
      FROM ${botTable(bot, 'positions')}
      WHERE status IN ('closed', 'expired')
        AND realized_pnl IS NOT NULL
        ${dteFilter}`,
    )

    const r = rows[0]
    const total = int(r?.total_trades)
    const wins = int(r?.wins)
    const winRate = total > 0 ? (wins / total) * 100 : 0

    return NextResponse.json({
      total_trades: total,
      wins,
      losses: int(r?.losses),
      win_rate: Math.round(winRate * 10) / 10,
      total_pnl: Math.round(num(r?.total_pnl) * 100) / 100,
      avg_win: Math.round(num(r?.avg_win) * 100) / 100,
      avg_loss: Math.round(num(r?.avg_loss) * 100) / 100,
      best_trade: Math.round(num(r?.best_trade) * 100) / 100,
      worst_trade: Math.round(num(r?.worst_trade) * 100) / 100,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
