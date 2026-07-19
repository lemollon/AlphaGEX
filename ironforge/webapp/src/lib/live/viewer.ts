import type { NextRequest } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { dbQuery } from '@/lib/db'

/**
 * Account-aware Live page: which live-money bots may this viewer see?
 *
 * - Operators (ops session / magic link): every live bot, with the top-right
 *   account toggle.
 * - Customers: exactly the bots mapped to them in ironforge_customer_bots
 *   (e.g. the SPARK2 account owner sees ONLY spark2). No mapping → NO account
 *   (empty state) — a fresh signup must never see the operator's real money.
 * - Anonymous: NO account (empty state) for the same reason.
 *
 * The API routes enforce this server-side; the client toggle merely renders
 * what `allowedBots` says.
 */

// Registry lives in ./bots (no server imports) so client components can use it
// too. Re-exported here to keep existing server-side import sites unchanged.
export {
  LIVE_BOTS,
  LIVE_BOT_MODE,
  LIVE_BOT_LABEL,
  LIVE_BOT_PILL,
  LIVE_BOT_TAGLINE,
  PAPER_DISCLOSURE,
  accountMode,
  isPaperBot,
  isLiveBot,
} from './bots'
export type { LiveBot, LiveAccountMode } from './bots'

import { LIVE_BOTS, LIVE_BOT_MODE, isLiveBot, type LiveBot, type LiveAccountMode } from './bots'
import { isFlameLiveArmed } from '@/lib/tradier'

/**
 * Effective account mode, resolved at request time.
 *
 * LIVE_BOT_MODE is the DECLARED default (client-safe, no env access). FLAME is
 * declared 'paper' and stays that way until it is genuinely armed for live
 * trading — at which point the page must stop showing the paper badge and start
 * reading the production ledger. Resolving here keeps the badge honest in both
 * directions instead of drifting out of sync with the arm switch.
 */
export function resolveAccountMode(bot: LiveBot): LiveAccountMode {
  if (bot === 'flame') return isFlameLiveArmed() ? 'production' : 'paper'
  return LIVE_BOT_MODE[bot]
}

export function resolvePaperBots(bots: LiveBot[]): LiveBot[] {
  return bots.filter((b) => resolveAccountMode(b) === 'paper')
}

export interface LiveViewer {
  /** null = this viewer is not authorized for any live account (empty state). */
  bot: LiveBot | null
  allowedBots: LiveBot[]
  /** Subset of allowedBots currently running on simulated money. Drives the
   *  "Paper" badge on the strategy pills/rail without the client needing env. */
  paperBots: LiveBot[]
}

export async function resolveLiveViewer(req: NextRequest): Promise<LiveViewer> {
  let allowed: LiveBot[] = []

  try {
    const ops = await getSession()
    if (ops.userId) {
      allowed = [...LIVE_BOTS]
    } else {
      const customer = await getCustomerSession()
      if (customer.customerId) {
        const rows = await dbQuery<{ bot: string }>(
          `SELECT bot FROM ironforge_customer_bots WHERE customer_id = $1`,
          [customer.customerId],
        )
        allowed = rows.map((r) => r.bot).filter(isLiveBot)
      }
    }
  } catch {
    // Fail closed: no account visibility on any error.
    allowed = []
  }

  const requested = req.nextUrl.searchParams.get('account')
  const bot = isLiveBot(requested) && allowed.includes(requested) ? requested : (allowed[0] ?? null)
  return { bot, allowedBots: allowed, paperBots: resolvePaperBots(allowed) }
}
