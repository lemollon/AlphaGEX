import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, validateBot, dteMode, heartbeatName } from '@/lib/db'

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

    // Update paper_account is_active flag
    const result = dte
      ? await query(
          `UPDATE ${botTable(bot, 'paper_account')}
           SET is_active = $1, updated_at = NOW()
           WHERE dte_mode = $2
           RETURNING is_active`,
          [active, dte],
        )
      : await query(
          `UPDATE ${botTable(bot, 'paper_account')}
           SET is_active = $1, updated_at = NOW()
           WHERE is_active IS NOT NULL
           RETURNING is_active`,
          [active],
        )

    if (result.length === 0) {
      return NextResponse.json(
        { error: 'No paper account found' },
        { status: 404 },
      )
    }

    // Log the toggle action
    const status = active ? 'ENABLED' : 'DISABLED'
    if (dte) {
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
    } else {
      await query(
        `INSERT INTO ${botTable(bot, 'logs')} (level, message, details)
         VALUES ($1, $2, $3)`,
        [
          'CONFIG',
          `${botName} bot ${status} via API`,
          JSON.stringify({ active, source: 'toggle_api' }),
        ],
      )
    }

    return NextResponse.json({
      success: true,
      is_active: active,
      message: `${botName} ${status.toLowerCase()}`,
    })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
