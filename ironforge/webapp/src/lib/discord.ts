/**
 * IronForge Discord webhook helper.
 *
 * Posts trade-open and trade-close embeds for FLAME (2DTE bull put credit
 * spread). Set DISCORD_WEBHOOK_URL on the Render service — same webhook the
 * SpreadWorks deployment already uses.
 *
 * All posts are best-effort: failures log a warning and return false but
 * never throw, so a Discord outage cannot block the scanner.
 */

type DiscordField = { name: string; value: string; inline?: boolean }

type DiscordEmbed = {
  title?: string
  description?: string
  color?: number
  fields?: DiscordField[]
  footer?: { text: string }
  timestamp?: string
}

const COLOR_OPEN = 0x3b82f6 // blue
const COLOR_WIN = 0x00e676 // green
const COLOR_LOSS = 0xff1744 // red
const COLOR_FLAT = 0x9ca3af // gray

function nowCtIso(): string {
  return new Date().toISOString()
}

function fmtUsd(n: number, signed = false): string {
  const sign = signed && n > 0 ? '+' : ''
  return `${sign}$${n.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

async function postEmbed(embed: DiscordEmbed): Promise<boolean> {
  const url = process.env.DISCORD_WEBHOOK_URL
  if (!url) {
    console.warn('[discord] DISCORD_WEBHOOK_URL not set — skipping post')
    return false
  }
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ embeds: [embed] }),
    })
    if (res.status === 200 || res.status === 204) return true
    const body = await res.text().catch(() => '')
    console.error(`[discord] post failed ${res.status}: ${body.slice(0, 300)}`)
    return false
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[discord] post exception: ${msg}`)
    return false
  }
}

export async function postFlameOpen(args: {
  positionId: string
  putShort: number
  putLong: number
  contracts: number
  credit: number
  collateral: number
  maxProfit: number
  expiration: string
  spot: number
  vix: number
  accountBalance: number
}): Promise<boolean> {
  const {
    positionId, putShort, putLong, contracts, credit, collateral,
    maxProfit, expiration, spot, vix, accountBalance,
  } = args

  const riskPct = accountBalance > 0 ? (collateral / accountBalance) * 100 : 0

  const embed: DiscordEmbed = {
    title: `FLAME · OPEN · SPY ${putLong}/${putShort} Put Credit Spread`,
    color: COLOR_OPEN,
    fields: [
      { name: 'Strikes', value: `${putLong}P / ${putShort}P (long / short)`, inline: true },
      { name: 'Contracts', value: `${contracts}`, inline: true },
      { name: 'Expiration', value: expiration, inline: true },
      { name: 'Credit', value: `${fmtUsd(credit)} per spread`, inline: true },
      { name: 'Max Profit', value: fmtUsd(maxProfit), inline: true },
      { name: 'Collateral', value: `${fmtUsd(collateral)} (${riskPct.toFixed(1)}%)`, inline: true },
      { name: 'SPY', value: `$${spot.toFixed(2)}`, inline: true },
      { name: 'VIX', value: vix.toFixed(2), inline: true },
      { name: 'Account', value: fmtUsd(accountBalance), inline: true },
    ],
    footer: { text: `IronForge · FLAME · ${positionId}` },
    timestamp: nowCtIso(),
  }
  return postEmbed(embed)
}

export async function postFlameClose(args: {
  positionId: string
  putShort: number
  putLong: number
  contracts: number
  entryCredit: number
  closePrice: number
  realizedPnl: number
  reason: string
  expiration: string
}): Promise<boolean> {
  const {
    positionId, putShort, putLong, contracts, entryCredit,
    closePrice, realizedPnl, reason, expiration,
  } = args

  const maxProfitPerSpread = entryCredit
  const maxProfit = maxProfitPerSpread * 100 * contracts
  const pctOfMax = maxProfit > 0
    ? (realizedPnl / maxProfit) * 100
    : 0

  let color = COLOR_FLAT
  let footerNote = 'Closed.'
  if (realizedPnl > 0) {
    color = COLOR_WIN
    footerNote = 'Win recorded. Capital released.'
  } else if (realizedPnl < 0) {
    color = COLOR_LOSS
    footerNote = 'Loss taken. Risk contained.'
  }

  const embed: DiscordEmbed = {
    title: `FLAME · CLOSE · SPY ${putLong}/${putShort} Put Credit Spread`,
    color,
    fields: [
      { name: 'Reason', value: reason, inline: true },
      { name: 'Contracts', value: `${contracts}`, inline: true },
      { name: 'Expiration', value: expiration, inline: true },
      { name: 'Entry Credit', value: `${fmtUsd(entryCredit)} per spread`, inline: true },
      { name: 'Close Price', value: `${fmtUsd(closePrice)} per spread`, inline: true },
      { name: 'Realized P&L', value: `${fmtUsd(realizedPnl, true)} (${pctOfMax >= 0 ? '+' : ''}${pctOfMax.toFixed(1)}% of max)`, inline: false },
    ],
    footer: { text: `IronForge · FLAME · ${positionId} · ${footerNote}` },
    timestamp: nowCtIso(),
  }
  return postEmbed(embed)
}

export async function postFlameTest(): Promise<boolean> {
  const embed: DiscordEmbed = {
    title: 'FLAME · Webhook Test',
    description: 'If you can see this, IronForge can post to Discord.',
    color: COLOR_OPEN,
    footer: { text: 'IronForge · FLAME · Test Ping' },
    timestamp: nowCtIso(),
  }
  return postEmbed(embed)
}

export function isDiscordConfigured(): boolean {
  return !!process.env.DISCORD_WEBHOOK_URL
}
