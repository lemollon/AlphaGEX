import { describe, it, expect } from 'vitest'
import { routeForNextStep, PAGE_RANK } from './steps'

describe('routeForNextStep', () => {
  it('routes plan -> /enroll/plan', () => {
    expect(routeForNextStep('plan', null)).toEqual({ route: '/enroll/plan', rank: PAGE_RANK.plan })
  })

  it('routes legal -> /enroll/legal for an automate-family plan', () => {
    expect(routeForNextStep('legal', 'spark')).toEqual({ route: '/enroll/legal', rank: PAGE_RANK.legal })
    expect(routeForNextStep('legal', 'automate')).toEqual({ route: '/enroll/legal', rank: PAGE_RANK.legal })
  })

  it('routes legal -> /enroll/billing for community (no standalone legal screen)', () => {
    expect(routeForNextStep('legal', 'community')).toEqual({ route: '/enroll/billing', rank: PAGE_RANK.billing })
  })

  it('routes billing -> /enroll/billing for any paid plan', () => {
    expect(routeForNextStep('billing', 'flame')).toEqual({ route: '/enroll/billing', rank: PAGE_RANK.billing })
    expect(routeForNextStep('billing', 'community')).toEqual({ route: '/enroll/billing', rank: PAGE_RANK.billing })
  })

  it('routes billing -> /enroll/broker for Ember (free, never asks for a card)', () => {
    expect(routeForNextStep('billing', 'ember')).toEqual({ route: '/enroll/broker', rank: PAGE_RANK.broker })
  })

  it('routes setup -> /enroll/broker (the first of the three setup screens)', () => {
    expect(routeForNextStep('setup', 'flame')).toEqual({ route: '/enroll/broker', rank: PAGE_RANK.broker })
  })

  it('routes done -> the tabs root, never an /enroll/* screen', () => {
    expect(routeForNextStep('done', 'flame')).toEqual({ route: '/', rank: PAGE_RANK.done })
  })

  it('defaults unknown/missing next_step to plan, same fail-safe as the server', () => {
    expect(routeForNextStep(undefined, null)).toEqual({ route: '/enroll/plan', rank: PAGE_RANK.plan })
    expect(routeForNextStep('something_new', null)).toEqual({ route: '/enroll/plan', rank: PAGE_RANK.plan })
  })

  it('broker/agents/review share one rank — client-navigated within "setup"', () => {
    expect(PAGE_RANK.broker).toBe(PAGE_RANK.agents)
    expect(PAGE_RANK.agents).toBe(PAGE_RANK.review)
  })

  it('rank climbs monotonically from plan through done', () => {
    expect(PAGE_RANK.plan).toBeLessThan(PAGE_RANK.legal)
    expect(PAGE_RANK.legal).toBeLessThan(PAGE_RANK.billing)
    expect(PAGE_RANK.billing).toBeLessThan(PAGE_RANK.broker)
    expect(PAGE_RANK.broker).toBeLessThan(PAGE_RANK.done)
  })
})

/**
 * Regression coverage for the TestFlight build 23 bug ("choose a plan, continue,
 * go back, choose a different plan does nothing"). useEnrollment's resume() guard
 * is `if (PAGE_RANK[current] > canonical.rank) router.replace(canonical.route)` —
 * it only ever redirects a customer FORWARD-of-canonical back down, never blocks
 * someone sitting on an EARLIER screen than canonical from staying there. These
 * pin that the guard never fires for a customer who goes back to /enroll/plan,
 * for any plan the server now has on file — the actual bug was a client `busy`
 * flag that never reset, not this routing guard, but this is the server contract
 * the fix depends on staying true.
 */
describe('choose A -> back -> choose B: the plan screen is never redirected away', () => {
  function wouldRedirectFromPlan(nextStep: string, selectedPlan: string | null) {
    const canonical = routeForNextStep(nextStep, selectedPlan)
    return PAGE_RANK.plan > canonical.rank
  }

  it('after choosing Spark (now legal_pending) and going back, plan stays put', () => {
    expect(wouldRedirectFromPlan('legal', 'spark')).toBe(false)
  })

  it('after choosing Ember (now legal_pending) and going back, plan stays put', () => {
    expect(wouldRedirectFromPlan('legal', 'ember')).toBe(false)
  })

  it('even further along (billing_pending) and going back, plan still stays put', () => {
    expect(wouldRedirectFromPlan('billing', 'spark')).toBe(false)
    // Ember's own billing_pending-equivalent is setup_required ('setup').
    expect(wouldRedirectFromPlan('setup', 'ember')).toBe(false)
  })

  it('choosing B after A re-routes to the right next screen for each plan, including the Ember <-> Spark switch', () => {
    // A: choose Spark -> server says legal.
    expect(routeForNextStep('legal', 'spark')).toEqual({ route: '/enroll/legal', rank: PAGE_RANK.legal })
    // back to plan, choose B: Ember instead -> server rewinds to legal again, same screen.
    expect(routeForNextStep('legal', 'ember')).toEqual({ route: '/enroll/legal', rank: PAGE_RANK.legal })
    // Ember's legal acceptance skips billing -> broker directly.
    expect(routeForNextStep('billing', 'ember')).toEqual({ route: '/enroll/broker', rank: PAGE_RANK.broker })
    // back to plan again, choose B: Spark instead -> billing step is required again.
    expect(routeForNextStep('billing', 'spark')).toEqual({ route: '/enroll/billing', rank: PAGE_RANK.billing })
  })
})
