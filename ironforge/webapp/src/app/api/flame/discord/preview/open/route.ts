import { NextResponse } from 'next/server'
import { isDiscordConfigured, postFlameOpen } from '@/lib/discord'

export const dynamic = 'force-dynamic'

/**
 * POST /api/flame/discord/preview/open
 *
 * Posts a sample FLAME OPEN embed to DISCORD_WEBHOOK_URL using realistic
 * synthetic trade values. The performance card is built from REAL stats
 * pulled from flame_positions, so what you see is exactly what live trades
 * will produce.
 */
export async function POST() {
  if (!isDiscordConfigured()) {
    return NextResponse.json(
      { ok: false, configured: false, detail: 'DISCORD_WEBHOOK_URL not set on this Render service' },
      { status: 503 },
    )
  }

  const ok = await postFlameOpen({
    positionId: 'FLAME-PREVIEW-OPEN',
    putShort: 555,
    putLong: 550,
    contracts: 12,
    credit: 0.95,
    collateral: 4860,
    maxProfit: 1140,
    expiration: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
    spot: 568.42,
    vix: 16.41,
    accountBalance: 50000,
  })

  return NextResponse.json({ ok, preview: 'open' }, { status: ok ? 200 : 502 })
}
