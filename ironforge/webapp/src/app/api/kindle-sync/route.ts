/**
 * KINDLE → real-account reconcile.
 *
 * GET  /api/kindle-sync  → preview: shows the real 6YB70795 balance + what would change.
 * POST /api/kindle-sync  → apply: clears KINDLE's PAPER position records and sets the
 *                          paper-ledger (starting_capital/balance/buying_power) to the
 *                          live account's equity, so the /kindle dashboard mirrors the
 *                          real Tradier account.
 *
 * Safety: writes ONLY to kindle_* tables. The DELETE is scoped to NON-production
 * rows so any real production position (account_type='production') is preserved.
 * Reads the live balance from TRADIER_KINDLE_* env (never the DB). KINDLE is paused;
 * this changes dashboard display only, never places an order.
 */
import { NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable } from '@/lib/db'
import { getTradierBalanceDetail } from '@/lib/tradier'

export const dynamic = 'force-dynamic'
const PROD = 'https://api.tradier.com/v1'

async function realBalance() {
  const key = process.env.TRADIER_KINDLE_API_KEY
  const acct = process.env.TRADIER_KINDLE_ACCOUNT_ID
  if (!key || !acct) return { error: 'TRADIER_KINDLE_API_KEY / TRADIER_KINDLE_ACCOUNT_ID not set' }
  const bal = await getTradierBalanceDetail(key, acct, PROD)
  if (!bal || bal.total_equity == null) {
    return { error: 'Could not read the live account balance (invalid creds or Tradier error)' }
  }
  return {
    account_id_masked: acct.length > 4 ? `${acct.slice(0, 3)}***${acct.slice(-2)}` : '***',
    total_equity: bal.total_equity,
    option_buying_power: bal.option_buying_power ?? bal.total_equity,
  }
}

export async function GET() {
  const rb = await realBalance()
  if ('error' in rb) return NextResponse.json({ ok: false, ...rb })
  const paper = await dbQuery(
    `SELECT person, account_type, starting_capital, current_balance, buying_power
     FROM ${botTable('kindle', 'paper_account')}`,
  )
  const openPaper = await dbQuery(
    `SELECT COUNT(*) AS cnt FROM ${botTable('kindle', 'positions')}
     WHERE COALESCE(account_type,'sandbox') <> 'production'`,
  )
  return NextResponse.json({
    ok: true,
    preview: true,
    real_account: rb,
    current_kindle_paper_account: paper,
    paper_positions_to_clear: Number((openPaper[0] as { cnt: number })?.cnt ?? 0),
    note: 'POST to apply: clears paper positions and sets the ledger to the real equity.',
  })
}

export async function POST() {
  const rb = await realBalance()
  if ('error' in rb) return NextResponse.json({ ok: false, ...rb }, { status: 502 })
  const equity = rb.total_equity
  const obp = rb.option_buying_power

  // Clear KINDLE paper positions only (preserve any real production position).
  await dbExecute(
    `DELETE FROM ${botTable('kindle', 'positions')}
     WHERE COALESCE(account_type,'sandbox') <> 'production'`,
  )
  // Clear stale equity snapshots (old $10,000-base rows) so the intraday equity
  // curve rebuilds from the correct ~$490 baseline on the next scan cycle.
  await dbExecute(`DELETE FROM ${botTable('kindle', 'equity_snapshots')}`)
  // Reset the paper ledger to mirror the live account.
  await dbExecute(
    `UPDATE ${botTable('kindle', 'paper_account')}
       SET starting_capital = $1,
           current_balance   = $1,
           cumulative_pnl    = 0,
           collateral_in_use = 0,
           buying_power      = $2,
           high_water_mark   = $1,
           max_drawdown      = 0,
           total_trades      = 0,
           updated_at        = NOW()`,
    [equity, obp],
  )

  return NextResponse.json({
    ok: true,
    applied: true,
    synced_to: rb,
    message: `KINDLE ledger reset to the live account: $${equity} equity, $${obp} buying power, paper positions cleared. Dashboard now mirrors 6YB***95.`,
  })
}
