import { describe, it, expect, beforeEach } from 'vitest'
import { setPendingPassword, getPendingPassword, clearPendingPassword } from './pending-credentials'

beforeEach(() => {
  clearPendingPassword()
})

describe('pending-credentials', () => {
  it('returns null before anything is set', () => {
    expect(getPendingPassword()).toBeNull()
  })
  it('returns the value set', () => {
    setPendingPassword('Str0ng!Passw0rd')
    expect(getPendingPassword()).toBe('Str0ng!Passw0rd')
  })
  it('is readable more than once without clearing (survives a resend + retry)', () => {
    setPendingPassword('Str0ng!Passw0rd')
    expect(getPendingPassword()).toBe('Str0ng!Passw0rd')
    expect(getPendingPassword()).toBe('Str0ng!Passw0rd')
  })
  it('clearPendingPassword blanks it', () => {
    setPendingPassword('Str0ng!Passw0rd')
    clearPendingPassword()
    expect(getPendingPassword()).toBeNull()
  })
  it('a later set overwrites an earlier one', () => {
    setPendingPassword('First!Pass1')
    setPendingPassword('Second!Pass2')
    expect(getPendingPassword()).toBe('Second!Pass2')
  })
})
