import { createHash } from 'crypto'

/**
 * Pure helpers for POST /api/track (first-party page-view analytics). Kept
 * DB-free and side-effect-free so the privacy-sensitive parts — what counts as
 * a trackable page, what counts as a bot, and how the visitor id is derived —
 * are unit-testable without a database.
 *
 * PRIVACY: nothing here stores or returns the raw IP or user agent. visitorHash
 * only ever produces a one-way digest, and it deliberately bakes the CALENDAR
 * DAY into the hash input, so the same person hashes to a different value
 * tomorrow — the id cannot be used to follow anyone across days.
 */

const DEFAULT_SALT = 'ironforge-track-v1'

const BOT_UA_RE = /bot|crawl|spider|slurp|headless|lighthouse|pingdom|uptime|monitor|curl|wget|python-requests/i

/** Server-rendered crawlers, uptime checks, and scripted clients never count as a visit. */
export function isBotUserAgent(ua: string | null | undefined): boolean {
  if (!ua) return false
  return BOT_UA_RE.test(ua)
}

/**
 * Normalizes a client-reported path for storage in `page_views`, or returns
 * `null` to mean "do not write this event" — /api/track turns a null here into
 * a silent 204, never a 500.
 *
 *  - strips the query string and hash
 *  - lowercases
 *  - trims a trailing slash (except the root path itself)
 *  - caps length at 200 chars
 *  - rejects API routes, Next internals, and anything that looks like a static
 *    asset (has a file extension) — those are not "pages" and would pollute
 *    the traffic dashboard with noise like /favicon.ico or /report.pdf
 */
export function normalizeTrackedPath(raw: unknown): string | null {
  if (typeof raw !== 'string' || raw.length === 0) return null

  let path = raw.split('?')[0].split('#')[0].toLowerCase()
  if (!path.startsWith('/')) path = `/${path}`
  if (path.length > 1) path = path.replace(/\/+$/, '') || '/'
  path = path.slice(0, 200)

  if (path.startsWith('/api') || path.startsWith('/_next')) return null

  const lastSegment = path.slice(path.lastIndexOf('/') + 1)
  if (lastSegment.includes('.')) return null // has a file extension → a static asset, not a page

  return path
}

/** Today's calendar date in America/Chicago, as 'YYYY-MM-DD'. */
export function ctDateString(d: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Chicago',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(d)
}

/**
 * A same-day-stable, cross-day-rotating visitor id. NEVER derived from
 * anything that outlives the day it was hashed for, and the IP/UA that feed it
 * are never themselves persisted — only this digest is.
 */
export function visitorHash(params: { day: string; ip: string; ua: string; salt?: string }): string {
  const salt = params.salt ?? process.env.TRACK_SALT ?? DEFAULT_SALT
  return createHash('sha256').update(`${salt}|${params.day}|${params.ip}|${params.ua}`).digest('hex')
}
