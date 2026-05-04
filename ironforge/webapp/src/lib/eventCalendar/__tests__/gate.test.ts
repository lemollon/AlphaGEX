import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('../repo', () => ({
  findCurrentBlackout: vi.fn(),
}))
vi.mock('../../db', () => ({
  query: vi.fn(),
}))

import { findCurrentBlackout } from '../repo'
import { query } from '../../db'
import { isEventBlackoutActive } from '../gate'

const mockedFindBlackout = vi.mocked(findCurrentBlackout)
const mockedQuery = vi.mocked(query)

beforeEach(() => {
  mockedFindBlackout.mockReset()
  mockedQuery.mockReset()
})

describe('isEventBlackoutActive', () => {
  it('returns blocked=false when bot toggle is off', async () => {
    mockedQuery.mockResolvedValueOnce([{ event_blackout_enabled: false }] as any)
    const result = await isEventBlackoutActive('flame', new Date())
    expect(result.blocked).toBe(false)
    expect(mockedFindBlackout).not.toHaveBeenCalled()
  })

  it('returns blocked=false when no blackout window matches', async () => {
    mockedQuery.mockResolvedValueOnce([{ event_blackout_enabled: true }] as any)
    mockedFindBlackout.mockResolvedValueOnce(null)
    const result = await isEventBlackoutActive('flame', new Date())
    expect(result.blocked).toBe(false)
  })

  it('returns blocked=true with reason when in blackout', async () => {
    mockedQuery.mockResolvedValueOnce([{ event_blackout_enabled: true }] as any)
    const haltEnd = new Date('2025-06-18T19:00:00Z')
    mockedFindBlackout.mockResolvedValueOnce({
      event_id: 'finnhub:FOMC:2025-06-18',
      title: 'FOMC Meeting',
      halt_end_ts: haltEnd,
    } as any)
    const result = await isEventBlackoutActive('flame', new Date('2025-06-16T15:00:00Z'))
    expect(result.blocked).toBe(true)
    expect(result.eventId).toBe('finnhub:FOMC:2025-06-18')
    expect(result.eventTitle).toBe('FOMC Meeting')
    expect(result.resumesAt).toEqual(haltEnd)
    expect(result.reason).toContain('event_blackout')
    expect(result.reason).toContain('FOMC Meeting')
  })

  it('treats missing config row as enabled (default true)', async () => {
    mockedQuery.mockResolvedValueOnce([] as any)
    mockedFindBlackout.mockResolvedValueOnce(null)
    const result = await isEventBlackoutActive('flame', new Date())
    expect(result.blocked).toBe(false)
    expect(mockedFindBlackout).toHaveBeenCalled()
  })

  it('rejects unknown bot names without querying', async () => {
    const result = await isEventBlackoutActive('bogus', new Date())
    expect(result.blocked).toBe(false)
    expect(mockedQuery).not.toHaveBeenCalled()
    expect(mockedFindBlackout).not.toHaveBeenCalled()
  })
})
