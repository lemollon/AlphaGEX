/**
 * Resend webhook verification + event parsing.
 *
 * Resend signs webhooks with Svix: headers `svix-id`, `svix-timestamp`, `svix-signature`;
 * the signed content is `${id}.${timestamp}.${rawBody}`; the key is the base64 part of the
 * `whsec_…` signing secret; the signature header carries one or more space-separated
 * `v1,<base64>` entries. Timestamps older/newer than 5 minutes are rejected (replay guard).
 *
 * FAILS CLOSED: with RESEND_WEBHOOK_SECRET unset every request is rejected. An unverified
 * webhook that could mark any address as bounced is a denial-of-service on the drip, so
 * "not configured" must mean "not accepting", never "accept everything".
 *
 * Hand-rolled on node:crypto — no `svix` package (package.json policy: nothing undeclared).
 */

import { createHmac, timingSafeEqual } from 'crypto'

export const SVIX_TOLERANCE_SECONDS = 5 * 60

export interface SvixHeaders {
  id: string | null
  timestamp: string | null
  signature: string | null
}

export type VerifyOutcome =
  | { ok: true }
  | { ok: false; reason: 'secret_unset' | 'missing_headers' | 'bad_timestamp' | 'stale_timestamp' | 'bad_signature' }

function secretBytes(secret: string): Buffer {
  const raw = secret.trim()
  const b64 = raw.startsWith('whsec_') ? raw.slice('whsec_'.length) : raw
  return Buffer.from(b64, 'base64')
}

/** Compute the `v1` signature Svix would produce for this content with this secret. */
export function svixSign(secret: string, id: string, timestamp: string, body: string): string {
  return createHmac('sha256', secretBytes(secret)).update(`${id}.${timestamp}.${body}`).digest('base64')
}

export function verifySvixSignature(
  headers: SvixHeaders,
  rawBody: string,
  opts: { secret?: string | null; now?: Date; toleranceSeconds?: number } = {},
): VerifyOutcome {
  const secret = opts.secret ?? process.env.RESEND_WEBHOOK_SECRET
  if (!secret || !secret.trim()) return { ok: false, reason: 'secret_unset' }
  const { id, timestamp, signature } = headers
  if (!id || !timestamp || !signature) return { ok: false, reason: 'missing_headers' }

  const ts = Number(timestamp)
  if (!Number.isFinite(ts)) return { ok: false, reason: 'bad_timestamp' }
  const nowSec = Math.floor((opts.now ?? new Date()).getTime() / 1000)
  if (Math.abs(nowSec - ts) > (opts.toleranceSeconds ?? SVIX_TOLERANCE_SECONDS)) {
    return { ok: false, reason: 'stale_timestamp' }
  }

  const expected = Buffer.from(svixSign(secret, id, timestamp, rawBody))
  for (const entry of signature.split(' ')) {
    const [version, sig] = entry.split(',')
    if (version !== 'v1' || !sig) continue
    const candidate = Buffer.from(sig)
    if (candidate.length === expected.length && timingSafeEqual(candidate, expected)) return { ok: true }
  }
  return { ok: false, reason: 'bad_signature' }
}

// ---------------------------------------------------------------------------
// Event parsing
// ---------------------------------------------------------------------------

/** The event types the drip acts on. Everything else is stored (if parseable) and ignored. */
export const SUPPRESSING_EVENT_TYPES = new Set(['email.bounced', 'email.complained'])

export interface ParsedResendEvent {
  type: string
  /** Recipient addresses, lowercased. */
  emails: string[]
  messageId: string | null
  /** 'Permanent' | 'Transient' for bounces; null otherwise. */
  bounceType: string | null
  createdAt: string | null
}

function asStringArray(v: unknown): string[] {
  if (typeof v === 'string') return [v]
  if (Array.isArray(v)) return v.filter((x): x is string => typeof x === 'string')
  return []
}

/**
 * Normalise a Resend event payload. Returns null when the body is not an event we can name
 * an address for — the route stores nothing in that case.
 */
export function parseResendEvent(body: unknown): ParsedResendEvent | null {
  if (!body || typeof body !== 'object') return null
  const b = body as Record<string, unknown>
  const type = typeof b.type === 'string' ? b.type : null
  const data = b.data && typeof b.data === 'object' ? (b.data as Record<string, unknown>) : null
  if (!type || !data) return null
  const emails = asStringArray(data.to).map((e) => e.trim().toLowerCase()).filter(Boolean)
  if (emails.length === 0) return null
  const bounce = data.bounce && typeof data.bounce === 'object' ? (data.bounce as Record<string, unknown>) : null
  const bounceType = bounce && typeof bounce.type === 'string' ? bounce.type : null
  return {
    type,
    emails,
    messageId: typeof data.email_id === 'string' ? data.email_id : null,
    bounceType,
    createdAt: typeof b.created_at === 'string' ? b.created_at : null,
  }
}

/** A bounce that should suppress: Resend's 'Permanent' type. Transient bounces are retried by Resend. */
export function isHardBounce(e: ParsedResendEvent): boolean {
  return e.type === 'email.bounced' && e.bounceType === 'Permanent'
}
