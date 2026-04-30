import { NextResponse } from 'next/server'
import { isDiscordConfigured, postFlameClose } from '@/lib/discord'

export const dynamic = 'force-dynamic'

/**
 * POST /api/flame/discord/preview/close-win
 *
 * Posts a sample FLAME CLOSE (winning) embed using synthetic trade values.
 * Performance card uses REAL stats from flame_positions.
 */
export async function POST() {
  if (!isDiscordConfigured()) {
    return NextResponse.json(
      { ok: false, configured: false, detail: 'DISCORD_WEBHOOK_URL not set on this Render service' },
      { status: 503 },
    )
  }

  const ok = await postFlameClose({
    positionId: 'FLAME-PREVIEW-CLOSE-WIN',
    putShort: 555,
    putLong: 550,
    contracts: 12,
    entryCredit: 0.95,
    closePrice: 0.28,
    realizedPnl: 804,
    reason: 'profit_target_AFTERNOON',
    expiration: new Date(Date.now() + 1 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
  })

  return NextResponse.json({ ok, preview: 'close-win' }, { status: ok ? 200 : 502 })
}
