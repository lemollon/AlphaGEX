import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, validateBot, dteMode, heartbeatName } from '@/lib/databricks'

export const dynamic = 'force-dynamic'

/** Escape a string for safe SQL interpolation. */
function esc(s: string): string {
  return s.replace(/\\/g, '\\\\').replace(/'/g, "''")
}

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

    // Update paper_account is_active flag
    await query(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET is_active = ${active}, updated_at = CURRENT_TIMESTAMP()
       WHERE dte_mode = '${dte}'`,
    )

    // Verify the update (Databricks doesn't support RETURNING)
    const result = await query(
      `SELECT is_active FROM ${botTable(bot, 'paper_account')}
       WHERE dte_mode = '${dte}' LIMIT 1`,
    )

    if (result.length === 0) {
      return NextResponse.json(
        { error: 'No paper account found' },
        { status: 404 },
      )
    }

    // Log the toggle action
    const status = active ? 'ENABLED' : 'DISABLED'
    const details = esc(JSON.stringify({ active, source: 'toggle_api' }))
    await query(
      `INSERT INTO ${botTable(bot, 'logs')} (log_time, level, message, details, dte_mode)
       VALUES (CURRENT_TIMESTAMP(), 'CONFIG', '${esc(`${botName} bot ${status} via API`)}', '${details}', '${dte}')`,
    )

    return NextResponse.json({
      success: true,
      is_active: active,
      message: `${botName} ${status.toLowerCase()}`,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
