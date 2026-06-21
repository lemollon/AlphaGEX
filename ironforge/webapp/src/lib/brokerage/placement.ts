/**
 * Pure provider dispatch for placing an approved order (brokerage sub-project, multi-provider).
 * Keeps the "which placer" decision unit-testable and in one place; the approve route performs
 * the actual network call for whichever provider this returns. No I/O.
 */

export type BrokerageProvider = 'snaptrade' | 'tradier'
export type PlacementTarget = 'snaptrade' | 'tradier' | 'unsupported'

/** Map a stored approval's provider to the placement path the approve route should take. */
export function resolvePlacement(provider: string | null | undefined): PlacementTarget {
  switch (provider) {
    case 'snaptrade':
      return 'snaptrade'
    case 'tradier':
      return 'tradier'
    default:
      // Legacy rows predate the provider column default; treat unknown as unsupported so we never
      // guess which broker to send a real order to.
      return 'unsupported'
  }
}
