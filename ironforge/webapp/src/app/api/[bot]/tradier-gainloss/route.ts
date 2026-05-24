/**
 * READ-ONLY diagnostic — Tradier realized gain/loss per closed position for the
 * loaded accounts, over an optional close-date range.
 *
 * Surfaces the broker's AUTHORITATIVE realized P&L, including option
 * EXPIRATIONS and ASSIGNMENTS — which never appear as orders and so cannot be
 * reconstructed by recover-today-trade's order-history path. Built to reconcile
 * broker_gone_blocked rows whose close orders were rejected or whose legs
 * vanished from the broker (we can't tell from the bot's logs whether such a
 * position expired worthless, closed at SL/PT, or never established — the
 * broker's gain/loss is the only ground truth).
 *
 *   GET /api/spark/tradier-gainloss?account_type=production&person=Logan
 *       &start=2026-05-19&end=2026-05-26&symbol=SPY
 *
 * Params (all optional):
 *   account_type = sandbox | production   (default: both)
 *   person       = e.g. Logan             (default: all loaded accounts)
 *   start, end   = YYYY-MM-DD close-date window
 *   symbol       = underlying root substring (default SPY)
 *
 * NO WRITES. Returns the raw closed-position legs plus a per-(account,
 * close_date) sum so a multileg IC (4 legs) can be matched and totaled, then
 * applied via manual-correct-trade.
 */
import { NextRequest, NextResponse } from 'next/server'
import { validateBot } from '@/lib/db'
import {
  getLoadedSandboxAccountsAsync,
  getAccountIdForKey,
  getTradierGainLoss,
  isConfigured,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (!isConfigured()) return NextResponse.json({ error: 'Tradier not configured' }, { status: 500 })

  const sp = req.nextUrl.searchParams
  const accountTypeFilter = sp.get('account_type')
  const personFilter = sp.get('person')
  const start = sp.get('start') ?? undefined
  const end = sp.get('end') ?? undefined
  const symbolFilter = (sp.get('symbol') ?? 'SPY').toUpperCase()

  const isDate = (s?: string) => !s || /^\d{4}-\d{2}-\d{2}$/.test(s)
  if (!isDate(start) || !isDate(end)) {
    return NextResponse.json({ error: 'start/end must be YYYY-MM-DD' }, { status: 400 })
  }

  try {
    let accounts = await getLoadedSandboxAccountsAsync()
    if (accountTypeFilter === 'sandbox' || accountTypeFilter === 'production') {
      accounts = accounts.filter((a) => a.type === accountTypeFilter)
    }
    if (personFilter) accounts = accounts.filter((a) => a.name === personFilter)

    const results: unknown[] = []
    for (const acct of accounts) {
      const accountId = await getAccountIdForKey(acct.apiKey, acct.baseUrl)
      if (!accountId) {
        results.push({ person: acct.name, account_type: acct.type, error: 'no account id resolved' })
        continue
      }
      const all = await getTradierGainLoss(acct.apiKey, accountId, acct.baseUrl, start, end)
      const closed = all.filter((p) => (p.symbol ?? '').toUpperCase().includes(symbolFilter))

      // Group by close date (date portion) → sum gain_loss so a 4-leg IC totals.
      const byDate: Record<string, { legs: number; gain_loss: number }> = {}
      for (const p of closed) {
        const d = (p.close_date ?? '').slice(0, 10) || 'unknown'
        if (!byDate[d]) byDate[d] = { legs: 0, gain_loss: 0 }
        byDate[d].legs += 1
        byDate[d].gain_loss += p.gain_loss ?? 0
      }
      const byCloseDate = Object.entries(byDate)
        .map(([close_date, v]) => ({ close_date, legs: v.legs, gain_loss: Math.round(v.gain_loss * 100) / 100 }))
        .sort((a, b) => a.close_date.localeCompare(b.close_date))

      results.push({
        person: acct.name,
        account_type: acct.type,
        account_id: accountId,
        closed_count: closed.length,
        by_close_date: byCloseDate,
        closed_positions: closed,
      })
    }

    return NextResponse.json({
      bot,
      filters: { account_type: accountTypeFilter, person: personFilter, start, end, symbol: symbolFilter },
      accounts: results,
      note:
        'READ-ONLY. by_close_date sums all matching option legs per close date — a 4-leg IC = 4 legs. ' +
        'Match to a blocked position by close_date + strikes, then apply via manual-correct-trade.',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
