import { describe, it, expect } from 'vitest'
import { parseBriefResponse } from '../schema'

const VALID = {
  title: 'FLAME — Day in the Forge',
  bot_voice_signature: 'The forge cools slowly, but it cools.',
  wisdom: 'Theta does its work whether you watch or not.',
  risk_score: 5,
  summary: 'Para 1.\n\nPara 2.',
  factors: [
    { rank: 1, title: 'Pin gravity at 587', detail: 'SPY hugged 587 from open to close.' },
    { rank: 2, title: 'VIX cooled', detail: 'VIX dropped 0.7 on the day.' },
  ],
  trade_of_day: {
    position_id: 'pos-1', strikes: { ps: 582, pl: 577, cs: 595, cl: 600 },
    entry_credit: 1.20, exit_cost: 0.36, contracts: 5, pnl: 420,
    payoff_points: [{ spot: 575, pnl: -800 }, { spot: 587, pnl: 420 }, { spot: 600, pnl: -800 }],
  },
}

describe('parseBriefResponse', () => {
  it('parses a valid response wrapped in JSON', () => {
    const r = parseBriefResponse(JSON.stringify(VALID))
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.brief.title).toBe('FLAME — Day in the Forge')
  })

  it('strips markdown code fences if Claude wraps the JSON', () => {
    const wrapped = '```json\n' + JSON.stringify(VALID) + '\n```'
    const r = parseBriefResponse(wrapped)
    expect(r.ok).toBe(true)
  })

  it('rejects when title is missing', () => {
    const bad = { ...VALID, title: undefined }
    const r = parseBriefResponse(JSON.stringify(bad))
    expect(r.ok).toBe(false)
  })

  it('rejects when risk_score is not 0-10', () => {
    const bad = { ...VALID, risk_score: 15 }
    const r = parseBriefResponse(JSON.stringify(bad))
    expect(r.ok).toBe(false)
  })

  it('accepts trade_of_day === null', () => {
    const noTrade = { ...VALID, trade_of_day: null }
    const r = parseBriefResponse(JSON.stringify(noTrade))
    expect(r.ok).toBe(true)
  })

  it('rejects unparseable strings', () => {
    expect(parseBriefResponse('not json').ok).toBe(false)
    expect(parseBriefResponse('').ok).toBe(false)
  })
})
