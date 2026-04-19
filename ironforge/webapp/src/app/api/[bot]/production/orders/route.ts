import { NextRequest, NextResponse } from 'next/server'
import { validateBot } from '@/lib/db'
import {
  getProductionAccountsForBot,
  getTradierOrders,
  PRODUCTION_BOT,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

const HISTORY_WINDOW_DAYS = 30

/**
 * GET /api/[bot]/production/orders
 *
 * Returns open + recent historical orders for each production account
 * assigned to this bot. Historical window is the last 30 days; open orders
 * are always included regardless of age.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== PRODUCTION_BOT) {
    return NextResponse.json({ accounts: [], production_bot: PRODUCTION_BOT })
  }

  try {
    const accounts = await getProductionAccountsForBot(bot)
    const cutoff = Date.now() - HISTORY_WINDOW_DAYS * 24 * 60 * 60 * 1000

    const details = await Promise.all(
      accounts.map(async (acct) => {
        if (!acct.accountId) {
          return {
            name: acct.name,
            account_id: null,
            open: [],
            history: [],
            error: 'account_id_unavailable',
          }
        }
        // Tradier returns all orders when status is omitted; we filter locally
        // so we get both the currently-working and recently-filled/canceled ones.
        const all = await getTradierOrders(acct.apiKey, acct.accountId, acct.baseUrl, 'all')
        const isOpen = (s: string) =>
          s === 'open' || s === 'partially_filled' || s === 'pending' || s === 'calculated'
        const inWindow = (o: { create_date: string | null; transaction_date: string | null }) => {
          const ts = o.transaction_date || o.create_date
          if (!ts) return true
          const t = Date.parse(ts)
          return isNaN(t) ? true : t >= cutoff
        }
        const open = all.filter(o => isOpen(o.status))
        const history = all
          .filter(o => !isOpen(o.status) && inWindow(o))
          .sort((a, b) => {
            const ta = Date.parse(a.transaction_date || a.create_date || '') || 0
            const tb = Date.parse(b.transaction_date || b.create_date || '') || 0
            return tb - ta
          })
        return {
          name: acct.name,
          account_id: acct.accountId,
          open,
          history,
        }
      }),
    )

    return NextResponse.json({
      production_bot: PRODUCTION_BOT,
      history_window_days: HISTORY_WINDOW_DAYS,
      accounts: details,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
