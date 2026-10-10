import { describe, it, expect } from 'vitest'
import { classifySuppression, isTerminalReason, type SuppressionFacts } from '../suppression'

const clean: SuppressionFacts = {
  unsubscribed: false,
  hardBounced: false,
  complained: false,
  hasAccount: false,
  alreadySentThisStage: false,
}

describe('classifySuppression — the kit rule, one fact at a time', () => {
  it('sends when nothing is wrong', () => {
    expect(classifySuppression(clean)).toBeNull()
  })

  it('unsubscribed', () => {
    expect(classifySuppression({ ...clean, unsubscribed: true })).toBe('unsubscribed')
  })

  it('complaint', () => {
    expect(classifySuppression({ ...clean, complained: true })).toBe('complaint')
  })

  it('hard bounce', () => {
    expect(classifySuppression({ ...clean, hardBounced: true })).toBe('hard_bounce')
  })

  it('moved into activation/onboarding (has a customer account)', () => {
    expect(classifySuppression({ ...clean, hasAccount: true })).toBe('onboarding')
  })

  it('duplicate: the stage already has a successful send', () => {
    expect(classifySuppression({ ...clean, alreadySentThisStage: true })).toBe('duplicate')
  })

  it('an unsubscribe outranks everything else — the reason recorded is the one the person chose', () => {
    expect(
      classifySuppression({ unsubscribed: true, hardBounced: true, complained: true, hasAccount: true, alreadySentThisStage: true }),
    ).toBe('unsubscribed')
  })
})

describe('isTerminalReason', () => {
  it('everything but duplicate ends the sequence', () => {
    expect(isTerminalReason('unsubscribed')).toBe(true)
    expect(isTerminalReason('hard_bounce')).toBe(true)
    expect(isTerminalReason('complaint')).toBe(true)
    expect(isTerminalReason('onboarding')).toBe(true)
    expect(isTerminalReason('duplicate')).toBe(false)
  })
})
