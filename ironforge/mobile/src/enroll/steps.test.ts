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

  it('routes billing -> /enroll/billing regardless of plan', () => {
    expect(routeForNextStep('billing', 'flame')).toEqual({ route: '/enroll/billing', rank: PAGE_RANK.billing })
    expect(routeForNextStep('billing', 'community')).toEqual({ route: '/enroll/billing', rank: PAGE_RANK.billing })
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
