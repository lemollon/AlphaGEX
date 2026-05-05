import { NextRequest, NextResponse } from 'next/server'
import { findById } from '@/lib/forgeBriefings/repo'
import { renderBriefImage } from '@/lib/forgeBriefings/png'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const brief = await findById(decodeURIComponent(params.id)).catch(() => null)
  if (!brief) return NextResponse.json({ error: 'not found' }, { status: 404 })
  return renderBriefImage(brief)
}
