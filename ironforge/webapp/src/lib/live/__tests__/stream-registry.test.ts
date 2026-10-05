import { describe, it, expect, beforeEach } from 'vitest'
import {
  acquireStreamSlot,
  releaseStreamSlot,
  currentStreamCount,
  _resetStreamRegistryForTest,
} from '../stream-registry'

beforeEach(() => {
  _resetStreamRegistryForTest()
})

describe('stream-registry', () => {
  it('starts every key at zero', () => {
    expect(currentStreamCount('a')).toBe(0)
  })

  it('acquires up to the max, then refuses', () => {
    expect(acquireStreamSlot('a', 2)).toBe(true)
    expect(acquireStreamSlot('a', 2)).toBe(true)
    expect(currentStreamCount('a')).toBe(2)
    expect(acquireStreamSlot('a', 2)).toBe(false)
    expect(currentStreamCount('a')).toBe(2)
  })

  it('releasing frees a slot for the next acquire', () => {
    acquireStreamSlot('a', 1)
    expect(acquireStreamSlot('a', 1)).toBe(false)
    releaseStreamSlot('a')
    expect(currentStreamCount('a')).toBe(0)
    expect(acquireStreamSlot('a', 1)).toBe(true)
  })

  it('release is safe to call with no matching acquire or past zero', () => {
    releaseStreamSlot('never-acquired')
    expect(currentStreamCount('never-acquired')).toBe(0)
    acquireStreamSlot('a', 3)
    releaseStreamSlot('a')
    releaseStreamSlot('a') // second release past zero must not go negative
    expect(currentStreamCount('a')).toBe(0)
  })

  it('keys are independent', () => {
    acquireStreamSlot('a', 1)
    expect(acquireStreamSlot('b', 1)).toBe(true)
    expect(currentStreamCount('a')).toBe(1)
    expect(currentStreamCount('b')).toBe(1)
  })
})
