import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/lib/db', () => ({ dbQuery: vi.fn() }))
vi.mock('@/lib/tradier', () => ({ getProductionAccountsForBot: vi.fn() }))
vi.mock('../viewer', () => ({
  isLiveBot: (v: string | null | undefined) => v === 'flame' || v === 'spark',
  resolveAccountMode: vi.fn(),
}))

import { dbQuery } from '@/lib/db'
import { getProductionAccountsForBot } from '@/lib/tradier'
import { resolveAccountMode } from '../viewer'
import { resolveExecutingBroker } from '../executing-broker'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('resolveExecutingBroker', () => {
  it('is null with no customerId', async () => {
    expect(await resolveExecutingBroker(null)).toBeNull()
    expect(await resolveExecutingBroker(undefined)).toBeNull()
    expect(dbQuery).not.toHaveBeenCalled()
  })

  it('resolves Tradier + the real last-4 for a bot mapped to a house production account', async () => {
    ;(dbQuery as any).mockResolvedValue([{ bot: 'flame' }])
    ;(resolveAccountMode as any).mockReturnValue('production')
    ;(getProductionAccountsForBot as any).mockResolvedValue([
      { name: 'Flame', apiKey: 'secret-key', baseUrl: 'https://api.tradier.com', accountId: '6YB71371' },
    ])
    const result = await resolveExecutingBroker('cust1')
    expect(result).toEqual({ bot: 'flame', broker: 'Tradier', last4: '1371' })
  })

  it('never includes the API key or full account number', async () => {
    ;(dbQuery as any).mockResolvedValue([{ bot: 'spark' }])
    ;(resolveAccountMode as any).mockReturnValue('production')
    ;(getProductionAccountsForBot as any).mockResolvedValue([
      { name: 'User', apiKey: 'top-secret', baseUrl: 'https://api.tradier.com', accountId: 'VA00112233' },
    ])
    const result = await resolveExecutingBroker('cust1')
    expect(result).toEqual({ bot: 'spark', broker: 'Tradier', last4: '2233' })
    expect(JSON.stringify(result)).not.toContain('top-secret')
    expect(JSON.stringify(result)).not.toContain('VA00112233')
  })

  it('is null when the mapped bot is not in production mode (paper)', async () => {
    ;(dbQuery as any).mockResolvedValue([{ bot: 'flame' }])
    ;(resolveAccountMode as any).mockReturnValue('paper')
    const result = await resolveExecutingBroker('cust1')
    expect(result).toBeNull()
    expect(getProductionAccountsForBot).not.toHaveBeenCalled()
  })

  it('is null when the mapped bot resolves to zero production accounts (e.g. paused)', async () => {
    ;(dbQuery as any).mockResolvedValue([{ bot: 'flame' }])
    ;(resolveAccountMode as any).mockReturnValue('production')
    ;(getProductionAccountsForBot as any).mockResolvedValue([])
    expect(await resolveExecutingBroker('cust1')).toBeNull()
  })

  it('ignores a bot mapping that is not a live bot (e.g. a retired/unknown name)', async () => {
    ;(dbQuery as any).mockResolvedValue([{ bot: 'kindle' }])
    const result = await resolveExecutingBroker('cust1')
    expect(result).toBeNull()
    expect(resolveAccountMode).not.toHaveBeenCalled()
  })

  it('fails closed (null) rather than throwing when the lookup errors', async () => {
    ;(dbQuery as any).mockRejectedValue(new Error('db down'))
    expect(await resolveExecutingBroker('cust1')).toBeNull()
  })
})
