/**
 * SnapTrade client for the brokerage-connection sub-project (Model A: customers link their own
 * brokerage; per-trade approval). Lazy singleton over the official SDK, keyed on two env vars.
 *
 * Mirrors the `customers-db.ts` guard pattern: if the keys are unset (not yet provisioned in
 * Render), every accessor throws SnapTradeNotConfiguredError so routes degrade to a clean 503
 * instead of crashing. Build + tests pass with no keys; nothing live happens until provisioned.
 *
 * Secrets: SNAPTRADE_CONSUMER_KEY signs requests and is NEVER logged or returned to clients.
 * The per-user `userSecret` is encrypted at rest via @/lib/crypto/secret-box before storage.
 */
import { Snaptrade } from 'snaptrade-typescript-sdk'

export class SnapTradeNotConfiguredError extends Error {
  constructor() {
    super('SNAPTRADE_CLIENT_ID / SNAPTRADE_CONSUMER_KEY are not configured')
    this.name = 'SnapTradeNotConfiguredError'
  }
}

export function isSnapTradeConfigured(): boolean {
  return !!process.env.SNAPTRADE_CLIENT_ID && !!process.env.SNAPTRADE_CONSUMER_KEY
}

let _client: Snaptrade | null = null

/** Returns a configured Snaptrade SDK instance. Throws SnapTradeNotConfiguredError when unset. */
export function getSnapTrade(): Snaptrade {
  if (!isSnapTradeConfigured()) throw new SnapTradeNotConfiguredError()
  if (!_client) {
    _client = new Snaptrade({
      clientId: process.env.SNAPTRADE_CLIENT_ID as string,
      consumerKey: process.env.SNAPTRADE_CONSUMER_KEY as string,
    })
  }
  return _client
}
