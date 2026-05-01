/**
 * List market-risk briefs.
 *
 *   GET /api/{bot}/briefs?date=YYYY-MM-DD&limit=50
 *     Returns briefs ordered newest-first. `date` optional (filter to one day).
 *     `limit` capped at 200.
 *
 * Read-only. Each bot has its own {bot}_market_briefs table.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, validateBot, escapeSql, botTable } from '@/lib/db'

export const dynamic = 'force-dynamic'

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dateParam = req.nextUrl.searchParams.get('date')
  const dateFilter = dateParam && /^\d{4}-\d{2}-\d{2}$/.test(dateParam)
    ? `WHERE brief_date = '${escapeSql(dateParam)}'`
    : ''
  const limitRaw = parseInt(req.nextUrl.searchParams.get('limit') || '50', 10)
  const limit = Number.isFinite(limitRaw) ? Math.max(1, Math.min(200, limitRaw)) : 50

  try {
    const rows = await dbQuery(
      `SELECT id, brief_date, brief_time, brief_type,
              risk_score, summary, factors_json,
              spy_price, vix, vix3m, term_structure, model, created_at
       FROM ${botTable(bot, 'market_briefs')}
       ${dateFilter}
       ORDER BY brief_time DESC
       LIMIT ${limit}`,
    )
    return NextResponse.json({
      briefs: rows.map((r) => ({
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
      })),
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    // Table may not exist on fresh deploy before ensureTables runs
    if (/relation .* does not exist/i.test(msg)) {
      return NextResponse.json({ briefs: [] })
    }
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
