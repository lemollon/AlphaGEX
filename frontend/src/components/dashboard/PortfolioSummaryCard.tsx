'use client'

import { useMemo } from 'react'
import useSWR from 'swr'
import { Wallet, TrendingUp, TrendingDown, Target, DollarSign, BarChart3, RefreshCw } from 'lucide-react'
import { BOT_BRANDS, BotName } from '@/components/trader/BotBranding'

interface BotStatus {
  is_active?: boolean
  bot_status?: string
  open_positions?: number
  today_pnl?: number  // May not be returned by all bots
  total_pnl?: number  // Backend name for realized P&L
  unrealized_pnl?: number
  realized_pnl?: number  // Alternative name
  win_rate?: number  // Percentage from backend (0-100)
  trade_count?: number  // Backend name for total trades
  total_trades?: number  // Alternative name
  winning_trades?: number
  starting_capital?: number  // From config table - USE THIS, not hardcoded
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

// Default starting capitals - used ONLY if API doesn't return starting_capital
// These should match the config table defaults in the backend
const DEFAULT_STARTING_CAPITALS: Record<BotName, number> = {
  FORTRESS: 100000,
  SOLOMON: 100000,
  GIDEON: 100000,
  ANCHOR: 200000,
  SAMSON: 200000,
  LAZARUS: 100000,
  CORNERSTONE: 100000,
  JUBILEE: 500000,
  VALOR: 100000,
  FAITH: 5000,
  AGAPE: 5000,
  AGAPE_SPOT: 8000,
  AGAPE_BTC: 5000,
  AGAPE_XRP: 5000,
  AGAPE_ETH_PERP: 12500,
  AGAPE_BTC_PERP: 25000,
  AGAPE_XRP_PERP: 9000,
  AGAPE_DOGE_PERP: 2500,
  AGAPE_SHIB_PERP: 1000,
}

const LIVE_BOTS: { name: BotName; endpoint: string }[] = [
  { name: 'FORTRESS', endpoint: '/api/fortress/status' },
  { name: 'SOLOMON', endpoint: '/api/solomon/status' },
  { name: 'GIDEON', endpoint: '/api/gideon/status' },
  { name: 'ANCHOR', endpoint: '/api/anchor/status' },
  { name: 'SAMSON', endpoint: '/api/samson/status' },
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
  const { data: aresData, isLoading: aresLoading } = useSWR('/api/fortress/status', fetcher, { refreshInterval: 30000 })
  const { data: solomonData, isLoading: solomonLoading } = useSWR('/api/solomon/status', fetcher, { refreshInterval: 30000 })
  const { data: icarusData, isLoading: icarusLoading } = useSWR('/api/gideon/status', fetcher, { refreshInterval: 30000 })
  const { data: anchorData, isLoading: anchorLoading } = useSWR('/api/anchor/status', fetcher, { refreshInterval: 30000 })
  const { data: titanData, isLoading: titanLoading } = useSWR('/api/samson/status', fetcher, { refreshInterval: 30000 })

  const isLoading = aresLoading || solomonLoading || icarusLoading || anchorLoading || titanLoading

  // Normalize bot data (handle both nested and flat response structures)
  const normalizeData = (response: BotStatusResponse | undefined): BotStatus => {
    if (!response) return {}
    if (response.data) return response.data
    return response as BotStatus
  }

  // Aggregate metrics across all bots
  const portfolio = useMemo(() => {
    // Pair each bot's data with its name for proper starting capital lookup
    const botDataList: { name: BotName; data: BotStatus }[] = [
      { name: 'FORTRESS', data: normalizeData(aresData) },
      { name: 'SOLOMON', data: normalizeData(solomonData) },
      { name: 'GIDEON', data: normalizeData(icarusData) },
      { name: 'ANCHOR', data: normalizeData(anchorData) },
      { name: 'SAMSON', data: normalizeData(titanData) },
    ]

    let totalStartingCapital = 0
    let totalCurrentEquity = 0
    let totalRealizedPnl = 0
    let totalUnrealizedPnl = 0
    let totalTodayPnl = 0
    let totalOpenPositions = 0
    let totalTrades = 0
    let weightedWinRateSum = 0  // For weighted average win rate
    let activeBots = 0

    botDataList.forEach(({ name, data: bot }) => {
      // CRITICAL FIX: Use starting_capital from API response, fallback to defaults
      // This ensures consistency with backend config table values
      const startingCapital = bot.starting_capital || DEFAULT_STARTING_CAPITALS[name]
      totalStartingCapital += startingCapital

      // Realized P&L: backend returns as total_pnl (realized_pnl is alternative)
      const realized = bot.realized_pnl || bot.total_pnl || 0
      const unrealized = bot.unrealized_pnl || 0

      // Use current_equity from API if available (already includes realized + unrealized)
      // Otherwise calculate from starting + pnl
      const currentEquity = bot.current_equity || (startingCapital + realized + unrealized)

      totalCurrentEquity += currentEquity
      totalRealizedPnl += realized
      totalUnrealizedPnl += unrealized
      totalTodayPnl += bot.today_pnl || 0
      totalOpenPositions += bot.open_positions || 0

      // CRITICAL FIX: Backend returns trade_count, not total_trades
      const tradeCount = bot.trade_count || bot.total_trades || 0
      totalTrades += tradeCount

      // CRITICAL FIX: Use win_rate directly from API (already a percentage)
      // Weight by trade count for accurate aggregate win rate
      const winRate = bot.win_rate || 0
      weightedWinRateSum += winRate * tradeCount

      if (bot.is_active || bot.bot_status === 'ACTIVE') {
        activeBots++
      }
    })

    const totalPnl = totalRealizedPnl + totalUnrealizedPnl
    const totalReturnPct = totalStartingCapital > 0 ? (totalPnl / totalStartingCapital) * 100 : 0

    // Calculate weighted average win rate across all bots
    const winRate = totalTrades > 0 ? weightedWinRateSum / totalTrades : 0

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
  }, [aresData, solomonData, icarusData, anchorData, titanData])

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
