import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { CustomersDbNotConfiguredError } from '@/lib/customers-db'
import { getReplies } from '@/lib/community/store'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/community/messages/[id]/replies — one message's thread (APP-055).
 *
 * Public like the main feed (reading Community needs no membership); paginated
 * oldest-first (cursor = last reply's created_at) so a long-running thread reads
 * top-to-bottom the way a conversation does, unlike the feed's newest-first.
 */
export async function GET(req: NextRequest, { params }: { params: { id: string } }) {
  try {
    const identity = await getCustomerIdentity()
    const viewerId = identity?.customerId ?? null
    const cursor = req.nextUrl.searchParams.get('cursor')
    const limitParam = req.nextUrl.searchParams.get('limit')
    const limit = limitParam ? Number(limitParam) : undefined

    const result = await getReplies(decodeURIComponent(params.id), viewerId, { cursor, limit })
    return NextResponse.json(result)
  } catch (e) {
    if (e instanceof CustomersDbNotConfiguredError) {
      return NextResponse.json({ error: 'Community is not available yet.' }, { status: 503 })
    }
    console.error('[community] GET replies failed:', e)
    return NextResponse.json({ error: 'Failed to load replies.' }, { status: 500 })
  }
}
