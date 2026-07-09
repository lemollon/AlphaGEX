import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { CustomersDbNotConfiguredError } from '@/lib/customers-db'
import { moderateMessage } from '@/lib/community/forge-ai'
import {
  DEFAULT_CHANNEL,
  getChannelId,
  getDisplayName,
  getFeed,
  insertMessage,
  maybeForgeReply,
  maybePostScheduledUpdate,
  seedWelcomeMessage,
  touchPresence,
} from '@/lib/community/store'
import { customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function dbUnavailable() {
  return NextResponse.json({ error: 'Community is not available yet.' }, { status: 503 })
}

/** Feed read — public like /api/live/* while the site is dark. */
export async function GET(req: NextRequest) {
  try {
    const channel = req.nextUrl.searchParams.get('channel') || DEFAULT_CHANNEL
    const session = await getCustomerSession()
    const viewerId = session.customerId ?? null

    await seedWelcomeMessage()
    if (viewerId) {
      const name = await getDisplayName(viewerId)
      await touchPresence(viewerId, name)
    }
    // Lazy scheduled Forge posts — fire-and-forget; next poll picks them up.
    void maybePostScheduledUpdate()

    const feed = await getFeed(channel, viewerId)
    return NextResponse.json(feed)
  } catch (e) {
    if (e instanceof CustomersDbNotConfiguredError) return dbUnavailable()
    console.error('[community] GET messages failed:', e)
    return NextResponse.json({ error: 'Failed to load messages.' }, { status: 500 })
  }
}

/** Post a message — requires a customer session; moderated before persistence. */
export async function POST(req: NextRequest) {
  try {
    const session = await getCustomerSession()
    if (!session.customerId) {
      return NextResponse.json({ error: 'Log in to join the conversation.' }, { status: 401 })
    }
    const body = await req.json().catch(() => ({}))
    const channelSlug = typeof body.channel === 'string' ? body.channel : DEFAULT_CHANNEL
    const message = typeof body.message === 'string' ? body.message.trim() : ''
    if (!message) return NextResponse.json({ error: 'Message is empty.' }, { status: 400 })
    if (message.length > 2000) {
      return NextResponse.json({ error: 'Message is too long (2000 characters max).' }, { status: 400 })
    }

    const channelId = await getChannelId(channelSlug)
    if (!channelId) return NextResponse.json({ error: 'Unknown channel.' }, { status: 404 })

    // Moderation executes BEFORE persistence (design doc acceptance criterion).
    const verdict = await moderateMessage(message)
    if (!verdict.ok) {
      await customerExecute(
        `INSERT INTO community_moderation_events (user_id, message_excerpt, category, score, action)
         VALUES ($1, $2, $3, $4, 'REJECTED')`,
        [session.customerId, message.slice(0, 200), verdict.category ?? 'UNKNOWN', verdict.score ?? null],
      ).catch(() => undefined)
      return NextResponse.json(
        { code: verdict.category ?? 'MODERATION_REJECTED', error: 'Message violates community guidelines.' },
        { status: 422 },
      )
    }

    const senderName = await getDisplayName(session.customerId)
    const messageId = await insertMessage({
      channelId,
      userId: session.customerId,
      senderName,
      senderType: 'USER',
      message,
    })
    await touchPresence(session.customerId, senderName)

    // Forge replies asynchronously; the 4s poll surfaces it.
    void maybeForgeReply({ channelId, senderName, message })

    return NextResponse.json({ messageId, status: 'success' })
  } catch (e) {
    if (e instanceof CustomersDbNotConfiguredError) return dbUnavailable()
    console.error('[community] POST message failed:', e)
    return NextResponse.json({ error: 'Failed to send message.' }, { status: 500 })
  }
}
