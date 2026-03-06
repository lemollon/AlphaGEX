import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, validateBot } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET /api/[bot]/pdt/audit — Recent PDT audit log entries
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const botName = bot.toUpperCase()

  try {
    const rows = await query(
      `SELECT action, old_value, new_value, reason, performed_by, created_at
       FROM ${botTable(bot, 'pdt_audit_log')}
       WHERE bot_name = $1
       ORDER BY created_at DESC
       LIMIT 10`,
      [botName],
    )

    return NextResponse.json({
      bot_name: botName,
      entries: rows.map((r) => ({
        action: r.action,
        old_value: r.old_value,
        new_value: r.new_value,
        reason: r.reason,
        performed_by: r.performed_by,
        created_at: r.created_at?.toISOString?.() ?? r.created_at ?? null,
      })),
    })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
