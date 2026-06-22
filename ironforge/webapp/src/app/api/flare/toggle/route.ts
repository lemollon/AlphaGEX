import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * FLARE master enable/disable.
 *
 * FLARE's only run gate is `flare_pdt_config.pdt_enabled` (read by
 * isFlareEnabled() in flare/scanner.ts — default OFF). FLARE is paper-only:
 * its executor inserts into flare_positions and sizes off the paper balance,
 * placing NO real Tradier orders. This route is the operator switch for that
 * gate so it can be flipped without a direct DB session.
 *
 * GET  /api/flare/toggle           → { enabled: boolean }
 * POST /api/flare/toggle  body { "active": boolean }  → set enabled state
 */

async function readEnabled(): Promise<boolean | null> {
  const rows = await dbQuery<{ pdt_enabled: boolean }>(
    `SELECT pdt_enabled FROM flare_pdt_config WHERE bot_name = 'FLARE' LIMIT 1`,
  )
  if (rows.length === 0) return null
  return Boolean(rows[0].pdt_enabled)
}

export async function GET() {
  try {
    const enabled = await readEnabled()
    return NextResponse.json({ bot: 'FLARE', enabled: enabled ?? false, seeded: enabled !== null })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const active = Boolean(body.active)

    // flare_pdt_config has NO unique index on bot_name (only the shared
    // ironforge_pdt_config does), so we can't ON CONFLICT. The bootstrap in
    // db.ts seeds the 'FLARE' row, so UPDATE normally hits; INSERT only if a
    // fresh DB somehow lacks it.
    const updated = await dbExecute(
      `UPDATE flare_pdt_config SET pdt_enabled = ${active}, updated_at = NOW() WHERE bot_name = 'FLARE'`,
    )
    if (updated === 0) {
      await dbExecute(
        `INSERT INTO flare_pdt_config (bot_name, pdt_enabled, day_trade_count, max_day_trades, window_days, max_trades_per_day)
         VALUES ('FLARE', ${active}, 0, 0, 5, 0)`,
      )
    }

    const enabled = await readEnabled()
    if (enabled === null) {
      return NextResponse.json({ error: 'FLARE config row not found after upsert' }, { status: 500 })
    }

    const status = active ? 'ENABLED' : 'DISABLED'
    await dbExecute(
      `INSERT INTO flare_logs (log_time, level, message, details, dte_mode, account_type, person)
       VALUES (NOW(), 'INFO', 'FLARE bot ${status} via API',
               '${JSON.stringify({ active, source: 'flare_toggle_api' }).replace(/'/g, "''")}',
               '0DTE', 'sandbox', 'User')`,
    )

    return NextResponse.json({ success: true, bot: 'FLARE', enabled, message: `FLARE ${status.toLowerCase()}` })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
