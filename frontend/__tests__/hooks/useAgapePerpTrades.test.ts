/**
 * useAgapePerpTrades - hook tests
 */
import React from 'react'
import { renderHook, act, waitFor } from '@testing-library/react'
import { SWRConfig } from 'swr'
import { useAgapePerpTrades } from '@/lib/hooks/useAgapePerpTrades'

const wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) =>
  React.createElement(
    SWRConfig,
    { value: { provider: () => new Map(), dedupingInterval: 0 } },
    children,
  )

beforeEach(() => {
  // @ts-ignore
  global.fetch = jest.fn()
})

afterEach(() => {
  jest.useRealTimers()
})

function mockResponse(payload: any) {
  // @ts-ignore
  global.fetch.mockResolvedValueOnce({
    ok: true,
    json: async () => payload,
  })
}

test('fetches initial page with default 30d range', async () => {
  mockResponse({
    trades: [
      {
        bot_id: 'btc',
        position_id: 'b1',
        close_time: '2026-05-05T10:00:00Z',
        realized_pnl: 10,
      },
    ],
    has_more: false,
    next_cursor: null,
  })

  const { result } = renderHook(
    () => useAgapePerpTrades({ bots: ['btc'], range: '30d' }),
    { wrapper },
  )
  await waitFor(() => expect(result.current.isLoading).toBe(false))
  await waitFor(() => expect(result.current.trades).toHaveLength(1))
  expect(result.current.hasMore).toBe(false)

  // @ts-ignore
  const url: string = global.fetch.mock.calls[0][0]
  expect(url).toContain('/api/agape-perpetuals/trades')
  expect(url).toContain('bots=btc')
  expect(url).toContain('limit=100')
})

test('loadMore appends next page using cursor', async () => {
  mockResponse({
    trades: [
      {
        bot_id: 'btc',
        position_id: 'b1',
        close_time: '2026-05-05T10:00:00Z',
        realized_pnl: 10,
      },
    ],
    has_more: true,
    next_cursor: 'CURSOR1',
  })

  const { result } = renderHook(
    () => useAgapePerpTrades({ bots: ['btc'], range: '30d' }),
    { wrapper },
  )
  await waitFor(() => expect(result.current.trades).toHaveLength(1))

  mockResponse({
    trades: [
      {
        bot_id: 'btc',
        position_id: 'b2',
        close_time: '2026-05-04T10:00:00Z',
        realized_pnl: 5,
      },
    ],
    has_more: false,
    next_cursor: null,
  })

  act(() => {
    result.current.loadMore()
  })
  await waitFor(() => expect(result.current.trades).toHaveLength(2))

  // @ts-ignore
  const url: string = global.fetch.mock.calls[1][0]
  expect(url).toContain('before=CURSOR1')
})

test('range change resets accumulated pages', async () => {
  mockResponse({
    trades: [
      {
        bot_id: 'btc',
        position_id: 'b1',
        close_time: '2026-05-05T10:00:00Z',
        realized_pnl: 1,
      },
    ],
    has_more: true,
    next_cursor: 'C',
  })
  const { result, rerender } = renderHook(
    ({ range }: { range: '7d' | '30d' }) => useAgapePerpTrades({ bots: ['btc'], range }),
    { wrapper, initialProps: { range: '30d' } },
  )
  await waitFor(() => expect(result.current.trades).toHaveLength(1))

  mockResponse({
    trades: [
      {
        bot_id: 'btc',
        position_id: 'b9',
        close_time: '2026-05-05T11:00:00Z',
        realized_pnl: 9,
      },
    ],
    has_more: false,
    next_cursor: null,
  })
  rerender({ range: '7d' })
  await waitFor(() =>
    expect(result.current.trades).toEqual([expect.objectContaining({ position_id: 'b9' })]),
  )
})
