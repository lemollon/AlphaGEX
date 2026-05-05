import { NextRequest, NextResponse } from 'next/server'
import { findById } from '@/lib/forgeBriefings/repo'

export const dynamic = 'force-dynamic'

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  try {
    const brief = await findById(decodeURIComponent(params.id))
    if (!brief) return NextResponse.json({ error: 'not found' }, { status: 404 })
    return NextResponse.json({ brief })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
