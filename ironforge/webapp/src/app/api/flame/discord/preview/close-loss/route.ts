import { NextResponse } from 'next/server'
import { isDiscordConfigured, postFlameClose } from '@/lib/discord'

export const dynamic = 'force-dynamic'

/**
 * POST /api/flame/discord/preview/close-loss
 *
 * Posts a sample FLAME CLOSE (losing, stop-loss) embed using synthetic
 * trade values. Performance card uses REAL stats from flame_positions.
 */
export async function POST() {
  if (!isDiscordConfigured()) {
    return NextResponse.json(
      { ok: false, configured: false, detail: 'DISCORD_WEBHOOK_URL not set on this Render service' },
      { status: 503 },
    )
  }

  const ok = await postFlameClose({
    positionId: 'FLAME-PREVIEW-CLOSE-LOSS',
    putShort: 560,
    putLong: 555,
    contracts: 10,
    entryCredit: 0.85,
    closePrice: 1.95,
    realizedPnl: -1100,
    reason: 'stop_loss',
    expiration: new Date(Date.now() + 1 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
  })

  return NextResponse.json({ ok, preview: 'close-loss' }, { status: ok ? 200 : 502 })
}
