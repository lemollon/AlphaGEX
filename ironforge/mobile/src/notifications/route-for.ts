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
 *
 * #269: the server now also sends a precomputed `link` alongside, never instead of,
 * trade_id/agent/kind (lib/push/render.ts's deriveLink() — the exact same priority as
 * below, computed once, server-side). A recognized `link` is used directly; the
 * trade_id/agent/kind fields are the fallback for an older server build that has
 * never heard of `link`, or a `link` value this build does not recognize.
 */

export interface PushNavData {
  trade_id?: unknown
  agent?: unknown
  kind?: unknown
  link?: unknown
}

export type AgentBot = 'spark' | 'flame'

const AGENT_BOTS: readonly AgentBot[] = ['spark', 'flame']

function isAgentBot(v: unknown): v is AgentBot {
  return typeof v === 'string' && (AGENT_BOTS as readonly string[]).includes(v)
}

/** Every href shape this app can actually open — same set routeFor() itself can
 *  produce below. A `link` outside this list falls through to the field-by-field
 *  fallback rather than being trusted verbatim. */
const KNOWN_LINK_PREFIXES = ['/trade/', '/agents/']

function isKnownLink(v: unknown): v is string {
  if (typeof v !== 'string' || !v || !v.startsWith('/') || v.startsWith('//')) return false
  if (v === '/account') return true
  return KNOWN_LINK_PREFIXES.some((p) => v.startsWith(p) && v.length > p.length)
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

  if (isKnownLink(data.link)) return data.link

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
