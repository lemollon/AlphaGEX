/**
 * Pure routing decision for a tapped push notification (APP-034).
 *
 * Kept separate from push.ts so the "which screen does this payload open" rule can be
 * unit tested without expo-notifications, expo-router, or any native module in the
 * loop — see vitest.config.ts's note on why logic lives in plain src/**\/*.ts modules.
 *
 * Priority is deliberate: a trade-specific payload always wins over a generic agent
 * payload, which always wins over a generic account-tab payload. A trade_closed push
 * could plausibly carry both `trade_id` and `agent` — the trade is the more specific
 * destination, so it goes first.
 */

export interface PushNavData {
  trade_id?: unknown
  agent?: unknown
  kind?: unknown
}

export type AgentBot = 'spark' | 'flame'

const AGENT_BOTS: readonly AgentBot[] = ['spark', 'flame']

function isAgentBot(v: unknown): v is AgentBot {
  return typeof v === 'string' && (AGENT_BOTS as readonly string[]).includes(v)
}

/**
 * Resolve a notification's `data` payload to an in-app href, or `null` when the
 * payload carries none of the destinations this app knows how to open — a push from a
 * newer server version describing a screen this build does not have yet, for example.
 */
export function routeFor(
  data: PushNavData | null | undefined,
  hrefs: {
    tradeDetailHref: (id: string) => string
    agentDetailHref: (bot: AgentBot) => string
  },
): string | null {
  if (!data) return null

  if (typeof data.trade_id === 'string' && data.trade_id.length > 0) {
    return hrefs.tradeDetailHref(data.trade_id)
  }
  if (isAgentBot(data.agent)) {
    return hrefs.agentDetailHref(data.agent)
  }
  if (data.kind === 'brokerage' || data.kind === 'billing') {
    // The Account tab. expo-router route groups like (tabs) are not part of the URL —
    // app/(tabs)/account.tsx resolves to '/account', the same string RootLayout uses
    // for '/'.
    return '/account'
  }
  return null
}
