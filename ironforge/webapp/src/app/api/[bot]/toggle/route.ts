import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, escapeSql, validateBot, dteMode, heartbeatName } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * POST /api/[bot]/toggle
 *
 * Enable or disable a bot. Persists `is_active` in paper_account so the
 * Python trader reads the state on its next cycle.
 *
 * Body: { "active": boolean }
 */
export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const botName = heartbeatName(bot)

  try {
    const body = await req.json()
    const active = Boolean(body.active)
    const accountType = body.account_type as string | undefined

    // Update paper_account is_active flag (filtered by account_type if provided)
    const dteFilter = dte ? `WHERE dte_mode = '${escapeSql(dte)}'` : 'WHERE is_active IS NOT NULL'
    const accountTypeFilter = accountType
      ? ` AND COALESCE(account_type, 'sandbox') = '${escapeSql(accountType)}'`
      : ''
    await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET is_active = ${active}, updated_at = NOW()
       ${dteFilter}${accountTypeFilter}`,
    )

    // Verify the update took effect
    const result = await dbQuery(
      `SELECT is_active FROM ${botTable(bot, 'paper_account')}
       ${dteFilter}${accountTypeFilter} LIMIT 1`,
    )

    if (result.length === 0) {
      return NextResponse.json(
        { error: 'No paper account found' },
        { status: 404 },
      )
    }

    // Log the toggle action
    const status = active ? 'ENABLED' : 'DISABLED'
    const dtePart = dte ? `, dte_mode = '${escapeSql(dte)}'` : ''
    await dbExecute(
      `INSERT INTO ${botTable(bot, 'logs')} (level, message, details${dte ? ', dte_mode' : ''})
       VALUES ('CONFIG', '${escapeSql(botName)} bot ${status} via API',
               '${escapeSql(JSON.stringify({ active, source: 'toggle_api' }))}'${dtePart})`,
    )

    return NextResponse.json({
      success: true,
      is_active: active,
      message: `${botName} ${status.toLowerCase()}`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
