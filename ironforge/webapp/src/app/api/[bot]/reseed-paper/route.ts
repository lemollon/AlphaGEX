/**
 * Re-base SPARK's PAPER (sandbox) ledger seed to the CURRENT live account
 * balance.
 *
 * Paper and sandbox are SEPARATE books. SPARK's paper account is a
 * self-contained ledger: its `starting_capital` is a one-time seed and its
 * balance then evolves only by paper P&L. The scanner no longer continuously
 * re-syncs that seed to live Tradier equity (see scanner.ts
 * loadConfigOverrides / syncPaperAccountCapital PRODUCTION_BOT guards), so this
 * endpoint is how an operator re-bases the seed to reality on demand — instead
 * of the old hardcoded $10,000 / capital_pct-scaled value.
 *
 * Model (matches the agreed design):
 *   seed (starting_capital) = live sandbox total_equity (100%, no capital_pct)
 *   current_balance         = seed + paper cumulative_pnl   (paper P&L preserved)
 *   buying_power            = current_balance - collateral_in_use
 *
 * Nothing is deleted — cumulative_pnl and the closed-position history are kept,
 * so this is a reconcile, not a reset.
 *
 * GET  /api/spark/reseed-paper              -> dry-run: live equity + before/after (safe).
 * POST /api/spark/reseed-paper?confirm=true -> apply.
 *
 * Scoped to the production bot (SPARK) only.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import { PRODUCTION_BOT, getAccountsForBot, getFullEquityForAccount } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

const SANDBOX = "COALESCE(account_type, 'sandbox') = 'sandbox'"

function guard(bot: string) {
  if (bot !== PRODUCTION_BOT) {
    return NextResponse.json(
      { error: `reseed-paper is only meaningful for the production bot: ${PRODUCTION_BOT}` },
      { status: 403 },
    )
  }
  return null
}

/** Read the active sandbox paper_account row for this dte_mode (most recent). */
async function readSandboxRow(bot: string, dte: string) {
  const rows = await dbQuery(
    `SELECT id, starting_capital, current_balance, cumulative_pnl,
            collateral_in_use, buying_power, high_water_mark
     FROM ${botTable(bot, 'paper_account')}
     WHERE is_active = TRUE AND dte_mode = '${escapeSql(dte)}' AND ${SANDBOX}
     ORDER BY id DESC LIMIT 1`,
  )
  if (rows.length === 0) return null
  const r = rows[0]
  return {
    id: int(r.id),
    starting_capital: num(r.starting_capital),
    current_balance: num(r.current_balance),
    cumulative_pnl: num(r.cumulative_pnl),
    collateral_in_use: num(r.collateral_in_use),
    buying_power: num(r.buying_power),
    high_water_mark: num(r.high_water_mark),
  }
}

/** Compute the post-reseed values from the live equity + existing paper P&L. */
function project(liveEquity: number, row: { cumulative_pnl: number; collateral_in_use: number; high_water_mark: number }) {
  const seed = Math.round(liveEquity * 100) / 100
  const newBalance = Math.round((seed + row.cumulative_pnl) * 100) / 100
  const newBp = Math.round((newBalance - row.collateral_in_use) * 100) / 100
  const newHwm = Math.max(row.high_water_mark, newBalance)
  return { seed, newBalance, newBp, newHwm }
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const g = guard(bot)
  if (g) return g
  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  try {
    const person = getAccountsForBot(bot)[0] ?? 'User'
    const liveEquity = await getFullEquityForAccount(person, 'sandbox')
    const row = await readSandboxRow(bot, dte)

    if (row == null) {
      return NextResponse.json(
        { error: `No active sandbox paper_account row for ${bot} (${dte}) — nothing to reseed.` },
        { status: 409 },
      )
    }
    if (liveEquity == null || liveEquity <= 0) {
      return NextResponse.json(
        {
          error: `Could not read live sandbox equity for '${person}' (Tradier unreachable or zero). Refusing to reseed.`,
          before: row,
        },
        { status: 502 },
      )
    }

    const { seed, newBalance, newBp, newHwm } = project(liveEquity, row)
    return NextResponse.json({
      dry_run: true,
      bot,
      dte_mode: dte,
      sandbox_account: person,
      live_equity: seed,
      before: row,
      after: {
        starting_capital: seed,
        current_balance: newBalance,
        buying_power: newBp,
        high_water_mark: newHwm,
        cumulative_pnl: row.cumulative_pnl, // unchanged — paper P&L preserved
      },
      model: 'starting_capital = live sandbox equity (100%); current_balance = seed + paper cumulative_pnl',
      instructions: 'POST ?confirm=true to apply. Paper P&L history is preserved (reconcile, not reset).',
    })
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : String(err) }, { status: 500 })
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const g = guard(bot)
  if (g) return g
  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  if (req.nextUrl.searchParams.get('confirm') !== 'true') {
    return NextResponse.json(
      { error: 'Refusing to apply without ?confirm=true — GET this URL first to preview.' },
      { status: 400 },
    )
  }

  try {
    const person = getAccountsForBot(bot)[0] ?? 'User'
    const liveEquity = await getFullEquityForAccount(person, 'sandbox')
    const before = await readSandboxRow(bot, dte)

    if (before == null) {
      return NextResponse.json(
        { error: `No active sandbox paper_account row for ${bot} (${dte}) — nothing to reseed.` },
        { status: 409 },
      )
    }
    if (liveEquity == null || liveEquity <= 0) {
      return NextResponse.json(
        {
          error: `Could not read live sandbox equity for '${person}' (Tradier unreachable or zero). Refusing to reseed.`,
          before,
        },
        { status: 502 },
      )
    }

    const { seed, newBalance, newBp, newHwm } = project(liveEquity, before)

    await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET starting_capital = $1,
           current_balance = $2,
           buying_power = $3,
           high_water_mark = $4,
           updated_at = NOW()
       WHERE id = $5`,
      [seed, newBalance, newBp, newHwm, before.id],
    )

    // Audit log (best-effort)
    try {
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
         VALUES ($1, $2, $3, $4)`,
        [
          'PAPER_RESEED',
          `Re-based SPARK paper (sandbox) seed to live balance: ` +
            `starting_capital $${before.starting_capital.toLocaleString()} → $${seed.toLocaleString()}, ` +
            `current_balance $${before.current_balance.toLocaleString()} → $${newBalance.toLocaleString()} ` +
            `(paper cumulative_pnl $${before.cumulative_pnl.toLocaleString()} preserved).`,
          JSON.stringify({
            event: 'paper_reseed',
            sandbox_account: person,
            live_equity: seed,
            before,
            after: {
              starting_capital: seed,
              current_balance: newBalance,
              buying_power: newBp,
              high_water_mark: newHwm,
            },
          }),
          dte,
        ],
      )
    } catch { /* audit log is best-effort */ }

    const after = await readSandboxRow(bot, dte)
    return NextResponse.json({
      bot,
      applied: true,
      sandbox_account: person,
      live_equity: seed,
      before,
      after,
      note: `Paper seed re-based to the live balance. The scanner will NOT re-sync it — ` +
            `paper now evolves only by its own P&L. Refresh /spark (Paper view).`,
    })
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : String(err) }, { status: 500 })
  }
}
