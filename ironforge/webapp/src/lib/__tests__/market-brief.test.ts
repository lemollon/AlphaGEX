/**
 * Unit tests for market-brief.ts's GEX sourcing + rendering.
 *
 * Covers the a964d310 regression: the old alphagex-api `/api/gex/{symbol}`
 * route is gone, so gatherInputs()/formatInputsForPrompt() must degrade to
 * null GEX fields (never fabricate) instead of throwing or showing stale data.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../db', () => ({
  dbQuery: vi.fn().mockResolvedValue([]),
  dbExecute: vi.fn().mockResolvedValue(1),
  botTable: (bot: string, suffix: string) => `${bot}_${suffix}`,
  num: (v: any) => { if (v == null || v === '') return 0; const n = parseFloat(v); return isNaN(n) ? 0 : n },
  dteMode: () => null,
}))

vi.mock('../tradier', () => ({
  getRawQuotes: vi.fn().mockResolvedValue({
    SPY: { last: 580 },
    VIX: { last: 16 },
    VVIX: { last: 90 },
    VIX9D: { last: 15 },
    VIX3M: { last: 17 },
    VIX6M: { last: 18 },
  }),
  isConfigured: vi.fn().mockReturnValue(true),
}))

const fetchGexLevelsMock = vi.fn()
vi.mock('../gex-levels', () => ({
  fetchGexLevels: (...args: any[]) => fetchGexLevelsMock(...args),
  regimeFromNetGex: (netGex: number) => {
    if (netGex >= 1e9) return 'MODERATE_POSITIVE'
    if (netGex <= -1e9) return 'MODERATE_NEGATIVE'
    return 'NEUTRAL'
  },
}))

const getTvMarketStructureMock = vi.fn()
vi.mock('../gex/trading-volatility-client', () => ({
  getTvMarketStructure: (...args: any[]) => getTvMarketStructureMock(...args),
}))

vi.mock('../volatility', () => ({
  formatVolRegime: vi.fn().mockReturnValue(null),
}))

import { gatherInputs, formatInputsForPrompt } from '../market-brief'

describe('market-brief GEX sourcing (post a964d310)', () => {
  beforeEach(() => {
    fetchGexLevelsMock.mockReset()
    getTvMarketStructureMock.mockReset()
    // gatherVolRegime() hits the (also-dead) /api/vix/regime-advisor endpoint
    // over real fetch(); stub it out so tests never make a network call and
    // fall straight through to the local VIX-based fallback.
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('no network in tests')))
  })

  it('gex_state.available is false and every field is null when the chain feed is totally empty', async () => {
    fetchGexLevelsMock.mockResolvedValue({
      spot: null, net_gex: null, call_gex: null, put_gex: null, call_wall: null, put_wall: null,
    })
    getTvMarketStructureMock.mockResolvedValue(null)

    const inputs = await gatherInputs('spark', 'morning')
    expect(inputs.gex_state.available).toBe(false)
    expect(inputs.gex_state.net_gex).toBeNull()
    expect(inputs.gex_state.call_wall).toBeNull()
    expect(inputs.gex_state.put_wall).toBeNull()
    expect(inputs.gex_state.flip_point).toBeNull()

    // Rendering must not throw and must not invent a number — it should say
    // the feed is unavailable rather than printing a fabricated level.
    const rendered = formatInputsForPrompt('spark', inputs)
    expect(rendered).toContain('GEX feed unavailable')
    expect(rendered).not.toMatch(/Call wall: \$/)
  })

  it('gex_state carries walls/regime from the chain and flip only from TradingVolatility', async () => {
    fetchGexLevelsMock.mockResolvedValue({
      spot: 580, net_gex: 1.5e9, call_gex: 3e9, put_gex: 1.5e9, call_wall: 590, put_wall: 570,
    })
    getTvMarketStructureMock.mockResolvedValue({
      ticker: 'SPY', gammaFlipPrice: 575, structureRegime: 'above_flip_positive_gamma',
      gammaToneState: 'positive', flipState: 'above_flip', spot: 580, distanceToFlipPct: 0.8, asof: '',
    })

    const inputs = await gatherInputs('spark', 'morning')
    expect(inputs.gex_state.available).toBe(true)
    expect(inputs.gex_state.call_wall).toBe(590)
    expect(inputs.gex_state.put_wall).toBe(570)
    expect(inputs.gex_state.flip_point).toBe(575)
    expect(inputs.gex_state.regime).toBe('MODERATE_POSITIVE')
    expect(inputs.gex_state.spot_vs_flip).toBe('above')

    const rendered = formatInputsForPrompt('spark', inputs)
    expect(rendered).toContain('Call wall: $590.00')
    expect(rendered).toContain('Put wall: $570.00')
    expect(rendered).toContain('Flip point: $575.00')
  })

  it('missing flip point alone does not mark the whole GEX profile unavailable', async () => {
    fetchGexLevelsMock.mockResolvedValue({
      spot: 580, net_gex: 1.5e9, call_gex: 3e9, put_gex: 1.5e9, call_wall: 590, put_wall: 570,
    })
    getTvMarketStructureMock.mockResolvedValue(null) // no TRADING_VOLATILITY_API_KEY

    const inputs = await gatherInputs('spark', 'morning')
    expect(inputs.gex_state.available).toBe(true)
    expect(inputs.gex_state.flip_point).toBeNull()
    expect(inputs.gex_state.spot_vs_flip).toBe('unknown')

    const rendered = formatInputsForPrompt('spark', inputs)
    expect(rendered).toContain('Flip point: n/a')
  })

  it('never throws when both the chain feed and TradingVolatility reject', async () => {
    fetchGexLevelsMock.mockRejectedValue(new Error('tradier down'))
    getTvMarketStructureMock.mockRejectedValue(new Error('tv down'))

    await expect(gatherInputs('spark', 'morning')).resolves.toBeTruthy()
  })
})
