import { describe, it, expect } from 'vitest'
import { hashPassword, verifyPassword } from '../password'

describe('password helpers', () => {
  it('hashes and verifies a correct password', async () => {
    const hash = await hashPassword('correct-horse-battery')
    expect(hash).not.toBe('correct-horse-battery')
    expect(await verifyPassword('correct-horse-battery', hash)).toBe(true)
  })

  it('rejects an incorrect password', async () => {
    const hash = await hashPassword('correct-horse-battery')
    expect(await verifyPassword('wrong', hash)).toBe(false)
  })

  it('returns false for an empty hash', async () => {
    expect(await verifyPassword('anything', '')).toBe(false)
  })
})
