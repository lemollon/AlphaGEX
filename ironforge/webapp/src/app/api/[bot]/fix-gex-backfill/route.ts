import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET  /api/[bot]/fix-gex-backfill  -> read-only diagnostic
 * POST /api/[bot]/fix-gex-backfill  -> apply the backfill
 *
 * Every position row this system has ever written stored the literals
 * `0, 0, 'UNKNOWN', 0, 0` for call_wall / put_wall / gex_regime / flip_point /
 * net_gex (four hardcoded INSERT sites in scanner.ts, fixed 2026-07-21). The
 * consequence: the live database could not answer "what gamma regime was this
 * trade opened in?" -- a question that matters a great deal, since negative-
 * gamma days carry ~74% of all loss mass in the 2020-26 backtest. The regime
 * had to be reconstructed from the offline DuckDB warehouse, which is not
 * available to the app.
 *
 * This route repairs history from `gex_history` (same database, symbol='SPY',
 * ~322 trading days from 2024-11-14 to present -- which spans SPARK's entire
 * live trading history). For each position it takes the SPY reading nearest in
 * time to the position's own open_time.
 *
 * SAFETY: only rows where net_gex IS NULL OR net_gex = 0 are touched. A row
 * that already carries a real reading is never overwritten.
 */

type Row = Record<string, unknown>

async function survey(bot: string, dte: string) {
  const totals = await dbQuery(
    `SELECT count(*)::int AS total,
            count(*) FILTER (WHERE net_gex IS NULL OR net_gex = 0)::int AS missing,
            count(*) FILTER (WHERE net_gex IS NOT NULL AND net_gex <> 0)::int AS populated,
            min(open_date)::text AS first_open,
            max(open_date)::text AS last_open
       FROM ${botTable(bot, 'positions')}
      WHERE dte_mode = $1`,
    [dte],
  )

  // How many of the missing rows can actually be repaired from gex_history?
  const cover = await dbQuery(
    `SELECT count(*)::int AS repairable
       FROM ${botTable(bot, 'positions')} p
      WHERE p.dte_mode = $1
        AND (p.net_gex IS NULL OR p.net_gex = 0)
        AND EXISTS (
          SELECT 1 FROM gex_history h
           WHERE h.symbol = 'SPY'
             AND (h.timestamp AT TIME ZONE 'America/Chicago')::date = p.open_date
             AND h.net_gex IS NOT NULL)`,
    [dte],
  )

  // Dates we cannot repair -- reported explicitly rather than silently skipped.
  const gaps = await dbQuery(
    `SELECT DISTINCT p.open_date::text AS open_date
       FROM ${botTable(bot, 'positions')} p
      WHERE p.dte_mode = $1
        AND (p.net_gex IS NULL OR p.net_gex = 0)
        AND NOT EXISTS (
          SELECT 1 FROM gex_history h
           WHERE h.symbol = 'SPY'
             AND (h.timestamp AT TIME ZONE 'America/Chicago')::date = p.open_date
             AND h.net_gex IS NOT NULL)
      ORDER BY 1`,
    [dte],
  )

  const t = (totals[0] ?? {}) as Row
  return {
    total: t.total ?? 0,
    missing_gex: t.missing ?? 0,
    already_populated: t.populated ?? 0,
    repairable: (cover[0] as Row)?.repairable ?? 0,
    unrepairable_dates: gaps.map((g) => (g as Row).open_date),
    first_open: t.first_open ?? null,
    last_open: t.last_open ?? null,
  }
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Invalid dte' }, { status: 400 })

  try {
    const s = await survey(bot, dte)
    // Preview: what the 10 largest-|P&L| rows would be tagged as.
    const preview = await dbQuery(
      `SELECT DISTINCT ON (p.position_id)
              p.position_id, p.open_date::text AS open_date, p.realized_pnl,
              h.net_gex,
              CASE WHEN h.net_gex < 0 THEN 'NEGATIVE' ELSE 'POSITIVE' END AS gex_regime
         FROM ${botTable(bot, 'positions')} p
         JOIN gex_history h
           ON h.symbol = 'SPY'
          AND (h.timestamp AT TIME ZONE 'America/Chicago')::date = p.open_date
          AND h.net_gex IS NOT NULL
        WHERE p.dte_mode = $1
          AND (p.net_gex IS NULL OR p.net_gex = 0)
          AND p.realized_pnl IS NOT NULL
        ORDER BY p.position_id,
                 abs(extract(epoch FROM (h.timestamp - p.open_time)))`,
      [dte],
    )
    preview.sort((a, b) =>
      Math.abs(Number((b as Row).realized_pnl)) - Math.abs(Number((a as Row).realized_pnl)))
    return NextResponse.json({
      mode: 'diagnostic (read-only)',
      bot, dte,
      ...s,
      preview_top_by_abs_pnl: preview.slice(0, 12),
      apply_with: `POST /api/${bot}/fix-gex-backfill`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function POST(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const dte = dteMode(bot)
  if (!dte) return NextResponse.json({ error: 'Invalid dte' }, { status: 400 })

  try {
    const before = await survey(bot, dte)

    // Nearest-in-time SPY reading per position. DISTINCT ON + ORDER BY picks
    // the gex_history row closest to that position's own open_time.
    const updated = await dbExecute(
      `UPDATE ${botTable(bot, 'positions')} p
          SET net_gex    = g.net_gex,
              gex_regime = CASE WHEN g.net_gex < 0 THEN 'NEGATIVE' ELSE 'POSITIVE' END,
              flip_point = COALESCE(NULLIF(g.flip_point, 0), p.flip_point),
              call_wall  = COALESCE(NULLIF(g.call_wall, 0), p.call_wall),
              put_wall   = COALESCE(NULLIF(g.put_wall, 0), p.put_wall),
              updated_at = NOW()
         FROM (
           SELECT DISTINCT ON (p2.position_id)
                  p2.position_id, h.net_gex, h.flip_point, h.call_wall, h.put_wall
             FROM ${botTable(bot, 'positions')} p2
             JOIN gex_history h
               ON h.symbol = 'SPY'
              AND (h.timestamp AT TIME ZONE 'America/Chicago')::date = p2.open_date
              AND h.net_gex IS NOT NULL
            WHERE p2.dte_mode = $1
              AND (p2.net_gex IS NULL OR p2.net_gex = 0)
            ORDER BY p2.position_id,
                     abs(extract(epoch FROM (h.timestamp - p2.open_time)))
         ) g
        WHERE p.position_id = g.position_id
          AND (p.net_gex IS NULL OR p.net_gex = 0)`,
      [dte],
    )

    const after = await survey(bot, dte)

    await dbExecute(
      `INSERT INTO ${botTable(bot, 'logs')} (level, message, details, dte_mode)
       VALUES ('BACKFILL', $1, $2, $3)`,
      [
        `GEX BACKFILL: ${updated} position row(s) repaired from gex_history ` +
        `(${before.missing_gex} missing before, ${after.missing_gex} after)`,
        JSON.stringify({
          source: 'gex_history', symbol: 'SPY',
          rows_updated: updated,
          missing_before: before.missing_gex,
          missing_after: after.missing_gex,
          unrepairable_dates: after.unrepairable_dates,
        }),
        dte,
      ],
    )

    return NextResponse.json({
      mode: 'applied',
      bot, dte,
      rows_updated: updated,
      before, after,
      note: 'Only rows with net_gex NULL or 0 were touched; existing readings were never overwritten.',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
