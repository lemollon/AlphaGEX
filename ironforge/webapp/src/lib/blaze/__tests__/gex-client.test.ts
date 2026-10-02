/**
 * Unit tests for blaze/gex-client.ts's post-a964d310 GEX sourcing.
 *
 * The old alphagex-api `/api/gex/{symbol}` route is gone (404 forever), so
 * fetchGexSnapshot() must now compute GEX from the live Tradier option chain
 * (lib/gex-levels.ts) + a TradingVolatility flip read, and degrade every
 * missing field to the exact "off" value setups.ts already treats as absent
 * — never fabricate, never throw except when spot itself is unavailable
 * (mirrors the old 404 behavior of skipping the whole cycle).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const fetchGexLevelsMock = vi.fn()
vi.mock('@/lib/gex-levels', () => ({
  fetchGexLevels: (...args: any[]) => fetchGexLevelsMock(...args),
  regimeFromNetGex: (netGex: number) => {
    if (netGex <= -3e9) return 'EXTREME_NEGATIVE'
    if (netGex <= -2e9) return 'HIGH_NEGATIVE'
    if (netGex <= -1e9) return 'MODERATE_NEGATIVE'
    if (netGex >= 3e9) return 'EXTREME_POSITIVE'
    if (netGex >= 2e9) return 'HIGH_POSITIVE'
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
import { evaluateWallFade, evaluateWallBreak, evaluateFlipCross, FlipBuffer } from '../setups'
import { DEFAULT_BLAZE_CONFIG } from '../types'

describe('blaze gex-client (post a964d310, direct Tradier compute)', () => {
  beforeEach(() => {
    fetchGexLevelsMock.mockReset()
    getTvMarketStructureMock.mockReset()
    getQuoteMock.mockReset()
  })

  it('maps a full gex-levels + TV + VIX result to the exact GexSnapshot shape the scanners consume', async () => {
    fetchGexLevelsMock.mockResolvedValue({
      spot: 580, net_gex: 1.5e9, call_gex: 3e9, put_gex: 1.5e9, call_wall: 590, put_wall: 570,
    })
    getTvMarketStructureMock.mockResolvedValue({
      ticker: 'SPY', gammaFlipPrice: 575, structureRegime: 'above_flip_positive_gamma',
      gammaToneState: 'positive', flipState: 'above_flip', spot: 580, distanceToFlipPct: 0.8, asof: '',
    })
    getQuoteMock.mockResolvedValue({ last: 16, bid: 16, ask: 16, symbol: 'VIX' })

    const snap = await fetchGexSnapshot('SPY', 90)

    expect(fetchGexLevelsMock).toHaveBeenCalledWith('SPY', 45)
    expect(getTvMarketStructureMock).toHaveBeenCalledWith('SPY')
    expect(getQuoteMock).toHaveBeenCalledWith('VIX')

    expect(snap.symbol).toBe('SPY')
    expect(snap.spot).toBe(580)
    expect(snap.net_gex).toBe(1.5e9)
    expect(snap.call_wall).toBe(590)
    expect(snap.put_wall).toBe(570)
    expect(snap.flip_point).toBe(575)
    expect(snap.vix).toBe(16)
    expect(snap.regime).toBe('MODERATE_POSITIVE')
    // spot * (vix/100) * sqrt(1/252)
    expect(snap.sigma_1d_band_width).toBeCloseTo(580 * 0.16 * Math.sqrt(1 / 252), 6)
    expect(snap.snapshot_at).toBeInstanceOf(Date)
  })

  it('degrades a missing wall/flip/net_gex/vix to 0, not a fabricated or stale number', async () => {
    fetchGexLevelsMock.mockResolvedValue({
      spot: 580, net_gex: null, call_gex: null, put_gex: null, call_wall: null, put_wall: null,
    })
    getTvMarketStructureMock.mockResolvedValue(null) // no TV key / feed down
    getQuoteMock.mockResolvedValue(null) // VIX quote unavailable

    const snap = await fetchGexSnapshot('SPY', 90)

    expect(snap.spot).toBe(580)
    expect(snap.net_gex).toBe(0)
    expect(snap.call_wall).toBe(0)
    expect(snap.put_wall).toBe(0)
    expect(snap.flip_point).toBe(0)
    expect(snap.vix).toBe(0)
    expect(snap.sigma_1d_band_width).toBe(0)
    expect(snap.regime).toBe('NEUTRAL')
  })

  it('null fields make every setup skip (fail safe) instead of trading on a fabricated level', async () => {
    fetchGexLevelsMock.mockResolvedValue({
      spot: 580, net_gex: null, call_gex: null, put_gex: null, call_wall: null, put_wall: null,
    })
    getTvMarketStructureMock.mockResolvedValue(null)
    getQuoteMock.mockResolvedValue(null)

    const snap = await fetchGexSnapshot('SPY', 90)

    // wall_fade requires a POSITIVE regime and sigma > 0 — NEUTRAL + sigma=0 skips.
    expect(evaluateWallFade(snap, DEFAULT_BLAZE_CONFIG)).toBeNull()
    // wall_break requires a NEGATIVE regime and sigma > 0 — same skip.
    expect(evaluateWallBreak(snap, DEFAULT_BLAZE_CONFIG)).toBeNull()
    // flip_cross requires flip > 0 — 0 means "no flip", skip.
    const buffer = new FlipBuffer(DEFAULT_BLAZE_CONFIG.flip_buffer_minutes)
    buffer.add(snap)
    expect(evaluateFlipCross(snap, buffer, DEFAULT_BLAZE_CONFIG)).toBeNull()
  })

  it('a fetch error (missing spot) still fails safe — throws instead of trading on a guess', async () => {
    fetchGexLevelsMock.mockResolvedValue({
      spot: null, net_gex: null, call_gex: null, put_gex: null, call_wall: null, put_wall: null,
    })
    getTvMarketStructureMock.mockResolvedValue(null)
    getQuoteMock.mockResolvedValue(null)

    await expect(fetchGexSnapshot('SPY', 90)).rejects.toThrow(GexFetchError)
  })

  it('a thrown gex-levels fetch failure propagates rather than being swallowed into a fake snapshot', async () => {
    fetchGexLevelsMock.mockRejectedValue(new Error('tradier chain fetch failed'))
    getTvMarketStructureMock.mockResolvedValue(null)
    getQuoteMock.mockResolvedValue(null)

    await expect(fetchGexSnapshot('SPY', 90)).rejects.toThrow('tradier chain fetch failed')
  })
})
