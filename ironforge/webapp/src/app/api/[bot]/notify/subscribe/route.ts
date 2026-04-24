/**
 * SPARK SMS subscription endpoint (Commit N1).
 *
 *   POST /api/spark/notify/subscribe?phone=+1XXXXXXXXXX[&label=...][&open=1&close=1]
 *     Adds (or re-enables) a subscriber. Phone must be in E.164 format.
 *   DELETE /api/spark/notify/subscribe?phone=+1XXXXXXXXXX
 *     Disables a subscriber (soft delete — toggles enabled=false so
 *     re-subscribe via POST restores preferences).
 *
 * SPARK-only. Other bots return 400.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, validateBot } from '@/lib/db'

export const dynamic = 'force-dynamic'

function normalizePhone(raw: string | null): string | null {
  if (!raw) return null
  const trimmed = raw.trim()
  if (!trimmed) return null
  // Strip every non-digit except a leading '+'
  const plus = trimmed.startsWith('+') ? '+' : ''
  const digits = trimmed.replace(/[^\d]/g, '')
  if (!digits) return null
  // E.164: if caller forgot the +, add one; US numbers need + prefix too.
  if (plus) return `+${digits}`
  // No leading +, assume US (+1) if 10 digits, else trust raw
  if (digits.length === 10) return `+1${digits}`
  if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`
  return `+${digits}`
}

function parseBool(raw: string | null, fallback: boolean): boolean {
  if (raw == null) return fallback
  const s = raw.trim().toLowerCase()
  if (s === '1' || s === 'true' || s === 'yes' || s === 'on') return true
  if (s === '0' || s === 'false' || s === 'no' || s === 'off') return false
  return fallback
}

export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== 'spark') {
    return NextResponse.json({ error: 'SPARK-only.' }, { status: 400 })
  }

  const phone = normalizePhone(req.nextUrl.searchParams.get('phone'))
  if (!phone) {
    return NextResponse.json({ error: 'phone query param required (E.164 format, e.g. +15551234567)' }, { status: 400 })
  }
  const label = req.nextUrl.searchParams.get('label') ?? null
  const notifyOpen = parseBool(req.nextUrl.searchParams.get('open'), true)
  const notifyClose = parseBool(req.nextUrl.searchParams.get('close'), true)

  try {
    const rows = await dbQuery(
      `INSERT INTO spark_sms_subscribers (phone_number, enabled, notify_open, notify_close, label)
       VALUES ($1, TRUE, $2, $3, $4)
       ON CONFLICT (phone_number)
       DO UPDATE SET enabled = TRUE,
                     notify_open = EXCLUDED.notify_open,
                     notify_close = EXCLUDED.notify_close,
                     label = COALESCE(EXCLUDED.label, spark_sms_subscribers.label),
                     updated_at = NOW()
       RETURNING id, phone_number, enabled, notify_open, notify_close, label, created_at, updated_at`,
      [phone, notifyOpen, notifyClose, label],
    )
    return NextResponse.json({
      subscribed: true,
      subscriber: rows[0],
      note: 'Will receive a text on every SPARK trade open AND close from now on. Texts start once TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER are set in IronForge Render env.',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== 'spark') {
    return NextResponse.json({ error: 'SPARK-only.' }, { status: 400 })
  }
  const phone = normalizePhone(req.nextUrl.searchParams.get('phone'))
  if (!phone) return NextResponse.json({ error: 'phone query param required' }, { status: 400 })

  try {
    const rows = await dbQuery(
      `UPDATE spark_sms_subscribers
       SET enabled = FALSE, updated_at = NOW()
       WHERE phone_number = $1
       RETURNING id, phone_number, enabled`,
      [phone],
    )
    if (rows.length === 0) {
      return NextResponse.json({ unsubscribed: false, note: 'No such subscriber.' }, { status: 404 })
    }
    return NextResponse.json({ unsubscribed: true, subscriber: rows[0] })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
