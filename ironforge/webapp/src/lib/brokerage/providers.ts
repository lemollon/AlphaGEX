/**
 * The options-capable broker allowlist, shared by the dropdown and the connect route.
 *
 * It previously lived only inside api/onboarding/brokerage/brokerages/route.ts, where it
 * filtered what the UI OFFERS but not what connect ACCEPTS — connect passed the
 * client-supplied `broker` string straight to SnapTrade. A curated list that only the UI
 * honours is decorative: the API is the boundary, so the check belongs where the request
 * is handled (APP-041 "provider allowlist").
 *
 * IronForge runs US equity-OPTIONS strategies, so a broker that cannot place those is
 * worse than useless — the connection succeeds and the bot then silently cannot trade.
 * SnapTrade's raw partner list includes crypto exchanges and international brokers that
 * would do exactly that.
 *
 * Keep it a SUPERSET: brokers not yet enabled on our SnapTrade account simply never
 * appear until they are.
 */
export const OPTIONS_CAPABLE_SLUGS = new Set<string>([
  'TASTYTRADE',
  'ETRADE',
  'WEBULL-US',
  'PUBLIC',
  'ROBINHOOD',
  'SCHWAB',
  'FIDELITY',
  'TRADESTATION',
  'INTERACTIVE-BROKERS',
  'IBKR',
])

export function isOptionsCapable(slug: string): boolean {
  return OPTIONS_CAPABLE_SLUGS.has(slug.toUpperCase())
}

/** Connection providers IronForge implements. */
export const ALLOWED_PROVIDERS = ['snaptrade', 'tradier'] as const
export type BrokerageProvider = (typeof ALLOWED_PROVIDERS)[number]

export function isAllowedProvider(v: unknown): v is BrokerageProvider {
  return typeof v === 'string' && (ALLOWED_PROVIDERS as readonly string[]).includes(v)
}
