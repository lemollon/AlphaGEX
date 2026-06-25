/**
 * GET  /api/sms-test → is Twilio configured? (no secrets leaked)
 * POST /api/sms-test → send a test SMS to ALERT_SMS_TO so you can confirm the
 *                      Twilio creds + phone number work before relying on alerts.
 */
import { NextResponse } from 'next/server'
import { isSmsConfigured, smsRecipients, sendVolAlertSms } from '@/lib/sms'

export const dynamic = 'force-dynamic'

function maskPhone(p: string): string {
  return p.length <= 4 ? '***' : `${p.slice(0, 3)}***${p.slice(-2)}`
}

export async function GET() {
  return NextResponse.json({
    sms_configured: isSmsConfigured(),
    recipients: smsRecipients().map(maskPhone),
    needs: ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_FROM_NUMBER', 'ALERT_SMS_TO'],
  })
}

export async function POST() {
  if (!isSmsConfigured()) {
    return NextResponse.json({
      sent: false,
      error: 'Twilio not configured — set TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER / ALERT_SMS_TO on the ironforge service.',
    })
  }
  const res = await sendVolAlertSms({
    signalKey: 'sms_test',
    reason: 'confirmed',
    headline: 'Test alert — if you got this, phone alerts are wired.',
  })
  return NextResponse.json({ ...res, recipients: smsRecipients().map(maskPhone) })
}
