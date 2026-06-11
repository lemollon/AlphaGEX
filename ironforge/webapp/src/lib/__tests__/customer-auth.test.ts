import { describe, it, expect } from 'vitest'
import { classifyLoginAttempt } from '@/lib/auth/customer-auth'

describe('classifyLoginAttempt', () => {
  it('is invalid_credentials when the user is missing', () => {
    expect(classifyLoginAttempt({ userExists: false, passwordOk: false, emailVerified: false })).toBe('invalid_credentials')
  })
  it('is invalid_credentials when the password is wrong', () => {
    expect(classifyLoginAttempt({ userExists: true, passwordOk: false, emailVerified: true })).toBe('invalid_credentials')
  })
  it('is email_unverified when creds are valid but email is unverified', () => {
    expect(classifyLoginAttempt({ userExists: true, passwordOk: true, emailVerified: false })).toBe('email_unverified')
  })
  it('is ok when creds are valid and email is verified', () => {
    expect(classifyLoginAttempt({ userExists: true, passwordOk: true, emailVerified: true })).toBe('ok')
  })
})
