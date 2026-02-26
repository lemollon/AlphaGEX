import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, validateBot } from '@/lib/databricks'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = bot === 'flame' ? '2DTE' : '1DTE'

  try {
    const rows = await query(`
      SELECT log_time, level, message, details
      FROM ${botTable(bot, 'logs')}
      WHERE dte_mode = '${dte}'
      ORDER BY log_time DESC
      LIMIT 50
    `)

    const logs = rows.map((r) => ({
      timestamp: r.log_time,
      level: r.level,
      message: r.message,
      details: r.details,
    }))

    return NextResponse.json({ logs })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
