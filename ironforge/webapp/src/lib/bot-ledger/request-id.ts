import { randomUUID } from 'crypto'

/**
 * Per-request correlation id (spec 13.3 / 14.4).
 *
 * Emitted as `x-request-id` on every response and echoed in the body of every
 * error, so a customer report ("the ledger showed an error at 14:12") can be
 * tied to a specific server log line without the payload itself carrying
 * anything sensitive.
 *
 * Honours an inbound `x-request-id` when a proxy already assigned one, so the
 * id survives the whole hop rather than being reassigned at this layer.
 */
export function requestIdFrom(headers: Headers): string {
  const inbound = headers.get('x-request-id')
  if (inbound && /^[\w.:-]{8,128}$/.test(inbound)) return inbound
  return `req_${randomUUID().replace(/-/g, '').slice(0, 24)}`
}
