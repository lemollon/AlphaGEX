import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, num, int, escapeSql } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET  /api/flare/fix-collateral
 *   Diagnose stranded FLARE positions: open rows whose expiration date has
 *   already passed (in Central Time). Shows the terminal-payoff calculation
 *   that the POST will apply.
 *
 * POST /api/flare/fix-collateral
 *   Reconcile the same rows:
 *     - settle each spread against SPY's spot at <= 15:00 CT on its expiration
 *       date (pulled from flare_gex_history)
 *     - set status='expired', close_price = payoff, realized_pnl = (payoff -
 *       debit) * 100 * contracts, close_reason='eod_expiry_reconcile'
 *     - re-sum the paper_account fields from the reconciled rows
 *
 * FLARE positions are vertical debit spreads, not iron condors, so the IC
 * fix-collateral route under [bot]/ doesn't apply.
 */

type StaleRow = {
  id: number
  position_id: string
  setup_type: string
  direction: string
  long_strike: number
  short_strike: number
  debit: number
  contracts: number
  expiration: string  // YYYY-MM-DD
  open_time_ct: string
  account_type: string | null
}

/** Look up SPY's settlement spot for a 0DTE expiration date (<= 15:00 CT). */
async function lookupSettleSpot(expiration: string): Promise<{ spot: number; source: string } | null> {
  const rows = await dbQuery(
    `SELECT spot_price
       FROM flare_gex_history
      WHERE (snapshot_time AT TIME ZONE 'America/Chicago')::date = DATE '${escapeSql(expiration)}'
        AND (snapshot_time AT TIME ZONE 'America/Chicago')::time <= '15:00:00'
      ORDER BY snapshot_time DESC
      LIMIT 1`,
  )
  if (rows.length && rows[0].spot_price != null) {
    return { spot: num(rows[0].spot_price), source: 'flare_gex_history@<=15:00CT' }
  }
  // Fallback: blaze_gex_history (same SPY feed, different bot's snapshot stream)
  const fb = await dbQuery(
    `SELECT spot_price
       FROM blaze_gex_history
      WHERE (snapshot_time AT TIME ZONE 'America/Chicago')::date = DATE '${escapeSql(expiration)}'
        AND (snapshot_time AT TIME ZONE 'America/Chicago')::time <= '15:00:00'
      ORDER BY snapshot_time DESC
      LIMIT 1`,
  )
  if (fb.length && fb[0].spot_price != null) {
    return { spot: num(fb[0].spot_price), source: 'blaze_gex_history@<=15:00CT' }
  }
  return null
}

/**
 * Terminal payoff per share for a vertical debit spread at expiration.
 * - put debit: long_strike > short_strike; payoff = max(0, min(width, long_strike - spy))
 * - call debit: long_strike < short_strike; payoff = max(0, min(width, spy - long_strike))
 */
function terminalPayoff(direction: string, long_strike: number, short_strike: number, spy: number): number {
  const width = Math.abs(long_strike - short_strike)
  const inner = direction === 'put' ? (long_strike - spy) : (spy - long_strike)
  return Math.max(0, Math.min(width, inner))
}

async function loadStaleRows(): Promise<StaleRow[]> {
  // A FLARE position is reconcilable when it can no longer trade:
  //   - expiration is before today's CT date (any stranded prior-day row), OR
  //   - expiration is today AND the CT time is past 15:00 (0DTE has settled).
  const rows = await dbQuery(
    `SELECT id, position_id, setup_type, direction,
            long_strike, short_strike, debit, contracts, expiration,
            (open_time AT TIME ZONE 'America/Chicago')::timestamp::text AS open_ct,
            account_type
       FROM flare_positions
      WHERE status = 'open'
        AND (
          expiration < (NOW() AT TIME ZONE 'America/Chicago')::date
          OR (
            expiration = (NOW() AT TIME ZONE 'America/Chicago')::date
            AND (NOW() AT TIME ZONE 'America/Chicago')::time > TIME '15:00:00'
          )
        )
      ORDER BY expiration, open_time`,
  )
  return rows.map(r => ({
    id: int(r.id),
    position_id: String(r.position_id),
    setup_type: String(r.setup_type),
    direction: String(r.direction),
    long_strike: num(r.long_strike),
    short_strike: num(r.short_strike),
    debit: num(r.debit),
    contracts: int(r.contracts),
    expiration: String(r.expiration || '').slice(0, 10),
    open_time_ct: String(r.open_ct || ''),
    account_type: r.account_type ? String(r.account_type) : null,
  }))
}

export async function GET(_req: NextRequest) {
  try {
    const stale = await loadStaleRows()

    // Resolve settle spots per unique expiration date.
    const expDates = Array.from(new Set(stale.map(r => r.expiration)))
    const settleByExp: Record<string, { spot: number; source: string } | null> = {}
    for (const d of expDates) {
      settleByExp[d] = await lookupSettleSpot(d)
    }

    const proposed = stale.map(r => {
      const s = settleByExp[r.expiration]
      const spy = s?.spot ?? null
      const payoff = spy != null ? terminalPayoff(r.direction, r.long_strike, r.short_strike, spy) : null
      const realized_pnl = payoff != null
        ? Math.round((payoff - r.debit) * 100 * r.contracts * 100) / 100
        : null
      return {
        ...r,
        spy_settle: spy,
        spy_settle_source: s?.source ?? null,
        terminal_payoff_per_share: payoff != null ? Math.round(payoff * 10000) / 10000 : null,
        proposed_realized_pnl: realized_pnl,
      }
    })

    const totalProposedPnl = proposed.reduce(
      (acc, r) => acc + (r.proposed_realized_pnl ?? 0),
      0,
    )

    return NextResponse.json({
      bot: 'FLARE',
      stale_count: stale.length,
      settles: settleByExp,
      proposed,
      total_proposed_realized_pnl: Math.round(totalProposedPnl * 100) / 100,
      healthy: stale.length === 0,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function POST(_req: NextRequest) {
  try {
    const stale = await loadStaleRows()
    const actions: string[] = []
    const settleByExp: Record<string, { spot: number; source: string } | null> = {}

    for (const r of stale) {
      if (!(r.expiration in settleByExp)) {
        settleByExp[r.expiration] = await lookupSettleSpot(r.expiration)
      }
      const s = settleByExp[r.expiration]
      if (!s) {
        actions.push(`SKIP ${r.position_id}: no SPY spot for expiration ${r.expiration}`)
        continue
      }
      const payoff = terminalPayoff(r.direction, r.long_strike, r.short_strike, s.spot)
      const realized_pnl = Math.round((payoff - r.debit) * 100 * r.contracts * 100) / 100
      const close_price = Math.round(payoff * 10000) / 10000

      const rowsAffected = await dbExecute(
        `UPDATE flare_positions
            SET status = 'expired',
                close_time = NOW(),
                close_price = ${close_price},
                realized_pnl = ${realized_pnl},
                close_reason = 'eod_expiry_reconcile',
                exit_reason = 'EXPIRED',
                updated_at = NOW()
          WHERE id = ${r.id}
            AND status = 'open'`,
      )
      if (rowsAffected === 0) {
        actions.push(`SKIP ${r.position_id}: already closed by another process`)
        continue
      }
      actions.push(
        `Expired ${r.position_id}: ${r.direction} ${r.long_strike}/${r.short_strike} exp=${r.expiration} ` +
        `spy=${s.spot} payoff=${close_price} pnl=$${realized_pnl.toFixed(2)}`,
      )
    }

    // Re-sum paper_account from canonical row state.
    const acct = await dbQuery(
      `SELECT COALESCE(starting_capital, 10000) AS starting_capital
         FROM flare_paper_account
        WHERE is_active = TRUE
        ORDER BY id DESC LIMIT 1`,
    )
    const startingCapital = num(acct[0]?.starting_capital) || 10000

    const pnlAgg = await dbQuery(
      `SELECT COALESCE(SUM(realized_pnl), 0) AS total_pnl,
              COUNT(*)                       AS total_trades
         FROM flare_positions
        WHERE status IN ('closed', 'expired')
          AND realized_pnl IS NOT NULL`,
    )
    const collAgg = await dbQuery(
      `SELECT COALESCE(SUM(collateral_required), 0) AS total_collateral
         FROM flare_positions
        WHERE status = 'open'`,
    )

    const actualPnl = num(pnlAgg[0]?.total_pnl)
    const actualTrades = int(pnlAgg[0]?.total_trades)
    const actualCollateral = num(collAgg[0]?.total_collateral)
    const expectedBalance = Math.round((startingCapital + actualPnl) * 100) / 100
    const correctBp = Math.round((expectedBalance - actualCollateral) * 100) / 100

    await dbExecute(
      `UPDATE flare_paper_account
          SET current_balance = ${expectedBalance},
              cumulative_pnl  = ${actualPnl},
              collateral_in_use = ${actualCollateral},
              buying_power = ${correctBp},
              total_trades = ${actualTrades},
              high_water_mark = GREATEST(COALESCE(high_water_mark, 0), ${expectedBalance}),
              updated_at = NOW()
        WHERE is_active = TRUE`,
    )

    return NextResponse.json({
      bot: 'FLARE',
      stale_closed: actions.filter(a => a.startsWith('Expired')).length,
      reconciled: {
        balance: expectedBalance,
        cumulative_pnl: actualPnl,
        collateral_in_use: actualCollateral,
        buying_power: correctBp,
        total_trades: actualTrades,
      },
      actions,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
