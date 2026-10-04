/**
 * Agent detail route helper (APP-024). Own module so WP-E's push tap handler
 * (src/notifications/route-for.ts) can deep-link `data.agent` without importing a screen.
 *
 * 'ember' added for the 10.4 redesign — Ember is a single customer-facing agent (free,
 * one account per person, $500–$2,000 capital), exactly like Spark/Flame are each one
 * agent. There is no sub-agent concept: "REFLEX" is Ember's internal strategy name
 * only and is never shown in the app (Leron, 2026-10-04 — overrides an earlier brief
 * that described REFLEX as a visible sub-agent).
 */

export type AgentBot = 'spark' | 'flame' | 'ember'

export function agentDetailHref(bot: AgentBot): string {
  return `/agents/${bot}`
}
