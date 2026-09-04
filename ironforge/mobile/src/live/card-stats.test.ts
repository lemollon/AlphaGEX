import { describe, it, expect } from 'vitest'
import {
  formatAccountCapital,
  formatGrowth,
  formatLast10,
  formatBestTrade,
  agentStatItems,
} from '@/live/card-stats'
import { color } from '@/theme/tokens'

describe('formatAccountCapital', () => {
  it('whole dollars, no cents, thousands separator', () => {
    expect(formatAccountCapital(500000)).toBe('$5,000')
    expect(formatAccountCapital(1250000)).toBe('$12,500')
  })

  it('— when null', () => {
    expect(formatAccountCapital(null)).toBe('—')
  })
})

describe('formatGrowth', () => {
  it('positive is green with a plus sign', () => {
    expect(formatGrowth(6.8)).toEqual({ text: '+6.8%', tone: color.pos })
  })

  it('negative is red, sign comes from toFixed', () => {
    expect(formatGrowth(-4.2)).toEqual({ text: '-4.2%', tone: color.neg })
  })

  it('exactly zero is muted, not green', () => {
    expect(formatGrowth(0)).toEqual({ text: '0.0%', tone: color.textDim })
  })

  it('null is muted "—"', () => {
    expect(formatGrowth(null)).toEqual({ text: '—', tone: color.textDim })
  })
})

describe('formatLast10', () => {
  it('wins > losses is green', () => {
    expect(formatLast10({ wins: 8, losses: 2 })).toEqual({ text: '8–2', tone: color.pos })
  })

  it('wins <= losses is not green', () => {
    expect(formatLast10({ wins: 3, losses: 7 })).toEqual({ text: '3–7', tone: color.text })
    expect(formatLast10({ wins: 5, losses: 5 })).toEqual({ text: '5–5', tone: color.text })
  })

  it('fewer than 10 counts what exists', () => {
    expect(formatLast10({ wins: 2, losses: 1 })).toEqual({ text: '2–1', tone: color.pos })
  })

  it('zero closed trades is "—", not "0–0"', () => {
    expect(formatLast10({ wins: 0, losses: 0 })).toEqual({ text: '—', tone: color.textDim })
  })
})

describe('formatBestTrade', () => {
  it('whole dollars with a plus sign, always green', () => {
    expect(formatBestTrade(12200)).toEqual({ text: '+$122', tone: color.pos })
  })

  it('— when null (no winning trade)', () => {
    expect(formatBestTrade(null)).toEqual({ text: '—', tone: color.textDim })
  })
})

describe('agentStatItems', () => {
  it('builds all four items from a full stats payload', () => {
    const items = agentStatItems(
      { account_capital_cents: 500000, growth_pct: 6.8, last10: { wins: 8, losses: 2 }, best_trade_cents: 12200 },
      false,
    )
    expect(items.map((i) => i.label)).toEqual(['Account Capital', 'Growth', 'Last 10', 'Best Trade'])
    expect(items.map((i) => i.value)).toEqual(['$5,000', '+6.8%', '8–2', '+$122'])
    expect(items.every((i) => i.loading === false)).toBe(true)
  })

  it('null stats renders every column as "—" rather than throwing', () => {
    const items = agentStatItems(null, false)
    expect(items.map((i) => i.value)).toEqual(['—', '—', '—', '—'])
  })

  it('propagates the loading flag to every column', () => {
    const items = agentStatItems(null, true)
    expect(items.every((i) => i.loading === true)).toBe(true)
  })
})
