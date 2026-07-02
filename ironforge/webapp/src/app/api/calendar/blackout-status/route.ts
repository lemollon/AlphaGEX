import { NextRequest, NextResponse } from 'next/server'
import { isEventBlackoutActive, BLACKOUT_HALT_ENABLED } from '@/lib/eventCalendar/gate'
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
    // When the blackout halt is globally disabled there are no upcoming halts to
    // advertise, so suppress next_blackout too — the UI should show nothing.
    const upcoming = BLACKOUT_HALT_ENABLED ? await listUpcomingEvents() : []
    const next = upcoming.find(e => e.halts_bots && new Date(e.halt_start_ts as any) > now) ?? null
    return NextResponse.json({
      bot,
      now: now.toISOString(),
      halt_enabled: BLACKOUT_HALT_ENABLED,
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
