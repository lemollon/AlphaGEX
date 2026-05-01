import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * Audit closed positions that look like "phantom closes" — i.e. the DB
 * recorded a close_price/realized_pnl that did NOT come from a real broker
 * fill. Two signatures we look for:
 *
 *   1. close_reason indicates a recovery/reconcile path
 *      (broker_position_gone, broker_gone_*, deferred_broker_gone) — these
 *      are the paths that historically used estimatedPrice fallbacks before
 *      the recent Path A/B safety gates landed.
 *
 *   2. sandbox_close_order_id JSON has no entry with fill_price > 0 for the
 *      position's account_type — meaning we never observed a real Tradier
 *      fill price. Even non-broker-gone reasons (eod_cutoff, profit_target_*)
 *      can be phantom if all close attempts failed.
 *
 * For each suspect row we compute:
 *   - max_profit_if_expired_worthless = total_credit * 100 * contracts
 *   - delta_to_max_profit = max_profit_if_expired_worthless - realized_pnl
 *     (positive = the recorded outcome is WORSE than max profit, suggesting
 *     the position may have actually expired worthless and the DB underreports)
 *
 * GET /api/{bot}/audit-phantom-closes?account_type=production&limit=50
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

  const accountTypeParam = req.nextUrl.searchParams.get('account_type')
  const accountTypeFilter = accountTypeParam
    ? `AND COALESCE(account_type, 'sandbox') = '${escapeSql(accountTypeParam)}'`
    : ''

  const limit = Math.min(int(req.nextUrl.searchParams.get('limit') || '50') || 50, 200)

  try {
    const rows = await dbQuery(
      `SELECT position_id, account_type, person, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts, total_credit, close_price, realized_pnl,
              close_reason, open_time, close_time,
              sandbox_close_order_id
       FROM ${botTable(bot, 'positions')}
       WHERE status IN ('closed', 'expired')
         ${dteFilter} ${accountTypeFilter}
       ORDER BY close_time DESC
       LIMIT ${limit}`,
    )

    type AccountFill = {
      account_key: string
      order_id: number | null
      contracts: number | null
      fill_price: number | null
      account_type: string | null
    }

    const phantomReasonRegex = /broker_position_gone|broker_gone|deferred_broker_gone/i

    const suspects = rows.map((r: any) => {
      const acctType = (r.account_type || 'sandbox') as string
      const reason = r.close_reason || ''
      const reasonMatches = phantomReasonRegex.test(reason)

      // Parse sandbox_close_order_id JSON to inspect per-account fills
      let parsedFills: AccountFill[] = []
      let parseError: string | null = null
      if (r.sandbox_close_order_id) {
        try {
          const obj = JSON.parse(r.sandbox_close_order_id)
          for (const [k, v] of Object.entries(obj)) {
            // Skip metadata keys (start with _)
            if (k.startsWith('_')) continue
            const info = v as Record<string, unknown>
            if (typeof info !== 'object' || info == null) continue
            parsedFills.push({
              account_key: k,
              order_id: typeof info.order_id === 'number' ? info.order_id : null,
              contracts: typeof info.contracts === 'number' ? info.contracts : null,
              fill_price: typeof info.fill_price === 'number' ? info.fill_price : null,
              account_type: typeof info.account_type === 'string' ? info.account_type : null,
            })
          }
        } catch (e: unknown) {
          parseError = e instanceof Error ? e.message : String(e)
        }
      }

      // For the position's account_type, did ANY account return a real fill?
      const matchingAccountFills = parsedFills.filter(
        (f) => (f.account_type ?? 'sandbox') === acctType,
      )
      const hasRealFill = matchingAccountFills.some(
        (f) => typeof f.fill_price === 'number' && f.fill_price > 0,
      )
      const hasOrderIdNoFill = matchingAccountFills.some(
        (f) => typeof f.order_id === 'number' && f.order_id > 0 && !(typeof f.fill_price === 'number' && f.fill_price > 0),
      )

      // Phantom signature: reason indicates recovery/reconcile path AND no real fill
      const isPhantomCandidate = reasonMatches || (!hasRealFill && parsedFills.length > 0 && hasOrderIdNoFill)

      const entryCredit = num(r.total_credit)
      const contracts = int(r.contracts)
      const realizedPnl = num(r.realized_pnl)
      const closePrice = num(r.close_price)
      const maxProfit = Math.round(entryCredit * 100 * contracts * 100) / 100
      const deltaToMaxProfit = Math.round((maxProfit - realizedPnl) * 100) / 100

      // Format close_time in CT for human readability
      let closeTimeCt: string | null = null
      try {
        if (r.close_time) {
          closeTimeCt = new Date(r.close_time).toLocaleString('en-US', {
            timeZone: 'America/Chicago',
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
          })
        }
      } catch { /* leave null */ }

      return {
        position_id: r.position_id,
        is_phantom_candidate: isPhantomCandidate,
        phantom_signals: {
          close_reason_matches: reasonMatches,
          no_real_fill_for_account_type: !hasRealFill,
          has_order_id_but_no_fill_price: hasOrderIdNoFill,
        },
        account_type: acctType,
        person: r.person ?? null,
        expiration: r.expiration?.toISOString?.()?.slice(0, 10)
          ?? (r.expiration ? String(r.expiration).slice(0, 10) : null),
        strikes: `${num(r.put_long_strike)}/${num(r.put_short_strike)}P - ${num(r.call_short_strike)}/${num(r.call_long_strike)}C`,
        contracts,
        entry_credit: entryCredit,
        stored: {
          close_price: closePrice,
          realized_pnl: realizedPnl,
          close_reason: reason,
          close_time_ct: closeTimeCt,
        },
        per_account_fills: parsedFills,
        sandbox_close_order_id_parse_error: parseError,
        max_profit_if_expired_worthless: maxProfit,
        delta_to_max_profit: deltaToMaxProfit,
      }
    })

    const candidates = suspects.filter((s) => s.is_phantom_candidate)
    const totalPhantomDelta = Math.round(
      candidates.reduce((acc, s) => acc + s.delta_to_max_profit, 0) * 100,
    ) / 100

    return NextResponse.json({
      bot,
      account_type_filter: accountTypeParam ?? 'all',
      scanned: rows.length,
      phantom_candidates: candidates.length,
      total_delta_to_max_profit: totalPhantomDelta,
      suspects: candidates,
      all_rows_scanned: suspects.length,
    })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
