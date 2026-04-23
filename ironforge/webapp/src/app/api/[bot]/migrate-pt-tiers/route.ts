/**
 * One-shot DB migration: bump FLAME/SPARK `profit_target_pct` from 30 → 50
 * across both Paper and Live config rows.
 *
 * Why this exists:
 *   Commit O updates the hardcoded `DEFAULT_CONFIGS` in scanner.ts from
 *   pt_pct=0.30 to 0.50. But any `{bot}_config` row in the database with
 *   `profit_target_pct=30` (from before the change) wins the merge — so
 *   without this migration, live behavior stays at 30/20/15 even though
 *   the code says 50/30/20.
 *
 *   This endpoint updates existing config rows. It's idempotent: re-running
 *   it on rows already at 50 is a no-op. Safe to call multiple times.
 *
 * Scope:
 *   FLAME + SPARK only. INFERNO intentionally left out — its own sliding
 *   schedule is 20/30/50 (reversed for 0DTE) and doesn't change.
 *
 *   Both `account_type = 'sandbox'` and `account_type = 'production'` rows
 *   are updated (user requested "Paper and live").
 *
 * GET  /api/{bot}/migrate-pt-tiers
 *   Dry-run: lists current config rows for flame + spark + inferno with
 *   their profit_target_pct values and says which would be migrated.
 *
 * POST /api/{bot}/migrate-pt-tiers?confirm=true
 *   Applies: UPDATE flame_config + spark_config SET profit_target_pct=50
 *   WHERE profit_target_pct=30. Writes HYPO_NOT_APPLICABLE-style audit
 *   logs to flame_logs/spark_logs for traceability.
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
  action: 'migrate' | 'already-at-50' | 'unmanaged-value'
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
      if (current === 30) action = 'migrate'
      else if (current === 50) action = 'already-at-50'
      else action = 'unmanaged-value'
      rows.push({
        bot,
        dte_mode: r.dte_mode,
        account_type: at,
        current_pt_pct: current,
        would_become: action === 'migrate' ? 50 : current,
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
      already_at_50: rows.filter((r) => r.action === 'already-at-50').length,
      unmanaged_values: rows.filter((r) => r.action === 'unmanaged-value').length,
      instructions: toMigrate > 0
        ? `POST /api/${bot}/migrate-pt-tiers?confirm=true to apply.`
        : 'Nothing to migrate — all FLAME/SPARK rows already at 50 or on a non-30 custom value.',
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
           SET profit_target_pct = 50, updated_at = NOW()
           WHERE profit_target_pct = 30`,
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
            `Sliding PT tiers migrated from 30/20/15 → 50/30/20 (Commit O)`,
            JSON.stringify({
              event: 'pt_tier_migration_v1',
              old_tiers: { morning: 30, midday: 20, afternoon: 15 },
              new_tiers: { morning: 50, midday: 30, afternoon: 20 },
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
