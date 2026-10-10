import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { CustomersDbNotConfiguredError } from '@/lib/customers-db'
import { blockUser, getMessageAuthor, listBlocked, unblockUser } from '@/lib/community/store'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Block / unblock another community member — the second half of Google Play's UGC
 * requirement (the first is reporting; see ../reports).
 *
 * A block is viewer-scoped and one-directional: the blocked author vanishes from the
 * blocker's feed and nobody else's. Nothing is deleted and the blocked user is not
 * notified, so blocking can never be used to erase someone else's history.
 *
 * The client identifies the target by `message_id`, not by user id: the feed never
 * exposes author ids, so resolving the author server-side keeps it that way.
 */
async function requireCustomer() {
  const identity = await getCustomerIdentity()
  return identity?.customerId ?? null
}

function unavailable(e: unknown) {
  if (e instanceof CustomersDbNotConfiguredError) {
    return NextResponse.json({ error: 'Community is not available yet.' }, { status: 503 })
  }
  return null
}

/** The viewer's block list, for the management screen. */
export async function GET() {
  try {
    const customerId = await requireCustomer()
    if (!customerId) return NextResponse.json({ blocked: [] })
    return NextResponse.json({ blocked: await listBlocked(customerId) })
  } catch (e) {
    const u = unavailable(e)
    if (u) return u
    console.error('[community] GET blocks failed:', e)
    return NextResponse.json({ error: 'Failed to load blocked members.' }, { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const customerId = await requireCustomer()
    if (!customerId) {
      return NextResponse.json({ error: 'Log in to block a member.' }, { status: 401 })
    }
    const body = await req.json().catch(() => ({}))
    const messageId = typeof body.message_id === 'string' ? body.message_id : ''
    if (!messageId) {
      return NextResponse.json({ error: 'A message is required.' }, { status: 400 })
    }

    const author = await getMessageAuthor(messageId)
    if (!author) {
      return NextResponse.json({ error: 'That message no longer exists.' }, { status: 404 })
    }
    if (!author.userId) {
      // FORGE/SYSTEM posts have no user to block. Say so plainly rather than
      // silently succeeding and leaving the post visible.
      return NextResponse.json(
        { error: 'Forge posts are written by IronForge and cannot be blocked.' },
        { status: 400 },
      )
    }
    if (author.userId === customerId) {
      return NextResponse.json({ error: 'You cannot block yourself.' }, { status: 400 })
    }

    await blockUser(customerId, author.userId)
    return NextResponse.json({ status: 'success', blocked_name: author.senderName })
  } catch (e) {
    const u = unavailable(e)
    if (u) return u
    console.error('[community] POST block failed:', e)
    return NextResponse.json({ error: 'Failed to block the member.' }, { status: 500 })
  }
}

/** Unblock. Takes the user id returned by GET — the block list is the only place it appears. */
export async function DELETE(req: NextRequest) {
  try {
    const customerId = await requireCustomer()
    if (!customerId) {
      return NextResponse.json({ error: 'Log in to manage blocked members.' }, { status: 401 })
    }
    const body = await req.json().catch(() => ({}))
    const userId =
      typeof body.user_id === 'string' ? body.user_id : req.nextUrl.searchParams.get('user_id') ?? ''
    if (!userId) return NextResponse.json({ error: 'A member is required.' }, { status: 400 })

    await unblockUser(customerId, userId)
    return NextResponse.json({ status: 'success' })
  } catch (e) {
    const u = unavailable(e)
    if (u) return u
    console.error('[community] DELETE block failed:', e)
    return NextResponse.json({ error: 'Failed to unblock the member.' }, { status: 500 })
  }
}
