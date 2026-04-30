import { NextResponse } from 'next/server'
import { isDiscordConfigured, postFlameTest } from '@/lib/discord'

export const dynamic = 'force-dynamic'

/**
 * POST /api/flame/discord/test
 *
 * Posts a small test embed to DISCORD_WEBHOOK_URL so you can verify the
 * webhook works without waiting for a real trade.
 */
export async function POST() {
  if (!isDiscordConfigured()) {
    return NextResponse.json(
      { ok: false, configured: false, detail: 'DISCORD_WEBHOOK_URL not set on this Render service' },
      { status: 503 },
    )
  }

  const ok = await postFlameTest()
  return NextResponse.json(
    { ok, configured: true },
    { status: ok ? 200 : 502 },
  )
}

export async function GET() {
  return NextResponse.json({ configured: isDiscordConfigured() })
}
