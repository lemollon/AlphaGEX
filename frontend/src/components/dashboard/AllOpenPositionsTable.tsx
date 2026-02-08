'use client'

import { useMemo, useState } from 'react'
import useSWR from 'swr'
import Link from 'next/link'
import { Briefcase, Clock, TrendingUp, TrendingDown, ChevronUp, ChevronDown, ExternalLink, RefreshCw } from 'lucide-react'
import { BOT_BRANDS, BotName } from '@/components/trader/BotBranding'

interface Position {
  position_id: string
  bot: BotName
  spread_type?: string
  direction?: string
  ticker: string
  contracts?: number
  entry_credit?: number
  entry_debit?: number
  entry_price?: number
  current_price?: number
  unrealized_pnl?: number
  return_pct?: number
  status: string
  open_time?: string
  entry_time?: string
  underlying_at_entry?: number
  spot_at_entry?: number
  // Strike info for Iron Condors
  short_call_strike?: number
  short_put_strike?: number
  long_call_strike?: number
  long_put_strike?: number
  // Strike info for Spreads
  long_strike?: number
  short_strike?: number
}

interface PositionsResponse {
  success?: boolean
  data?: Position[] | { open_positions?: Position[]; positions?: Position[] }
  positions?: Position[]
  open_positions?: Position[]
}

const LIVE_BOTS: { name: BotName; endpoint: string; link: string }[] = [
  { name: 'FORTRESS', endpoint: '/api/fortress/positions', link: '/fortress' },
  { name: 'SOLOMON', endpoint: '/api/solomon/positions', link: '/solomon' },
  { name: 'GIDEON', endpoint: '/api/gideon/positions', link: '/gideon' },
  { name: 'ANCHOR', endpoint: '/api/anchor/positions', link: '/anchor' },
  { name: 'SAMSON', endpoint: '/api/samson/positions', link: '/samson' },
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

type SortField = 'bot' | 'ticker' | 'pnl' | 'time'
type SortDirection = 'asc' | 'desc'

export default function AllOpenPositionsTable() {
  const [sortField, setSortField] = useState<SortField>('time')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  // Fetch positions for all bots
  const { data: aresData, isLoading: aresLoading } = useSWR('/api/fortress/positions', fetcher, { refreshInterval: 30000 })
  const { data: solomonData, isLoading: solomonLoading } = useSWR('/api/solomon/positions', fetcher, { refreshInterval: 30000 })
  const { data: icarusData, isLoading: icarusLoading } = useSWR('/api/gideon/positions', fetcher, { refreshInterval: 30000 })
  const { data: anchorData, isLoading: anchorLoading } = useSWR('/api/anchor/positions', fetcher, { refreshInterval: 30000 })
  const { data: titanData, isLoading: titanLoading } = useSWR('/api/samson/positions', fetcher, { refreshInterval: 30000 })

  const isLoading = aresLoading || solomonLoading || icarusLoading || anchorLoading || titanLoading

  // Extract open positions from response (handle different response structures)
  const extractOpenPositions = (response: PositionsResponse | undefined, botName: BotName): Position[] => {
    if (!response) return []

    let positions: Position[] = []

    // Handle different response structures
    if (response.data) {
      if (Array.isArray(response.data)) {
        positions = response.data
      } else if (response.data.open_positions) {
        positions = response.data.open_positions
      } else if (response.data.positions) {
        positions = response.data.positions
      }
    } else if (response.positions) {
      positions = response.positions
    } else if (response.open_positions) {
      positions = response.open_positions
    }

    // Filter to only open positions and add bot name
    return positions
      .filter(p => p.status === 'open' || p.status === 'OPEN')
      .map(p => ({ ...p, bot: botName }))
  }

  // Combine all positions
  const allPositions = useMemo(() => {
    const positions = [
      ...extractOpenPositions(aresData, 'FORTRESS'),
      ...extractOpenPositions(solomonData, 'SOLOMON'),
      ...extractOpenPositions(icarusData, 'GIDEON'),
      ...extractOpenPositions(anchorData, 'ANCHOR'),
      ...extractOpenPositions(titanData, 'SAMSON'),
    ]

    // Sort positions
    return positions.sort((a, b) => {
      let comparison = 0

      switch (sortField) {
        case 'bot':
          comparison = a.bot.localeCompare(b.bot)
          break
        case 'ticker':
          comparison = a.ticker.localeCompare(b.ticker)
          break
        case 'pnl':
          comparison = (a.unrealized_pnl || 0) - (b.unrealized_pnl || 0)
          break
        case 'time':
          const timeA = new Date(a.open_time || a.entry_time || 0).getTime()
          const timeB = new Date(b.open_time || b.entry_time || 0).getTime()
          comparison = timeA - timeB
          break
      }

      return sortDirection === 'asc' ? comparison : -comparison
    })
  }, [aresData, solomonData, icarusData, anchorData, titanData, sortField, sortDirection])

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDirection('desc')
    }
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return null
    return sortDirection === 'asc' ? (
      <ChevronUp className="w-3 h-3" />
    ) : (
      <ChevronDown className="w-3 h-3" />
    )
  }

  const formatTime = (timestamp: string | undefined) => {
    if (!timestamp) return '--'
    const date = new Date(timestamp)
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
      timeZone: 'America/Chicago',
    })
  }

  const formatTimeAgo = (timestamp: string | undefined) => {
    if (!timestamp) return ''
    const now = new Date()
    const then = new Date(timestamp)
    const diffMs = now.getTime() - then.getTime()
    const diffMins = Math.floor(diffMs / 60000)

    if (diffMins < 60) return `${diffMins}m ago`
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return `${diffHours}h ago`
    return `${Math.floor(diffHours / 24)}d ago`
  }

  const getPositionDescription = (pos: Position) => {
    if (pos.spread_type === 'IRON_CONDOR' || pos.short_call_strike) {
      return `IC ${pos.short_put_strike}/${pos.short_call_strike}`
    }
    if (pos.direction) {
      const dir = pos.direction === 'BULLISH' ? 'Bull' : 'Bear'
      return `${dir} ${pos.long_strike}/${pos.short_strike}`
    }
    return pos.spread_type || 'Position'
  }

  const getBotLink = (botName: BotName) => {
    return LIVE_BOTS.find(b => b.name === botName)?.link || '/'
  }

  return (
    <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Briefcase className="w-5 h-5 text-primary" />
          <div>
            <h3 className="font-semibold text-white">All Open Positions</h3>
            <p className="text-xs text-gray-500">{allPositions.length} positions across all bots</p>
          </div>
        </div>
        {isLoading && <RefreshCw className="w-4 h-4 text-gray-500 animate-spin" />}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        {allPositions.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            <Briefcase className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>No open positions</p>
            <p className="text-xs mt-1">Positions will appear here when bots enter trades</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th
                  className="text-left py-2 px-4 text-gray-500 font-medium cursor-pointer hover:text-gray-300"
                  onClick={() => toggleSort('bot')}
                >
                  <div className="flex items-center gap-1">
                    Bot <SortIcon field="bot" />
                  </div>
                </th>
                <th
                  className="text-left py-2 px-4 text-gray-500 font-medium cursor-pointer hover:text-gray-300"
                  onClick={() => toggleSort('ticker')}
                >
                  <div className="flex items-center gap-1">
                    Position <SortIcon field="ticker" />
                  </div>
                </th>
                <th className="text-right py-2 px-4 text-gray-500 font-medium">
                  Entry
                </th>
                <th
                  className="text-right py-2 px-4 text-gray-500 font-medium cursor-pointer hover:text-gray-300"
                  onClick={() => toggleSort('pnl')}
                >
                  <div className="flex items-center justify-end gap-1">
                    P&L <SortIcon field="pnl" />
                  </div>
                </th>
                <th
                  className="text-right py-2 px-4 text-gray-500 font-medium cursor-pointer hover:text-gray-300"
                  onClick={() => toggleSort('time')}
                >
                  <div className="flex items-center justify-end gap-1">
                    Opened <SortIcon field="time" />
                  </div>
                </th>
                <th className="py-2 px-4"></th>
              </tr>
            </thead>
            <tbody>
              {allPositions.map((pos, idx) => {
                const brand = BOT_BRANDS[pos.bot]
                const Icon = brand.icon
                const pnl = pos.unrealized_pnl || 0
                const returnPct = pos.return_pct || 0
                const entryPrice = pos.entry_credit || pos.entry_debit || pos.entry_price || 0

                return (
                  <tr key={`${pos.bot}-${pos.position_id}-${idx}`} className="border-b border-gray-800/50 hover:bg-gray-900/30">
                    {/* Bot */}
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <span style={{ color: brand.hexPrimary }}>
                          <Icon className="w-4 h-4" />
                        </span>
                        <span style={{ color: brand.hexPrimary }} className="font-medium">
                          {pos.bot}
                        </span>
                      </div>
                    </td>

                    {/* Position */}
                    <td className="py-3 px-4">
                      <div>
                        <div className="text-white font-medium">
                          {pos.ticker} {getPositionDescription(pos)}
                        </div>
                        <div className="text-xs text-gray-500">
                          {pos.contracts || 1} contract{(pos.contracts || 1) > 1 ? 's' : ''}
                        </div>
                      </div>
                    </td>

                    {/* Entry */}
                    <td className="py-3 px-4 text-right">
                      <div className="text-gray-300">${entryPrice.toFixed(2)}</div>
                      {pos.underlying_at_entry && (
                        <div className="text-xs text-gray-500">
                          @ ${pos.underlying_at_entry.toFixed(2)}
                        </div>
                      )}
                    </td>

                    {/* P&L */}
                    <td className="py-3 px-4 text-right">
                      <div className={`font-medium ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {pnl >= 0 ? '+' : ''}${pnl.toFixed(0)}
                      </div>
                      <div className={`text-xs ${returnPct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        {returnPct >= 0 ? '+' : ''}{returnPct.toFixed(1)}%
                      </div>
                    </td>

                    {/* Time */}
                    <td className="py-3 px-4 text-right">
                      <div className="text-gray-300">{formatTime(pos.open_time || pos.entry_time)}</div>
                      <div className="text-xs text-gray-500 flex items-center justify-end gap-1">
                        <Clock className="w-3 h-3" />
                        {formatTimeAgo(pos.open_time || pos.entry_time)}
                      </div>
                    </td>

                    {/* Link */}
                    <td className="py-3 px-4">
                      <Link
                        href={getBotLink(pos.bot)}
                        className="p-1.5 rounded hover:bg-gray-800 transition-colors inline-flex"
                        title={`View ${pos.bot}`}
                      >
                        <ExternalLink className="w-4 h-4 text-gray-500 hover:text-gray-300" />
                      </Link>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
