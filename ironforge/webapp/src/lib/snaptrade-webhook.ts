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

function hmacB64Matches(content: string, header: string): boolean {
  const key = process.env.SNAPTRADE_CONSUMER_KEY
  if (!key) return false
  // Tolerate stray whitespace picked up when the key was pasted into the env editor.
  for (const k of key.trim() === key ? [key] : [key, key.trim()]) {
    const digest = createHmac('sha256', k).update(content).digest('base64')
    const a = Buffer.from(digest)
    const b = Buffer.from(header)
    if (a.length === b.length && timingSafeEqual(a, b)) return true
  }
  return false
}

/** base64(HMAC-SHA256(canonical body, consumer key)) must equal the Signature header. */
export function snaptradeSignatureValid(body: unknown, header: string | null): boolean {
  if (!header) return false
  return hmacB64Matches(snaptradeCanonicalJson(body), header)
}

/** Same HMAC over the raw wire body — covers senders that sign the exact bytes they POST. */
export function snaptradeRawSignatureValid(raw: string, header: string | null): boolean {
  if (!header || !raw) return false
  return hmacB64Matches(raw, header)
}
