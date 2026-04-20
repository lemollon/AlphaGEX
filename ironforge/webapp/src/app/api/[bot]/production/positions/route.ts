import { NextRequest, NextResponse } from 'next/server'
import { validateBot } from '@/lib/db'
import {
  getProductionAccountsForBot,
  getSandboxAccountPositions,
  PRODUCTION_BOT,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * GET /api/[bot]/production/positions
 *
 * Returns live Tradier positions on each production account assigned to this bot.
 * Paper-only bots return an empty array.
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
    const details = await Promise.all(
      accounts.map(async (acct) => {
        const positions = await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
        return {
          name: acct.name,
          account_id: acct.accountId,
          positions: positions.filter(p => p.quantity !== 0),
        }
      }),
    )

    return NextResponse.json({
      production_bot: PRODUCTION_BOT,
      accounts: details,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
