import { createHmac, timingSafeEqual } from 'crypto'

/**
 * Canonical JSON per SnapTrade's signature spec — equivalent to Python's
 * json.dumps(payload, separators=(",", ":"), sort_keys=True): recursively sorted keys,
 * no whitespace, non-ASCII escaped as backslash-uXXXX.
 */
export function snaptradeCanonicalJson(value: unknown): string {
  const esc = (s: string) =>
    s.replace(/[\u0080-\uffff]/g, (c) => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'))
  if (value === null || typeof value !== 'object') return esc(JSON.stringify(value))
  if (Array.isArray(value)) return '[' + value.map(snaptradeCanonicalJson).join(',') + ']'
  const obj = value as Record<string, unknown>
  const keys = Object.keys(obj).sort()
  return '{' + keys.map((k) => esc(JSON.stringify(k)) + ':' + snaptradeCanonicalJson(obj[k])).join(',') + '}'
}

/** base64(HMAC-SHA256(canonical body, consumer key)) must equal the Signature header. */
export function snaptradeSignatureValid(body: unknown, header: string | null): boolean {
  const key = process.env.SNAPTRADE_CONSUMER_KEY
  if (!key || !header) return false
  const digest = createHmac('sha256', key).update(snaptradeCanonicalJson(body)).digest('base64')
  const a = Buffer.from(digest)
  const b = Buffer.from(header)
  return a.length === b.length && timingSafeEqual(a, b)
}
