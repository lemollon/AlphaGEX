/**
 * One-shot migration for the FLAME→SPARK production cutover.
 *
 * Context: the production-bot identity moved from FLAME to SPARK. After the
 * cutover the scanner only reconciles/closes production positions under the
 * current PRODUCTION_BOT. Any flame_positions rows left in `open` state with
 * account_type='production' are now strandable — the scanner ignores them.
 *
 * GET  /api/flame/fix-legacy-production
 *   Read-only. Reports counts and open rows so an operator can see exactly
 *   what needs to be cleaned up. Safe to call anytime.
 *
 * POST /api/flame/fix-legacy-production
 *   Marks leftover FLAME production positions closed in the database with
 *   close_reason = 'flame_spark_cutover'. This only touches the DB; the
 *   operator is responsible for verifying no broker-side positions remain
 *   (run /api/spark/reconcile?account_type=production first). Requires
 *   ?confirm=true so a drive-by GET can't accidentally flip to POST.
 *
 * This endpoint is FLAME-specific by design — other bots never had a
 * production account, so there's nothing to migrate for them. Returns 400
 * for any other bot value to keep the scope explicit.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, validateBot } from '@/lib/db'
import { PRODUCTION_BOT } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

const LEGACY_PRODUCTION_BOT = 'flame'
const CUTOVER_CLOSE_REASON = 'flame_spark_cutover'

function isLegacyBot(bot: string): boolean {
  // Typed check: legacy-production cleanup only makes sense for the old
  // production bot, and only while it is no longer the current one.
  return bot === LEGACY_PRODUCTION_BOT && (PRODUCTION_BOT as string) !== LEGACY_PRODUCTION_BOT
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  if (!isLegacyBot(bot)) {
    return NextResponse.json({
      error: `fix-legacy-production is only valid for the legacy production bot '${LEGACY_PRODUCTION_BOT}'. ` +
        `Current production bot is '${PRODUCTION_BOT}'.`,
    }, { status: 400 })
  }

  try {
    const openRows = await dbQuery(
      `SELECT position_id, dte_mode, person, expiration, contracts,
              total_credit, collateral_required, open_time, account_type
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' AND COALESCE(account_type, 'sandbox') = 'production'
       ORDER BY open_time DESC`,
    )

    const paperAccountRows = await dbQuery(
      `SELECT id, person, dte_mode, starting_capital, current_balance,
              cumulative_pnl, collateral_in_use, buying_power, total_trades,
              is_active, account_type
       FROM ${botTable(bot, 'paper_account')}
       WHERE COALESCE(account_type, 'sandbox') = 'production'
       ORDER BY id`,
    )

    const accountsRows = await dbQuery(
      `SELECT id, person, bot, type, is_active
       FROM ironforge_accounts
       WHERE is_active = TRUE AND type = 'production'
         AND (bot ILIKE '%FLAME%')
       ORDER BY person`,
    )

    const totalCollateral = openRows.reduce(
      (sum: number, r: any) => sum + num(r.collateral_required),
      0,
    )

    return NextResponse.json({
      legacy_bot: LEGACY_PRODUCTION_BOT,
      current_production_bot: PRODUCTION_BOT,
      open_positions: openRows.map((r: any) => ({
        position_id: r.position_id,
        dte_mode: r.dte_mode,
        person: r.person,
        expiration: String(r.expiration || '').slice(0, 10),
        contracts: int(r.contracts),
        total_credit: num(r.total_credit),
        collateral_required: num(r.collateral_required),
        open_time: r.open_time || null,
        account_type: r.account_type || 'sandbox',
      })),
      open_position_count: openRows.length,
      stranded_collateral: Math.round(totalCollateral * 100) / 100,
      paper_account_rows: paperAccountRows.map((r: any) => ({
        id: r.id,
        person: r.person,
        dte_mode: r.dte_mode,
        starting_capital: num(r.starting_capital),
        current_balance: num(r.current_balance),
        cumulative_pnl: num(r.cumulative_pnl),
        collateral_in_use: num(r.collateral_in_use),
        total_trades: int(r.total_trades),
        is_active: r.is_active === true || r.is_active === 'true',
      })),
      accounts_with_flame: accountsRows.map((r: any) => ({
        id: r.id,
        person: r.person,
        bot: r.bot,
      })),
      accounts_with_flame_count: accountsRows.length,
      instructions: openRows.length === 0
        ? `No stranded FLAME production positions. Safe to skip POST.`
        : `POST /api/${bot}/fix-legacy-production?confirm=true to mark all ` +
          `${openRows.length} open FLAME production position(s) closed with ` +
          `close_reason='${CUTOVER_CLOSE_REASON}'. ` +
          `VERIFY no broker positions remain first (run /api/${PRODUCTION_BOT}/reconcile?account_type=production).`,
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

  if (!isLegacyBot(bot)) {
    return NextResponse.json({
      error: `fix-legacy-production is only valid for '${LEGACY_PRODUCTION_BOT}'. Current production bot is '${PRODUCTION_BOT}'.`,
    }, { status: 400 })
  }

  const confirm = req.nextUrl.searchParams.get('confirm') === 'true'
  if (!confirm) {
    return NextResponse.json({
      error: `Refusing to modify data without ?confirm=true. Call GET first to preview impact.`,
    }, { status: 400 })
  }

  try {
    // Snapshot what we're about to close (so the response documents the change)
    const openRows = await dbQuery(
      `SELECT position_id, dte_mode, person, collateral_required, total_credit
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' AND COALESCE(account_type, 'sandbox') = 'production'`,
    )

    if (openRows.length === 0) {
      return NextResponse.json({
        bot,
        closed_count: 0,
        closed_positions: [],
        message: 'No stranded FLAME production positions — nothing to do.',
      })
    }

    // Close them in DB with realized_pnl = 0. We cannot compute a real P&L
    // because FLAME no longer has production broker access to query fills —
    // the operator should reconcile actual P&L separately via the broker
    // statement. Close price is set to entry credit so (entry - close) = 0.
    const closed = await dbExecute(
      `UPDATE ${botTable(bot, 'positions')}
       SET status = 'closed',
           close_time = NOW(),
           close_price = total_credit,
           realized_pnl = 0,
           close_reason = $1,
           updated_at = NOW()
       WHERE status = 'open' AND COALESCE(account_type, 'sandbox') = 'production'`,
      [CUTOVER_CLOSE_REASON],
    )

    // Release collateral on the paper_account rows that were tracking these
    // positions. Safe because the stranded positions are no longer 'open'.
    await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET collateral_in_use = 0,
           buying_power = current_balance,
           updated_at = NOW()
       WHERE COALESCE(account_type, 'sandbox') = 'production'`,
    )

    // Write a single audit log row so operators can find this action later.
    try {
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
         VALUES ($1, $2, $3, $4)`,
        [
          'CUTOVER',
          `FLAME→SPARK cutover: marked ${openRows.length} legacy production position(s) closed in DB`,
          JSON.stringify({
            event: 'flame_spark_cutover',
            closed_position_ids: openRows.map((r: any) => r.position_id),
          }),
          '2DTE',
        ],
      )
    } catch {
      // logs insert is advisory; don't fail the migration if the table schema
      // on this deploy doesn't line up.
    }

    return NextResponse.json({
      bot,
      closed_count: closed,
      closed_positions: openRows.map((r: any) => ({
        position_id: r.position_id,
        dte_mode: r.dte_mode,
        person: r.person,
        collateral_released: num(r.collateral_required),
        entry_credit: num(r.total_credit),
      })),
      close_reason: CUTOVER_CLOSE_REASON,
      reminder:
        `Broker-side verification required: check /api/${PRODUCTION_BOT}/reconcile` +
        `?account_type=production and the Tradier production account statement ` +
        `to confirm no real-money positions remain open.`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
