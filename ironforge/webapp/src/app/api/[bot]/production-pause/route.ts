/**
 * Production-pause control for the live-trading bot.
 *
 * GET  /api/{bot}/production-pause
 *   Returns current pause state for this bot (paused, when, by whom, reason).
 *   Only meaningful for PRODUCTION_BOT — other bots always return `paused:false`.
 *
 * POST /api/{bot}/production-pause
 *   Body: { "paused": boolean, "reason": "optional string", "by": "optional actor" }
 *   Toggles pause state for PRODUCTION_BOT. When paused:
 *     - scanner skips production orders (paper/sandbox continue untouched)
 *     - tradier.ts placeIcOrderAllAccounts drops production accounts defensively
 *     - preflight-live surfaces the pause as an informational advisory
 *   Returns the updated state.
 *
 * Only PRODUCTION_BOT accepts POST. Other bots receive 400 because pausing
 * production for a bot that never had production accounts is meaningless.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbExecute, validateBot } from '@/lib/db'
import { PRODUCTION_BOT, getProductionPauseState } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  if (bot !== PRODUCTION_BOT) {
    return NextResponse.json({
      bot_name: bot.toUpperCase(),
      paused: false,
      paused_at: null,
      paused_by: null,
      paused_reason: null,
      updated_at: null,
      note: `Production pause only applies to ${PRODUCTION_BOT.toUpperCase()} (the live-trading bot).`,
    })
  }

  try {
    const state = await getProductionPauseState(bot)
    return NextResponse.json(state)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  if (bot !== PRODUCTION_BOT) {
    return NextResponse.json(
      { error: `Production pause is only configurable for ${PRODUCTION_BOT.toUpperCase()}.` },
      { status: 400 },
    )
  }

  let body: { paused?: unknown; reason?: unknown; by?: unknown }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 })
  }

  const paused = body.paused === true
  const reason = typeof body.reason === 'string' ? body.reason.slice(0, 500) : null
  const by = typeof body.by === 'string' ? body.by.slice(0, 120) : 'ui'

  try {
    // Upsert the single pause row for this bot. When paused flips to true
    // we stamp paused_at/paused_by/paused_reason; when it flips to false
    // we clear them so the "last reason" doesn't linger on the resumed row.
    if (paused) {
      await dbExecute(
        `INSERT INTO ironforge_production_pause (bot_name, paused, paused_at, paused_by, paused_reason, updated_at)
         VALUES ($1, TRUE, NOW(), $2, $3, NOW())
         ON CONFLICT (bot_name) DO UPDATE SET
           paused = TRUE,
           paused_at = COALESCE(ironforge_production_pause.paused_at, NOW()),
           paused_by = EXCLUDED.paused_by,
           paused_reason = EXCLUDED.paused_reason,
           updated_at = NOW()`,
        [bot.toUpperCase(), by, reason],
      )
    } else {
      await dbExecute(
        `INSERT INTO ironforge_production_pause (bot_name, paused, paused_at, paused_by, paused_reason, updated_at)
         VALUES ($1, FALSE, NULL, $2, NULL, NOW())
         ON CONFLICT (bot_name) DO UPDATE SET
           paused = FALSE,
           paused_at = NULL,
           paused_by = EXCLUDED.paused_by,
           paused_reason = NULL,
           updated_at = NOW()`,
        [bot.toUpperCase(), by],
      )
    }

    const state = await getProductionPauseState(bot)
    return NextResponse.json({ ...state, action: paused ? 'paused' : 'resumed' })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
