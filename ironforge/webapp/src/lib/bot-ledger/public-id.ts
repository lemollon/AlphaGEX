import { createHash } from 'crypto'

import { PUBLIC_ID_SALT, type LedgerBot } from './constants'

/**
 * Opaque, stable public reference for a trade.
 *
 * Deterministic (same row always yields the same id, across deploys and in
 * tests) and non-sequential, so it cannot be walked to infer how many trades
 * exist or in what order they were written.
 */
export function publicIdFor(bot: LedgerBot, rowId: number | string): string {
  const digest = createHash('sha256').update(`${PUBLIC_ID_SALT}|${bot}|${rowId}`).digest('hex')
  return `trd_${digest.slice(0, 12)}`
}
