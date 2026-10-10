/**
 * FLARE re-exports BLAZE's gex-client unchanged (see flare/gex-client.ts),
 * so this only needs to confirm the re-export still resolves to the fixed
 * client (post a964d310 direct-Tradier compute) and that FLARE's own setups
 * (also a re-export of blaze/setups.ts) skip cleanly on a degraded snapshot.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const fetchGexLevelsMock = vi.fn()
vi.mock('@/lib/gex-levels', () => ({
  fetchGexLevels: (...args: any[]) => fetchGexLevelsMock(...args),
  regimeFromNetGex: (netGex: number) => {
    if (netGex <= -1e9) return 'MODERATE_NEGATIVE'
    if (netGex >= 1e9) return 'MODERATE_POSITIVE'
    return 'NEUTRAL'
  },
}))

const getTvMarketStructureMock = vi.fn()
vi.mock('@/lib/gex/trading-volatility-client', () => ({
  getTvMarketStructure: (...args: any[]) => getTvMarketStructureMock(...args),
}))

const getQuoteMock = vi.fn()
vi.mock('@/lib/tradier', () => ({
  getQuote: (...args: any[]) => getQuoteMock(...args),
}))

import { fetchGexSnapshot, GexFetchError } from '../gex-client'
import { evaluateWallFade, evaluateWallBreak } from '../setups'
import { DEFAULT_FLARE_CONFIG } from '../types'

describe('flare gex-client (re-export of the fixed blaze client)', () => {
  beforeEach(() => {
    fetchGexLevelsMock.mockReset()
    getTvMarketStructureMock.mockReset()
    getQuoteMock.mockReset()
  })

  it('maps a full gex-levels result to the GexSnapshot shape FLARE consumes', async () => {
    fetchGexLevelsMock.mockResolvedValue({
      spot: 660, net_gex: -1.2e9, call_gex: 1e9, put_gex: 2.2e9, call_wall: 665, put_wall: 655,
    })
    getTvMarketStructureMock.mockResolvedValue({
      ticker: 'SPY', gammaFlipPrice: 658, structureRegime: 'below_flip_negative_gamma',
      gammaToneState: 'negative', flipState: 'below_flip', spot: 660, distanceToFlipPct: 0.3, asof: '',
    })
    getQuoteMock.mockResolvedValue({ last: 22, bid: 22, ask: 22, symbol: 'VIX' })

    const snap = await fetchGexSnapshot('SPY', 90)

    expect(snap.spot).toBe(660)
    expect(snap.net_gex).toBe(-1.2e9)
    expect(snap.call_wall).toBe(665)
    expect(snap.put_wall).toBe(655)
    expect(snap.flip_point).toBe(658)
    expect(snap.vix).toBe(22)
    expect(snap.regime).toBe('MODERATE_NEGATIVE')
  })

  it('null wall/regime fields degrade to 0/NEUTRAL and every FLARE setup skips', async () => {
    fetchGexLevelsMock.mockResolvedValue({
      spot: 660, net_gex: null, call_gex: null, put_gex: null, call_wall: null, put_wall: null,
    })
    getTvMarketStructureMock.mockResolvedValue(null)
    getQuoteMock.mockResolvedValue(null)

    const snap = await fetchGexSnapshot('SPY', 90)
    expect(snap.call_wall).toBe(0)
    expect(snap.put_wall).toBe(0)
    expect(snap.regime).toBe('NEUTRAL')

    expect(evaluateWallFade(snap, DEFAULT_FLARE_CONFIG)).toBeNull()
    expect(evaluateWallBreak(snap, DEFAULT_FLARE_CONFIG)).toBeNull()
  })

  it('a missing spot still fails safe on the FLARE path (throws, never trades on a guess)', async () => {
    fetchGexLevelsMock.mockResolvedValue({
      spot: null, net_gex: null, call_gex: null, put_gex: null, call_wall: null, put_wall: null,
    })
    getTvMarketStructureMock.mockResolvedValue(null)
    getQuoteMock.mockResolvedValue(null)

    await expect(fetchGexSnapshot('SPY', 90)).rejects.toThrow(GexFetchError)
  })
})
