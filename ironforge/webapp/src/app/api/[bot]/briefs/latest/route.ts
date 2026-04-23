/**
 * Latest SPARK brief (Commit Q1).
 *
 *   GET /api/spark/briefs/latest
 *     Returns the single most recent brief, or null if none exist.
 *
 * Used by the LatestBriefCard component on /spark Equity Curve tab.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, validateBot } from '@/lib/db'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== 'spark') {
    return NextResponse.json({ brief: null })
  }
  try {
    const rows = await dbQuery(
      `SELECT id, brief_date, brief_time, brief_type,
              risk_score, summary, factors_json,
              spy_price, vix, vix3m, term_structure, model
       FROM spark_market_briefs
       ORDER BY brief_time DESC
       LIMIT 1`,
    )
    if (rows.length === 0) return NextResponse.json({ brief: null })
    const r = rows[0]
    return NextResponse.json({
      brief: {
        id: Number(r.id),
        brief_date: r.brief_date instanceof Date
          ? r.brief_date.toISOString().slice(0, 10)
          : String(r.brief_date),
        brief_time: r.brief_time,
        brief_type: r.brief_type,
        risk_score: r.risk_score != null ? Number(r.risk_score) : null,
        summary: r.summary ?? '',
        factors_json: r.factors_json ?? null,
        spy_price: r.spy_price != null ? Number(r.spy_price) : null,
        vix: r.vix != null ? Number(r.vix) : null,
        vix3m: r.vix3m != null ? Number(r.vix3m) : null,
        term_structure: r.term_structure != null ? Number(r.term_structure) : null,
        model: r.model ?? null,
      },
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    if (/relation .* does not exist/i.test(msg)) return NextResponse.json({ brief: null })
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
