import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import path from 'node:path'

/**
 * Pins the PUBLISHED Universal Links association file.
 *
 * This file is uniquely unforgiving: it has no extension (so nothing type-checks it),
 * it is only ever read by Apple's CDN (so nothing in this codebase exercises it), and
 * iOS CACHES a failed association — a wrong Team ID or a placeholder left in place can
 * leave Universal Links dead on a device even after the file is corrected. The failure
 * mode is silent everywhere: no error, no log, links just quietly open Safari forever.
 *
 * The template at ironforge/mobile/well-known/ carries placeholders on purpose. This
 * test exists to make sure a placeholder never reaches the served copy.
 */
const AASA_PATH = path.join(
  process.cwd(),
  'public',
  '.well-known',
  'apple-app-site-association',
)

const APP_ID = 'NDQD9S95ZK.trade.ironforge.app'

describe('apple-app-site-association', () => {
  const raw = readFileSync(AASA_PATH, 'utf8')

  it('is valid JSON', () => {
    expect(() => JSON.parse(raw)).not.toThrow()
  })

  it('carries the real Team ID, never a placeholder', () => {
    expect(raw).not.toMatch(/TEAMID|REPLACE|PLACEHOLDER/i)
    expect(JSON.parse(raw).applinks.details[0].appIDs).toEqual([APP_ID])
  })

  it('declares the same app id for webcredentials as for applinks', () => {
    // A mismatch here is the shape that ships a working link handler with dead password
    // autofill, and vice versa.
    const parsed = JSON.parse(raw)
    expect(parsed.webcredentials.apps).toEqual(parsed.applinks.details[0].appIDs)
  })

  it('claims the OAuth return bridge, which is what actually has to work', () => {
    const paths = JSON.parse(raw).applinks.details[0].components.map(
      (c: Record<string, string>) => c['/'],
    )
    // /app/return is the Stripe + brokerage callback. If it stops being claimed, the
    // connect flow strands the customer in a browser tab instead of returning to the app.
    expect(paths).toContain('/app/return')
    expect(paths).toContain('/app/brokerage/return')
  })
})
