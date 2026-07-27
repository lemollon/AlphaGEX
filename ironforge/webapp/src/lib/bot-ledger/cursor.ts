/**
 * Bot Ledger — opaque, signed pagination cursors.
 *
 * HMAC-signed so a client cannot forge one. The payload is base64url JSON and
 * therefore readable, which is fine: it holds a snapshot id, a filter key and
 * an integer offset — nothing secret. Encrypting it would buy no security and
 * would make debugging a production pagination bug materially harder.
 *
 * Offset paging is safe here precisely because the snapshot digest has already
 * proven the ordering is identical to the one that produced the cursor; if it
 * were not, the request would have 409'd before reaching this code.
 */

import { createHmac, timingSafeEqual } from 'crypto'

import { CALCULATION_VERSION } from './constants'

export interface CursorPayload {
  /** Formula version. */
  v: number
  /** Snapshot the cursor was minted against. */
  s: string
  /** Filter key — stops a spark cursor being replayed against bot=all. */
  f: string
  /** Row offset. */
  o: number
}

function signingKey(): string {
  // Guaranteed present on the customer service (it is the iron-session
  // password). DATABASE_URL is a high-entropy fallback so a public read
  // endpoint never hard-fails on a misconfigured service. Never fall back to a
  // literal default — that would make cursors forgeable.
  const secret = process.env.IRONFORGE_SESSION_SECRET || process.env.DATABASE_URL
  if (!secret) throw new Error('bot-ledger cursor: no signing key available')
  return secret
}

function b64url(buf: Buffer): string {
  return buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function fromB64url(s: string): Buffer {
  const pad = s.length % 4 === 0 ? '' : '='.repeat(4 - (s.length % 4))
  return Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/') + pad, 'base64')
}

function sign(body: string): string {
  return b64url(createHmac('sha256', signingKey()).update(body).digest())
}

export function encodeCursor(payload: CursorPayload): string {
  const body = b64url(Buffer.from(JSON.stringify(payload), 'utf8'))
  return `${body}.${sign(body)}`
}

/** Returns null for anything malformed, tampered, or signed with another key. */
export function decodeCursor(raw: unknown): CursorPayload | null {
  if (typeof raw !== 'string' || raw.length === 0 || raw.length > 512) return null
  const dot = raw.lastIndexOf('.')
  if (dot <= 0 || dot === raw.length - 1) return null

  const body = raw.slice(0, dot)
  const mac = raw.slice(dot + 1)

  let expected: string
  try {
    expected = sign(body)
  } catch {
    return null
  }

  const a = Buffer.from(mac, 'utf8')
  const b = Buffer.from(expected, 'utf8')
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null

  try {
    const parsed = JSON.parse(fromB64url(body).toString('utf8')) as CursorPayload
    if (
      typeof parsed?.v !== 'number' ||
      typeof parsed?.s !== 'string' ||
      typeof parsed?.f !== 'string' ||
      !Number.isSafeInteger(parsed?.o) ||
      parsed.o < 0
    ) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function filterKey(bot: string, limit: number): string {
  return `${bot}:${limit}`
}

export function currentCursorVersion(): number {
  return CALCULATION_VERSION
}
