/**
 * One-shot DB migration: revert FLAME/SPARK `profit_target_pct` from 50 → 30
 * across both Paper and Live config rows.
 *
 * Why this exists:
 *   We reverted the hardcoded `DEFAULT_CONFIGS` in scanner.ts back to
 *   pt_pct=0.30 (sliding 30/20/15). But any `{bot}_config` row in the
 *   database with `profit_target_pct=50` (from the prior Commit O migration)
 *   wins the merge — so without this migration, live behavior stays at
 *   50/30/20 even though the code says 30/20/15.
 *
 *   This endpoint updates existing config rows. It's idempotent: re-running
 *   it on rows already at 30 is a no-op. Safe to call multiple times.
 *
 * Scope:
 *   FLAME + SPARK only. INFERNO intentionally left out — its own sliding
 *   schedule is 20/30/50 (reversed for 0DTE) and doesn't change.
 *
 *   Both `account_type = 'sandbox'` and `account_type = 'production'` rows
 *   are updated (Paper and live).
 *
 * GET  /api/{bot}/migrate-pt-tiers
 *   Dry-run: lists current config rows for flame + spark with their
 *   profit_target_pct values and says which would be migrated.
 *
 * POST /api/{bot}/migrate-pt-tiers?confirm=true
 *   Applies: UPDATE flame_config + spark_config SET profit_target_pct=30
 *   WHERE profit_target_pct=50. Writes audit logs to flame_logs/spark_logs
 *   for traceability.
 *
 *   `bot` path parameter is accepted for routing parity but the migration
 *   always touches both flame and spark — calling from /api/spark/... or
 *   /api/flame/... produces the same effect.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, num, validateBot, escapeSql } from '@/lib/db'

export const dynamic = 'force-dynamic'

interface ConfigRow {
  bot: string
  dte_mode: string
  account_type: string
  current_pt_pct: number
  would_become: number
  action: 'migrate' | 'already-at-30' | 'unmanaged-value'
}

async function listConfigs(): Promise<ConfigRow[]> {
  const rows: ConfigRow[] = []
  for (const bot of ['flame', 'spark']) {
    let results: Array<{ dte_mode: string; account_type: string | null; profit_target_pct: string }> = []
    try {
      results = await dbQuery(
        `SELECT dte_mode, account_type, profit_target_pct
         FROM ${escapeSql(bot)}_config
         ORDER BY account_type, dte_mode`,
      )
    } catch {
      // Config table may be empty/missing on fresh cold start — defaults apply.
      continue
    }
    for (const r of results) {
      const current = num(r.profit_target_pct)
      const at = r.account_type ?? 'sandbox'
      let action: ConfigRow['action']
      if (current === 50) action = 'migrate'
      else if (current === 30) action = 'already-at-30'
      else action = 'unmanaged-value'
      rows.push({
        bot,
        dte_mode: r.dte_mode,
        account_type: at,
        current_pt_pct: current,
        would_become: action === 'migrate' ? 30 : current,
        action,
      })
    }
  }
  return rows
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  try {
    const rows = await listConfigs()
    const toMigrate = rows.filter((r) => r.action === 'migrate').length
    return NextResponse.json({
      dry_run: true,
      scope: 'flame + spark (both Paper and Live) — INFERNO unaffected',
      rows,
      will_migrate: toMigrate,
      already_at_30: rows.filter((r) => r.action === 'already-at-30').length,
      unmanaged_values: rows.filter((r) => r.action === 'unmanaged-value').length,
      instructions: toMigrate > 0
        ? `POST /api/${bot}/migrate-pt-tiers?confirm=true to apply.`
        : 'Nothing to migrate — all FLAME/SPARK rows already at 30 or on a non-50 custom value.',
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
  if (req.nextUrl.searchParams.get('confirm') !== 'true') {
    return NextResponse.json(
      { error: 'Refusing to mutate config without ?confirm=true — call GET first to preview.' },
      { status: 400 },
    )
  }

  try {
    const before = await listConfigs()
    let updated = 0
    for (const target of ['flame', 'spark']) {
      try {
        const result = await dbExecute(
          `UPDATE ${escapeSql(target)}_config
           SET profit_target_pct = 30, updated_at = NOW()
           WHERE profit_target_pct = 50`,
        )
        updated += result
      } catch { /* table may not exist */ }

      // Best-effort audit log per bot
      try {
        await dbExecute(
          `INSERT INTO ${escapeSql(target)}_logs (level, message, details)
           VALUES ($1, $2, $3)`,
          [
            'CONFIG',
            `Sliding PT tiers reverted from 50/30/20 → 30/20/15`,
            JSON.stringify({
              event: 'pt_tier_revert_v1',
              old_tiers: { morning: 50, midday: 30, afternoon: 20 },
              new_tiers: { morning: 30, midday: 20, afternoon: 15 },
              scope: `${target} (flame + spark), both sandbox + production`,
            }),
          ],
        )
      } catch { /* logs table may be missing columns */ }
    }
    const after = await listConfigs()
    return NextResponse.json({
      applied: true,
      rows_updated: updated,
      before,
      after,
      note: 'Scanner reads these values on its next cycle (within 60s). No restart required.',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
