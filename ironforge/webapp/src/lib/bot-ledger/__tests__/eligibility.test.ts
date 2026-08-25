import { describe, expect, it } from 'vitest'

import { eligibilitySql, reconcileSql } from '../query'
import { dteMode } from '@/lib/db'

/*
 * DERIVED, NOT TYPED — this suite failed on main for nine days.
 *
 * It asserted `dte_mode = '1DTE'` for SPARK and `'2DTE'` for FLAME. The
 * 2026-08-16 EBB change moved BOTH bots to '0DTE', so both assertions became
 * false the moment it landed, and the red stayed on main where it masked
 * anything else that might break here.
 *
 * Hardcoding '0DTE' would only reset the clock to the next roster move. The
 * point of these two lines is that `query.ts` filters by the SAME dte_mode the
 * roster reports — so ask the roster. The bug this catches is a query that
 * drifts from `dteMode`, which is exactly what it should catch.
 */
const SPARK_DTE = dteMode('spark')
const FLAME_DTE = dteMode('flame')

describe('eligibilitySql', () => {
  const spark = eligibilitySql('spark')
  const flame = eligibilitySql('flame')

  it('targets the right table and dte_mode per bot', () => {
    expect(spark).toContain('FROM spark_positions')
    expect(spark).toContain(`AND dte_mode = '${SPARK_DTE}'`)
    expect(flame).toContain('FROM flame_positions')
    expect(flame).toContain(`AND dte_mode = '${FLAME_DTE}'`)
  })

  it('reproduces the operator console predicate', () => {
    // Must match src/app/api/[bot]/performance/route.ts, or the public page and
    // the internal dashboard would disagree about the same bot.
    expect(spark).toContain("status IN ('closed', 'expired')")
    expect(spark).toContain('realized_pnl IS NOT NULL')
  })

  it('has NO account_type filter', () => {
    // SPARK has no sandbox rows; adding one would silently empty the card.
    expect(spark).not.toContain('account_type')
    expect(flame).not.toContain('account_type')
  })

  it('has no person filter', () => {
    expect(spark).not.toContain('person')
  })

  it('requires the fields every published figure depends on', () => {
    expect(spark).toContain('close_time IS NOT NULL')
    expect(spark).toContain('contracts > 0')
    expect(spark).toContain('COALESCE(NULLIF(collateral_required, 0), NULLIF(max_loss, 0)) > 0')
  })

  it('dedupes on position_id, keeping the latest write', () => {
    expect(spark).toContain('SELECT DISTINCT ON (position_id)')
    expect(spark).toContain('ORDER BY position_id, id DESC')
  })

  it('pins row membership to a parameterised snapshot boundary', () => {
    expect(spark).toContain('AND close_time < $1')
  })

  it('projects the public date in market time and keeps CT for monitoring', () => {
    expect(spark).toContain("AT TIME ZONE 'America/New_York'")
    expect(spark).toContain("AT TIME ZONE 'America/Chicago'")
  })

  it('never interpolates caller-supplied text', () => {
    // The only interpolations are the table name and the dte literal, both
    // derived from the allowlisted bot.
    expect(spark).not.toContain('undefined')
    expect(spark).not.toContain('null')
  })

  it('refuses a bot outside the ledger allowlist', () => {
    // @ts-expect-error deliberately passing an unsupported bot
    expect(() => eligibilitySql('inferno')).toThrow()
    // @ts-expect-error deliberately passing junk
    expect(() => eligibilitySql("spark'; DROP TABLE users;--")).toThrow()
  })
})

describe('reconcileSql', () => {
  it('sums over the deduped set so the total is comparable to what we keep', () => {
    const sql = reconcileSql('flame')
    expect(sql).toContain('WITH deduped AS')
    expect(sql).toContain('SELECT DISTINCT ON (position_id)')
    expect(sql).toContain('SUM(realized_pnl)')
    expect(sql).toContain('AS raw_count')
    expect(sql).toContain('AS deduped_count')
  })

  it('uses the same predicate as the row query', () => {
    const sql = reconcileSql('spark')
    expect(sql).toContain("status IN ('closed', 'expired')")
    expect(sql).toContain(`AND dte_mode = '${SPARK_DTE}'`)
    expect(sql).toContain('AND close_time < $1')
    expect(sql).not.toContain('account_type')
  })
})
