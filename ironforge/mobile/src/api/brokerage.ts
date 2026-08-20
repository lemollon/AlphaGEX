/**
 * Brokerage connection helpers (APP-014, APP-040/041).
 *
 * The endpoint has been live in production since PR #2740 — it already accepts a mobile
 * bearer through getCustomerIdentity — and nothing in this app called it. These are the
 * small shared pieces the Forge tile and the Account section both need.
 *
 * Account numbers never leave the server's encrypted column; `mask` is the only
 * identifier that crosses the wire, and it is the only one rendered.
 */
import type { BrokerageConnection, BrokerageConnections } from '@/api/types'

/**
 * Display name for a provider/brokerage slug.
 *
 * The server sends the real institution in `broker` (e.g. "tastytrade") and the
 * aggregator in `provider` (e.g. "snaptrade"). UAT-012 was exactly this going wrong —
 * every SnapTrade connection got labelled with the aggregator. Prefer `broker`, and
 * title-case anything unrecognised rather than printing a raw slug.
 */
const KNOWN: Record<string, string> = {
  tradier: 'Tradier',
  tastytrade: 'Tastytrade',
  snaptrade: 'SnapTrade',
  schwab: 'Schwab',
  ibkr: 'Interactive Brokers',
  robinhood: 'Robinhood',
  etrade: 'E*TRADE',
  fidelity: 'Fidelity',
}

export function brokerLabel(slug: string | null | undefined): string {
  if (!slug) return 'Brokerage'
  const key = slug.trim().toLowerCase()
  if (KNOWN[key]) return KNOWN[key]
  return key
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

/** Normalized connection health -> the four APP-014 states, plus a colour role. */
export type HealthKey = 'connected' | 'attention' | 'disconnected' | 'restricted'

export function health(status: string | null | undefined): { key: HealthKey; label: string } {
  const s = (status ?? '').toLowerCase()
  if (s === 'active' || s === 'connected' || s === 'ok') {
    return { key: 'connected', label: 'Connected' }
  }
  if (s === 'restricted') return { key: 'restricted', label: 'Restricted' }
  if (s === 'disconnected' || s === 'revoked' || s === 'expired') {
    return { key: 'disconnected', label: 'Disconnected' }
  }
  // Anything the server invents later reads as "look at this", never as healthy.
  return { key: 'attention', label: 'Attention required' }
}

export interface SoleConnection {
  provider: string
  broker: string | null
  mask: string | null
}

/**
 * The single connection, when there is exactly one.
 *
 * The Forge tile wants "Tradier •••• 4821" under the agent name, but no payload maps an
 * agent to a connection. With one connection the attribution is unambiguous; with two
 * it would be a guess, and a guess that puts the wrong account number under an agent on
 * a trading dashboard is worse than showing nothing. So: exactly one, or nothing.
 */
export function soleConnection(data: BrokerageConnections | undefined): SoleConnection | null {
  const conns = data?.connections ?? []
  if (conns.length !== 1) return null
  const c = conns[0]
  const masks = c.accounts.map((a) => a.mask).filter((m): m is string => !!m)
  return {
    provider: c.provider,
    broker: c.broker,
    mask: masks.length === 1 ? masks[0] : null,
  }
}

export type { BrokerageConnection, BrokerageConnections }
