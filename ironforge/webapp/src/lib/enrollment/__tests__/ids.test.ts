import { describe, it, expect } from 'vitest'
import { isUuid } from '../ids'

describe('isUuid', () => {
  it('accepts a real v4 uuid in either case', () => {
    expect(isUuid('edeabb85-d9e0-4de3-8c8d-088961d49758')).toBe(true)
    expect(isUuid('EDEABB85-D9E0-4DE3-8C8D-088961D49758')).toBe(true)
  })

  it('rejects the values that actually caused 500s in production', () => {
    // These reached `WHERE id = $1` against a UUID column and made Postgres raise
    // rather than return no rows.
    expect(isUuid('does-not-exist')).toBe(false)
    expect(isUuid('')).toBe(false)
    expect(isUuid('undefined')).toBe(false)
    expect(isUuid('null')).toBe(false)
  })

  it('rejects near-misses', () => {
    expect(isUuid('edeabb85-d9e0-4de3-8c8d-088961d4975')).toBe(false) // short
    expect(isUuid('edeabb85-d9e0-4de3-8c8d-088961d497588')).toBe(false) // long
    expect(isUuid('edeabb85d9e04de38c8d088961d49758')).toBe(false) // no dashes
    expect(isUuid('gdeabb85-d9e0-4de3-8c8d-088961d49758')).toBe(false) // non-hex
    expect(isUuid(' edeabb85-d9e0-4de3-8c8d-088961d49758 ')).toBe(false) // padded
  })

  it('rejects non-strings without throwing', () => {
    for (const v of [null, undefined, 42, {}, [], true]) {
      expect(isUuid(v)).toBe(false)
    }
  })

  it('is not defeated by a newline (the anchors are ^ and $, not \\A/\\z)', () => {
    // JS $ matches before a trailing newline in multiline mode only, but a literal
    // newline inside the string must still fail.
    expect(isUuid('edeabb85-d9e0-4de3-8c8d-088961d49758\ndrop')).toBe(false)
  })
})
