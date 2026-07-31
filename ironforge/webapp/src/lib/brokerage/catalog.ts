/**
 * THE ordered broker catalog (UAT-015) — the single source every surface derives its
 * broker list, ordering, and display names from: Sparky's knowledge base, the
 * brokerage-settings labels, and (kept in sync manually for now) the enrollment
 * tiles in enroll/broker/BrokerClient.tsx.
 *
 * Order matters: Tradier first (IronForge's partner brokerage and the only direct
 * integration that reports options approval level), then tastytrade (multi-leg
 * options via SnapTrade — the automated-trading lane), then data-only connections.
 */

export interface BrokerCatalogEntry {
  /** Canonical lowercase slug — matches normalizeInstitutionSlug output casing. */
  slug: string
  displayName: string
  lane: 'oauth' | 'snaptrade'
  /** What automation can actually do there — keep claims factual (UAT-015). */
  trading: 'multi_leg' | 'data_only'
  partner?: boolean
  note?: string
}

export const SUPPORTED_BROKERS: readonly BrokerCatalogEntry[] = [
  {
    slug: 'tradier',
    displayName: 'Tradier',
    lane: 'oauth',
    trading: 'multi_leg',
    partner: true,
    note: 'IronForge partner brokerage — direct integration that verifies options approval level.',
  },
  {
    slug: 'tastytrade',
    displayName: 'tastytrade',
    lane: 'snaptrade',
    trading: 'multi_leg',
    note: 'Multi-leg options trading via SnapTrade.',
  },
  {
    slug: 'robinhood',
    displayName: 'Robinhood',
    lane: 'snaptrade',
    trading: 'data_only',
    note: 'View-only via SnapTrade — automated trading is not available there.',
  },
]

/** Display name for a broker slug/institution string; falls back to the input. */
export function brokerDisplayName(slugOrName: string | null | undefined): string | null {
  if (!slugOrName) return null
  const key = slugOrName.trim().toLowerCase()
  return SUPPORTED_BROKERS.find((b) => b.slug === key)?.displayName ?? slugOrName
}

/** Tradeable brokers in catalog order — the list quoted anywhere automation is discussed. */
export function tradeableBrokers(): readonly BrokerCatalogEntry[] {
  return SUPPORTED_BROKERS.filter((b) => b.trading === 'multi_leg')
}
