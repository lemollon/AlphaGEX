/**
 * Agent detail route helper (APP-024). Own module so WP-E's push tap handler
 * (src/notifications/route-for.ts) can deep-link `data.agent` without importing a screen.
 */

export type AgentBot = 'spark' | 'flame'

export function agentDetailHref(bot: AgentBot): string {
  return `/agents/${bot}`
}
