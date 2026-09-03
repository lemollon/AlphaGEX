import { ctDateString } from './track'

/**
 * Pure shaping helpers for GET /api/ops/traffic. Kept DB-free so the day-range
 * math and the zero-filling/sorting logic are unit-testable without a
 * database — the route itself only runs the grouped SQL and hands the raw
 * rows to these functions.
 */

export interface PageViewRow {
  day: string // 'YYYY-MM-DD'
  path: string
  visitors: number
  views: number
}

export interface WaitlistDayRow {
  day: string // 'YYYY-MM-DD'
  c: number
}

export interface PageSummary {
  path: string
  totalVisitors: number
  totalViews: number
  byDay: Record<string, { visitors: number; views: number }>
}

/**
 * Ascending list of 'YYYY-MM-DD' America/Chicago calendar dates, `count` days
 * ending today (inclusive).
 *
 * Anchored at UTC noon of today's CT date, then walked back in whole 24h steps.
 * UTC noon always falls within CT's daytime on both sides of a DST transition,
 * so subtracting exact days can never accidentally cross into the wrong CT
 * calendar date the way subtracting from local midnight could.
 */
export function ctDayRange(count: number, now: Date = new Date()): string[] {
  const n = Math.max(1, Math.trunc(count))
  const [y, m, d] = ctDateString(now).split('-').map(Number)
  const anchorMs = Date.UTC(y, m - 1, d, 12)
  const out: string[] = []
  for (let i = n - 1; i >= 0; i--) {
    out.push(ctDateString(new Date(anchorMs - i * 86_400_000)))
  }
  return out
}

/**
 * Shapes grouped (day, path) → {visitors, views} rows into the sorted,
 * zero-filled page list the dashboard renders. `totalVisitors`/`totalViews`
 * are sums of the PER-DAY counts — a visitor active on 3 different days within
 * the range counts 3 times, since page_views has no cross-day identity to
 * de-duplicate on (see the table's PRIMARY KEY).
 */
export function shapePages(rows: readonly PageViewRow[], days: readonly string[]): PageSummary[] {
  const byPath = new Map<string, PageSummary>()
  for (const row of rows) {
    let entry = byPath.get(row.path)
    if (!entry) {
      entry = { path: row.path, totalVisitors: 0, totalViews: 0, byDay: {} }
      byPath.set(row.path, entry)
    }
    entry.byDay[row.day] = { visitors: row.visitors, views: row.views }
    entry.totalVisitors += row.visitors
    entry.totalViews += row.views
  }
  const pages = Array.from(byPath.values())
  for (const entry of pages) {
    for (const day of days) {
      if (!entry.byDay[day]) entry.byDay[day] = { visitors: 0, views: 0 }
    }
  }
  return pages.sort((a, b) => b.totalVisitors - a.totalVisitors)
}

/** Zero-fills a day→count map (waitlist submissions per CT date) over the full day range. */
export function shapeWaitlistByDay(rows: readonly WaitlistDayRow[], days: readonly string[]): Record<string, number> {
  const map: Record<string, number> = {}
  for (const day of days) map[day] = 0
  for (const row of rows) map[row.day] = row.c
  return map
}
