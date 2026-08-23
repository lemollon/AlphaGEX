/**
 * Create the PRODUCTION `{bot}_paper_account` row that no code path can create.
 *
 * 🚨 THE BUG THIS REPAIRS (2026-08-23). FLAME has been placing REAL Tradier
 * orders on 6YB71371 since 2026-08-20 (orders 142765167 and 142920961), and a
 * signed-in customer saw nothing. One missing row explains all of it:
 *
 *   `flame_paper_account` held exactly one production row —
 *   `person='Logan', dte_mode='2DTE', is_active=false`, untouched since
 *   2026-04-23. FLAME runs 0DTE now and its live account is composed in code as
 *   person 'Flame' (tradier.ts, flameProductionAccount). Nothing matched.
 *
 * Every auto-seed in scanner.ts hardcodes `account_type='sandbox'`, so a
 * production row has only ever existed if someone made one by hand. Without it:
 *
 *   - the entry collateral deduction and the close credit both UPDATE 0 rows,
 *     silently (Postgres does not consider that an error) — the +$21 settlement
 *     on 8/21 was never booked to any ledger;
 *   - production equity snapshots are written by looping over these same rows,
 *     so `{bot}_equity_snapshots` gained no production rows at all — no curve,
 *     no return, for the live account;
 *   - `live/summary.ts` reads `starting_capital` from this row, so
 *     `accountLinked` was false and the Live page told the owner their bot
 *     "isn't connected to your account yet — contact support".
 *
 * GET  /api/{bot}/seed-production-ledger
 *   Dry run. Shows the live Tradier balance, the production history already in
 *   the positions table, any existing rows, and exactly what would be inserted.
 *
 * POST /api/{bot}/seed-production-ledger?confirm=true
 *   Inserts one active production row reconciled to the broker:
 *     starting_capital = live total_equity − Σ realized_pnl(production, dte)
 *     current_balance  = starting_capital + Σ realized_pnl   (= live equity when flat)
 *     cumulative_pnl   = Σ realized_pnl of closed production positions
 *     collateral_in_use = Σ collateral_required of OPEN production positions
 *     total_trades     = count of closed production positions
 *   so the ledger agrees with both the broker AND the trade history that
 *   already happened, instead of restarting the curve from zero.
 *
 * IDEMPOTENT: refuses (409) if an active production row already exists for this
 * (person, dte_mode). Use reset-paper-account to rebase an existing one — this
 * route only fills a hole.
 *
 * Scoped to FLAME. SPARK's production rows come from ironforge_accounts and
 * already exist; SPARK2 is paper. Widening this to a bot whose production
 * identity is not env-credentialed would invent an owner name.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import {
  flameProductionAccount,
  getFlameProductionBalance,
  canReadProductionBalance,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

const SUPPORTED_BOTS = new Set(['flame'])

interface SeedPreview {
  bot: string
  dte_mode: string
  person: string | null
  account_id: string | null
  tradier: {
    total_equity: number | null
    option_buying_power: number | null
    reachable: boolean
    /** Where total_equity came from — an override must never read as a broker read. */
    source: 'tradier' | 'override' | 'unavailable'
    note?: string
  }
  existing_rows: Array<{
    id: number
    person: string | null
    dte_mode: string | null
    is_active: boolean
    starting_capital: number
    current_balance: number
    updated_at: string | null
  }>
  history: {
    closed_positions: number
    realized_pnl: number
    open_positions: number
    open_collateral: number
  }
  proposed: {
    starting_capital: number
    current_balance: number
    cumulative_pnl: number
    collateral_in_use: number
    buying_power: number
    total_trades: number
  } | null
  blocked_reason: string | null
}

/**
 * The production owner name, taken from the SAME composition the order path
 * uses. Reading it here rather than hardcoding 'Flame' is the whole point: if
 * that name ever changes, the seeded row follows it instead of silently
 * re-creating this bug under a new label.
 * requireArmed:false — repairing the ledger is a READ-side concern, and a
 * disarmed FLAME still owns the money it already traded.
 */
function productionPerson(bot: string): { person: string | null; accountId: string | null } {
  if (bot === 'flame') {
    const acct = flameProductionAccount({ requireArmed: false })
    return { person: acct?.name ?? null, accountId: acct?.cachedAccountId ?? null }
  }
  return { person: null, accountId: null }
}

async function gather(
  bot: string,
  dte: string,
  /**
   * Explicit operator override for the live equity — the same escape hatch
   * reset-paper-account already has. 🚨 Only reachable by typing a number into
   * the URL: the default path still refuses to seed a real-money ledger from a
   * guess, and the response labels the number `source: 'override'` so it can
   * never be mistaken for a broker read.
   *
   * Needed on 2026-08-23. Tradier's ACCOUNT endpoints for 6YB71371 began timing
   * out at 5000ms — quotes on the same host were fine, so it was neither the key
   * nor the network — which left the repair for a live customer-visibility bug
   * waiting on a third party with no way to proceed.
   */
  overrideEquity: number | null = null,
): Promise<SeedPreview> {
  const { person, accountId } = productionPerson(bot)

  const existing = await dbQuery(
    `SELECT id, person, dte_mode, is_active, starting_capital, current_balance, updated_at
     FROM ${botTable(bot, 'paper_account')}
     WHERE COALESCE(account_type, 'sandbox') = 'production'
     ORDER BY id`,
  )

  const hist = person
    ? await dbQuery(
        `SELECT
           COUNT(*) FILTER (WHERE status IN ('closed', 'expired')) AS closed_count,
           COALESCE(SUM(realized_pnl) FILTER (WHERE status IN ('closed', 'expired')), 0) AS realized,
           COUNT(*) FILTER (WHERE status = 'open') AS open_count,
           COALESCE(SUM(collateral_required) FILTER (WHERE status = 'open'), 0) AS open_collateral
         FROM ${botTable(bot, 'positions')}
         WHERE COALESCE(account_type, 'sandbox') = 'production'
           AND person = '${escapeSql(person)}'
           AND dte_mode = '${escapeSql(dte)}'`,
      )
    : []

  let equity: number | null = null
  let obp: number | null = null
  let note: string | undefined
  let equitySource: SeedPreview['tradier']['source'] = 'unavailable'
  if (overrideEquity != null) {
    equity = overrideEquity
    equitySource = 'override'
    note = 'Live equity was supplied by the operator — Tradier was NOT consulted for this number.'
  } else if (!canReadProductionBalance(bot)) {
    note =
      `${bot.toUpperCase()} has no live credentials on this service — ` +
      `TRADIER_${bot.toUpperCase()}_API_KEY / _ACCOUNT_ID are unset here. ` +
      `Arming env is PER-SERVICE; ask the process that prints [scanner].`
  } else {
    try {
      const det = bot === 'flame' ? await getFlameProductionBalance() : null
      equity = det?.total_equity ?? null
      obp = det?.option_buying_power ?? null
      if (equity == null) {
        note =
          'Tradier returned no total_equity for the live account — the balances endpoint is ' +
          'timing out or the key was rejected. Pass ?starting_capital=N (the account TOTAL ' +
          'EQUITY) to seed from a number you have verified yourself.'
      } else {
        equitySource = 'tradier'
      }
    } catch (err: unknown) {
      note = `Tradier balance read failed: ${err instanceof Error ? err.message : String(err)}`
    }
  }

  const realized = Math.round(num(hist[0]?.realized) * 100) / 100
  const openCollateral = Math.round(num(hist[0]?.open_collateral) * 100) / 100
  const closedCount = int(hist[0]?.closed_count)

  const activeDuplicate = existing.some(
    (r) =>
      (r.is_active === true || r.is_active === 'true') &&
      r.person === person &&
      r.dte_mode === dte,
  )

  let blocked: string | null = null
  if (!person) {
    blocked = `No production account is composed for ${bot} — cannot name the ledger owner.`
  } else if (activeDuplicate) {
    blocked =
      `An ACTIVE production row already exists for person='${person}', dte_mode='${dte}'. ` +
      `This route only fills a hole; use reset-paper-account to rebase an existing ledger.`
  } else if (equity == null) {
    blocked = note ?? 'Live balance unavailable — refusing to seed a ledger from a guess. Pass ?starting_capital=N to override.'
  }

  // starting_capital is the BASIS: what the account was worth before the trades
  // already recorded here. equity − Σrealized reproduces the same basis the
  // operator equity-curve route reports (rebase_source:"tradier"), so the two
  // surfaces cannot disagree about where the curve starts.
  const startingCapital = equity != null ? Math.round((equity - realized) * 100) / 100 : 0

  return {
    bot,
    dte_mode: dte,
    person,
    account_id: accountId,
    tradier: {
      total_equity: equity,
      option_buying_power: obp,
      reachable: equity != null,
      source: equitySource,
      note,
    },
    existing_rows: existing.map((r) => ({
      id: int(r.id),
      person: r.person ?? null,
      dte_mode: r.dte_mode ?? null,
      is_active: r.is_active === true || r.is_active === 'true',
      starting_capital: num(r.starting_capital),
      current_balance: num(r.current_balance),
      updated_at: r.updated_at ? new Date(r.updated_at).toISOString() : null,
    })),
    history: {
      closed_positions: closedCount,
      realized_pnl: realized,
      open_positions: int(hist[0]?.open_count),
      open_collateral: openCollateral,
    },
    proposed: blocked
      ? null
      : {
          starting_capital: startingCapital,
          current_balance: Math.round((startingCapital + realized) * 100) / 100,
          cumulative_pnl: realized,
          collateral_in_use: openCollateral,
          // Prefer the broker's real option buying power; fall back to equity
          // less committed collateral rather than inventing headroom.
          buying_power:
            obp != null
              ? Math.round(obp * 100) / 100
              : Math.round(((equity ?? 0) - openCollateral) * 100) / 100,
          total_trades: closedCount,
        },
    blocked_reason: blocked,
  }
}

/**
 * Read `?starting_capital=N`, the operator override for the live equity.
 *
 * The number is the account's TOTAL EQUITY, not the basis — realized P&L is
 * subtracted downstream, exactly as it would be from a Tradier read. Naming it
 * `starting_capital` matches reset-paper-account's existing parameter, so the
 * two repair routes take the same argument spelled the same way.
 */
function parseOverride(req: NextRequest): { value: number | null } | { error: NextResponse } {
  const raw = req.nextUrl.searchParams.get('starting_capital')
  if (raw == null) return { value: null }
  const n = parseFloat(raw)
  if (!Number.isFinite(n) || n <= 0) {
    return {
      error: NextResponse.json(
        {
          error:
            'starting_capital must be a positive number — the account TOTAL EQUITY, not the ' +
            'basis. Realized P&L is subtracted for you.',
        },
        { status: 400 },
      ),
    }
  }
  return { value: n }
}

export async function GET(req: NextRequest, { params }: { params: { bot: string } }) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (!SUPPORTED_BOTS.has(bot)) {
    return NextResponse.json(
      { error: `seed-production-ledger is only enabled for: ${Array.from(SUPPORTED_BOTS).join(', ')}` },
      { status: 403 },
    )
  }
  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  const override = parseOverride(req)
  if ('error' in override) return override.error

  try {
    const preview = await gather(bot, dte, override.value)
    return NextResponse.json({
      dry_run: true,
      ...preview,
      instructions:
        `POST /api/${bot}/seed-production-ledger?confirm=true to apply.` +
        (preview.tradier.reachable
          ? ''
          : ' Tradier is not answering — add &starting_capital=N (total equity) to override.'),
    })
  } catch (err: unknown) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    )
  }
}

export async function POST(req: NextRequest, { params }: { params: { bot: string } }) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (!SUPPORTED_BOTS.has(bot)) {
    return NextResponse.json(
      { error: `seed-production-ledger is only enabled for: ${Array.from(SUPPORTED_BOTS).join(', ')}` },
      { status: 403 },
    )
  }
  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  if (req.nextUrl.searchParams.get('confirm') !== 'true') {
    return NextResponse.json(
      { error: 'Refusing to write without ?confirm=true — GET this URL first to preview.' },
      { status: 400 },
    )
  }

  const override = parseOverride(req)
  if ('error' in override) return override.error

  try {
    const preview = await gather(bot, dte, override.value)
    if (preview.blocked_reason || !preview.proposed) {
      return NextResponse.json(
        { error: preview.blocked_reason ?? 'Cannot seed', preview },
        { status: preview.blocked_reason?.startsWith('An ACTIVE') ? 409 : 503 },
      )
    }
    const p = preview.proposed

    await dbExecute(
      `INSERT INTO ${botTable(bot, 'paper_account')}
         (starting_capital, current_balance, cumulative_pnl,
          collateral_in_use, buying_power, total_trades,
          high_water_mark, max_drawdown,
          is_active, dte_mode, person, account_type,
          created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, 0, TRUE, $8, $9, 'production', NOW(), NOW())`,
      [
        p.starting_capital,
        p.current_balance,
        p.cumulative_pnl,
        p.collateral_in_use,
        p.buying_power,
        p.total_trades,
        // High-water mark starts at the greater of basis and current value, so a
        // ledger seeded mid-drawdown does not report a fake 0% max drawdown.
        Math.max(p.starting_capital, p.current_balance),
        dte,
        preview.person,
      ],
    )

    try {
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode, person)
         VALUES ($1, $2, $3, $4, $5)`,
        [
          'PRODUCTION_LEDGER_SEED',
          `Seeded production paper_account for ${preview.person} (${dte}): ` +
            `basis $${p.starting_capital.toFixed(2)}, balance $${p.current_balance.toFixed(2)}, ` +
            `reconciled to ${preview.history.closed_positions} closed production trade(s) ` +
            `worth $${p.cumulative_pnl.toFixed(2)}. Equity source: ${preview.tradier.source}.`,
          JSON.stringify({
            event: 'production_ledger_seed',
            account_id: preview.account_id,
            equity_source: preview.tradier.source,
            ...p,
          }),
          dte,
          preview.person,
        ],
      )
    } catch { /* audit log is best-effort */ }

    return NextResponse.json({
      bot,
      applied: true,
      person: preview.person,
      dte_mode: dte,
      account_id: preview.account_id,
      seeded: p,
      live_equity: preview.tradier.total_equity,
      equity_source: preview.tradier.source,
      note:
        `Production ledger created. Collateral deductions and close credits now land, and the ` +
        `scanner will start writing production equity snapshots on its next cycle (the curve ` +
        `begins now — it does not backfill the ${preview.history.closed_positions} trade(s) ` +
        `already closed, whose P&L is carried in cumulative_pnl instead).`,
    })
  } catch (err: unknown) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    )
  }
}
