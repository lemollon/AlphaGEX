import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, escapeSql, validateBot } from '@/lib/databricks-sql'

export const dynamic = 'force-dynamic'

/**
 * GET /api/[bot]/pdt/audit — Recent PDT audit log entries.
 * Reads from {bot}_pdt_audit_log (per-bot table for UI actions).
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const botName = bot.toUpperCase()

  try {
    const rows = await dbQuery(
      `SELECT action, old_value, new_value, reason, performed_by, created_at
       FROM ${botTable(bot, 'pdt_audit_log')}
       WHERE bot_name = '${escapeSql(botName)}'
       ORDER BY created_at DESC
       LIMIT 10`,
    )

    return NextResponse.json({
      bot_name: botName,
      entries: rows.map((r) => ({
        action: r.action,
        old_value: r.old_value,
        new_value: r.new_value,
        reason: r.reason,
        performed_by: r.performed_by,
        created_at: r.created_at ?? null,
      })),
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
