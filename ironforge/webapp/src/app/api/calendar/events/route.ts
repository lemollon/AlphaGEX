import { NextRequest, NextResponse } from 'next/server'
import { listEventsInRange, listUpcomingEvents, upsertEvent } from '@/lib/eventCalendar/repo'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const from = searchParams.get('from')
  const to = searchParams.get('to')
  try {
    const events = (from && to)
      ? await listEventsInRange(from, to)
      : await listUpcomingEvents()
    return NextResponse.json({ events })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    if (!body.title || !body.event_date || !body.event_time_ct) {
      return NextResponse.json(
        { error: 'title, event_date, event_time_ct required' },
        { status: 400 },
      )
    }
    const id = `manual:${crypto.randomUUID()}`
    const result = await upsertEvent({
      event_id: id,
      source: 'manual',
      event_type: body.event_type || 'CUSTOM',
      title: body.title,
      description: body.description ?? null,
      event_date: body.event_date,
      event_time_ct: body.event_time_ct,
      resume_offset_min: body.resume_offset_min ?? 60,
      created_by: 'admin-ui',
    })
    return NextResponse.json({ event_id: id, inserted: result.inserted })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
