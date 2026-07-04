/**
 * Production-pause control for the live-trading bot.
 *
 * GET  /api/{bot}/production-pause
 *   Returns current pause state for this bot (paused, when, by whom, reason).
 *   Only meaningful for PRODUCTION_BOT — other bots always return `paused:false`.
 *
 * POST /api/{bot}/production-pause
 *   Body: { "paused": boolean, "reason": "optional string", "by": "optional actor",
 *           "password": "required unless an operator session is present" }
 *   Toggles pause state for PRODUCTION_BOT. When paused:
 *     - scanner skips production orders (paper/sandbox continue untouched)
 *     - tradier.ts placeIcOrderAllAccounts drops production accounts defensively
 *     - preflight-live surfaces the pause as an informational advisory
 *   Returns the updated state.
 *
 * POST is self-guarded (the path is middleware-open so the customer Live page
 * can reach it): the caller must either hold a valid operator session or send
 * `password` matching the IRONFORGE_PAUSE_PASSWORD env var. When the env var
 * is unset the password path is disabled entirely (fail-closed, session only).
 *
 * Only PRODUCTION_BOT accepts POST. Other bots receive 400 because pausing
 * production for a bot that never had production accounts is meaningless.
 */
import { createHash, timingSafeEqual } from 'crypto'
import { NextRequest, NextResponse } from 'next/server'
import { dbExecute, validateBot } from '@/lib/db'
import { getSession } from '@/lib/auth/server'
import { PRODUCTION_BOT, isProductionBot, getProductionPauseState } from '@/lib/tradier'

/** Constant-time password check; sha256 first so length never leaks. */
function pausePasswordMatches(candidate: string): boolean {
  const expected = process.env.IRONFORGE_PAUSE_PASSWORD
  if (!expected) return false
  const a = createHash('sha256').update(candidate).digest()
  const b = createHash('sha256').update(expected).digest()
  return timingSafeEqual(a, b)
}

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  if (!isProductionBot(bot)) {
    return NextResponse.json({
      bot_name: bot.toUpperCase(),
      paused: false,
      paused_at: null,
      paused_by: null,
      paused_reason: null,
      updated_at: null,
      note: `Production pause only applies to live-trading bots (${PRODUCTION_BOT.toUpperCase()}, KINDLE).`,
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

  if (!isProductionBot(bot)) {
    return NextResponse.json(
      { error: `Production pause is only configurable for live-trading bots (${PRODUCTION_BOT.toUpperCase()}, KINDLE).` },
      { status: 400 },
    )
  }

  let body: { paused?: unknown; reason?: unknown; by?: unknown; password?: unknown }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 })
  }

  // Auth: operator session OR the shared pause password. Session read never
  // throws the request into a 500 — a broken cookie just falls through to
  // the password check.
  let authorized = false
  try {
    const session = await getSession()
    authorized = Boolean(session.userId)
  } catch { /* no/invalid operator session — try the password */ }
  if (!authorized && typeof body.password === 'string' && pausePasswordMatches(body.password)) {
    authorized = true
  }
  if (!authorized) {
    return NextResponse.json({ error: 'password_required' }, { status: 403 })
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
