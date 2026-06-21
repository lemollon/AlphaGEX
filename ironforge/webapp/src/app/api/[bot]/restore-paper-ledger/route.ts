/**
 * One-time repair: restore SPARK's PAPER (sandbox) ledger.
 *
 * On 2026-06-16 the reset-paper-account run filtered by dte_mode only (not
 * account_type), so it archived BOTH the paper (sandbox) and live (production)
 * ledgers and deactivated the active sandbox paper_account row. The live reset
 * was intended and is kept; this un-does the collateral damage to the paper
 * side, which is fully recoverable because nothing was deleted:
 *
 *   1. Reactivate the most-recent sandbox paper_account row for this dte_mode
 *      (deactivating any other sandbox rows so exactly one is active).
 *   2. Un-archive sandbox positions: dte_mode ARCHIVED_<dte> -> <dte> for rows
 *      where COALESCE(account_type,'sandbox') = 'sandbox'.
 *
 * Production rows/positions are left EXACTLY as the reset left them (the live
 * day-1 reset stands). reset-paper-account is now account_type-scoped so this
 * can't recur.
 *
 * GET  /api/spark/restore-paper-ledger            -> dry-run counts (safe).
 * POST /api/spark/restore-paper-ledger?confirm=true -> apply.
 *
 * Scoped to the production bot (SPARK) only.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import { PRODUCTION_BOT } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

const SANDBOX = "COALESCE(account_type, 'sandbox') = 'sandbox'"
const PRODUCTION = "COALESCE(account_type, 'sandbox') = 'production'"

async function gather(bot: string, dte: string) {
  const archivedDte = `ARCHIVED_${dte}`

  const sandboxRows = await dbQuery(
    `SELECT id, is_active, starting_capital, current_balance, cumulative_pnl, account_type
     FROM ${botTable(bot, 'paper_account')}
     WHERE dte_mode = '${escapeSql(dte)}' AND ${SANDBOX}
     ORDER BY id`,
  )
  const archivedSandbox = await dbQuery(
    `SELECT COUNT(*) AS cnt FROM ${botTable(bot, 'positions')}
     WHERE dte_mode = '${escapeSql(archivedDte)}' AND ${SANDBOX}`,
  )
  const archivedProduction = await dbQuery(
    `SELECT COUNT(*) AS cnt FROM ${botTable(bot, 'positions')}
     WHERE dte_mode = '${escapeSql(archivedDte)}' AND ${PRODUCTION}`,
  )
  // Pick the REAL paper ledger to reactivate: the sandbox row with the most
  // capital, not a fresh scanner-seeded default. (After the reset deactivated
  // the active sandbox row, the scanner auto-inserted a $10k default row; that
  // one must NOT win.) Tie-break by newest id.
  const pick = await dbQuery(
    `SELECT id FROM ${botTable(bot, 'paper_account')}
     WHERE dte_mode = '${escapeSql(dte)}' AND ${SANDBOX}
     ORDER BY current_balance DESC, id DESC LIMIT 1`,
  )

  return {
    bot,
    dte_mode: dte,
    sandbox_paper_account_rows: sandboxRows.map((r) => ({
      id: int(r.id),
      is_active: r.is_active === true || r.is_active === 'true',
      starting_capital: num(r.starting_capital),
      current_balance: num(r.current_balance),
      cumulative_pnl: num(r.cumulative_pnl),
      account_type: r.account_type ?? null,
    })),
    row_to_reactivate: pick[0]?.id != null ? int(pick[0].id) : null,
    archived_sandbox_positions_to_restore: int(archivedSandbox[0]?.cnt),
    archived_production_positions_kept: int(archivedProduction[0]?.cnt),
  }
}

function guard(bot: string) {
  if (bot !== PRODUCTION_BOT) {
    return NextResponse.json(
      { error: `restore-paper-ledger is only meaningful for the production bot: ${PRODUCTION_BOT}` },
      { status: 403 },
    )
  }
  return null
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
    const state = await gather(bot, dte)
    return NextResponse.json({
      dry_run: true,
      ...state,
      instructions: 'POST ?confirm=true to apply: reactivate row_to_reactivate and un-archive the sandbox positions. Production is untouched.',
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
    const before = await gather(bot, dte)

    // Optional explicit override: ?row_id=N must be one of the sandbox rows.
    const rowIdParam = req.nextUrl.searchParams.get('row_id')
    let targetRow: number | null = before.row_to_reactivate
    if (rowIdParam != null) {
      const requested = parseInt(rowIdParam, 10)
      const valid = before.sandbox_paper_account_rows.some((r) => r.id === requested)
      if (!Number.isFinite(requested) || !valid) {
        return NextResponse.json(
          {
            error: `row_id=${rowIdParam} is not a sandbox paper_account row for this dte_mode. ` +
              `Valid: ${before.sandbox_paper_account_rows.map((r) => r.id).join(', ')}`,
            before,
          },
          { status: 400 },
        )
      }
      targetRow = requested
    }

    if (targetRow == null) {
      return NextResponse.json(
        { error: 'No sandbox paper_account row found to reactivate — nothing to restore.', before },
        { status: 409 },
      )
    }

    const archivedDte = `ARCHIVED_${dte}`

    // 1. Deactivate all sandbox rows, then reactivate exactly the most-recent one.
    await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET is_active = FALSE, updated_at = NOW()
       WHERE dte_mode = $1 AND ${SANDBOX}`,
      [dte],
    )
    const reactivated = await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET is_active = TRUE, updated_at = NOW()
       WHERE id = $1`,
      [targetRow],
    )

    // 2. Un-archive sandbox positions (ARCHIVED_<dte> -> <dte>). Production stays archived.
    const restoredPositions = await dbExecute(
      `UPDATE ${botTable(bot, 'positions')}
       SET dte_mode = $1, updated_at = NOW()
       WHERE dte_mode = $2 AND ${SANDBOX}`,
      [dte, archivedDte],
    )

    // Audit log (best-effort)
    try {
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
         VALUES ($1, $2, $3, $4)`,
        [
          'PAPER_RESTORE',
          `Restored SPARK paper (sandbox) ledger after the 2026-06-16 reset over-reach: ` +
            `reactivated paper_account row id=${targetRow}, ` +
            `un-archived ${restoredPositions} sandbox positions. Production ledger untouched.`,
          JSON.stringify({
            event: 'paper_restore',
            reactivated_row: targetRow,
            reactivated_count: reactivated,
            restored_sandbox_positions: restoredPositions,
            production_positions_left_archived: before.archived_production_positions_kept,
          }),
          dte,
        ],
      )
    } catch { /* audit log is best-effort */ }

    const after = await gather(bot, dte)
    return NextResponse.json({
      bot,
      applied: true,
      reactivated_paper_account_row: targetRow,
      restored_sandbox_positions: restoredPositions,
      production_positions_left_archived: before.archived_production_positions_kept,
      after,
      note: `Refresh /spark and toggle to Paper — it should read the restored sandbox ledger again. ` +
            `Live (production) stays at its day-1 reset.`,
    })
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : String(err) }, { status: 500 })
  }
}
