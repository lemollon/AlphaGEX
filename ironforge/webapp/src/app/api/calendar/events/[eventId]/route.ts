import { NextRequest, NextResponse } from 'next/server'
import { upsertEvent, deactivateEvent } from '@/lib/eventCalendar/repo'

export const dynamic = 'force-dynamic'

export async function PUT(req: NextRequest, { params }: { params: { eventId: string } }) {
  if (!params.eventId.startsWith('manual:')) {
    return NextResponse.json({ error: 'Only manual events are editable' }, { status: 403 })
  }
  try {
    const body = await req.json()
    if (!body.title || !body.event_date || !body.event_time_ct) {
      return NextResponse.json(
        { error: 'title, event_date, event_time_ct required' },
        { status: 400 },
      )
    }
    const result = await upsertEvent({
      event_id: params.eventId,
      source: 'manual',
      event_type: body.event_type || 'CUSTOM',
      title: body.title,
      description: body.description ?? null,
      event_date: body.event_date,
      event_time_ct: body.event_time_ct,
      resume_offset_min: body.resume_offset_min ?? 60,
      created_by: 'admin-ui',
    })
    return NextResponse.json({ event_id: params.eventId, inserted: result.inserted })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}

export async function DELETE(_req: NextRequest, { params }: { params: { eventId: string } }) {
  if (!params.eventId.startsWith('manual:')) {
    return NextResponse.json({ error: 'Only manual events are deletable' }, { status: 403 })
  }
  try {
    const rows = await deactivateEvent(params.eventId)
    return NextResponse.json({ deactivated: rows })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
