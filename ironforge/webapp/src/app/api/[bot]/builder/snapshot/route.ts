/**
 * Builder snapshot endpoint — the single data source for the `/spark`
 * IC Chart tab. Returns the LATEST IC position (open or closed) plus
 * everything the ported SpreadWorks components need to render:
 *
 *   - position         : strikes, expiration, contracts, entry credit,
 *                        plus status + close metadata when closed
 *   - legs             : per-leg Tradier quote + greeks for OPEN positions;
 *                        for closed positions, the legs are gone at the
 *                        broker so we return strikes + entry credits only
 *   - payoff           : expiration P&L curve + breakevens + max profit/loss
 *                        (pure math from strikes + entry credit — works for
 *                        both open and closed positions)
 *   - metrics          : aggregate credit/max/pop/net-greeks for MetricsBar
 *   - mtm              : live mark-to-market (unrealized P&L) — only when
 *                        the position is OPEN. For closed positions we
 *                        report realized_pnl via `closed` object instead.
 *   - closed           : close_price, close_time, close_reason, realized_pnl
 *                        (null when position is open)
 *   - spot_price       : current SPY quote (always, so candles stay current)
 *
 * When the bot has never traded in this scope, returns `{ position: null }`
 * so the UI can render a placeholder ("IC Chart renders when SPARK has
 * traded").
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
  getVerticalMarkToMarket,
  isConfigured,
  type LegQuoteWithGreeks,
} from '@/lib/tradier'
import {
  computeIcPayoff,
  computePutSpreadPayoff,
  computeVerticalDebitPayoff,
} from '@/lib/ic-payoff'

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
    // LATEST position for this bot + scope — open OR closed OR expired.
    // Operator-requested change (Commit G): the IC Chart should always
    // render, not just when a position is currently open. We prioritize
    // open positions first (ORDER BY status, then open_time DESC) so an
    // active trade wins over an older closed one. Falls through to the
    // most recent closed/expired if no open position exists.
    // BLAZE positions store vertical-debit columns (direction, long/short
    // strikes, debit, OCC leg symbols) alongside the IC schema. Selecting
    // them conditionally keeps the query valid for non-blaze tables which
    // don't have these columns.
    const blazeCols = bot === 'blaze'
      ? `, setup_type, direction, long_strike, short_strike, debit, long_symbol, short_symbol`
      : ''
    const rows = await dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike, put_credit,
              call_short_strike, call_long_strike, call_credit,
              contracts, spread_width, total_credit,
              underlying_at_entry, vix_at_entry,
              open_time, close_time, close_price, close_reason,
              realized_pnl, status,
              COALESCE(account_type, 'sandbox') AS account_type,
              person${blazeCols}
       FROM ${botTable(bot, 'positions')}
       WHERE 1=1 ${dteFilter} ${accountTypeFilter}
       ORDER BY
         CASE WHEN status = 'open' THEN 0 ELSE 1 END,
         open_time DESC
       LIMIT 1`,
    )
    if (rows.length === 0) {
      return NextResponse.json({ position: null, tradier_connected: isConfigured() })
    }

    const r = rows[0]
    const isOpen = r.status === 'open'
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
    // FLAME is moving from IC to Put Credit Spread. For the put-spread
    // view we use just the put-side credit (stored separately in
    // flame_positions.put_credit). For SPARK/INFERNO (IC) we keep the
    // full entry credit.
    const putCredit = num(r.put_credit) || 0
    const isPutCreditSpread = bot === 'flame'
    // BLAZE is a 2-leg vertical debit spread (long_strike, short_strike,
    // debit, direction='call'|'put'). The IC schema's put_*/call_* columns
    // hold zeros for the unused side per blaze/db.ts insert logic, so the
    // IC payoff math would compute garbage — branch into a dedicated
    // vertical-debit code path that uses canonical columns directly.
    const blazeDirection: 'call' | 'put' | null = bot === 'blaze'
      ? (r.direction === 'call' || r.direction === 'put' ? r.direction : null)
      : null
    const isVerticalDebit = blazeDirection != null
    const blazeLongStrike = isVerticalDebit ? num(r.long_strike) : 0
    const blazeShortStrike = isVerticalDebit ? num(r.short_strike) : 0
    const blazeDebit = isVerticalDebit ? num(r.debit) : 0
    // "Effective" entry credit + spread width: what the payoff, MTM,
    // metrics, and realized-% calcs use. Derived once here and reused
    // throughout the route so all numbers reconcile. For BLAZE, we
    // represent debit as a NEGATIVE credit so MetricsBar's sign-based
    // "NET CREDIT" / "NET DEBIT" label switches correctly.
    const effectiveEntryCredit = isVerticalDebit
      ? -blazeDebit
      : isPutCreditSpread
        ? (putCredit > 0 ? putCredit : entryCredit)
        : entryCredit
    const effectiveSpreadWidth = isVerticalDebit
      ? Math.abs(blazeLongStrike - blazeShortStrike)
      : isPutCreditSpread
        ? (ps - pl)
        : (num(r.spread_width) || Math.min(ps - pl, cl - cs))

    // BLAZE positions store the OCC leg symbols directly in long_symbol /
    // short_symbol; IC bots derive them from strikes via buildOccSymbol.
    const blazeLongSymbol = isVerticalDebit ? String(r.long_symbol || '') : ''
    const blazeShortSymbol = isVerticalDebit ? String(r.short_symbol || '') : ''
    const occ = isVerticalDebit
      ? {
          long_put: '',
          short_put: '',
          short_call: '',
          long_call: '',
        }
      : {
          long_put: buildOccSymbol(ticker, expiration, pl, 'P'),
          short_put: buildOccSymbol(ticker, expiration, ps, 'P'),
          short_call: buildOccSymbol(ticker, expiration, cs, 'C'),
          long_call: buildOccSymbol(ticker, expiration, cl, 'C'),
        }

    // Live Tradier fetches. For CLOSED positions the legs are gone at the
    // broker, so quote/MTM calls would return zeros or 404 and pollute the
    // display — skip them entirely in that case. We still fetch the
    // underlying (spot) quote because candles + spot remain relevant
    // context regardless of whether the position is open.
    //
    // BLAZE branches: quotes come from the stored leg symbols, and MTM
    // uses getVerticalMarkToMarket (returns value_to_close instead of
    // cost_to_close — debit spreads are bought, not sold).
    const blazeSymbols = isVerticalDebit && blazeLongSymbol && blazeShortSymbol
      ? [blazeLongSymbol, blazeShortSymbol]
      : []
    const blazeVerticalSpreadWidth = isVerticalDebit
      ? Math.abs(blazeLongStrike - blazeShortStrike)
      : 0
    const [quotesMap, mtm, blazeMtm, underlyingQuote] = await Promise.all([
      isOpen && !isVerticalDebit
        ? getBatchOptionQuotesWithGreeks(Object.values(occ)).catch(() => ({}))
        : isOpen && isVerticalDebit && blazeSymbols.length === 2
          ? getBatchOptionQuotesWithGreeks(blazeSymbols).catch(() => ({}))
          : Promise.resolve({}),
      isOpen && !isVerticalDebit
        ? getIcMarkToMarket(ticker, expiration, ps, pl, cs, cl, entryCredit).catch(() => null)
        : Promise.resolve(null),
      isOpen && isVerticalDebit && blazeSymbols.length === 2
        ? getVerticalMarkToMarket(blazeLongSymbol, blazeShortSymbol, blazeVerticalSpreadWidth, ticker).catch(() => null)
        : Promise.resolve(null),
      getQuote(ticker).catch(() => null),
    ]) as [
      Record<string, LegQuoteWithGreeks>,
      Awaited<ReturnType<typeof getIcMarkToMarket>>,
      Awaited<ReturnType<typeof getVerticalMarkToMarket>>,
      Awaited<ReturnType<typeof getQuote>>,
    ]

    const spotPrice = underlyingQuote?.last
      ?? mtm?.spot_price
      ?? blazeMtm?.spot_price
      ?? num(r.underlying_at_entry)

    // Legs: BLAZE returns 2 legs (long + short, both same direction);
    // FLAME returns 2 put legs; IC bots return all 4.
    const blazeLegType: 'P' | 'C' = blazeDirection === 'call' ? 'C' : 'P'
    const legs: LegOut[] = isVerticalDebit
      ? [
          { role: blazeLegType === 'C' ? 'long_call' : 'long_put',  strike: blazeLongStrike,  type: blazeLegType, occ_symbol: blazeLongSymbol,  ...emptyQuote() },
          { role: blazeLegType === 'C' ? 'short_call' : 'short_put', strike: blazeShortStrike, type: blazeLegType, occ_symbol: blazeShortSymbol, ...emptyQuote() },
        ]
      : isPutCreditSpread
        ? [
            { role: 'long_put', strike: pl, type: 'P', occ_symbol: occ.long_put, ...emptyQuote() },
            { role: 'short_put', strike: ps, type: 'P', occ_symbol: occ.short_put, ...emptyQuote() },
          ]
        : [
            { role: 'long_put', strike: pl, type: 'P', occ_symbol: occ.long_put, ...emptyQuote() },
            { role: 'short_put', strike: ps, type: 'P', occ_symbol: occ.short_put, ...emptyQuote() },
            { role: 'short_call', strike: cs, type: 'C', occ_symbol: occ.short_call, ...emptyQuote() },
            { role: 'long_call', strike: cl, type: 'C', occ_symbol: occ.long_call, ...emptyQuote() },
          ]
    if (isOpen) {
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
    }

    // Bot config — load stop_loss_pct for the matched account_type so we can
    // compute the realistic SL-bounded max loss alongside the theoretical
    // wing-breach max_loss. Loaded scoped to the position's account_type
    // (production rows can have different sl_mult than sandbox).
    const cfgScope = r.account_type === 'production' ? 'production' : 'sandbox'
    let slMult: number | null = null
    try {
      const cfgRows = await dbQuery(
        `SELECT stop_loss_pct
         FROM ${botTable(bot, 'config')}
         WHERE COALESCE(account_type, 'sandbox') IN ('${escapeSql(cfgScope)}', 'sandbox')
           ${dteFilter}
         ORDER BY CASE WHEN COALESCE(account_type, 'sandbox') = '${escapeSql(cfgScope)}' THEN 0 ELSE 1 END
         LIMIT 1`,
      )
      const slPct = num(cfgRows[0]?.stop_loss_pct)
      if (slPct > 0) slMult = slPct / 100
    } catch { /* no config row — leave slMult null and let UI fall back */ }

    // Payoff math is pure — works identically for open or closed positions.
    // BLAZE uses the vertical-debit payoff (direction + long/short + debit);
    // FLAME uses the 2-leg put-credit-spread payoff (credit = put-side only);
    // SPARK/INFERNO keep the 4-leg IC payoff (credit = total credit).
    const payoff = isVerticalDebit
      ? computeVerticalDebitPayoff(
          blazeDirection as 'call' | 'put',
          blazeLongStrike,
          blazeShortStrike,
          blazeDebit,
          contracts,
          spotPrice,
        )
      : isPutCreditSpread
        ? computePutSpreadPayoff(
            { putLong: pl, putShort: ps },
            effectiveEntryCredit,
            contracts,
            spotPrice,
          )
        : computeIcPayoff(
            { putLong: pl, putShort: ps, callShort: cs, callLong: cl },
            effectiveEntryCredit,
            contracts,
            spotPrice,
          )

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

    // MTM-derived unrealized P&L — only meaningful when the position is open.
    // For FLAME (put-credit-spread view), derive put-spread cost-to-close
    // from the 2 put leg quotes already fetched. Buy back short put (pay
    // ask), sell long put (receive bid): cost = short_put.ask − long_put.bid.
    // If either leg quote is missing, fall back to mid. Used in place of
    // the full IC MTM so the unrealized P&L matches the put-spread payoff.
    let putSpreadMtm: { last: number | null; mid: number | null; bidAsk: number | null } | null = null
    if (isPutCreditSpread && isOpen) {
      const psQ = quotesMap[occ.short_put]
      const plQ = quotesMap[occ.long_put]
      if (psQ && plQ) {
        const bidAsk = (psQ.ask != null && plQ.bid != null) ? psQ.ask - plQ.bid : null
        const mid = (psQ.mid != null && plQ.mid != null) ? psQ.mid - plQ.mid : null
        const last = (psQ.last != null && plQ.last != null && psQ.last > 0 && plQ.last > 0)
          ? psQ.last - plQ.last : null
        putSpreadMtm = { last, mid, bidAsk }
      }
    }

    let unrealizedPnl: number | null = null
    let unrealizedPct: number | null = null
    if (isOpen) {
      if (isVerticalDebit) {
        // Vertical debit: P&L = (value_to_close − debit) × 100 × contracts.
        // We BOUGHT the spread, so closing it is a SELL at value_to_close.
        const valueLast = blazeMtm?.value_to_close_last ?? blazeMtm?.value_to_close
        if (valueLast != null && Number.isFinite(valueLast)) {
          unrealizedPnl = Math.round((valueLast - blazeDebit) * 100 * contracts * 100) / 100
          if (blazeDebit > 0) {
            unrealizedPct = Math.round(((valueLast - blazeDebit) / blazeDebit) * 10000) / 100
          }
        }
      } else {
        // Choose cost-basis source per strategy. For FLAME use the put-spread
        // MTM derived above; for IC bots keep the existing getIcMarkToMarket
        // output.
        const costBasis = isPutCreditSpread
          ? (putSpreadMtm?.last ?? putSpreadMtm?.mid ?? putSpreadMtm?.bidAsk)
          : (mtm?.cost_to_close_last ?? mtm?.cost_to_close_mid)
        if (costBasis != null && Number.isFinite(costBasis)) {
          unrealizedPnl = Math.round((effectiveEntryCredit - costBasis) * 100 * contracts * 100) / 100
          if (effectiveEntryCredit > 0) {
            unrealizedPct = Math.round(((effectiveEntryCredit - costBasis) / effectiveEntryCredit) * 10000) / 100
          }
        }
      }
    }

    // Closed-position metadata — null when open. For BLAZE (debit) the
    // capital-at-risk denominator is the debit paid (positive value), so
    // we use |effectiveEntryCredit| to avoid the sign-flip that would
    // otherwise mis-render a winning trade as a negative percent.
    const realizedPnlDenom = Math.abs(effectiveEntryCredit) * 100 * contracts
    const closed = !isOpen
      ? {
          status: r.status as string,
          close_price: r.close_price != null ? num(r.close_price) : null,
          close_time: r.close_time ? new Date(r.close_time).toISOString() : null,
          close_reason: r.close_reason || null,
          realized_pnl: r.realized_pnl != null ? num(r.realized_pnl) : null,
          realized_pnl_pct: (r.realized_pnl != null && realizedPnlDenom > 0)
            ? Math.round((num(r.realized_pnl) / realizedPnlDenom) * 10000) / 100
            : null,
        }
      : null

    // BLAZE returns a single directional pair of strikes (long + short);
    // the unused IC side is null'd so the chart renders only those two
    // lines. FLAME nulls the call side for the same reason.
    const respPutLong = isVerticalDebit
      ? (blazeDirection === 'put' ? blazeLongStrike : null)
      : pl
    const respPutShort = isVerticalDebit
      ? (blazeDirection === 'put' ? blazeShortStrike : null)
      : ps
    const respCallShort = isVerticalDebit
      ? (blazeDirection === 'call' ? blazeShortStrike : null)
      : (isPutCreditSpread ? null : cs)
    const respCallLong = isVerticalDebit
      ? (blazeDirection === 'call' ? blazeLongStrike : null)
      : (isPutCreditSpread ? null : cl)
    return NextResponse.json({
      tradier_connected: isConfigured(),
      strategy_type: isVerticalDebit
        ? `vertical_debit_${blazeDirection}`
        : isPutCreditSpread ? 'put_credit_spread' : 'iron_condor',
      position: {
        position_id: r.position_id,
        ticker,
        expiration,
        put_long_strike: respPutLong,
        put_short_strike: respPutShort,
        call_short_strike: respCallShort,
        call_long_strike: respCallLong,
        contracts,
        entry_credit: effectiveEntryCredit,
        spread_width: effectiveSpreadWidth,
        underlying_at_entry: num(r.underlying_at_entry),
        vix_at_entry: num(r.vix_at_entry),
        open_time: r.open_time || null,
        account_type: r.account_type,
        person: r.person || null,
        status: r.status as string,
        is_open: isOpen,
        ...(isVerticalDebit
          ? {
              direction: blazeDirection,
              long_strike: blazeLongStrike,
              short_strike: blazeShortStrike,
              debit: blazeDebit,
              setup_type: r.setup_type || null,
            }
          : {}),
      },
      spot_price: spotPrice,
      legs,
      payoff,
      metrics: {
        net_credit: Math.round(effectiveEntryCredit * 100 * contracts * 100) / 100,
        max_profit: payoff.max_profit,
        // True max loss: full wing breach at expiration = collateral at risk.
        // This is the headline number — stops can fail (gap moves, hung
        // scanner, slippage 10–50% past trigger) so the operator's risk view
        // must anchor on the worst case the position can realize.
        max_loss_at_expiry: payoff.max_loss,
        // Configured stop-loss target: if the stop fires at sl_mult × credit,
        // dollar loss = (sl_mult − 1) × credit_dollars. NOT a max-loss claim —
        // surfaced as a secondary "where the stop sits" indicator only.
        // Null when no config row exists yet (cold start).
        stop_target_loss: slMult != null
          ? Math.round((slMult - 1) * effectiveEntryCredit * 100 * contracts * -100) / 100
          : null,
        sl_mult: slMult,
        // Legacy alias of max_loss_at_expiry (wing-breach max). Kept for
        // backward compat with any older clients.
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
      mtm: isOpen && isVerticalDebit && blazeMtm
        ? {
            // For verticals we report value_to_close (what you'd RECEIVE
            // closing the SOLD-back debit spread) — semantically the
            // counterpart to cost_to_close on a credit spread.
            value_to_close_last: blazeMtm.value_to_close_last,
            value_to_close_mid: blazeMtm.value_to_close_mid,
            value_to_close: blazeMtm.value_to_close,
            unrealized_pnl: unrealizedPnl,
            unrealized_pnl_pct: unrealizedPct,
          }
        : isOpen && mtm
          ? {
              cost_to_close_last: mtm.cost_to_close_last,
              cost_to_close_mid: mtm.cost_to_close_mid,
              cost_to_close: mtm.cost_to_close,
              unrealized_pnl: unrealizedPnl,
              unrealized_pnl_pct: unrealizedPct,
            }
          : null,
      closed,
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
