import { describe, it, expect } from 'vitest'
import { isAuthGroupSegment } from './gate'

describe('isAuthGroupSegment', () => {
  it('sign-in is in the auth group', () => {
    expect(isAuthGroupSegment('sign-in')).toBe(true)
  })

  it('forgot-password is in the auth group — regression test for the signed-out lockout bug', () => {
    expect(isAuthGroupSegment('forgot-password')).toBe(true)
  })

  it('reset-password is in the auth group — regression test for the signed-out lockout bug', () => {
    expect(isAuthGroupSegment('reset-password')).toBe(true)
  })

  it('change-password is NOT in the auth group (signed-in-only screen, must stay gated)', () => {
    expect(isAuthGroupSegment('change-password')).toBe(false)
  })

  it('enroll and waitlist are their own separate groups, not the auth group', () => {
    expect(isAuthGroupSegment('enroll')).toBe(false)
    expect(isAuthGroupSegment('waitlist')).toBe(false)
    expect(isAuthGroupSegment('waitlist-success')).toBe(false)
  })

  it('undefined segment (root) is not in the auth group', () => {
    expect(isAuthGroupSegment(undefined)).toBe(false)
  })

  it('an unrelated screen is not in the auth group', () => {
    expect(isAuthGroupSegment('live')).toBe(false)
  })
})
