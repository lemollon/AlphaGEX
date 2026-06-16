/**
 * Reset FLAME's paper ledger to mirror the Tradier User sandbox account.
 *
 * Why this exists: `flame_paper_account` accumulated multiple active rows
 * (starting_capital = $10K vs $3,840) and `flame_positions` carried 30
 * historical trades summing to −$31,266 realized. The dashboard's
 * status API picks `ORDER BY id DESC LIMIT 1`, so displayed balance
 * flipped between −$21,266 and +$3,512 non-deterministically. Meanwhile
 * the real Tradier User sandbox shows ~$70K and 0 open positions. This
 * endpoint reconciles the ledger to match Tradier reality.
 *
 * GET /api/flame/reset-paper-account
 *   Dry-run. Shows current paper_account rows, FLAME position counts,
 *   Tradier User sandbox total_equity, and what the reset would do.
 *   Safe to call anytime.
 *
 * POST /api/flame/reset-paper-account?confirm=true
 *   Applies the reset:
 *     1. Archive all non-open FLAME positions by setting
 *        dte_mode='ARCHIVED_2DTE' so their realized_pnl stops being
 *        summed into status/performance/equity-curve. Data persists and
 *        the rename is reversible.
 *     2. Force-close any open FLAME positions (status='closed',
 *        realized_pnl=0, close_reason='paper_reset'). There shouldn't
 *        be any right now, but guard against it.
 *     3. Mark all flame_paper_account rows is_active=false.
 *     4. INSERT one fresh active row with
 *        starting_capital = current_balance = Tradier User total_equity,
 *        cumulative_pnl = 0, collateral_in_use = 0.
 *
 * Optional query param `starting_capital=N` overrides the Tradier read
 * and uses N instead. Useful if Tradier is unreachable or you want a
 * specific value (e.g. after manually resetting Tradier sandbox to $100K).
 *
 * SPARK (the live production bot) is supported with extra safety:
 *   - The day-1 seed comes from SPARK's REAL production balance
 *     (total_cash → total_equity), NOT the sandbox User account.
 *   - The reset REFUSES if SPARK holds any open live position at Tradier,
 *     or any open row in the spark ledger. It never force-closes on the
 *     production bot (that would orphan a real broker position). Run it
 *     only on a flat, settled book — i.e. after the close, so the next
 *     session opens clean as "day 1".
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode, CT_TODAY } from '@/lib/db'
import {
  getSandboxAccountBalances,
  getProductionAccountsForBot,
  getProductionPauseState,
  getTradierBalanceDetail,
  getSandboxAccountPositions,
  PRODUCTION_BOT,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

// FLAME: reconcile to Tradier sandbox equity. FLARE: hard reset to a fixed
// paper base (pass ?starting_capital=10000) after the 2026-06-04 blow-up;
// archives the old -$47k tape via dte_mode rename so the equity curve restarts.
// SPARK: live production bot — seeds from real production cash, refuses on an open book.
const SUPPORTED_BOTS = new Set(['flame', 'flare', 'spark'])
const ARCHIVED_SUFFIX = 'ARCHIVED_'

interface ResetPreview {
  bot: string
  dte_mode: string
  tradier: {
    user_total_equity: number | null
    source: 'tradier' | 'production' | 'override' | 'unavailable'
    note?: string
  }
  // Present only for the live production bot (SPARK): the real broker book.
  live?: {
    paused: boolean
    account_name: string | null
    total_cash: number | null
    total_equity: number | null
    open_position_count: number
    open_symbols: string[]
  }
  current: {
    paper_account_rows: Array<{
      id: number
      is_active: boolean
      starting_capital: number
      current_balance: number
      cumulative_pnl: number
      account_type: string | null
      updated_at: string | null
    }>
    open_positions: number
    closed_positions: number
    total_realized_pnl: number
  }
  proposed: {
    action: string
    archive_dte_mode: string
    new_starting_capital: number
    new_balance: number
    new_cumulative_pnl: number
  }
}

// For the live production bot (SPARK) the paper (sandbox) and live (production)
// ledgers coexist in the same tables under the same dte_mode, separated only by
// account_type. A "reset" must touch ONLY the production ledger, or it clobbers
// the paper ledger too. Paper-only bots have no production rows, so this is a
// no-op for them.
function acctScope(bot: string): string {
  return bot === PRODUCTION_BOT
    ? " AND COALESCE(account_type, 'sandbox') = 'production'"
    : ''
}

async function gatherState(
  bot: string,
  dte: string,
  overrideCapital: number | null,
): Promise<ResetPreview> {
  const scope = acctScope(bot)
  const acctRows = await dbQuery(
    `SELECT id, is_active, starting_capital, current_balance, cumulative_pnl,
            account_type, updated_at
     FROM ${botTable(bot, 'paper_account')}
     WHERE dte_mode = '${escapeSql(dte)}'${scope}
     ORDER BY id`,
  )

  const posStats = await dbQuery(
    `SELECT
       COUNT(*) FILTER (WHERE status = 'open') AS open_count,
       COUNT(*) FILTER (WHERE status IN ('closed', 'expired')) AS closed_count,
       COALESCE(SUM(realized_pnl) FILTER (WHERE status IN ('closed', 'expired')), 0) AS total_pnl
     FROM ${botTable(bot, 'positions')}
     WHERE dte_mode = '${escapeSql(dte)}'${scope}`,
  )

  // Resolve the day-1 seed capital. For SPARK (the live production bot) this
  // comes from the REAL production balance and we also read the live broker
  // book so the reset can refuse on an open position. For paper bots it comes
  // from the Tradier User sandbox account (legacy behavior).
  let tradierEquity: number | null = null
  let source: 'tradier' | 'production' | 'override' | 'unavailable' = 'unavailable'
  let note: string | undefined
  let live: ResetPreview['live']

  if (bot === PRODUCTION_BOT) {
    const pause = await getProductionPauseState(bot)
    const accounts = await getProductionAccountsForBot(bot) // [] when paused
    const acct = accounts[0]
    if (acct?.accountId) {
      try {
        const bal = await getTradierBalanceDetail(acct.apiKey, acct.accountId, acct.baseUrl)
        const cash = bal?.total_cash ?? bal?.total_equity ?? null
        const positions = (
          await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
        ).filter((p) => p.quantity !== 0)
        live = {
          paused: pause.paused,
          account_name: acct.name,
          total_cash: bal?.total_cash ?? null,
          total_equity: bal?.total_equity ?? null,
          open_position_count: positions.length,
          open_symbols: positions.map((p) => p.symbol),
        }
        if (overrideCapital != null) {
          tradierEquity = overrideCapital
          source = 'override'
        } else if (cash != null) {
          tradierEquity = cash
          source = 'production'
        } else {
          note = 'Production balance returned no total_cash/total_equity — pass ?starting_capital=N to override'
        }
      } catch (err: unknown) {
        note = `Production balance read failed: ${err instanceof Error ? err.message : String(err)}`
      }
    } else {
      // No production account visible — either paused (accounts hidden) or unconfigured.
      live = {
        paused: pause.paused,
        account_name: null,
        total_cash: null,
        total_equity: null,
        open_position_count: 0,
        open_symbols: [],
      }
      if (overrideCapital != null) {
        tradierEquity = overrideCapital
        source = 'override'
      } else {
        note = pause.paused
          ? 'SPARK production is PAUSED, so the live account + book are hidden. Cannot verify a flat book or read real cash. Un-pause SPARK, or pass ?starting_capital=N only if you have independently confirmed the book is flat.'
          : 'No SPARK production account configured — pass ?starting_capital=N to override.'
      }
    }
  } else if (overrideCapital != null) {
    tradierEquity = overrideCapital
    source = 'override'
  } else {
    try {
      const balances = await getSandboxAccountBalances()
      const user = balances.find(
        (b) => b.name === 'User' && b.account_type === 'sandbox',
      )
      if (user?.total_equity != null) {
        tradierEquity = user.total_equity
        source = 'tradier'
      } else {
        note = 'User sandbox account returned no total_equity — pass ?starting_capital=N to override'
      }
    } catch (err: unknown) {
      note = `Tradier read failed: ${err instanceof Error ? err.message : String(err)}`
    }
  }

  const newCapital = tradierEquity ?? 0

  return {
    bot,
    dte_mode: dte,
    tradier: { user_total_equity: tradierEquity, source, note },
    live,
    current: {
      paper_account_rows: acctRows.map((r) => ({
        id: int(r.id),
        is_active: r.is_active === true || r.is_active === 'true',
        starting_capital: num(r.starting_capital),
        current_balance: num(r.current_balance),
        cumulative_pnl: num(r.cumulative_pnl),
        account_type: r.account_type ?? null,
        updated_at: r.updated_at ? new Date(r.updated_at).toISOString() : null,
      })),
      open_positions: int(posStats[0]?.open_count),
      closed_positions: int(posStats[0]?.closed_count),
      total_realized_pnl: Math.round(num(posStats[0]?.total_pnl) * 100) / 100,
    },
    proposed: {
      action:
        'Archive closed/open positions, deactivate all paper_account rows, insert one fresh active row matching Tradier',
      archive_dte_mode: `${ARCHIVED_SUFFIX}${dte}`,
      new_starting_capital: newCapital,
      new_balance: newCapital,
      new_cumulative_pnl: 0,
    },
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (!SUPPORTED_BOTS.has(bot)) {
    return NextResponse.json(
      { error: `reset-paper-account is only enabled for: ${Array.from(SUPPORTED_BOTS).join(', ')}` },
      { status: 403 },
    )
  }

  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  const overrideStr = req.nextUrl.searchParams.get('starting_capital')
  const overrideCapital = overrideStr != null ? parseFloat(overrideStr) : null
  if (overrideStr != null && (!Number.isFinite(overrideCapital) || (overrideCapital as number) < 0)) {
    return NextResponse.json({ error: 'starting_capital must be a non-negative number' }, { status: 400 })
  }

  try {
    const preview = await gatherState(bot, dte, overrideCapital)
    return NextResponse.json({
      dry_run: true,
      ...preview,
      instructions: `POST /api/${bot}/reset-paper-account?confirm=true to apply. Add &starting_capital=N to override the Tradier-derived value.`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (!SUPPORTED_BOTS.has(bot)) {
    return NextResponse.json(
      { error: `reset-paper-account is only enabled for: ${Array.from(SUPPORTED_BOTS).join(', ')}` },
      { status: 403 },
    )
  }

  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Unknown dte_mode' }, { status: 400 })

  if (req.nextUrl.searchParams.get('confirm') !== 'true') {
    return NextResponse.json(
      { error: 'Refusing to reset without ?confirm=true — GET this URL first to preview.' },
      { status: 400 },
    )
  }

  const overrideStr = req.nextUrl.searchParams.get('starting_capital')
  const overrideCapital = overrideStr != null ? parseFloat(overrideStr) : null
  if (overrideStr != null && (!Number.isFinite(overrideCapital) || (overrideCapital as number) < 0)) {
    return NextResponse.json({ error: 'starting_capital must be a non-negative number' }, { status: 400 })
  }

  try {
    const preview = await gatherState(bot, dte, overrideCapital)
    const newCapital = preview.tradier.user_total_equity
    if (newCapital == null) {
      return NextResponse.json(
        { error: 'Cannot determine starting_capital — Tradier unavailable and no override passed.', preview },
        { status: 503 },
      )
    }

    // SPARK is the live real-money bot. Guard hard before mutating anything:
    // never reset on an open book (would orphan a live broker position), and
    // never fall through to the force-close step on the production bot.
    if (bot === PRODUCTION_BOT) {
      const liveUnverified =
        !preview.live ||
        (preview.live.account_name == null && preview.tradier.source !== 'override')
      if (liveUnverified) {
        return NextResponse.json(
          {
            error:
              'Cannot verify SPARK live account state (paused or unconfigured). Refusing to reset. ' +
              'Un-pause SPARK so the book can be checked, or pass ?starting_capital=N only after ' +
              'independently confirming a flat book.',
            preview,
          },
          { status: 503 },
        )
      }
      if (preview.live && preview.live.open_position_count > 0) {
        return NextResponse.json(
          {
            error:
              `Refusing to reset: SPARK holds ${preview.live.open_position_count} open live position(s) ` +
              `at Tradier (${preview.live.open_symbols.join(', ')}). Reset only on a flat book — ` +
              `wait until after the close and settlement.`,
            preview,
          },
          { status: 409 },
        )
      }
      if (preview.current.open_positions > 0) {
        return NextResponse.json(
          {
            error:
              `Refusing to reset: ${preview.current.open_positions} open position(s) remain in the spark ` +
              `ledger. Close/reconcile them first (force-close or fix-collateral); the live reset will ` +
              `not force-close on the production bot.`,
            preview,
          },
          { status: 409 },
        )
      }
    }

    const archivedDte = `${ARCHIVED_SUFFIX}${dte}`
    // Scope mutations to the production ledger for SPARK (no-op clause for paper bots).
    const scope = acctScope(bot)

    // 1. Archive closed/expired positions (rename dte_mode so they stop being summed)
    const archivedClosed = await dbExecute(
      `UPDATE ${botTable(bot, 'positions')}
       SET dte_mode = $1, updated_at = NOW()
       WHERE dte_mode = $2 AND status IN ('closed', 'expired')${scope}`,
      [archivedDte, dte],
    )

    // 2. Force-close any open positions (dashboard showed 0, but guard anyway)
    const forcedClosed = await dbExecute(
      `UPDATE ${botTable(bot, 'positions')}
       SET status = 'closed',
           close_time = COALESCE(close_time, NOW()),
           realized_pnl = COALESCE(realized_pnl, 0),
           close_reason = COALESCE(close_reason, 'paper_reset'),
           dte_mode = $1,
           updated_at = NOW()
       WHERE dte_mode = $2 AND status = 'open'${scope}`,
      [archivedDte, dte],
    )

    // 3. Deactivate existing paper_account rows for this dte_mode (production-scoped for SPARK)
    const deactivated = await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET is_active = FALSE, updated_at = NOW()
       WHERE dte_mode = $1${scope}`,
      [dte],
    )

    // 4. Insert one fresh active row matching Tradier
    await dbExecute(
      `INSERT INTO ${botTable(bot, 'paper_account')}
         (starting_capital, current_balance, cumulative_pnl,
          collateral_in_use, buying_power, total_trades,
          high_water_mark, max_drawdown,
          is_active, dte_mode, account_type,
          created_at, updated_at)
       VALUES ($1, $1, 0, 0, $1, 0, $1, 0, TRUE, $2, $3, NOW(), NOW())`,
      [newCapital, dte, bot === PRODUCTION_BOT ? 'production' : 'sandbox'],
    )

    // Audit log
    try {
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
         VALUES ($1, $2, $3, $4)`,
        [
          'PAPER_RESET',
          `Reset paper_account: starting_capital=$${newCapital.toFixed(2)} (source=${preview.tradier.source}). ` +
            `Archived ${archivedClosed} closed + ${forcedClosed} forced-closed positions. ` +
            `Deactivated ${deactivated} paper_account rows. ` +
            `Prior total_realized_pnl=$${preview.current.total_realized_pnl.toFixed(2)} now archived.`,
          JSON.stringify({
            event: 'paper_reset',
            new_starting_capital: newCapital,
            tradier_source: preview.tradier.source,
            archived_closed: archivedClosed,
            forced_closed: forcedClosed,
            deactivated_paper_rows: deactivated,
            archived_dte_mode: archivedDte,
            prior_realized_pnl: preview.current.total_realized_pnl,
            ct_date: null, // CT_TODAY is a SQL literal, not a JS value — left null in the JSON
          }),
          dte,
        ],
      )
      // Reference CT_TODAY so the import isn't flagged as unused; the audit log
      // intentionally doesn't embed it (SQL literal, not serializable).
      void CT_TODAY
    } catch { /* audit log is best-effort */ }

    return NextResponse.json({
      bot,
      applied: true,
      new_starting_capital: newCapital,
      tradier_source: preview.tradier.source,
      archived_closed_positions: archivedClosed,
      forced_closed_open_positions: forcedClosed,
      deactivated_paper_account_rows: deactivated,
      archived_dte_mode: archivedDte,
      prior_realized_pnl: preview.current.total_realized_pnl,
      note: `Refresh /${bot} — balance should now read $${newCapital.toFixed(2)}. ` +
            `Old trade history is preserved but moved to dte_mode='${archivedDte}'.`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
