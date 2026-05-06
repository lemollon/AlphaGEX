import { NextRequest, NextResponse } from 'next/server'
import { isEventBlackoutActive } from '@/lib/eventCalendar/gate'
import { listUpcomingEvents } from '@/lib/eventCalendar/repo'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const bot = (searchParams.get('bot') || 'flame').toLowerCase()
  if (!['flame', 'spark', 'inferno'].includes(bot)) {
    return NextResponse.json({ error: 'invalid bot' }, { status: 400 })
  }
  try {
    const now = new Date()
    const status = await isEventBlackoutActive(bot, now)
    // next_blackout = next halt-triggering event whose halt window hasn't started yet.
    // Informational Tier-2/3 events (PCE, GDP, ISM, JOLTs) are skipped.
    const upcoming = await listUpcomingEvents()
    const next = upcoming.find(e => e.halts_bots && new Date(e.halt_start_ts as any) > now) ?? null
    return NextResponse.json({
      bot,
      now: now.toISOString(),
      blackout: status,
      next_blackout: next ? {
        event_id: next.event_id,
        title: next.title,
        halt_start_ts: next.halt_start_ts,
        halt_end_ts: next.halt_end_ts,
        event_date: next.event_date,
        event_time_ct: next.event_time_ct,
        event_type: next.event_type,
        resume_offset_min: next.resume_offset_min,
      } : null,
    })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
