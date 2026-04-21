/**
 * Builder snapshot endpoint — the single data source for the `/spark`
 * Builder tab. Returns the currently open IC position plus everything
 * the four ported SpreadWorks components need to render:
 *
 *   - position         : current strikes, expiration, contracts, entry credit
 *   - legs             : per-leg Tradier quote + greeks (for LegBreakdown)
 *   - payoff           : expiration P&L curve + breakevens + max profit/loss
 *                        (for PayoffDiagram / PayoffPanel)
 *   - metrics          : aggregate credit/max/pop/net-greeks (for MetricsBar)
 *   - mtm              : live mark-to-market (unrealized P&L)
 *   - spot_price       : current SPY quote (also for CandleChart's price marker)
 *
 * When no open position exists for the requested bot + scope, returns
 * `{ position: null }` so the UI can render a placeholder ("Builder
 * renders when SPARK is in a position").
 *
 * Filters:
 *   account_type = 'production' | 'sandbox' (default: 'sandbox')
 *     Matches the Paper/Live toggle elsewhere on the dashboard.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import {
  buildOccSymbol,
  getBatchOptionQuotesWithGreeks,
  getIcMarkToMarket,
  getQuote,
  isConfigured,
  type LegQuoteWithGreeks,
} from '@/lib/tradier'
import { computeIcPayoff } from '@/lib/ic-payoff'

export const dynamic = 'force-dynamic'

interface LegOut {
  role: 'long_put' | 'short_put' | 'short_call' | 'long_call'
  strike: number
  type: 'P' | 'C'
  occ_symbol: string
  bid: number | null
  ask: number | null
  mid: number | null
  last: number | null
  delta: number | null
  gamma: number | null
  theta: number | null
  vega: number | null
  mid_iv: number | null
}

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

  try {
    // Most recent open position for this bot + scope. Builder focuses on
    // one position at a time — if there are multiple opens (INFERNO), we
    // show the most recent and let the existing Positions tab handle the
    // fleet view.
    const rows = await dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts, spread_width, total_credit,
              underlying_at_entry, vix_at_entry,
              open_time,
              COALESCE(account_type, 'sandbox') AS account_type,
              person
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter} ${accountTypeFilter}
       ORDER BY open_time DESC
       LIMIT 1`,
    )
    if (rows.length === 0) {
      return NextResponse.json({ position: null, tradier_connected: isConfigured() })
    }

    const r = rows[0]
    const ticker = r.ticker || 'SPY'
    const expirationRaw = r.expiration
    const expiration = expirationRaw?.toISOString?.()?.slice(0, 10)
      ?? String(expirationRaw).slice(0, 10)
    const ps = num(r.put_short_strike)
    const pl = num(r.put_long_strike)
    const cs = num(r.call_short_strike)
    const cl = num(r.call_long_strike)
    const contracts = int(r.contracts)
    const entryCredit = num(r.total_credit)

    // Build OCC symbols for the 4 legs (same helper the scanner uses)
    const occ = {
      long_put: buildOccSymbol(ticker, expiration, pl, 'P'),
      short_put: buildOccSymbol(ticker, expiration, ps, 'P'),
      short_call: buildOccSymbol(ticker, expiration, cs, 'C'),
      long_call: buildOccSymbol(ticker, expiration, cl, 'C'),
    }

    // Parallel fetch everything so one slow call doesn't stack with the others.
    // All three are best-effort — if Tradier is down we still return the
    // position row and a payoff curve (payoff is pure math, needs no network).
    const [quotesMap, mtm, underlyingQuote] = await Promise.all([
      getBatchOptionQuotesWithGreeks(Object.values(occ)).catch(() => ({})),
      getIcMarkToMarket(ticker, expiration, ps, pl, cs, cl, entryCredit).catch(() => null),
      getQuote(ticker).catch(() => null),
    ]) as [Record<string, LegQuoteWithGreeks>, Awaited<ReturnType<typeof getIcMarkToMarket>>, Awaited<ReturnType<typeof getQuote>>]

    const spotPrice = underlyingQuote?.last ?? mtm?.spot_price ?? num(r.underlying_at_entry)

    // Assemble legs array. The role determines sign for greeks aggregation
    // in the metrics bar: long = +1, short = −1.
    const legs: LegOut[] = [
      { role: 'long_put', strike: pl, type: 'P', occ_symbol: occ.long_put, ...emptyQuote() },
      { role: 'short_put', strike: ps, type: 'P', occ_symbol: occ.short_put, ...emptyQuote() },
      { role: 'short_call', strike: cs, type: 'C', occ_symbol: occ.short_call, ...emptyQuote() },
      { role: 'long_call', strike: cl, type: 'C', occ_symbol: occ.long_call, ...emptyQuote() },
    ]
    for (const leg of legs) {
      const q = quotesMap[leg.occ_symbol]
      if (q) {
        leg.bid = q.bid
        leg.ask = q.ask
        leg.mid = q.mid
        leg.last = q.last
        leg.delta = q.delta
        leg.gamma = q.gamma
        leg.theta = q.theta
        leg.vega = q.vega
        leg.mid_iv = q.mid_iv
      }
    }

    // Payoff math is pure — never fails.
    const payoff = computeIcPayoff(
      { putLong: pl, putShort: ps, callShort: cs, callLong: cl },
      entryCredit,
      contracts,
      spotPrice,
    )

    // Net Greeks from the 4 legs × sign (long = +, short = −) × contracts.
    // Some legs may lack greeks (quote without greeks payload) — null-guard.
    const sign = (role: LegOut['role']) =>
      role === 'long_put' || role === 'long_call' ? 1 : -1
    const sumGreek = (pick: (l: LegOut) => number | null): number | null => {
      let any = false
      let sum = 0
      for (const leg of legs) {
        const v = pick(leg)
        if (v == null) continue
        any = true
        sum += v * sign(leg.role) * contracts
      }
      return any ? Math.round(sum * 10000) / 10000 : null
    }
    const netDelta = sumGreek((l) => l.delta)
    const netGamma = sumGreek((l) => l.gamma)
    const netTheta = sumGreek((l) => l.theta)
    const netVega = sumGreek((l) => l.vega)

    // MTM-derived unrealized P&L. Prefer cost_to_close_last (matches Tradier
    // portfolio), fall back to mid if last is missing or stale.
    let unrealizedPnl: number | null = null
    let unrealizedPct: number | null = null
    if (mtm) {
      const costBasis = mtm.cost_to_close_last ?? mtm.cost_to_close_mid
      if (costBasis != null && Number.isFinite(costBasis)) {
        unrealizedPnl = Math.round((entryCredit - costBasis) * 100 * contracts * 100) / 100
        if (entryCredit > 0) {
          unrealizedPct = Math.round(((entryCredit - costBasis) / entryCredit) * 10000) / 100
        }
      }
    }

    return NextResponse.json({
      tradier_connected: isConfigured(),
      position: {
        position_id: r.position_id,
        ticker,
        expiration,
        put_long_strike: pl,
        put_short_strike: ps,
        call_short_strike: cs,
        call_long_strike: cl,
        contracts,
        entry_credit: entryCredit,
        spread_width: num(r.spread_width) || Math.min(ps - pl, cl - cs),
        underlying_at_entry: num(r.underlying_at_entry),
        vix_at_entry: num(r.vix_at_entry),
        open_time: r.open_time || null,
        account_type: r.account_type,
        person: r.person || null,
      },
      spot_price: spotPrice,
      legs,
      payoff,
      metrics: {
        net_credit: Math.round(entryCredit * 100 * contracts * 100) / 100,
        max_profit: payoff.max_profit,
        max_loss: payoff.max_loss,
        breakeven_low: payoff.breakeven_low,
        breakeven_high: payoff.breakeven_high,
        profit_zone: payoff.profit_zone,
        pop_heuristic: payoff.pop_heuristic,
        net_delta: netDelta,
        net_gamma: netGamma,
        net_theta: netTheta,
        net_vega: netVega,
      },
      mtm: mtm
        ? {
            cost_to_close_last: mtm.cost_to_close_last,
            cost_to_close_mid: mtm.cost_to_close_mid,
            cost_to_close: mtm.cost_to_close,
            unrealized_pnl: unrealizedPnl,
            unrealized_pnl_pct: unrealizedPct,
          }
        : null,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

function emptyQuote() {
  return {
    bid: null as number | null,
    ask: null as number | null,
    mid: null as number | null,
    last: null as number | null,
    delta: null as number | null,
    gamma: null as number | null,
    theta: null as number | null,
    vega: null as number | null,
    mid_iv: null as number | null,
  }
}
