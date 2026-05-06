/**
 * TradeHistoryTable - shared component tests
 */
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TradeHistoryTable } from '@/components/perpetuals/TradeHistoryTable'
import * as hookMod from '@/lib/hooks/useAgapePerpTrades'

jest.mock('@/lib/hooks/useAgapePerpTrades')

function mockHook(
  overrides: Partial<ReturnType<typeof hookMod.useAgapePerpTrades>> = {},
) {
  ;(hookMod.useAgapePerpTrades as jest.Mock).mockReturnValue({
    trades: [],
    hasMore: false,
    loadMore: jest.fn(),
    reset: jest.fn(),
    isLoading: false,
    isLoadingMore: false,
    error: undefined,
    ...overrides,
  })
}

const sampleTrade = {
  bot_id: 'btc',
  bot_label: 'BTC-PERP',
  position_id: 'b1',
  side: 'long' as const,
  quantity: 1,
  entry_price: 100,
  close_price: 110,
  realized_pnl: 10,
  realized_pnl_pct: 10,
  close_reason: 'PROFIT',
  open_time: null,
  close_time: '2026-05-05T10:00:00Z',
  max_risk_usd: 100,
}

test('renders rows from hook', () => {
  mockHook({ trades: [sampleTrade] })
  render(<TradeHistoryTable bots={['btc']} />)
  expect(screen.getByText('PROFIT')).toBeInTheDocument()
})

test('shows bot column when showBotColumn=true', () => {
  mockHook({ trades: [sampleTrade] })
  render(<TradeHistoryTable bots={['btc', 'eth']} showBotColumn />)
  expect(screen.getByText('BTC-PERP')).toBeInTheDocument()
})

test('Load more invokes hook.loadMore', () => {
  const loadMore = jest.fn()
  mockHook({ trades: [sampleTrade], hasMore: true, loadMore })
  render(<TradeHistoryTable bots={['btc']} />)
  fireEvent.click(screen.getByRole('button', { name: /load more/i }))
  expect(loadMore).toHaveBeenCalled()
})

test('range chip switches range', async () => {
  mockHook({ trades: [] })
  render(<TradeHistoryTable bots={['btc']} defaultRange="30d" />)
  fireEvent.click(screen.getByRole('button', { name: '7d' }))
  await waitFor(() => {
    const lastCall = (hookMod.useAgapePerpTrades as jest.Mock).mock.calls.at(-1)?.[0]
    expect(lastCall?.range).toBe('7d')
  })
})

test('shows empty state when no trades and not loading', () => {
  mockHook({ trades: [], isLoading: false })
  render(<TradeHistoryTable bots={['btc']} />)
  expect(screen.getByText(/no closed trades/i)).toBeInTheDocument()
})
