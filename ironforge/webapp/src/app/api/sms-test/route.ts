/**
 * GET  /api/sms-test → which phone-alert channels are configured? (no secrets leaked)
 * POST /api/sms-test → send a test alert over every configured phone channel
 *                      (ntfy push / carrier SMS gateway / Twilio) so you can
 *                      confirm delivery before relying on alerts.
 */
import { NextResponse } from 'next/server'
import {
  isSmsConfigured,
  isNtfyConfigured,
  isSmsGatewayConfigured,
  isTwilioConfigured,
  isDiscordConfigured,
  smsRecipients,
  smsGatewayRecipients,
  sendVolAlertSms,
} from '@/lib/sms'

export const dynamic = 'force-dynamic'

function maskPhone(p: string): string {
  return p.length <= 4 ? '***' : `${p.slice(0, 3)}***${p.slice(-2)}`
}

function channels() {
  return {
    discord: isDiscordConfigured(),
    ntfy: isNtfyConfigured(),
    sms_gateway: isSmsGatewayConfigured(),
    sms_gateway_recipients: smsGatewayRecipients().map(maskPhone),
    twilio: isTwilioConfigured(),
    twilio_recipients: smsRecipients().map(maskPhone),
  }
}

export async function GET() {
  return NextResponse.json({
    sms_configured: isSmsConfigured(),
    channels: channels(),
    needs: 'ALERT_DISCORD_WEBHOOK | ALERT_NTFY_TOPIC | ALERT_SMS_GATEWAY_TO (+Resend) | TWILIO_* + ALERT_SMS_TO',
  })
}

export async function POST() {
  if (!isSmsConfigured()) {
    return NextResponse.json({
      sent: false,
      error:
        'No phone channel configured — set ALERT_NTFY_TOPIC, ALERT_SMS_GATEWAY_TO (with Resend), or the TWILIO_* vars on the ironforge service.',
    })
  }
  const res = await sendVolAlertSms({
    signalKey: 'sms_test',
    reason: 'confirmed',
    headline: 'Test alert — if you got this, phone alerts are wired.',
  })
  return NextResponse.json({ ...res, channels: channels() })
}
