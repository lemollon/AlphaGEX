/**
 * MultiBotPerpEquityChart - normalization helper tests.
 */
import { normalizeForChart } from '@/components/perpetuals/MultiBotPerpEquityChart'

const today = new Date().toISOString().slice(0, 10)
const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10)
const twoDaysAgo = new Date(Date.now() - 2 * 86_400_000).toISOString().slice(0, 10)

const eth = {
  bot_id: 'eth',
  label: 'ETH-PERP',
  color: '#aaa',
  starting_capital: 10000,
  equity_curve: [
    { date: twoDaysAgo, equity: 10000 },
    { date: yesterday, equity: 10500 },
    { date: today, equity: 11000 },
  ],
}
const btc = {
  bot_id: 'btc',
  label: 'BTC-PERP',
  color: '#bbb',
  starting_capital: 25000,
  equity_curve: [
    { date: yesterday, equity: 25000 },
    { date: today, equity: 26000 },
  ],
}

test('indexed mode: every visible bot first in-window point is 100', () => {
  const series = normalizeForChart([eth, btc], { mode: 'indexed', windowDays: 90 })
  expect(series.find(s => s.bot_id === 'eth')!.points[0].value).toBe(100)
  expect(series.find(s => s.bot_id === 'btc')!.points[0].value).toBe(100)
})

test('indexed mode: subsequent points scale by ratio', () => {
  const series = normalizeForChart([eth], { mode: 'indexed', windowDays: 90 })
  const ethSeries = series.find(s => s.bot_id === 'eth')!
  expect(ethSeries.points[1].value).toBeCloseTo(105, 5)
  expect(ethSeries.points[2].value).toBeCloseTo(110, 5)
})

test('percent mode: matches (equity - starting) / starting × 100', () => {
  const series = normalizeForChart([eth, btc], { mode: 'percent', windowDays: 90 })
  const ethSeries = series.find(s => s.bot_id === 'eth')!
  expect(ethSeries.points[2].value).toBeCloseTo(10, 5)
  const btcSeries = series.find(s => s.bot_id === 'btc')!
  expect(btcSeries.points[1].value).toBeCloseTo(4, 5)
})

test('bot with no in-window data is excluded from indexed series', () => {
  const orphan = {
    bot_id: 'old',
    label: 'OLD',
    color: '#ccc',
    starting_capital: 1000,
    equity_curve: [{ date: '2020-01-01', equity: 500 }],
  }
  const series = normalizeForChart([eth, orphan], { mode: 'indexed', windowDays: 30 })
  expect(series.find(s => s.bot_id === 'old')).toBeUndefined()
})
