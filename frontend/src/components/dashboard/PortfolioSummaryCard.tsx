'use client'

import { useMemo } from 'react'
import useSWR from 'swr'
import { Wallet, TrendingUp, TrendingDown, Target, DollarSign, BarChart3, RefreshCw } from 'lucide-react'
import { BOT_BRANDS, BotName } from '@/components/trader/BotBranding'

interface BotStatus {
  is_active?: boolean
  bot_status?: string
  open_positions?: number
  today_pnl?: number
  total_pnl?: number
  unrealized_pnl?: number
  realized_pnl?: number
  win_rate?: number
  total_trades?: number
  winning_trades?: number
  starting_capital?: number
  current_equity?: number
}

interface BotStatusResponse {
  success?: boolean
  data?: BotStatus
  // Some endpoints return data at root level
  is_active?: boolean
  bot_status?: string
  open_positions?: number
  today_pnl?: number
  total_pnl?: number
  unrealized_pnl?: number
  realized_pnl?: number
  win_rate?: number
}

const LIVE_BOTS: { name: BotName; endpoint: string; startingCapital: number }[] = [
  { name: 'ARES', endpoint: '/api/ares/status', startingCapital: 100000 },
  { name: 'ATHENA', endpoint: '/api/athena/status', startingCapital: 100000 },
  { name: 'ICARUS', endpoint: '/api/icarus/status', startingCapital: 100000 },
  { name: 'PEGASUS', endpoint: '/api/pegasus/status', startingCapital: 200000 },
  { name: 'TITAN', endpoint: '/api/titan/status', startingCapital: 200000 },
]

const fetcher = async (url: string): Promise<BotStatusResponse> => {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}${url}`)
    if (!res.ok) return {}
    return res.json()
  } catch {
    return {}
  }
}

export default function PortfolioSummaryCard() {
  // Fetch status for all bots
  const { data: aresData, isLoading: aresLoading } = useSWR('/api/ares/status', fetcher, { refreshInterval: 30000 })
  const { data: athenaData, isLoading: athenaLoading } = useSWR('/api/athena/status', fetcher, { refreshInterval: 30000 })
  const { data: icarusData, isLoading: icarusLoading } = useSWR('/api/icarus/status', fetcher, { refreshInterval: 30000 })
  const { data: pegasusData, isLoading: pegasusLoading } = useSWR('/api/pegasus/status', fetcher, { refreshInterval: 30000 })
  const { data: titanData, isLoading: titanLoading } = useSWR('/api/titan/status', fetcher, { refreshInterval: 30000 })

  const isLoading = aresLoading || athenaLoading || icarusLoading || pegasusLoading || titanLoading

  // Normalize bot data (handle both nested and flat response structures)
  const normalizeData = (response: BotStatusResponse | undefined): BotStatus => {
    if (!response) return {}
    if (response.data) return response.data
    return response as BotStatus
  }

  // Aggregate metrics across all bots
  const portfolio = useMemo(() => {
    const botDataList = [
      { ...normalizeData(aresData), startingCapital: 100000 },
      { ...normalizeData(athenaData), startingCapital: 100000 },
      { ...normalizeData(icarusData), startingCapital: 100000 },
      { ...normalizeData(pegasusData), startingCapital: 200000 },
      { ...normalizeData(titanData), startingCapital: 200000 },
    ]

    let totalStartingCapital = 0
    let totalCurrentEquity = 0
    let totalRealizedPnl = 0
    let totalUnrealizedPnl = 0
    let totalTodayPnl = 0
    let totalOpenPositions = 0
    let totalTrades = 0
    let totalWinningTrades = 0
    let activeBots = 0

    botDataList.forEach((bot) => {
      totalStartingCapital += bot.startingCapital

      // Use current_equity if available, otherwise calculate from starting + pnl
      const realized = bot.realized_pnl || bot.total_pnl || 0
      const unrealized = bot.unrealized_pnl || 0
      const currentEquity = bot.current_equity || (bot.startingCapital + realized + unrealized)

      totalCurrentEquity += currentEquity
      totalRealizedPnl += realized
      totalUnrealizedPnl += unrealized
      totalTodayPnl += bot.today_pnl || 0
      totalOpenPositions += bot.open_positions || 0
      totalTrades += bot.total_trades || 0
      totalWinningTrades += bot.winning_trades || 0

      if (bot.is_active || bot.bot_status === 'ACTIVE') {
        activeBots++
      }
    })

    const totalPnl = totalRealizedPnl + totalUnrealizedPnl
    const totalReturnPct = totalStartingCapital > 0 ? (totalPnl / totalStartingCapital) * 100 : 0
    const winRate = totalTrades > 0 ? (totalWinningTrades / totalTrades) * 100 : 0

    return {
      totalStartingCapital,
      totalCurrentEquity,
      totalRealizedPnl,
      totalUnrealizedPnl,
      totalTodayPnl,
      totalPnl,
      totalReturnPct,
      totalOpenPositions,
      totalTrades,
      winRate,
      activeBots,
    }
  }, [aresData, athenaData, icarusData, pegasusData, titanData])

  const formatCurrency = (value: number) => {
    const absValue = Math.abs(value)
    if (absValue >= 1000000) {
      return `$${(value / 1000000).toFixed(2)}M`
    }
    if (absValue >= 1000) {
      return `$${(value / 1000).toFixed(1)}k`
    }
    return `$${value.toFixed(0)}`
  }

  const formatPnl = (value: number) => {
    const sign = value >= 0 ? '+' : ''
    return `${sign}${formatCurrency(value)}`
  }

  return (
    <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Wallet className="w-5 h-5 text-primary" />
          <div>
            <h3 className="font-semibold text-white">Portfolio Summary</h3>
            <p className="text-xs text-gray-500">Aggregated across all 5 bots</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">{portfolio.activeBots}/5 bots active</span>
          {isLoading && <RefreshCw className="w-4 h-4 text-gray-500 animate-spin" />}
        </div>
      </div>

      {/* Main Stats */}
      <div className="p-4">
        {/* Top Row - Big Numbers */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          {/* Total Equity */}
          <div className="bg-gray-900/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <DollarSign className="w-4 h-4 text-gray-500" />
              <span className="text-xs text-gray-500 uppercase">Total Equity</span>
            </div>
            <div className="text-xl font-bold text-white">
              {formatCurrency(portfolio.totalCurrentEquity)}
            </div>
            <div className="text-xs text-gray-500">
              of {formatCurrency(portfolio.totalStartingCapital)} starting
            </div>
          </div>

          {/* Total P&L */}
          <div className="bg-gray-900/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              {portfolio.totalPnl >= 0 ? (
                <TrendingUp className="w-4 h-4 text-green-500" />
              ) : (
                <TrendingDown className="w-4 h-4 text-red-500" />
              )}
              <span className="text-xs text-gray-500 uppercase">Total P&L</span>
            </div>
            <div className={`text-xl font-bold ${portfolio.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {formatPnl(portfolio.totalPnl)}
            </div>
            <div className={`text-xs ${portfolio.totalReturnPct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {portfolio.totalReturnPct >= 0 ? '+' : ''}{portfolio.totalReturnPct.toFixed(2)}% return
            </div>
          </div>

          {/* Today's P&L */}
          <div className="bg-gray-900/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <BarChart3 className="w-4 h-4 text-gray-500" />
              <span className="text-xs text-gray-500 uppercase">Today</span>
            </div>
            <div className={`text-xl font-bold ${portfolio.totalTodayPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {formatPnl(portfolio.totalTodayPnl)}
            </div>
            <div className="text-xs text-gray-500">
              realized today
            </div>
          </div>

          {/* Win Rate */}
          <div className="bg-gray-900/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <Target className="w-4 h-4 text-gray-500" />
              <span className="text-xs text-gray-500 uppercase">Win Rate</span>
            </div>
            <div className={`text-xl font-bold ${portfolio.winRate >= 50 ? 'text-green-400' : 'text-yellow-400'}`}>
              {portfolio.winRate.toFixed(1)}%
            </div>
            <div className="text-xs text-gray-500">
              {portfolio.totalTrades} total trades
            </div>
          </div>
        </div>

        {/* Bottom Row - Secondary Stats */}
        <div className="grid grid-cols-3 gap-4">
          {/* Realized */}
          <div className="text-center p-2 border border-gray-800 rounded-lg">
            <div className="text-xs text-gray-500 mb-1">Realized</div>
            <div className={`text-sm font-semibold ${portfolio.totalRealizedPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {formatPnl(portfolio.totalRealizedPnl)}
            </div>
          </div>

          {/* Unrealized */}
          <div className="text-center p-2 border border-gray-800 rounded-lg">
            <div className="text-xs text-gray-500 mb-1">Unrealized</div>
            <div className={`text-sm font-semibold ${portfolio.totalUnrealizedPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {formatPnl(portfolio.totalUnrealizedPnl)}
            </div>
          </div>

          {/* Open Positions */}
          <div className="text-center p-2 border border-gray-800 rounded-lg">
            <div className="text-xs text-gray-500 mb-1">Open Positions</div>
            <div className="text-sm font-semibold text-white">
              {portfolio.totalOpenPositions}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
