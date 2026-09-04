import type { AgentCardStats } from '@/api/types'
import type { StatItem } from '@/components/StatRow'
import { color } from '@/theme/tokens'

/**
 * Forge agent-card stat row (handoff/ledger-kpis.md PART 2): Account Capital,
 * Growth, Last 10, Best Trade — all LIFETIME, sourced from LiveAgent.stats.
 * Extracted from AgentTile so the formatting/colour rules are testable without
 * a React Native renderer, same reasoning as live/capital.ts.
 */

/** "$5,000" — whole dollars, no cents. "—" when the bot has no configured capital. */
export function formatAccountCapital(cents: number | null): string {
  if (cents == null) return '—'
  return `$${Math.round(cents / 100).toLocaleString('en-US')}`
}

/** "+6.8%" / "0.0%" / "-4.2%", green only when strictly positive — a flat or
 *  unknown lifetime return must not read as a win. */
export function formatGrowth(pct: number | null): { text: string; tone: string } {
  if (pct == null) return { text: '—', tone: color.textDim }
  const sign = pct > 0 ? '+' : ''
  return { text: `${sign}${pct.toFixed(1)}%`, tone: pct > 0 ? color.pos : pct < 0 ? color.neg : color.textDim }
}

/** "8–2" (en dash) over the last 10 closed trades — fewer than 10 counts what
 *  exists; zero closed trades is an honest "—", not "0–0". */
export function formatLast10(last10: AgentCardStats['last10']): { text: string; tone: string } {
  const { wins, losses } = last10
  if (wins + losses === 0) return { text: '—', tone: color.textDim }
  return { text: `${wins}–${losses}`, tone: wins > losses ? color.pos : color.text }
}

/** "+$122" whole dollars, always green — a "best trade" is by definition a
 *  win; an all-losing history has none, so it's "—", not the smallest loss. */
export function formatBestTrade(cents: number | null): { text: string; tone: string } {
  if (cents == null) return { text: '—', tone: color.textDim }
  return { text: `+$${Math.round(cents / 100).toLocaleString('en-US')}`, tone: color.pos }
}

/** Build the four StatRow items for one agent's card. `stats` is null while
 *  the payload is loading OR when the server couldn't compute it — both
 *  render as loading/"—", never a fabricated number. */
export function agentStatItems(stats: AgentCardStats | null, loading: boolean): StatItem[] {
  const growth = formatGrowth(stats?.growth_pct ?? null)
  const last10 = formatLast10(stats?.last10 ?? { wins: 0, losses: 0 })
  const bestTrade = formatBestTrade(stats?.best_trade_cents ?? null)

  return [
    {
      label: 'Account Capital',
      value: formatAccountCapital(stats?.account_capital_cents ?? null),
      tone: color.text,
      loading,
    },
    { label: 'Growth', value: growth.text, tone: growth.tone, loading },
    { label: 'Last 10', value: last10.text, tone: last10.tone, loading },
    { label: 'Best Trade', value: bestTrade.text, tone: bestTrade.tone, loading },
  ]
}
