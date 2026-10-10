import { NextRequest, NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isPublicMode } from '@/lib/auth/access'
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { ctDayRange, shapePages, shapeWaitlistByDay, type PageViewRow, type WaitlistDayRow } from '@/lib/traffic'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/ops/traffic?days=30 — the data feed for the /ops/traffic dashboard.
 *
 * Two grouped queries (page_views by day+path, waitlist_submissions by CT
 * day) plus three cheap scalar aggregates for the summary tiles — no N+1: the
 * per-page/per-day shaping happens in lib/traffic.ts against the already-
 * fetched rows, never with an extra query per row.
 *
 * Operator-gated the same way as /api/ops/customers: a public-mode deployment
 * has no login wall at all, so it is treated as already-authorized; everyone
 * else needs an operator session.
 */

const DEFAULT_DAYS = 30
const MAX_DAYS = 90

async function requireOperator(): Promise<{ ok: true } | { ok: false; res: NextResponse }> {
  if (isPublicMode()) return { ok: true }
  const ops = await getSession()
  if (!ops.userId) {
    return { ok: false, res: NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 }) }
  }
  return { ok: true }
}

export async function GET(req: NextRequest) {
  const gate = await requireOperator()
  if (!gate.ok) return gate.res
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'Customers DB not configured.' }, { status: 503 })
  }

  const requested = Number(req.nextUrl.searchParams.get('days') ?? DEFAULT_DAYS)
  const days = Number.isFinite(requested) && requested > 0 ? Math.min(Math.trunc(requested), MAX_DAYS) : DEFAULT_DAYS
  const dayList = ctDayRange(days)
  const startDay = dayList[0]
  const today = dayList[dayList.length - 1]
  const last7Start = ctDayRange(7)[0]

  const [pageRows, waitlistDayRows, waitlistTotalRows, firstSeenRows, todayRows, last7Rows] = await Promise.all([
    customerQuery<PageViewRow>(
      `SELECT day::text AS day, path, COUNT(*)::int AS visitors, SUM(hits)::int AS views
         FROM page_views
        WHERE day >= $1::date
        GROUP BY day, path`,
      [startDay],
    ),
    customerQuery<WaitlistDayRow>(
      `SELECT (created_at AT TIME ZONE 'America/Chicago')::date::text AS day, COUNT(*)::int AS c
         FROM waitlist_submissions
        WHERE (created_at AT TIME ZONE 'America/Chicago')::date >= $1::date
        GROUP BY 1`,
      [startDay],
    ),
    customerQuery<{ c: number }>(`SELECT COUNT(*)::int AS c FROM waitlist_submissions`),
    customerQuery<{ min_first_seen: string | null }>(`SELECT MIN(first_seen)::text AS min_first_seen FROM page_views`),
    // Site-wide DISTINCT visitor counts. Deliberately separate from the
    // per-page `pages[].byDay` numbers above: those are per-path, so a visitor
    // who viewed two pages the same day counts twice there. These two are the
    // honest site-wide figures the summary tiles need.
    customerQuery<{ c: number }>(`SELECT COUNT(DISTINCT visitor)::int AS c FROM page_views WHERE day = $1::date`, [today]),
    customerQuery<{ c: number }>(`SELECT COUNT(DISTINCT visitor)::int AS c FROM page_views WHERE day >= $1::date`, [
      last7Start,
    ]),
  ])

  return NextResponse.json({
    ok: true,
    generatedAt: new Date().toISOString(),
    tz: 'America/Chicago',
    days: dayList,
    pages: shapePages(pageRows, dayList),
    waitlistSubmissions: {
      total: waitlistTotalRows[0]?.c ?? 0,
      byDay: shapeWaitlistByDay(waitlistDayRows, dayList),
    },
    // Earliest event ever recorded, regardless of the requested window — drives
    // the "Collecting since …" empty state on the dashboard.
    firstSeen: firstSeenRows[0]?.min_first_seen ?? null,
    distinctVisitorsToday: todayRows[0]?.c ?? 0,
    distinctVisitorsLast7Days: last7Rows[0]?.c ?? 0,
  })
}
