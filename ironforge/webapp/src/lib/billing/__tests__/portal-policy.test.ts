import { describe, it, expect } from 'vitest'
import { resolvePortalConfiguration } from '../portal-policy'

/**
 * The case worth protecting: a mobile caller must never be handed Stripe's default
 * portal. That portal permits changing plan, which puts the $15 / $50 / $75 tiers one
 * tap inside the iOS app — App Review Guideline 3.1.1, and a rejected build.
 */
describe('resolvePortalConfiguration', () => {
  it('gives web the default portal', () => {
    expect(resolvePortalConfiguration('web', null)).toEqual({
      allowed: true,
      configuration: null,
    })
  })

  it('web is unaffected by the mobile configuration being present', () => {
    expect(resolvePortalConfiguration('web', 'bpc_restricted')).toEqual({
      allowed: true,
      configuration: null,
    })
  })

  it('gives mobile the restricted configuration when it exists', () => {
    expect(resolvePortalConfiguration('mobile', 'bpc_restricted')).toEqual({
      allowed: true,
      configuration: 'bpc_restricted',
    })
  })

  it('REFUSES mobile when the configuration is missing, rather than falling back', () => {
    // The whole point. A fallback here reintroduces the violation silently.
    expect(resolvePortalConfiguration('mobile', null)).toEqual({
      allowed: false,
      reason: 'portal_unconfigured',
    })
    expect(resolvePortalConfiguration('mobile', undefined)).toEqual({
      allowed: false,
      reason: 'portal_unconfigured',
    })
  })

  it('treats a blank or whitespace env var as missing', () => {
    // An env var set to "" is the realistic failure — a rotated secret, a bad deploy —
    // and it must not read as a valid configuration id.
    expect(resolvePortalConfiguration('mobile', '')).toEqual({
      allowed: false,
      reason: 'portal_unconfigured',
    })
    expect(resolvePortalConfiguration('mobile', '   ')).toEqual({
      allowed: false,
      reason: 'portal_unconfigured',
    })
  })

  it('trims the configuration id so a stray newline does not reach Stripe', () => {
    expect(resolvePortalConfiguration('mobile', ' bpc_restricted\n')).toEqual({
      allowed: true,
      configuration: 'bpc_restricted',
    })
  })
})
