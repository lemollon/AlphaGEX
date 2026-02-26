import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, validateBot } from '@/lib/db'

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

  const dte = bot === 'flame' ? '2DTE' : '1DTE'
  const botName = bot.toUpperCase()

  try {
    const body = await req.json()
    const active = Boolean(body.active)

    // Update paper_account is_active flag
    const result = await query(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET is_active = $1, updated_at = NOW()
       WHERE dte_mode = $2
       RETURNING is_active`,
      [active, dte],
    )

    if (result.length === 0) {
      return NextResponse.json(
        { error: 'No paper account found' },
        { status: 404 },
      )
    }

    // Log the toggle action
    const status = active ? 'ENABLED' : 'DISABLED'
    await query(
      `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
       VALUES ($1, $2, $3, $4)`,
      [
        'CONFIG',
        `${botName} bot ${status} via API`,
        JSON.stringify({ active, source: 'toggle_api' }),
        dte,
      ],
    )

    return NextResponse.json({
      success: true,
      is_active: active,
      message: `${botName} ${status.toLowerCase()}`,
    })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
