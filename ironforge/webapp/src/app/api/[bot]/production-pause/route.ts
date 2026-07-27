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
 *   - any caller, when this deployment runs in public mode (isPublicMode() —
 *     the operator console has no login wall, so no caller there can hold a
 *     session and the dashboard's Pause button would be permanently 403), or
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
import { isPublicMode } from '@/lib/auth/access'
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

  // Auth AND scope, in order of preference:
  //   0. public mode               — no login on this deployment      -> FLEET
  //   1. operator session          — may pause any bot                -> FLEET
  //   2. customer owning this bot  — resolveLiveViewer.allowedBots    -> OWN ACCOUNT
  //   3. the shared pause password — legacy operator fallback         -> FLEET
  //
  // (2) is the point of this block, in two stages. Ownership stops one customer
  // pausing a bot that isn't theirs. SCOPE stops the other half of the problem:
  // ironforge_production_pause is ONE ROW PER BOT, so an authorized customer
  // pressing Pause used to halt every other owner's real-money trading too. A
  // customer now writes ironforge_owner_pause keyed by their own account owner
  // and cannot reach the fleet row at all.
  let authorized = false
  let actor = 'ui'
  // null = FLEET scope (stops the bot for every owner). A non-null value scopes
  // the pause to that one ironforge_accounts.person.
  let ownerScope: string | null = null
  // Public mode short-circuits the session ladder below: on a deployment with
  // the login wall lifted, none of those checks can ever pass, so the control
  // would be dead rather than open. Recorded as 'public-mode' in paused_by so
  // the pause row still says how the change was authorised.
  if (isPublicMode()) {
    authorized = true
    actor = 'public-mode'
  }

  if (!authorized) {
    try {
      // resolveLiveViewer is the SINGLE source of both authorization and scope.
      // It already distinguishes the two cases correctly: isOperator is true only
      // for a real operator session, and false while impersonating (a customer
      // session wins — #2619). So an operator driving the customer UI as a
      // customer pauses that customer's account, not everyone's, which is what
      // the screen in front of them claims to be doing. Fleet pause stays
      // available to an operator who is not impersonating.
      const viewer = await resolveLiveViewer(req)
      if (viewer.allowedBots.includes(bot as LiveBot)) {
        if (viewer.isOperator) {
          authorized = true
          actor = 'operator'
        } else if (viewer.person) {
          authorized = true
          actor = 'customer'
          ownerScope = viewer.person
        } else {
          // A customer with no account mapped has nothing of their own to pause,
          // and must never be able to fall through to a fleet-wide stop.
          return NextResponse.json(
            { error: 'no_account_linked', detail: 'No trading account is linked to your profile yet.' },
            { status: 403 },
          )
        }
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
    // OWNER-SCOPED pause (a customer stopping their own account). Writes a
    // different table entirely, so a customer can never touch the fleet row —
    // ironforge_production_pause is one row per bot, and before this any
    // customer mapped to SPARK could halt every other owner's trading.
    if (ownerScope) {
      if (paused) {
        await dbExecute(
          `INSERT INTO ironforge_owner_pause (bot_name, person, paused, paused_at, paused_by, paused_reason, updated_at)
           VALUES ($1, $2, TRUE, NOW(), $3, $4, NOW())
           ON CONFLICT (bot_name, person) DO UPDATE SET
             paused = TRUE,
             paused_at = COALESCE(ironforge_owner_pause.paused_at, NOW()),
             paused_by = EXCLUDED.paused_by,
             paused_reason = EXCLUDED.paused_reason,
             updated_at = NOW()`,
          [bot.toUpperCase(), ownerScope, by, reason],
        )
      } else {
        await dbExecute(
          `INSERT INTO ironforge_owner_pause (bot_name, person, paused, paused_at, paused_by, paused_reason, updated_at)
           VALUES ($1, $2, FALSE, NULL, $3, NULL, NOW())
           ON CONFLICT (bot_name, person) DO UPDATE SET
             paused = FALSE,
             paused_at = NULL,
             paused_by = EXCLUDED.paused_by,
             paused_reason = NULL,
             updated_at = NOW()`,
          [bot.toUpperCase(), ownerScope, by],
        )
      }
      return NextResponse.json({ ok: true, bot: bot.toUpperCase(), paused, scope: 'owner', person: ownerScope })
    }

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
    return NextResponse.json({ ...state, action: paused ? 'paused' : 'resumed', scope: 'fleet' })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
