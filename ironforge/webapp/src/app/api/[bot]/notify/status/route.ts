/**
 * SPARK SMS subscriber status (Commit N1).
 *
 *   GET /api/spark/notify/status
 *     Returns all subscribers with the last 4 digits of each phone
 *     masked for privacy, plus config check: which Twilio env vars
 *     are present (not the values — just presence).
 *
 * SPARK-only.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, validateBot } from '@/lib/db'

export const dynamic = 'force-dynamic'

function maskPhone(phone: string): string {
  if (!phone) return '—'
  if (phone.length <= 4) return `*${phone}`
  const tail = phone.slice(-4)
  const masked = '*'.repeat(Math.max(0, phone.length - 4))
  return `${masked}${tail}`
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== 'spark') {
    return NextResponse.json({ error: 'SPARK-only.' }, { status: 400 })
  }

  const twilioConfigured =
    !!process.env.TWILIO_ACCOUNT_SID &&
    !!process.env.TWILIO_AUTH_TOKEN &&
    !!process.env.TWILIO_FROM_NUMBER
  const env_flags = {
    TWILIO_ACCOUNT_SID_set: !!process.env.TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN_set: !!process.env.TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER_set: !!process.env.TWILIO_FROM_NUMBER,
  }

  try {
    const rows = await dbQuery(
      `SELECT id, phone_number, enabled, notify_open, notify_close, label, created_at, updated_at
       FROM spark_sms_subscribers
       ORDER BY id ASC`,
    )
    const subscribers = rows.map((r) => ({
      id: Number(r.id),
      phone_masked: maskPhone(String(r.phone_number)),
      enabled: Boolean(r.enabled),
      notify_open: Boolean(r.notify_open),
      notify_close: Boolean(r.notify_close),
      label: r.label ?? null,
      created_at: r.created_at,
      updated_at: r.updated_at,
    }))
    const enabled = subscribers.filter((s) => s.enabled).length
    return NextResponse.json({
      total: subscribers.length,
      enabled,
      twilio_configured: twilioConfigured,
      env_flags,
      subscribers,
      note: twilioConfigured
        ? 'Twilio is configured — subscribers will receive texts on SPARK trades.'
        : 'Twilio env vars missing (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER). Subscribers are stored but no texts are sent until these are set.',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    if (/relation .* does not exist/i.test(msg)) {
      return NextResponse.json({
        total: 0, enabled: 0, twilio_configured: twilioConfigured, env_flags, subscribers: [],
        note: 'Table not yet created. It auto-creates on first DB connection.',
      })
    }
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
