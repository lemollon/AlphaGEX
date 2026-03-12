import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, escapeSql, validateBot, dteMode } from '@/lib/databricks-sql'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `WHERE dte_mode = '${escapeSql(dte)}'` : ''

  try {
    const rows = await dbQuery(
      `SELECT log_time, level, message, details
       FROM ${botTable(bot, 'logs')}
       ${dteFilter}
       ORDER BY log_time DESC
       LIMIT 50`,
    )

    const logs = rows.map((r) => ({
      timestamp: r.log_time || null,
      level: r.level,
      message: r.message,
      details: r.details,
    }))

    return NextResponse.json({ logs })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
