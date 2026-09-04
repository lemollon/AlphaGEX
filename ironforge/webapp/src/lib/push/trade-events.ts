/**
 * Copy + payload builders for the two trade-lifecycle pushes (UAT #7:
 * notification on trade OPEN and trade CLOSE).
 *
 * Kept separate from dispatch.ts/render.ts, same reason as trade-events being its
 * own module elsewhere in this codebase: the copy — and the dedupe key, which per
 * types.ts's rule MUST be derived from an immutable id, never a timestamp — needs
 * to be unit-testable without a DB, the Expo transport, or scanner.ts in the loop.
 *
 * Scoped to LiveBot ('spark' | 'flame') only: those are the only two bots on the
 * customer product surface (webapp/src/lib/live/bots.ts LIVE_BOTS) and the only
 * two the mobile app's route-for.ts / agents/[bot].tsx know how to open.
 */
import { LIVE_BOT_LABEL, type LiveBot } from '@/lib/live/bots'
import type { NotificationEvent } from '@/lib/push/types'

/**
 * Flame's mascot emoji matches the existing Discord copy (discord.ts postFlameOpen:
 * "🔥 FLAME LIT"). Spark has no established emoji anywhere else in this codebase —
 * ⚡ was chosen to match the bot's name. Flag for Leron if a different mark is wanted.
 */
const AGENT_EMOJI: Record<LiveBot, string> = {
  spark: '⚡',
  flame: '🔥',
}

/**
 * U+2212 MINUS SIGN — not the ASCII hyphen render.ts's formatAmount uses for the
 * lock-screen amount. The trade-closed subtitle copy spec calls for the typographic
 * minus specifically.
 */
function formatPnlForSubtitle(n: number): string {
  const sign = n >= 0 ? '+' : '−'
  return `${sign}$${Math.abs(n).toFixed(2)}`
}

export interface TradeOpenedArgs {
  bot: LiveBot
  positionId: string
  occurredAt: string
}

export interface TradeClosedArgs {
  bot: LiveBot
  positionId: string
  realizedPnl: number
  occurredAt: string
}

/**
 * Deep-links to the AGENT detail page (`/agents/{bot}`), not the trade ledger page:
 * GET /api/live/trades/{id} only ever serves CLOSED trades (see the route's own
 * comment), so a trade_id here would 404 on tap before the position ever closes.
 */
export function buildTradeOpenedEvent(args: TradeOpenedArgs): NotificationEvent {
  const label = LIVE_BOT_LABEL[args.bot]
  return {
    category: 'trade_opened',
    eventKey: `trade_opened:${args.positionId}`,
    occurredAt: args.occurredAt,
    route: '/live',
    routeParams: { account: args.bot },
    title: 'Trade Opened',
    subtitle: `${AGENT_EMOJI[args.bot]} ${label} entered a new position`,
    body: "Trade is live. We'll handle it from here.",
  }
}

/**
 * Deep-links to the trade's ledger detail — a just-closed trade is exactly what
 * GET /api/live/trades/{id} serves.
 */
export function buildTradeClosedEvent(args: TradeClosedArgs): NotificationEvent {
  const label = LIVE_BOT_LABEL[args.bot]
  return {
    category: 'trade_closed',
    eventKey: `trade_closed:${args.positionId}`,
    occurredAt: args.occurredAt,
    route: '/live',
    routeParams: { account: args.bot, tradeId: args.positionId },
    title: 'Trade Closed',
    subtitle: `✅ ${label} closed ${formatPnlForSubtitle(args.realizedPnl)}`,
    body: 'Position exited successfully and added to your Ledger.',
    amount: args.realizedPnl,
  }
}
