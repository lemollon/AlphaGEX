/**
 * IronForge Discord webhook helper — FLAME edition.
 *
 * Posts trade-open and trade-close updates that include:
 *   - Strategy explainer (why we took the trade, what the exit plan is)
 *   - Live stats from flame_positions (win rate, current streak, cumulative P&L)
 *   - ASCII progress bar for % of max profit
 *   - Emoji-driven flair based on outcome
 *   - Custom webhook username so the bot announces itself as "FLAME · IronForge"
 *   - Two embeds per message (trade card + stats card)
 *
 * Configure via env: DISCORD_WEBHOOK_URL on the IronForge Render service.
 * All posts are best-effort — failures log a warning but never throw.
 */

import { query, botTable } from './db'

type DiscordField = { name: string; value: string; inline?: boolean }

type DiscordEmbed = {
  title?: string
  description?: string
  color?: number
  fields?: DiscordField[]
  footer?: { text: string }
  timestamp?: string
  author?: { name: string; icon_url?: string }
}

const COLOR_OPEN = 0xff6a00 // flame orange
const COLOR_WIN = 0x00e676 // green
const COLOR_LOSS = 0xff1744 // red
const COLOR_FLAT = 0x9ca3af // gray
const COLOR_STATS = 0x1f2937 // slate

const WEBHOOK_USERNAME = 'FLAME · IronForge'
const WEBHOOK_AVATAR = 'https://em-content.zobj.net/source/microsoft-teams/337/fire_1f525.png'

function nowIso(): string {
  return new Date().toISOString()
}

function ctNow(): string {
  return new Date().toLocaleString('en-US', {
    timeZone: 'America/Chicago',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  }) + ' CT'
}

function fmtUsd(n: number, signed = false): string {
  const sign = signed && n > 0 ? '+' : ''
  return `${sign}$${n.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function progressBar(pct: number, width = 14): string {
  const clamped = Math.max(0, Math.min(100, pct))
  const filled = Math.round((clamped / 100) * width)
  return '█'.repeat(filled) + '░'.repeat(width - filled)
}

function streakEmoji(kind: 'W' | 'L' | 'F' | null, len: number): string {
  if (!kind || len === 0) return 'No streak'
  if (kind === 'W') return `🔥 W${len} streak`
  if (kind === 'L') return `❄️ L${len} streak`
  return `⚪ F${len}`
}

type FlameStats = {
  totalClosed: number
  totalWins: number
  totalLosses: number
  winRate: number
  totalPnl: number
  last10Wins: number
  last10Total: number
  last10WinRate: number
  streakKind: 'W' | 'L' | 'F' | null
  streakLen: number
  bestWin: number
  worstLoss: number
}

const EMPTY_STATS: FlameStats = {
  totalClosed: 0, totalWins: 0, totalLosses: 0, winRate: 0, totalPnl: 0,
  last10Wins: 0, last10Total: 0, last10WinRate: 0,
  streakKind: null, streakLen: 0, bestWin: 0, worstLoss: 0,
}

async function getFlameStats(): Promise<FlameStats> {
  try {
    const rows = await query(
      `SELECT realized_pnl
       FROM ${botTable('flame', 'positions')}
       WHERE status IN ('closed','expired')
         AND realized_pnl IS NOT NULL
         AND COALESCE(account_type, 'sandbox') = 'sandbox'
       ORDER BY close_time DESC`,
      [],
    )
    if (!rows.length) return { ...EMPTY_STATS }

    const pnls: number[] = rows.map((r: any) => Number(r.realized_pnl) || 0)
    const totalPnl = pnls.reduce((a, b) => a + b, 0)
    const totalWins = pnls.filter((p) => p > 0).length
    const totalLosses = pnls.filter((p) => p < 0).length
    const totalClosed = pnls.length
    const winRate = totalClosed ? (totalWins / totalClosed) * 100 : 0
    const bestWin = pnls.length ? Math.max(...pnls) : 0
    const worstLoss = pnls.length ? Math.min(...pnls) : 0

    const last10 = pnls.slice(0, 10)
    const last10Wins = last10.filter((p) => p > 0).length
    const last10Total = last10.length
    const last10WinRate = last10Total ? (last10Wins / last10Total) * 100 : 0

    let streakKind: 'W' | 'L' | 'F' | null = null
    let streakLen = 0
    if (pnls.length) {
      const first = pnls[0]
      streakKind = first > 0 ? 'W' : first < 0 ? 'L' : 'F'
      for (const p of pnls) {
        const k = p > 0 ? 'W' : p < 0 ? 'L' : 'F'
        if (k === streakKind) streakLen++
        else break
      }
    }

    return {
      totalClosed, totalWins, totalLosses, winRate, totalPnl,
      last10Wins, last10Total, last10WinRate,
      streakKind, streakLen, bestWin, worstLoss,
    }
  } catch (err: unknown) {
    console.warn(`[discord] stats query failed: ${err instanceof Error ? err.message : err}`)
    return { ...EMPTY_STATS }
  }
}

function buildStatsEmbed(stats: FlameStats, includeBanner = true): DiscordEmbed {
  const pnlEmoji = stats.totalPnl > 0 ? '📈' : stats.totalPnl < 0 ? '📉' : '➖'
  const winRateBar = progressBar(stats.winRate, 14)

  const lines: string[] = []
  if (includeBanner) {
    lines.push(`${pnlEmoji} **All-Time P&L:** ${fmtUsd(stats.totalPnl, true)}`)
    lines.push('')
  }
  lines.push(`\`${winRateBar}\` ${stats.winRate.toFixed(1)}% · ${stats.totalWins}W / ${stats.totalLosses}L`)

  const desc = lines.join('\n')

  return {
    color: COLOR_STATS,
    description: desc,
    fields: [
      {
        name: '🏅 Last 10',
        value: `${stats.last10Wins}/${stats.last10Total} wins · ${stats.last10WinRate.toFixed(0)}%`,
        inline: true,
      },
      {
        name: '🔥 Streak',
        value: streakEmoji(stats.streakKind, stats.streakLen),
        inline: true,
      },
      {
        name: '🎯 Closed Trades',
        value: `${stats.totalClosed}`,
        inline: true,
      },
      {
        name: '💎 Best Win',
        value: stats.bestWin > 0 ? fmtUsd(stats.bestWin, true) : '—',
        inline: true,
      },
      {
        name: '💀 Worst Loss',
        value: stats.worstLoss < 0 ? fmtUsd(stats.worstLoss, true) : '—',
        inline: true,
      },
      {
        name: '⏱️ As Of',
        value: ctNow(),
        inline: true,
      },
    ],
    footer: { text: 'IronForge · FLAME · 2DTE Bull Put Credit Spread' },
  }
}

async function postEmbeds(embeds: DiscordEmbed[], opts?: { content?: string }): Promise<boolean> {
  const url = process.env.DISCORD_WEBHOOK_URL
  if (!url) {
    console.warn('[discord] DISCORD_WEBHOOK_URL not set — skipping post')
    return false
  }
  try {
    const payload = {
      username: WEBHOOK_USERNAME,
      avatar_url: WEBHOOK_AVATAR,
      content: opts?.content,
      embeds,
    }
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
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
  const breakeven = putShort - credit
  const otmPct = spot > 0 ? ((spot - putShort) / spot) * 100 : 0

  // Profit-target ladder targets (mirrors getSlidingProfitTarget defaults)
  const ptMorning = credit * 0.30
  const ptMidday = credit * 0.40
  const ptAfter = credit * 0.50
  const stopLoss = credit * 2.0

  const desc = [
    `🔥 **A new spread is live.** Premium collected, theta clock started.`,
    ``,
    `**Why now:** VIX in tradeable range, account has buying power, no open position. We sell ~1.0σ OTM and let theta do the work.`,
    ``,
    `**Trade Plan**`,
    `🟢 **Entry** — sold the ${putShort}/${putLong} put credit spread for **${fmtUsd(credit)}** per spread`,
    `🎯 **Profit Target** — close when cost ≤ ${fmtUsd(ptMorning)} (morning), ${fmtUsd(ptMidday)} (midday), ${fmtUsd(ptAfter)} (afternoon)`,
    `🛑 **Stop Loss** — close when cost ≥ ${fmtUsd(stopLoss)} (2× the credit)`,
    `⏰ **EOD Safety** — auto-close all positions by 2:50 PM CT on expiry day`,
  ].join('\n')

  const tradeEmbed: DiscordEmbed = {
    author: { name: '🔥 FLAME LIT — Position Opened' },
    title: `SPY ${putShort}P / ${putLong}P · ${contracts}× · exp ${expiration}`,
    color: COLOR_OPEN,
    description: desc,
    fields: [
      { name: '💰 Credit', value: `${fmtUsd(credit)}/spread\n**${fmtUsd(maxProfit)}** total`, inline: true },
      { name: '🛡️ Collateral', value: `${fmtUsd(collateral)}\n${riskPct.toFixed(1)}% of acct`, inline: true },
      { name: '📐 Cushion', value: `Short ${putShort}P\n${otmPct.toFixed(2)}% OTM`, inline: true },
      { name: '🪨 Breakeven', value: `$${breakeven.toFixed(2)}\n(short − credit)`, inline: true },
      { name: '📊 SPY / VIX', value: `$${spot.toFixed(2)} / ${vix.toFixed(2)}`, inline: true },
      { name: '🏦 Account', value: fmtUsd(accountBalance), inline: true },
    ],
    footer: { text: `IronForge · FLAME · ${positionId}` },
    timestamp: nowIso(),
  }

  const stats = await getFlameStats()
  const statsEmbed = buildStatsEmbed(stats, true)
  statsEmbed.author = { name: '📊 FLAME · Performance Snapshot' }

  return postEmbeds([tradeEmbed, statsEmbed])
}

function classifyClose(reason: string, realizedPnl: number): {
  flair: string
  color: number
  footerNote: string
  outcomeLine: string
} {
  const r = reason.toLowerCase()
  if (r.startsWith('profit_target')) {
    const tier = reason.split('_').pop() || ''
    return {
      flair: '🟢 PROFIT TARGET HIT',
      color: COLOR_WIN,
      footerNote: 'Win recorded. Capital released.',
      outcomeLine: `Cost-to-close fell into the ${tier.toUpperCase()} profit-target tier — we paid less to close than we collected to open.`,
    }
  }
  if (r === 'stop_loss') {
    return {
      flair: '🔴 STOP LOSS TRIGGERED',
      color: COLOR_LOSS,
      footerNote: 'Loss taken. Risk contained.',
      outcomeLine: 'Cost-to-close hit 2× the entry credit — discipline says exit, no hero plays.',
    }
  }
  if (r.startsWith('eod')) {
    return {
      flair: '⏰ EOD SAFETY CLOSE',
      color: realizedPnl >= 0 ? COLOR_WIN : COLOR_LOSS,
      footerNote: 'Day ended. No overnight risk.',
      outcomeLine: 'Closed at 2:50 PM CT to prevent overnight gap risk.',
    }
  }
  if (r.startsWith('stale') || r.startsWith('expired')) {
    return {
      flair: '📜 EXPIRED / STALE',
      color: realizedPnl >= 0 ? COLOR_WIN : COLOR_LOSS,
      footerNote: 'Cleaned up.',
      outcomeLine: 'Position rolled off — past expiration or carried over from a prior session.',
    }
  }
  return {
    flair: realizedPnl > 0 ? '🟢 POSITION CLOSED' : realizedPnl < 0 ? '🔴 POSITION CLOSED' : '⚪ POSITION CLOSED',
    color: realizedPnl > 0 ? COLOR_WIN : realizedPnl < 0 ? COLOR_LOSS : COLOR_FLAT,
    footerNote: 'Closed.',
    outcomeLine: `Closed by trigger: \`${reason}\`.`,
  }
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

  const maxProfit = entryCredit * 100 * contracts
  const pctOfMax = maxProfit > 0 ? (realizedPnl / maxProfit) * 100 : 0
  const bar = progressBar(pctOfMax, 14)
  const cls = classifyClose(reason, realizedPnl)

  const desc = [
    `**${cls.flair}**`,
    ``,
    cls.outcomeLine,
    ``,
    `**Outcome bar (% of max profit)**`,
    `\`${bar}\` ${pctOfMax >= 0 ? '+' : ''}${pctOfMax.toFixed(1)}%`,
  ].join('\n')

  const tradeEmbed: DiscordEmbed = {
    author: { name: `${realizedPnl > 0 ? '🟢' : realizedPnl < 0 ? '🔴' : '⚪'} FLAME · Position Closed` },
    title: `SPY ${putShort}P / ${putLong}P · ${contracts}× · exp ${expiration}`,
    color: cls.color,
    description: desc,
    fields: [
      { name: '💰 Realized P&L', value: `**${fmtUsd(realizedPnl, true)}**`, inline: true },
      { name: '🎯 Trigger', value: `\`${reason}\``, inline: true },
      { name: '📅 Expiration', value: expiration, inline: true },
      { name: '🟢 Entry Credit', value: `${fmtUsd(entryCredit)}/spread`, inline: true },
      { name: '🔚 Close Price', value: `${fmtUsd(closePrice)}/spread`, inline: true },
      { name: '🧮 P&L Math', value: `(entry − close) × ${contracts} × 100`, inline: true },
    ],
    footer: { text: `IronForge · FLAME · ${positionId} · ${cls.footerNote}` },
    timestamp: nowIso(),
  }

  const stats = await getFlameStats()
  const statsEmbed = buildStatsEmbed(stats, true)
  statsEmbed.author = { name: '📊 FLAME · Updated Performance' }

  // High-flair callouts when the trade was notable
  let content: string | undefined
  if (stats.streakKind === 'W' && stats.streakLen >= 3) {
    content = `🔥🔥🔥 **W${stats.streakLen} streak.** FLAME is hot.`
  } else if (stats.streakKind === 'L' && stats.streakLen >= 3) {
    content = `❄️ L${stats.streakLen} streak. Time to slow down.`
  } else if (realizedPnl > 0 && stats.bestWin > 0 && realizedPnl >= stats.bestWin) {
    content = `🏆 **NEW BEST WIN** — ${fmtUsd(realizedPnl, true)}`
  } else if (realizedPnl < 0 && stats.worstLoss < 0 && realizedPnl <= stats.worstLoss) {
    content = `💀 New worst loss. Reviewing the tape.`
  }

  return postEmbeds([tradeEmbed, statsEmbed], { content })
}

export async function postFlameTest(): Promise<boolean> {
  const stats = await getFlameStats()
  const banner: DiscordEmbed = {
    author: { name: '🔥 FLAME · Webhook Test' },
    title: 'IronForge connected',
    color: COLOR_OPEN,
    description: 'If you can read this, FLAME can post live trade updates to this channel.',
    footer: { text: 'IronForge · FLAME · Test Ping' },
    timestamp: nowIso(),
  }
  const statsEmbed = buildStatsEmbed(stats, true)
  statsEmbed.author = { name: '📊 FLAME · Current Performance' }
  return postEmbeds([banner, statsEmbed])
}

export function isDiscordConfigured(): boolean {
  return !!process.env.DISCORD_WEBHOOK_URL
}
