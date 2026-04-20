import { NextRequest, NextResponse } from 'next/server'
import { validateBot } from '@/lib/db'
import {
  getProductionAccountsForBot,
  getTradierBalanceDetail,
  PRODUCTION_BOT,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * GET /api/[bot]/production/balances
 *
 * Returns live Tradier balance + buying power for each production account
 * assigned to this bot. Only the production bot (SPARK) returns data;
 * paper-only bots get an empty array.
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
        if (!acct.accountId) {
          return {
            name: acct.name,
            account_id: null,
            error: 'account_id_unavailable',
          }
        }
        const bal = await getTradierBalanceDetail(acct.apiKey, acct.accountId, acct.baseUrl)
        if (!bal) {
          return {
            name: acct.name,
            account_id: acct.accountId,
            error: 'balance_fetch_failed',
          }
        }
        return { name: acct.name, ...bal }
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
