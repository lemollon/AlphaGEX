'use client'

import { useMemo } from 'react'
import useSWR from 'swr'
import Link from 'next/link'
import { Activity, ArrowUpRight, ArrowDownRight, Clock, RefreshCw, CheckCircle, XCircle, Timer } from 'lucide-react'
import { BOT_BRANDS, BotName } from '@/components/trader/BotBranding'

interface Trade {
  position_id: string
  bot: BotName
  action: 'ENTRY' | 'EXIT' | 'EXPIRED'
  spread_type?: string
  direction?: string
  ticker: string
  contracts?: number
  realized_pnl?: number
  return_pct?: number
  close_reason?: string
  status: string
  timestamp: string
  open_time?: string
  close_time?: string
  entry_time?: string
}

interface PositionsResponse {
  success?: boolean
  data?: Trade[] | { open_positions?: Trade[]; closed_positions?: Trade[]; positions?: Trade[] }
  positions?: Trade[]
  open_positions?: Trade[]
  closed_positions?: Trade[]
}

const LIVE_BOTS: { name: BotName; endpoint: string }[] = [
  { name: 'ARES', endpoint: '/api/ares/positions' },
  { name: 'ATHENA', endpoint: '/api/athena/positions' },
  { name: 'ICARUS', endpoint: '/api/icarus/positions' },
  { name: 'PEGASUS', endpoint: '/api/pegasus/positions' },
  { name: 'TITAN', endpoint: '/api/titan/positions' },
]

const fetcher = async (url: string): Promise<PositionsResponse> => {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}${url}`)
    if (!res.ok) return {}
    return res.json()
  } catch {
    return {}
  }
}

export default function TodaysActivityFeed() {
  // Fetch positions for all bots
  const { data: aresData, isLoading: aresLoading } = useSWR('/api/ares/positions', fetcher, { refreshInterval: 30000 })
  const { data: athenaData, isLoading: athenaLoading } = useSWR('/api/athena/positions', fetcher, { refreshInterval: 30000 })
  const { data: icarusData, isLoading: icarusLoading } = useSWR('/api/icarus/positions', fetcher, { refreshInterval: 30000 })
  const { data: pegasusData, isLoading: pegasusLoading } = useSWR('/api/pegasus/positions', fetcher, { refreshInterval: 30000 })
  const { data: titanData, isLoading: titanLoading } = useSWR('/api/titan/positions', fetcher, { refreshInterval: 30000 })

  const isLoading = aresLoading || athenaLoading || icarusLoading || pegasusLoading || titanLoading

  // Get today's date in Central Time
  const getTodayString = () => {
    const now = new Date()
    return now.toLocaleDateString('en-CA', { timeZone: 'America/Chicago' }) // YYYY-MM-DD format
  }

  // Extract all trades from response
  const extractTrades = (response: PositionsResponse | undefined, botName: BotName): Trade[] => {
    if (!response) return []

    const trades: Trade[] = []
    const today = getTodayString()

    // Handle different response structures
    const extractFromArray = (arr: Trade[], isOpen: boolean) => {
      arr.forEach(pos => {
        const openTime = pos.open_time || pos.entry_time || pos.timestamp
        const closeTime = pos.close_time

        // Check if entry was today
        if (openTime) {
          const openDate = new Date(openTime).toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
          if (openDate === today) {
            trades.push({
              ...pos,
              bot: botName,
              action: 'ENTRY',
              timestamp: openTime,
            })
          }
        }

        // Check if exit was today (only for closed positions)
        if (!isOpen && closeTime) {
          const closeDate = new Date(closeTime).toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
          if (closeDate === today) {
            trades.push({
              ...pos,
              bot: botName,
              action: pos.status === 'expired' || pos.close_reason?.toLowerCase().includes('expir') ? 'EXPIRED' : 'EXIT',
              timestamp: closeTime,
            })
          }
        }
      })
    }

    if (response.data) {
      if (Array.isArray(response.data)) {
        const openPos = response.data.filter(p => p.status === 'open' || p.status === 'OPEN')
        const closedPos = response.data.filter(p => p.status !== 'open' && p.status !== 'OPEN')
        extractFromArray(openPos, true)
        extractFromArray(closedPos, false)
      } else {
        if (response.data.open_positions) {
          extractFromArray(response.data.open_positions, true)
        }
        if (response.data.closed_positions) {
          extractFromArray(response.data.closed_positions, false)
        }
        if (response.data.positions) {
          const openPos = response.data.positions.filter(p => p.status === 'open' || p.status === 'OPEN')
          const closedPos = response.data.positions.filter(p => p.status !== 'open' && p.status !== 'OPEN')
          extractFromArray(openPos, true)
          extractFromArray(closedPos, false)
        }
      }
    } else {
      if (response.open_positions) {
        extractFromArray(response.open_positions, true)
      }
      if (response.closed_positions) {
        extractFromArray(response.closed_positions, false)
      }
      if (response.positions) {
        const openPos = response.positions.filter(p => p.status === 'open' || p.status === 'OPEN')
        const closedPos = response.positions.filter(p => p.status !== 'open' && p.status !== 'OPEN')
        extractFromArray(openPos, true)
        extractFromArray(closedPos, false)
      }
    }

    return trades
  }

  // Combine and sort all trades
  const todaysTrades = useMemo(() => {
    const allTrades = [
      ...extractTrades(aresData, 'ARES'),
      ...extractTrades(athenaData, 'ATHENA'),
      ...extractTrades(icarusData, 'ICARUS'),
      ...extractTrades(pegasusData, 'PEGASUS'),
      ...extractTrades(titanData, 'TITAN'),
    ]

    // Sort by timestamp descending (most recent first)
    return allTrades.sort((a, b) => {
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    })
  }, [aresData, athenaData, icarusData, pegasusData, titanData])

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
      timeZone: 'America/Chicago',
    })
  }

  const getActionIcon = (action: string, pnl?: number) => {
    switch (action) {
      case 'ENTRY':
        return <ArrowUpRight className="w-4 h-4 text-blue-400" />
      case 'EXIT':
        if (pnl !== undefined) {
          return pnl >= 0 ? (
            <CheckCircle className="w-4 h-4 text-green-400" />
          ) : (
            <XCircle className="w-4 h-4 text-red-400" />
          )
        }
        return <ArrowDownRight className="w-4 h-4 text-gray-400" />
      case 'EXPIRED':
        return <Timer className="w-4 h-4 text-purple-400" />
      default:
        return <Activity className="w-4 h-4 text-gray-400" />
    }
  }

  const getActionLabel = (trade: Trade) => {
    switch (trade.action) {
      case 'ENTRY':
        return 'Opened'
      case 'EXIT':
        return trade.close_reason || 'Closed'
      case 'EXPIRED':
        return 'Expired'
      default:
        return trade.action
    }
  }

  const getPositionDescription = (trade: Trade) => {
    if (trade.spread_type === 'IRON_CONDOR') {
      return 'Iron Condor'
    }
    if (trade.direction) {
      return `${trade.direction === 'BULLISH' ? 'Bull' : 'Bear'} Spread`
    }
    return trade.spread_type || 'Position'
  }

  // Calculate summary stats
  const summary = useMemo(() => {
    const entries = todaysTrades.filter(t => t.action === 'ENTRY').length
    const exits = todaysTrades.filter(t => t.action === 'EXIT' || t.action === 'EXPIRED').length
    const totalPnl = todaysTrades
      .filter(t => t.action !== 'ENTRY' && t.realized_pnl !== undefined)
      .reduce((sum, t) => sum + (t.realized_pnl || 0), 0)

    return { entries, exits, totalPnl }
  }, [todaysTrades])

  return (
    <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Activity className="w-5 h-5 text-primary" />
          <div>
            <h3 className="font-semibold text-white">Today's Trading Activity</h3>
            <p className="text-xs text-gray-500">
              {summary.entries} entries, {summary.exits} exits
              {summary.exits > 0 && (
                <span className={summary.totalPnl >= 0 ? 'text-green-500' : 'text-red-500'}>
                  {' '} ({summary.totalPnl >= 0 ? '+' : ''}${summary.totalPnl.toFixed(0)} P&L)
                </span>
              )}
            </p>
          </div>
        </div>
        {isLoading && <RefreshCw className="w-4 h-4 text-gray-500 animate-spin" />}
      </div>

      {/* Activity List */}
      <div className="max-h-[400px] overflow-y-auto">
        {todaysTrades.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            <Activity className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>No trading activity today</p>
            <p className="text-xs mt-1">Trades will appear here as bots enter/exit positions</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-800/50">
            {todaysTrades.map((trade, idx) => {
              const brand = BOT_BRANDS[trade.bot]
              const Icon = brand.icon

              return (
                <div
                  key={`${trade.bot}-${trade.position_id}-${trade.action}-${idx}`}
                  className="px-4 py-3 hover:bg-gray-900/30 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      {/* Action Icon */}
                      <div className="mt-0.5">
                        {getActionIcon(trade.action, trade.realized_pnl)}
                      </div>

                      {/* Trade Details */}
                      <div>
                        <div className="flex items-center gap-2">
                          <Icon className="w-4 h-4" style={{ color: brand.hexPrimary }} />
                          <span className="font-medium text-white">
                            {trade.bot}
                          </span>
                          <span className="text-gray-500">•</span>
                          <span className="text-gray-300">
                            {trade.ticker} {getPositionDescription(trade)}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-1 text-sm">
                          <span className={`
                            ${trade.action === 'ENTRY' ? 'text-blue-400' : ''}
                            ${trade.action === 'EXIT' ? (trade.realized_pnl && trade.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400') : ''}
                            ${trade.action === 'EXPIRED' ? 'text-purple-400' : ''}
                          `}>
                            {getActionLabel(trade)}
                          </span>
                          {trade.action !== 'ENTRY' && trade.realized_pnl !== undefined && (
                            <>
                              <span className="text-gray-500">•</span>
                              <span className={trade.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                                {trade.realized_pnl >= 0 ? '+' : ''}${trade.realized_pnl.toFixed(0)}
                              </span>
                              {trade.return_pct !== undefined && (
                                <span className={`text-xs ${trade.return_pct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                  ({trade.return_pct >= 0 ? '+' : ''}{trade.return_pct.toFixed(1)}%)
                                </span>
                              )}
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Time */}
                    <div className="text-right">
                      <div className="text-sm text-gray-400">{formatTime(trade.timestamp)}</div>
                      <div className="text-xs text-gray-600 flex items-center justify-end gap-1">
                        <Clock className="w-3 h-3" />
                        CT
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
