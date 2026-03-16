import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, escapeSql, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `WHERE dte_mode = '${escapeSql(dte)}'` : ''

  const url = new URL(req.url)
  const limit = Math.min(Math.max(1, parseInt(url.searchParams.get('limit') || '50', 10) || 50), 200)
  const offset = Math.max(0, parseInt(url.searchParams.get('offset') || '0', 10) || 0)

  try {
    const rows = await dbQuery(
      `SELECT log_time, level, message, details
       FROM ${botTable(bot, 'logs')}
       ${dteFilter}
       ORDER BY log_time DESC
       LIMIT ${limit} OFFSET ${offset}`,
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
