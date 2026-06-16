import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable } from '@/lib/db'
import { getRawQuotes, isConfigured } from '@/lib/tradier'
import { ensureRegimeDailyTable } from '@/lib/volAlerts.server'
import { buildHedgePlan, hedgePlanText } from '@/lib/hedge/advisor'
import { getTodayHedgeOrder, hedgeArmState } from '@/lib/hedge/place.server'

export const dynamic = 'force-dynamic'

/** Fallback tail (SPARK IC bad-day magnitude) used when SPARK is flat. */
const DEFAULT_TAIL = Number(process.env.HEDGE_DEFAULT_TAIL) || 1200

/**
 * Today's regime hedge plan (Phase 2, advisory). Reads the latched daily hedge
 * decision (regime_daily) + SPARK's live IC capital-at-risk + SPY spot, and emits
 * a concrete SPY put-debit-spread plan sized to ~`coverage` of the tail. Calm
 * day → { hedge:false }. Advisory only — does not place anything.
 */
export async function GET(req: NextRequest) {
  const coverage = Number(req.nextUrl.searchParams.get('coverage')) || undefined
  try {
    await ensureRegimeDailyTable()

    const regimeRows = await dbQuery<{
      hedge_flagged: boolean
      hedge_reasons: string[] | null
      regime_label: string | null
      vix: number | null
      vvix: number | null
    }>(
      `SELECT hedge_flagged, hedge_reasons, regime_label, vix, vvix
         FROM regime_daily
        WHERE ct_date = (NOW() AT TIME ZONE 'America/Chicago')::date
        LIMIT 1`,
    )
    const reg = regimeRows[0]
    const flagged = reg?.hedge_flagged === true
    const reasons = reg?.hedge_reasons ?? []

    // SPARK's live capital-at-risk = Σ open IC max-loss; fall back to the typical
    // bad-day tail when flat (the hedge guards the next IC the bot opens).
    const tailRows = await dbQuery<{ tail: number }>(
      `SELECT COALESCE(SUM(GREATEST(spread_width - total_credit, 0) * contracts * 100), 0) AS tail
         FROM ${botTable('spark', 'positions')}
        WHERE status = 'open' AND dte_mode = '1'
          AND COALESCE(account_type, 'sandbox') = 'production'`,
    )
    const openTail = Number(tailRows[0]?.tail ?? 0)
    const tail = openTail > 0 ? Math.round(openTail) : DEFAULT_TAIL

    let spy: number | null = null
    if (isConfigured()) {
      const quotes = await getRawQuotes(['SPY']).catch(() => ({}))
      const q = (quotes as Record<string, Record<string, unknown>>)['SPY']
      const last = q?.last
      spy = last == null ? null : Number(last)
    }

    if (spy == null || !(spy > 0)) {
      return NextResponse.json({
        ok: true,
        as_of: new Date().toISOString(),
        flagged,
        plan: { hedge: false, reason: 'Awaiting SPY quote.' },
        inputs: { tail, tail_source: openTail > 0 ? 'open_positions' : 'default', regime: reg?.regime_label ?? null },
      })
    }

    const plan = buildHedgePlan({ flagged, reasons, tail, spy, coverage })
    const execution = await getTodayHedgeOrder().catch(() => null)
    return NextResponse.json({
      ok: true,
      as_of: new Date().toISOString(),
      flagged,
      summary: hedgePlanText(plan),
      plan,
      execution,
      arm: hedgeArmState(),
      inputs: {
        tail,
        tail_source: openTail > 0 ? 'open_positions' : 'default',
        regime: reg?.regime_label ?? null,
        vix: reg?.vix ?? null,
        vvix: reg?.vvix ?? null,
      },
    })
  } catch (err: unknown) {
    return NextResponse.json({ ok: false, error: err instanceof Error ? err.message : String(err) }, { status: 500 })
  }
}
