import { NextRequest, NextResponse } from 'next/server'
import { eventCalendarRefresh } from '@/lib/eventCalendar/refresh'
import { getRefreshMeta } from '@/lib/eventCalendar/repo'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const meta = await getRefreshMeta()
    return NextResponse.json({ meta })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}

export async function POST(_req: NextRequest) {
  try {
    await eventCalendarRefresh({ force: true })
    const meta = await getRefreshMeta()
    return NextResponse.json({ ok: true, meta })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
