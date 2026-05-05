import { NextRequest, NextResponse } from 'next/server'
import { listCalendarBadges } from '@/lib/forgeBriefings/repo'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const sp = new URL(req.url).searchParams
  const from = sp.get('from')
  const to = sp.get('to')
  if (!from || !to) return NextResponse.json({ error: 'from + to required (YYYY-MM-DD)' }, { status: 400 })
  try {
    const rows = await listCalendarBadges(from, to)
    const byDate: Record<string, any> = {}
    for (const r of rows) {
      if (!byDate[r.brief_date]) {
        byDate[r.brief_date] = {
          brief_date: r.brief_date,
          per_bot: {} as Record<string, { mood: string | null; risk_score: number | null; brief_id: string }>,
          lead: null as null | { brief_id: string; risk_score: number | null; first_sentence: string },
        }
      }
      byDate[r.brief_date].per_bot[r.bot] = {
        mood: r.mood, risk_score: r.risk_score, brief_id: r.brief_id,
      }
      const isPortfolio = r.bot === 'portfolio'
      if (!byDate[r.brief_date].lead || isPortfolio) {
        byDate[r.brief_date].lead = {
          brief_id: r.brief_id, risk_score: r.risk_score, first_sentence: r.first_sentence,
        }
      }
    }
    return NextResponse.json({ days: Object.values(byDate) })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
