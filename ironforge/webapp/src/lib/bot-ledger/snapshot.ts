/**
 * Bot Ledger — snapshot identity.
 *
 * There is no materialised snapshot table (IronForge has no revision trail to
 * build one from). Instead the id is a 5-minute time bucket PLUS a content
 * digest over the fully-projected public DTOs of the entire eligible universe.
 *
 * What that buys: both endpoints compute the same universe, so both derive the
 * same id from the same data. If the underlying rows change between two calls,
 * the digests disagree and `/trades` returns 409 instead of rendering a table
 * that does not add up to the headline KPIs.
 *
 * What it does NOT buy — and the page must never claim otherwise: this DETECTS
 * divergence, it does not PREVENT it, and it records nothing about what
 * changed. Operator corrections are still in-place UPDATEs. The words
 * "immutable", "append-only", "tamper-evident" and "verified" are off-limits.
 *
 * Digesting the projected DTO rather than a hand-picked field list means the
 * digest changes if and only if a DISPLAYED value changes — you cannot forget
 * to add a new field to the hash input.
 */

import { createHash } from 'crypto'

import { CALCULATION_VERSION, SNAPSHOT_BUCKET_MS, SNAPSHOT_TTL_MS } from './constants'
import type { PublicLedgerTrade } from './types'

export interface ParsedSnapshot {
  version: number
  bucketStartMs: number
  digest: string
}

export function bucketStartMs(nowMs: number): number {
  return Math.floor(nowMs / SNAPSHOT_BUCKET_MS) * SNAPSHOT_BUCKET_MS
}

export function bucketEndMs(nowMs: number): number {
  return bucketStartMs(nowMs) + SNAPSHOT_BUCKET_MS
}

/**
 * Separators for the canonical form. ASCII unit/record separators, written as
 * escapes so they are VISIBLE in source: they were literal control characters,
 * which a reformat could silently drop -- and dropping them would change every
 * snapshot digest while looking like a pure whitespace diff.
 *
 * They matter: joining on '' would let ['ab','c'] and ['a','bc'] serialise
 * identically, so two different ledgers could collide on one digest.
 */
const FIELD_SEP = '\u001f'
const RECORD_SEP = '\u001e'

/**
 * Canonical digest over the whole universe. Input order is normalised first so
 * the digest depends on content, not on how Postgres happened to return rows.
 */
export function digestOf(dtos: readonly PublicLedgerTrade[]): string {
  const canonical = dtos
    .map((d) =>
      [
        d.bot,
        d.public_id,
        d.closed_date,
        d.setup,
        d.buying_power_used,
        d.net_result,
        d.return_on_bp_pct,
        d.outcome,
      ].join(FIELD_SEP),
    )
    .sort()
    .join(RECORD_SEP)
  return createHash('sha256').update(canonical).digest('hex').slice(0, 8)
}

export function makeSnapshotId(bucketMs: number, digest: string): string {
  return `bl${CALCULATION_VERSION}_${Math.floor(bucketMs / 1000)}_${digest}`
}

export function parseSnapshotId(raw: unknown): ParsedSnapshot | null {
  if (typeof raw !== 'string') return null
  const m = /^bl(\d+)_(\d+)_([0-9a-f]{8})$/.exec(raw)
  if (!m) return null
  const version = Number(m[1])
  const bucketStart = Number(m[2]) * 1000
  if (!Number.isSafeInteger(version) || !Number.isSafeInteger(bucketStart)) return null
  if (bucketStart % SNAPSHOT_BUCKET_MS !== 0) return null
  return { version, bucketStartMs: bucketStart, digest: m[3] }
}

export type SnapshotVerdict = 'ok' | 'INVALID_SNAPSHOT' | 'SNAPSHOT_EXPIRED'

/**
 * Decide whether a client-supplied snapshot id may still be served.
 * `actualDigest` is omitted on the first pass (before the universe is loaded)
 * and supplied on the second, once we can compare content.
 */
export function classifySnapshot(
  parsed: ParsedSnapshot | null,
  nowMs: number,
  actualDigest?: string,
): SnapshotVerdict {
  if (!parsed) return 'INVALID_SNAPSHOT'
  // A different formula version means the numbers are not comparable.
  if (parsed.version !== CALCULATION_VERSION) return 'SNAPSHOT_EXPIRED'
  const current = bucketStartMs(nowMs)
  // A future bucket is clock skew or forgery, not staleness.
  if (parsed.bucketStartMs > current) return 'INVALID_SNAPSHOT'
  if (current - parsed.bucketStartMs > SNAPSHOT_TTL_MS) return 'SNAPSHOT_EXPIRED'
  if (actualDigest !== undefined && actualDigest !== parsed.digest) return 'SNAPSHOT_EXPIRED'
  return 'ok'
}
