import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { CustomersDbNotConfiguredError } from '@/lib/customers-db'
import { toggleReaction } from '@/lib/community/store'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const ALLOWED_EMOJI = new Set(['👍', '🔥', '💯', '😂', '🎯', '🙌'])

export async function POST(req: NextRequest) {
  try {
    const session = await getCustomerSession()
    if (!session.customerId) {
      return NextResponse.json({ error: 'Log in to react.' }, { status: 401 })
    }
    const body = await req.json().catch(() => ({}))
    const messageId = typeof body.message_id === 'string' ? body.message_id : ''
    const emoji = typeof body.emoji === 'string' ? body.emoji : ''
    if (!messageId || !ALLOWED_EMOJI.has(emoji)) {
      return NextResponse.json({ error: 'Invalid reaction.' }, { status: 400 })
    }
    const result = await toggleReaction(messageId, session.customerId, emoji)
    return NextResponse.json({ status: 'success', result })
  } catch (e) {
    if (e instanceof CustomersDbNotConfiguredError) {
      return NextResponse.json({ error: 'Community is not available yet.' }, { status: 503 })
    }
    console.error('[community] POST reaction failed:', e)
    return NextResponse.json({ error: 'Failed to react.' }, { status: 500 })
  }
}
