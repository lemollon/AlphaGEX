/**
 * SPARK SMS test send (Commit N1).
 *
 *   POST /api/spark/notify/test?phone=+1XXXXXXXXXX
 *     Sends a one-time test SMS to the given number via Twilio. Does
 *     NOT create a subscriber row; pure smoke-test for env config.
 *
 * SPARK-only.
 */
import { NextRequest, NextResponse } from 'next/server'
import { validateBot } from '@/lib/db'
import { sendTestSms } from '@/lib/notifications'

export const dynamic = 'force-dynamic'

function normalizePhone(raw: string | null): string | null {
  if (!raw) return null
  const trimmed = raw.trim()
  const plus = trimmed.startsWith('+') ? '+' : ''
  const digits = trimmed.replace(/[^\d]/g, '')
  if (!digits) return null
  if (plus) return `+${digits}`
  if (digits.length === 10) return `+1${digits}`
  if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`
  return `+${digits}`
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
    return NextResponse.json({ error: 'phone query param required (E.164 format)' }, { status: 400 })
  }

  try {
    const result = await sendTestSms(phone)
    return NextResponse.json({
      phone,
      ...result,
      note: result.success
        ? 'Test SMS sent. Check the phone.'
        : result.error === 'TWILIO_NOT_CONFIGURED'
          ? 'Twilio env vars missing in IronForge Render (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER). Set them and retry.'
          : `Twilio send failed: ${result.error}`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
