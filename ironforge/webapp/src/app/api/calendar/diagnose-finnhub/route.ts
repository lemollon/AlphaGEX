import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

/**
 * Diagnostic: returns the raw Finnhub /calendar/economic response filtered to
 * US events only (no regex/impact filter), so the operator can see exactly
 * what's available before we tighten the parser.  Cheap to call (one
 * upstream request to Finnhub).
 */
export async function GET(req: NextRequest) {
  const apiKey = process.env.FINNHUB_API_KEY
  if (!apiKey) {
    return NextResponse.json({ error: 'FINNHUB_API_KEY not set' }, { status: 503 })
  }
  const sp = new URL(req.url).searchParams
  const days = Math.max(1, Math.min(parseInt(sp.get('days') || '60'), 395))
  const today = new Date()
  const fmt = (d: Date) => `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
  const from = fmt(today)
  const to_ = new Date(today); to_.setUTCDate(to_.getUTCDate() + days)
  const url = `https://finnhub.io/api/v1/calendar/economic?from=${from}&to=${fmt(to_)}&token=${encodeURIComponent(apiKey)}`
  try {
    const res = await fetch(url, { method: 'GET' })
    if (!res.ok) {
      return NextResponse.json({ error: `Finnhub ${res.status}: ${await res.text().catch(() => '')}` }, { status: 502 })
    }
    const json: any = await res.json()
    const all = Array.isArray(json.economicCalendar) ? json.economicCalendar : []
    const usOnly = all.filter((r: any) => r?.country === 'US')
    const usHigh = usOnly.filter((r: any) => (r.impact || '').toLowerCase() === 'high')
    // Distinct event titles, with counts and impact distribution
    const distinctTitles: Record<string, { count: number; impacts: Record<string, number>; firstDate: string }> = {}
    for (const r of usOnly) {
      if (!r?.event || typeof r.event !== 'string') continue
      const k = r.event
      if (!distinctTitles[k]) distinctTitles[k] = { count: 0, impacts: {}, firstDate: r.time || '' }
      distinctTitles[k].count++
      const imp = (r.impact || 'unknown').toLowerCase()
      distinctTitles[k].impacts[imp] = (distinctTitles[k].impacts[imp] || 0) + 1
    }
    return NextResponse.json({
      window: { from, to: fmt(to_), days },
      counts: { total_us: usOnly.length, us_high: usHigh.length },
      distinct_titles_us: distinctTitles,
      sample_high_impact_us: usHigh.slice(0, 30).map((r: any) => ({
        time: r.time, event: r.event, impact: r.impact, actual: r.actual ?? null,
      })),
    })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
