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
 *   (e.g. the SPARK2 account owner sees ONLY spark2). No mapping → the
 *   default public view (spark), same as today.
 * - Anonymous (site dark): spark only — unchanged behavior.
 *
 * The API routes enforce this server-side; the client toggle merely renders
 * what `allowedBots` says.
 */

export const LIVE_BOTS = ['spark', 'spark2'] as const
export type LiveBot = (typeof LIVE_BOTS)[number]
const DEFAULT_BOT: LiveBot = 'spark'

export interface LiveViewer {
  bot: LiveBot
  allowedBots: LiveBot[]
}

function isLiveBot(v: string | null): v is LiveBot {
  return v === 'spark' || v === 'spark2'
}

export async function resolveLiveViewer(req: NextRequest): Promise<LiveViewer> {
  let allowed: LiveBot[] = [DEFAULT_BOT]

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
        const mapped = rows.map((r) => r.bot).filter(isLiveBot)
        if (mapped.length > 0) allowed = mapped
      }
    }
  } catch {
    // Fail closed to the public default view.
    allowed = [DEFAULT_BOT]
  }

  const requested = req.nextUrl.searchParams.get('account')
  const bot = isLiveBot(requested) && allowed.includes(requested) ? requested : allowed[0]
  return { bot, allowedBots: allowed }
}
