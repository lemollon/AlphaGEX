/**
 * The floating "trade opened/closed" banner (10.4 design `.banner` / `banner()`) —
 * NOT the same mechanism as alerts/banner.ts's `pickBanner` (brokerage/membership/
 * market-condition, one at a time, inline at the top of the Forge scroll). This one
 * is a transient overlay that floats in from the top of the screen on a REAL trade
 * event and auto-dismisses — same severity-free, single-purpose shape as the
 * prototype's `banner(k,title,sub,onTap)`.
 *
 * The event source is the existing push-notification payload (api/types.ts
 * NotificationKind 'trade_opened' | 'trade_closed'), delivered live via
 * expo-notifications' foreground listener — this is real data a trade event
 * actually produced server-side, not a local guess derived from polling deltas.
 * Pulled out as a pure function so the "which payload shows a banner, and what it
 * says" rule is unit-tested without expo-notifications in the loop, same pattern as
 * notifications/route-for.ts.
 */
import { tradeDetailHref } from '@/ledger/detail'
import { agentDetailHref, type AgentBot } from '@/agents/routes'

export interface TradeBannerNotification {
  title?: string | null
  body?: string | null
  data?: {
    kind?: unknown
    trade_id?: unknown
    agent?: unknown
  } | null
}

export interface TradeBanner {
  bot: string | null
  title: string
  subtitle: string
  href: string | null
}

const AGENT_BOTS: readonly AgentBot[] = ['spark', 'flame', 'ember']

function isAgentBot(v: unknown): v is AgentBot {
  return typeof v === 'string' && (AGENT_BOTS as readonly string[]).includes(v)
}

/**
 * Returns `null` for every notification kind that is not a trade open/close — the
 * host component must not float a banner for, say, a brokerage-health push, which
 * already has its own in-page AlertBanner treatment.
 */
export function tradeBannerFromNotification(n: TradeBannerNotification): TradeBanner | null {
  const kind = n.data?.kind
  if (kind !== 'trade_opened' && kind !== 'trade_closed') return null

  const bot = isAgentBot(n.data?.agent) ? n.data!.agent : null
  const tradeId = typeof n.data?.trade_id === 'string' ? n.data!.trade_id : null
  const href = tradeId ? tradeDetailHref(tradeId) : bot ? agentDetailHref(bot) : null

  return {
    bot,
    title: n.title?.trim() || (kind === 'trade_opened' ? 'Trade opened' : 'Trade closed'),
    subtitle: n.body?.trim() || '',
    href,
  }
}
