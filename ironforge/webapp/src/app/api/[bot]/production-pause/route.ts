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
 * POST is self-guarded. The caller must be ONE of:
 *   - an operator session, or
 *   - a customer session that OWNS this bot (resolveLiveViewer.allowedBots), or
 *   - a holder of IRONFORGE_PAUSE_PASSWORD (legacy operator fallback; disabled
 *     entirely when the env var is unset — fail closed).
 * Ownership matters: without it, any password holder could pause any customer's
 * bot. Middleware additionally requires a session to reach this path at all.
 *
 * Only PRODUCTION_BOT accepts POST. Other bots receive 400 because pausing
 * production for a bot that never had production accounts is meaningless.
 */
import { createHash, timingSafeEqual } from 'crypto'
import { NextRequest, NextResponse } from 'next/server'
import { dbExecute, validateBot } from '@/lib/db'
import { getSession } from '@/lib/auth/server'
import { resolveLiveViewer } from '@/lib/live/viewer'
import type { LiveBot } from '@/lib/live/bots'
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

  // Auth, in order of preference:
  //   1. operator session          — may pause any bot
  //   2. customer session + OWNERSHIP of this bot (resolveLiveViewer)
  //   3. the shared pause password — legacy operator fallback
  //
  // (2) is the point of this block. Previously any caller holding the shared
  // password could pause any bot, so one customer could stop another customer's
  // trading. Ownership is resolved through the same path the Live page uses, so
  // a viewer can only pause a bot that appears in their own allowedBots.
  let authorized = false
  let actor = 'ui'
  try {
    const session = await getSession()
    if (session.userId) {
      authorized = true
      actor = 'operator'
    }
  } catch { /* no/invalid operator session — fall through */ }

  if (!authorized) {
    try {
      const viewer = await resolveLiveViewer(req)
      // isOperator covers IRONFORGE_LIVE_OPEN review mode, which is defined as
      // "see what the owner sees"; ownership still has to include this bot.
      if (viewer.allowedBots.includes(bot as LiveBot)) {
        authorized = true
        actor = viewer.isOperator ? 'operator' : 'customer'
      }
    } catch { /* fail closed — fall through to the password path */ }
  }

  if (!authorized && typeof body.password === 'string' && pausePasswordMatches(body.password)) {
    authorized = true
    actor = 'password'
  }
  if (!authorized) {
    return NextResponse.json({ error: 'not_authorized' }, { status: 403 })
  }

  const paused = body.paused === true
  const reason = typeof body.reason === 'string' ? body.reason.slice(0, 500) : null
  const by = typeof body.by === 'string' ? body.by.slice(0, 120) : actor

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
