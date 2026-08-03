/**
 * Cross-origin access for the mobile app's WEB build (Expo web / `expo start --web`).
 *
 * Native iOS and Android do not enforce CORS, so the real app never needed this. The
 * browser preview does — without it every API call fails with a bare "Failed to fetch",
 * which is what happens today.
 *
 * ── The three rules that keep this from becoming a hole ──
 *
 * 1. ALLOWLIST ONLY, NEVER `*`. The origin is echoed back only if it appears verbatim
 *    in CORS_ALLOWED_ORIGINS. An unrecognised origin gets NO CORS headers at all, which
 *    is what the browser needs to see in order to block the request.
 *
 * 2. NEVER `Access-Control-Allow-Credentials`. This is the important one. Without it a
 *    browser will not attach the ironforge_customer cookie to a cross-origin request,
 *    so even a fully-allowed origin cannot ride a signed-in customer's WEB session.
 *    Only the mobile bearer token works cross-origin, and that lives in the app's own
 *    storage where another origin cannot read it. Turning credentials on would convert
 *    this from a dev convenience into a CSRF surface — do not add it.
 *
 * 3. OFF BY DEFAULT. CORS_ALLOWED_ORIGINS unset (the production state) means this
 *    module does nothing whatsoever. It has to be switched on deliberately, per
 *    service, and production never should be.
 *
 * Scoped to /api/* — HTML pages have no reason to be read cross-origin.
 */

/** Parsed once per request; the env var is read at call time so tests can vary it. */
function allowedOrigins(): string[] {
  const raw = process.env.CORS_ALLOWED_ORIGINS
  if (!raw) return []
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

export function isCorsEnabled(): boolean {
  return allowedOrigins().length > 0
}

/**
 * The origin to echo, or null to send no CORS headers.
 * Exact string match — no wildcards, no prefix matching, no suffix matching.
 * `https://evil-ironforge.trade` must never satisfy an entry for `https://ironforge.trade`.
 */
export function resolveAllowedOrigin(origin: string | null | undefined): string | null {
  if (!origin) return null
  const list = allowedOrigins()
  return list.includes(origin) ? origin : null
}

/** Headers the app legitimately sends. Authorization is the whole point. */
const ALLOWED_HEADERS = 'Authorization, Content-Type, Accept'
const ALLOWED_METHODS = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'

export function corsHeaders(origin: string): Record<string, string> {
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': ALLOWED_METHODS,
    'Access-Control-Allow-Headers': ALLOWED_HEADERS,
    'Access-Control-Max-Age': '600',
    // Responses differ by Origin, so any shared cache must key on it. Without this a
    // proxy could serve one origin's CORS headers to another.
    Vary: 'Origin',
    // NOTE: Access-Control-Allow-Credentials is deliberately absent. See rule 2 above.
  }
}

/**
 * Preflight response. Returns null when this is not a preflight or the origin is not
 * allowed, so the caller falls through to normal handling.
 *
 * Answering OPTIONS BEFORE the auth gate is correct and not a bypass: a preflight
 * carries no credentials and reads no data — it only asks "may I send the real
 * request?". Gating it would 401 the preflight and the real request would never be
 * attempted, which is exactly the failure this fixes.
 */
export function preflightResponse(
  method: string,
  origin: string | null | undefined,
  pathname: string,
): Response | null {
  if (method !== 'OPTIONS') return null
  if (!pathname.startsWith('/api/')) return null
  const allowed = resolveAllowedOrigin(origin)
  if (!allowed) return null
  return new Response(null, { status: 204, headers: corsHeaders(allowed) })
}
