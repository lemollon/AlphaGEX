import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { snaptradeCanonicalJson, snaptradeSignatureValid } from '../snaptrade-webhook'

// Reference values generated with Python:
//   json.dumps(payload, separators=(",", ":"), sort_keys=True)
//   base64(hmac_sha256(b"test-consumer-key", canonical))
const payload = {
  webhookId: 'wh_1',
  eventType: 'CONNECTION_ADDED',
  userId: 'u-123',
  eventTimestamp: '2026-07-04T12:00:00Z',
  details: { brokerage: 'Alpaca', accounts: [1, 2], note: 'café ✓' },
  flag: true,
  nothing: null,
  num: 12.5,
}
const PY_CANON =
  '{"details":{"accounts":[1,2],"brokerage":"Alpaca","note":"caf\\u00e9 \\u2713"},"eventTimestamp":"2026-07-04T12:00:00Z","eventType":"CONNECTION_ADDED","flag":true,"nothing":null,"num":12.5,"userId":"u-123","webhookId":"wh_1"}'
const PY_SIG = 'qFSWhxeWLBQhKpABUPz4im49xCF9RDNyQEmSxTCfY40='

describe('snaptradeCanonicalJson', () => {
  it('matches Python json.dumps(sort_keys=True, separators=(",",":"))', () => {
    expect(snaptradeCanonicalJson(payload)).toBe(PY_CANON)
  })
})

describe('snaptradeSignatureValid', () => {
  const OLD = process.env.SNAPTRADE_CONSUMER_KEY
  beforeEach(() => { process.env.SNAPTRADE_CONSUMER_KEY = 'test-consumer-key' })
  afterEach(() => { process.env.SNAPTRADE_CONSUMER_KEY = OLD })

  it('accepts the Python-reference signature', () => {
    expect(snaptradeSignatureValid(payload, PY_SIG)).toBe(true)
  })
  it('rejects a tampered body', () => {
    expect(snaptradeSignatureValid({ ...payload, userId: 'u-999' }, PY_SIG)).toBe(false)
  })
  it('rejects a missing header', () => {
    expect(snaptradeSignatureValid(payload, null)).toBe(false)
  })
  it('rejects when the consumer key is unset', () => {
    delete process.env.SNAPTRADE_CONSUMER_KEY
    expect(snaptradeSignatureValid(payload, PY_SIG)).toBe(false)
  })
})
