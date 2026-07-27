import { describe, expect, it } from 'vitest'

import { CALCULATION_VERSION, SNAPSHOT_BUCKET_MS } from '../constants'
import {
  bucketStartMs,
  classifySnapshot,
  digestOf,
  makeSnapshotId,
  parseSnapshotId,
} from '../snapshot'
import type { PublicLedgerTrade } from '../types'

const BASE = Date.UTC(2026, 6, 26, 21, 0, 0)

function dto(over: Partial<PublicLedgerTrade> = {}): PublicLedgerTrade {
  return {
    public_id: 'trd_abc123abc123',
    closed_date: '2026-07-25',
    bot: 'spark',
    setup: 'SPY 1DTE Iron Condor',
    buying_power_used: '500.00',
    net_result: '42.00',
    return_on_bp_pct: '8.40',
    outcome: 'win',
    ...over,
  }
}

describe('bucketing', () => {
  it('holds one bucket across the interval and rolls after it', () => {
    expect(bucketStartMs(BASE)).toBe(bucketStartMs(BASE + SNAPSHOT_BUCKET_MS - 1))
    expect(bucketStartMs(BASE)).not.toBe(bucketStartMs(BASE + SNAPSHOT_BUCKET_MS))
  })
})

describe('digestOf', () => {
  it('is stable regardless of the order rows arrive in', () => {
    const a = [dto({ public_id: 'trd_1' }), dto({ public_id: 'trd_2' })]
    expect(digestOf(a)).toBe(digestOf([...a].reverse()))
  })

  it('changes when any displayed value changes', () => {
    const base = digestOf([dto()])
    expect(digestOf([dto({ net_result: '43.00' })])).not.toBe(base)
    expect(digestOf([dto({ outcome: 'loss' })])).not.toBe(base)
    expect(digestOf([dto({ closed_date: '2026-07-24' })])).not.toBe(base)
    expect(digestOf([dto({ buying_power_used: '501.00' })])).not.toBe(base)
  })

  it('changes when a row is added or removed', () => {
    expect(digestOf([dto()])).not.toBe(digestOf([dto(), dto({ public_id: 'trd_2' })]))
    expect(digestOf([])).not.toBe(digestOf([dto()]))
  })
})

describe('snapshot ids', () => {
  it('round-trips', () => {
    const id = makeSnapshotId(bucketStartMs(BASE), 'a8f3c1d2')
    const parsed = parseSnapshotId(id)
    expect(parsed).not.toBeNull()
    expect(parsed?.version).toBe(CALCULATION_VERSION)
    expect(parsed?.bucketStartMs).toBe(bucketStartMs(BASE))
    expect(parsed?.digest).toBe('a8f3c1d2')
  })

  it('rejects malformed input', () => {
    for (const bad of ['', 'nonsense', 'bl1_abc_a8f3c1d2', 'bl1_1000_XYZ', null, 42]) {
      expect(parseSnapshotId(bad)).toBeNull()
    }
  })

  it('rejects a bucket that is not on a bucket boundary', () => {
    expect(parseSnapshotId(`bl${CALCULATION_VERSION}_1_a8f3c1d2`)).toBeNull()
  })
})

describe('classifySnapshot', () => {
  const digest = 'a8f3c1d2'
  const fresh = parseSnapshotId(makeSnapshotId(bucketStartMs(BASE), digest))

  it('serves a current snapshot whose content still matches', () => {
    expect(classifySnapshot(fresh, BASE, digest)).toBe('ok')
  })

  it('expires a snapshot whose content has changed underneath it', () => {
    expect(classifySnapshot(fresh, BASE, 'ffffffff')).toBe('SNAPSHOT_EXPIRED')
  })

  it('still serves a snapshot inside the TTL', () => {
    // 14 minutes on -> the current bucket is 10 minutes past this one, under the
    // 15-minute TTL, so a client that loaded the summary two buckets ago can
    // still page through the log it was shown beside.
    expect(classifySnapshot(fresh, BASE + 14 * 60_000, digest)).toBe('ok')
  })

  it('expires anything older than the TTL', () => {
    // Bucket difference, not wall clock, is what the TTL measures: 20 minutes on
    // puts the current bucket 20 minutes past this one.
    expect(classifySnapshot(fresh, BASE + 20 * 60_000, digest)).toBe('SNAPSHOT_EXPIRED')
  })

  it('expires a different calculation version', () => {
    const other = parseSnapshotId(`bl${CALCULATION_VERSION + 1}_${bucketStartMs(BASE) / 1000}_${digest}`)
    expect(classifySnapshot(other, BASE, digest)).toBe('SNAPSHOT_EXPIRED')
  })

  it('treats a future bucket as invalid, not merely stale', () => {
    const future = parseSnapshotId(makeSnapshotId(bucketStartMs(BASE) + SNAPSHOT_BUCKET_MS, digest))
    expect(classifySnapshot(future, BASE, digest)).toBe('INVALID_SNAPSHOT')
  })

  it('rejects an unparseable snapshot', () => {
    expect(classifySnapshot(null, BASE, digest)).toBe('INVALID_SNAPSHOT')
  })
})
