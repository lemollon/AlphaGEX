/**
 * Tests for track.ts — the pure helpers behind POST /api/track.
 *
 * PRIVACY is the property under test: visitorHash must rotate every calendar
 * day and never leak the raw IP/UA it was built from.
 */

import { describe, it, expect } from 'vitest'
import { ctDateString, isBotUserAgent, normalizeTrackedPath, visitorHash } from '../track'

/* ================================================================== */
/*  normalizeTrackedPath                                              */
/* ================================================================== */

describe('normalizeTrackedPath', () => {
  it('strips the query string and hash', () => {
    expect(normalizeTrackedPath('/live?utm_source=twitter')).toBe('/live')
    expect(normalizeTrackedPath('/live#section')).toBe('/live')
    expect(normalizeTrackedPath('/live?a=1#b')).toBe('/live')
  })

  it('lowercases the path', () => {
    expect(normalizeTrackedPath('/Live/SPARK')).toBe('/live/spark')
  })

  it('trims a trailing slash except the root', () => {
    expect(normalizeTrackedPath('/live/')).toBe('/live')
    expect(normalizeTrackedPath('/')).toBe('/')
  })

  it('caps length at 200 chars', () => {
    const long = '/' + 'a'.repeat(500)
    const out = normalizeTrackedPath(long)
    expect(out).not.toBeNull()
    expect(out!.length).toBeLessThanOrEqual(200)
  })

  it('rejects API routes', () => {
    expect(normalizeTrackedPath('/api/track')).toBeNull()
    expect(normalizeTrackedPath('/api/live/summary')).toBeNull()
  })

  it('rejects Next internals', () => {
    expect(normalizeTrackedPath('/_next/static/chunk.js')).toBeNull()
  })

  it('rejects anything with a file extension', () => {
    expect(normalizeTrackedPath('/favicon.ico')).toBeNull()
    expect(normalizeTrackedPath('/report.pdf')).toBeNull()
    expect(normalizeTrackedPath('/images/logo.png')).toBeNull()
  })

  it('does not reject a real page whose earlier segment merely contains a dot', () => {
    // Only the LAST segment decides — a path like /v1.2/live must not be rejected.
    expect(normalizeTrackedPath('/v1.2/live')).toBe('/v1.2/live')
  })

  it('rejects non-string / empty input', () => {
    expect(normalizeTrackedPath(undefined)).toBeNull()
    expect(normalizeTrackedPath(null)).toBeNull()
    expect(normalizeTrackedPath(123)).toBeNull()
    expect(normalizeTrackedPath('')).toBeNull()
  })

  it('adds a leading slash if missing', () => {
    expect(normalizeTrackedPath('live')).toBe('/live')
  })
})

/* ================================================================== */
/*  isBotUserAgent                                                    */
/* ================================================================== */

describe('isBotUserAgent', () => {
  it('flags known bot/crawler/monitor substrings, case-insensitively', () => {
    for (const ua of [
      'Googlebot/2.1',
      'Mozilla/5.0 (compatible; bingbot/2.0)',
      'Slurp',
      'HeadlessChrome/120.0',
      'Lighthouse',
      'Pingdom.com_bot_version_1.4',
      'UptimeRobot/2.0',
      'Better Uptime Bot',
      'curl/8.4.0',
      'Wget/1.21',
      'python-requests/2.31.0',
      'SomeSpiderCrawler',
    ]) {
      expect(isBotUserAgent(ua), ua).toBe(true)
    }
  })

  it('does not flag a normal browser UA', () => {
    expect(
      isBotUserAgent(
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
      ),
    ).toBe(false)
  })

  it('treats null/undefined/empty as not a bot', () => {
    expect(isBotUserAgent(null)).toBe(false)
    expect(isBotUserAgent(undefined)).toBe(false)
    expect(isBotUserAgent('')).toBe(false)
  })
})

/* ================================================================== */
/*  ctDateString                                                      */
/* ================================================================== */

describe('ctDateString', () => {
  it('formats as YYYY-MM-DD', () => {
    expect(ctDateString(new Date('2026-09-03T18:00:00Z'))).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it('converts to America/Chicago, not UTC', () => {
    // 2026-09-04 03:00 UTC is still 2026-09-03 evening in Chicago (UTC-5, CDT).
    expect(ctDateString(new Date('2026-09-04T03:00:00Z'))).toBe('2026-09-03')
  })
})

/* ================================================================== */
/*  visitorHash                                                       */
/* ================================================================== */

describe('visitorHash', () => {
  it('is a 64-char hex sha256 digest', () => {
    const h = visitorHash({ day: '2026-09-03', ip: '1.2.3.4', ua: 'UA', salt: 'test-salt' })
    expect(h).toMatch(/^[0-9a-f]{64}$/)
  })

  it('is stable for the same day/ip/ua/salt', () => {
    const a = visitorHash({ day: '2026-09-03', ip: '1.2.3.4', ua: 'UA', salt: 'test-salt' })
    const b = visitorHash({ day: '2026-09-03', ip: '1.2.3.4', ua: 'UA', salt: 'test-salt' })
    expect(a).toBe(b)
  })

  it('differs across days for the same visitor — no cross-day tracking', () => {
    const day1 = visitorHash({ day: '2026-09-03', ip: '1.2.3.4', ua: 'UA', salt: 'test-salt' })
    const day2 = visitorHash({ day: '2026-09-04', ip: '1.2.3.4', ua: 'UA', salt: 'test-salt' })
    expect(day1).not.toBe(day2)
  })

  it('differs across IPs on the same day', () => {
    const a = visitorHash({ day: '2026-09-03', ip: '1.2.3.4', ua: 'UA', salt: 'test-salt' })
    const b = visitorHash({ day: '2026-09-03', ip: '5.6.7.8', ua: 'UA', salt: 'test-salt' })
    expect(a).not.toBe(b)
  })

  it('differs across user agents on the same day', () => {
    const a = visitorHash({ day: '2026-09-03', ip: '1.2.3.4', ua: 'UA-A', salt: 'test-salt' })
    const b = visitorHash({ day: '2026-09-03', ip: '1.2.3.4', ua: 'UA-B', salt: 'test-salt' })
    expect(a).not.toBe(b)
  })

  it('falls back to the default salt when none is configured', () => {
    const prev = process.env.TRACK_SALT
    delete process.env.TRACK_SALT
    const h = visitorHash({ day: '2026-09-03', ip: '1.2.3.4', ua: 'UA' })
    expect(h).toMatch(/^[0-9a-f]{64}$/)
    if (prev === undefined) delete process.env.TRACK_SALT
    else process.env.TRACK_SALT = prev
  })
})
