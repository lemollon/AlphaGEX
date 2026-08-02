import { describe, it, expect } from 'vitest'
import {
  safeAppRoute,
  isAllowedAppRoute,
  appSchemeUrl,
  billingReturn,
  ALLOWED_APP_ROUTES,
} from '@/lib/mobile/deep-link'

describe('safeAppRoute', () => {
  it('passes through every allowlisted route', () => {
    for (const r of ALLOWED_APP_ROUTES) expect(safeAppRoute(r)).toBe(r)
  })

  it('strips query and hash before matching', () => {
    expect(safeAppRoute('/live?account=spark')).toBe('/live')
    expect(safeAppRoute('/community#latest')).toBe('/community')
  })

  // `to` arrives from a third-party redirect (Stripe, a brokerage portal), so these are
  // the open-redirect shapes it must never honour.
  it('refuses absolute and protocol-relative URLs', () => {
    expect(safeAppRoute('//evil.example')).toBe('/live')
    expect(safeAppRoute('https://evil.example/live')).toBe('/live')
    expect(safeAppRoute('http://evil.example')).toBe('/live')
    expect(safeAppRoute('ironforge://live')).toBe('/live')
  })

  it('refuses paths that merely start with a slash', () => {
    // The reason this is an allowlist and not a startsWith('/') check.
    expect(safeAppRoute('/ops/impersonate')).toBe('/live')
    expect(safeAppRoute('/api/ops/admin')).toBe('/live')
    expect(isAllowedAppRoute('/ops/impersonate')).toBe(false)
  })

  it('falls back for empty and non-string input', () => {
    expect(safeAppRoute(null)).toBe('/live')
    expect(safeAppRoute(undefined)).toBe('/live')
    expect(safeAppRoute('')).toBe('/live')
    expect(safeAppRoute(42 as unknown as string)).toBe('/live')
  })
})

describe('appSchemeUrl', () => {
  it('builds a custom-scheme url with params', () => {
    expect(appSchemeUrl('/live', { account: 'spark' })).toBe('ironforge://live?account=spark')
    expect(appSchemeUrl('/account/billing')).toBe('ironforge://account/billing')
  })
})

describe('billingReturn', () => {
  const origin = 'https://ironforge.trade'

  it('sends web callers straight to the page', () => {
    expect(billingReturn(origin, 'web', '/account/billing')).toBe(
      'https://ironforge.trade/account/billing',
    )
    expect(billingReturn(origin, 'web', '/community', { welcome: 'community' })).toBe(
      'https://ironforge.trade/community?welcome=community',
    )
  })

  // Stripe rejects non-https return urls at session creation, so mobile cannot be sent
  // to ironforge:// directly — it must go through the https bridge.
  it('sends mobile callers through the https bridge, never a custom scheme', () => {
    const url = billingReturn(origin, 'mobile', '/account/billing')
    expect(url.startsWith('https://ironforge.trade/app/return?')).toBe(true)
    expect(url).not.toContain('ironforge://')
    expect(url).toContain('to=%2Faccount%2Fbilling')
  })

  it('carries Stripe placeholders through untouched', () => {
    // {CHECKOUT_SESSION_ID} is substituted by Stripe; encoding must not mangle it
    // beyond what decoding restores.
    const url = billingReturn(origin, 'mobile', '/live', { session_id: '{CHECKOUT_SESSION_ID}' })
    expect(decodeURIComponent(url)).toContain('{CHECKOUT_SESSION_ID}')
  })

  it('sanitizes the destination even on the mobile path', () => {
    const url = billingReturn(origin, 'mobile', '//evil.example')
    expect(url).toContain('to=%2Flive')
    expect(url).not.toContain('evil.example')
  })
})
