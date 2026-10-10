import type { LiveAgent } from '@/api/types'

export interface PositionsPush {
  bot: string
  trade: LiveAgent['trade']
}

/**
 * Applies one positions-stream push onto the cached /api/live/agents list.
 *
 * The stream only ever carries `trade` (open positions + unrealized P&L) for
 * the bots this viewer owns — never `state`/`account`/`stats`, which keep
 * coming from the slower /api/live/agents poll. Merging only that one field
 * means the stream can't drift the rest of a tile out of sync with itself,
 * and a bot the push didn't mention (nothing has streamed for it yet, or its
 * REST half errored) keeps whatever it already had rather than being
 * dropped from the list.
 */
export function mergeAgentsTrade(current: LiveAgent[], pushes: PositionsPush[]): LiveAgent[] {
  if (pushes.length === 0) return current
  const byBot = new Map(pushes.map((p) => [p.bot, p.trade]))
  return current.map((agent) => (byBot.has(agent.bot) ? { ...agent, trade: byBot.get(agent.bot)! } : agent))
}
