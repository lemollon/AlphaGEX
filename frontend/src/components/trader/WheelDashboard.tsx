'use client'

import { useState, useEffect } from 'react'
import {
  RefreshCw, CircleDot, TrendingUp, TrendingDown,
  DollarSign, Calendar, ArrowRight, CheckCircle,
  XCircle, Clock, Play, Square, RotateCcw
} from 'lucide-react'
import { api } from '@/lib/api'

interface WheelCycle {
  id: number
  cycle_id: number
  symbol: string
  status: 'CSP' | 'ASSIGNED' | 'COVERED_CALL' | 'CALLED_AWAY' | 'CLOSED'
  start_date: string
  end_date: string | null
  shares_owned: number
  share_cost_basis: number
  total_csp_premium: number
  total_cc_premium: number
  total_premium_collected: number
  assignment_date: string | null
  assignment_price: number | null
  called_away_date: string | null
  called_away_price: number | null
  realized_pnl: number
  current_strike: number | null
  current_expiration: string | null
  current_leg_type: string | null
}

interface WheelSummary {
  total_cycles: number
  total_realized_pnl: number
  total_premium_collected: number
  total_csp_premium: number
  total_cc_premium: number
  avg_pnl_per_complete_cycle: number
  by_status: Record<string, { count: number; realized_pnl: number; total_premium: number }>
}

interface WheelPhase {
  id: string
  name: string
  description: string
}

export default function WheelDashboard() {
  const [activeCycles, setActiveCycles] = useState<WheelCycle[]>([])
  const [summary, setSummary] = useState<WheelSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchWheelData()
  }, [])

  const fetchWheelData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [cyclesRes, summaryRes] = await Promise.all([
        api.get('/api/wheel/active'),
        api.get('/api/wheel/summary')
      ])
      setActiveCycles(cyclesRes.data.data || [])
      setSummary(summaryRes.data.data)
    } catch (err: any) {
      console.error('Error fetching wheel data:', err)
      setError(err.message || 'Failed to load wheel data')
    } finally {
      setLoading(false)
    }
  }

  const getPhaseColor = (status: string) => {
    switch (status) {
      case 'CSP': return 'bg-blue-500/20 text-blue-400 border-blue-500/50'
      case 'ASSIGNED': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50'
      case 'COVERED_CALL': return 'bg-purple-500/20 text-purple-400 border-purple-500/50'
      case 'CALLED_AWAY': return 'bg-green-500/20 text-green-400 border-green-500/50'
      case 'CLOSED': return 'bg-gray-500/20 text-gray-400 border-gray-500/50'
      default: return 'bg-gray-500/20 text-gray-400 border-gray-500/50'
    }
  }

  const getPhaseIcon = (status: string) => {
    switch (status) {
      case 'CSP': return <CircleDot className="w-4 h-4" />
      case 'ASSIGNED': return <TrendingDown className="w-4 h-4" />
      case 'COVERED_CALL': return <TrendingUp className="w-4 h-4" />
      case 'CALLED_AWAY': return <CheckCircle className="w-4 h-4" />
      case 'CLOSED': return <XCircle className="w-4 h-4" />
      default: return <Clock className="w-4 h-4" />
    }
  }

  if (loading) {
    return (
      <div className="bg-slate-800/50 rounded-lg p-6 border border-slate-700">
        <div className="flex items-center gap-2 mb-4">
          <RefreshCw className="w-5 h-5 animate-spin text-blue-400" />
          <span className="text-gray-400">Loading wheel strategy data...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Wheel Strategy Overview */}
      <div className="bg-slate-800/50 rounded-lg p-6 border border-slate-700">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/20 rounded-lg">
              <RotateCcw className="w-6 h-6 text-purple-400" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-white">Wheel Strategy</h2>
              <p className="text-sm text-gray-400">Premium income through CSP + Covered Calls</p>
            </div>
          </div>
          <button
            onClick={fetchWheelData}
            className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
          >
            <RefreshCw className="w-4 h-4 text-gray-400" />
          </button>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-4 mb-4">
            <p className="text-red-400">{error}</p>
          </div>
        )}

        {/* Summary Cards */}
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-slate-700/50 rounded-lg p-4">
              <p className="text-sm text-gray-400">Total Cycles</p>
              <p className="text-2xl font-bold text-white">{summary.total_cycles}</p>
            </div>
            <div className="bg-slate-700/50 rounded-lg p-4">
              <p className="text-sm text-gray-400">Total Premium</p>
              <p className={`text-2xl font-bold ${summary.total_premium_collected >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${summary.total_premium_collected.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
            </div>
            <div className="bg-slate-700/50 rounded-lg p-4">
              <p className="text-sm text-gray-400">Realized P&L</p>
              <p className={`text-2xl font-bold ${summary.total_realized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${summary.total_realized_pnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
            </div>
            <div className="bg-slate-700/50 rounded-lg p-4">
              <p className="text-sm text-gray-400">Avg P&L/Cycle</p>
              <p className={`text-2xl font-bold ${summary.avg_pnl_per_complete_cycle >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${summary.avg_pnl_per_complete_cycle.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
            </div>
          </div>
        )}

        {/* Premium Breakdown */}
        {summary && (
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <CircleDot className="w-4 h-4 text-blue-400" />
                <span className="text-sm text-blue-400">CSP Premium</span>
              </div>
              <p className="text-xl font-bold text-white">
                ${summary.total_csp_premium.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </p>
            </div>
            <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="w-4 h-4 text-purple-400" />
                <span className="text-sm text-purple-400">Covered Call Premium</span>
              </div>
              <p className="text-xl font-bold text-white">
                ${summary.total_cc_premium.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </p>
            </div>
          </div>
        )}

        {/* Wheel Flow Diagram */}
        <div className="bg-slate-700/30 rounded-lg p-4 mb-6">
          <h3 className="text-sm font-medium text-gray-400 mb-3">Wheel Cycle Flow</h3>
          <div className="flex items-center justify-between gap-2 overflow-x-auto">
            <div className="flex flex-col items-center min-w-[100px]">
              <div className="p-3 bg-blue-500/20 rounded-lg border border-blue-500/50">
                <CircleDot className="w-6 h-6 text-blue-400" />
              </div>
              <span className="text-xs text-blue-400 mt-2">Sell CSP</span>
            </div>
            <ArrowRight className="w-5 h-5 text-gray-600" />
            <div className="flex flex-col items-center min-w-[100px]">
              <div className="p-3 bg-yellow-500/20 rounded-lg border border-yellow-500/50">
                <TrendingDown className="w-6 h-6 text-yellow-400" />
              </div>
              <span className="text-xs text-yellow-400 mt-2">Assigned</span>
            </div>
            <ArrowRight className="w-5 h-5 text-gray-600" />
            <div className="flex flex-col items-center min-w-[100px]">
              <div className="p-3 bg-purple-500/20 rounded-lg border border-purple-500/50">
                <TrendingUp className="w-6 h-6 text-purple-400" />
              </div>
              <span className="text-xs text-purple-400 mt-2">Sell CC</span>
            </div>
            <ArrowRight className="w-5 h-5 text-gray-600" />
            <div className="flex flex-col items-center min-w-[100px]">
              <div className="p-3 bg-green-500/20 rounded-lg border border-green-500/50">
                <CheckCircle className="w-6 h-6 text-green-400" />
              </div>
              <span className="text-xs text-green-400 mt-2">Called Away</span>
            </div>
          </div>
        </div>

        {/* Active Cycles */}
        <div>
          <h3 className="text-lg font-medium text-white mb-3">Active Wheel Cycles</h3>
          {activeCycles.length === 0 ? (
            <div className="bg-slate-700/30 rounded-lg p-8 text-center">
              <RotateCcw className="w-12 h-12 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400 mb-2">No active wheel cycles</p>
              <p className="text-sm text-gray-500">Start a new wheel by selling a cash-secured put</p>
            </div>
          ) : (
            <div className="space-y-3">
              {activeCycles.map((cycle) => (
                <div
                  key={cycle.id || cycle.cycle_id}
                  className="bg-slate-700/30 rounded-lg p-4 border border-slate-600/50"
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <span className="text-lg font-bold text-white">{cycle.symbol}</span>
                      <span className={`px-2 py-1 rounded-full text-xs font-medium border flex items-center gap-1 ${getPhaseColor(cycle.status)}`}>
                        {getPhaseIcon(cycle.status)}
                        {cycle.status.replace('_', ' ')}
                      </span>
                    </div>
                    <div className="text-right">
                      <p className={`text-lg font-bold ${cycle.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${cycle.realized_pnl.toFixed(2)}
                      </p>
                      <p className="text-xs text-gray-500">Realized P&L</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div>
                      <p className="text-gray-500">Started</p>
                      <p className="text-gray-300">{new Date(cycle.start_date).toLocaleDateString()}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Premium Collected</p>
                      <p className="text-green-400">${cycle.total_premium_collected.toFixed(2)}</p>
                    </div>
                    {cycle.shares_owned > 0 && (
                      <>
                        <div>
                          <p className="text-gray-500">Shares</p>
                          <p className="text-gray-300">{cycle.shares_owned}</p>
                        </div>
                        <div>
                          <p className="text-gray-500">Cost Basis</p>
                          <p className="text-gray-300">${cycle.share_cost_basis.toFixed(2)}</p>
                        </div>
                      </>
                    )}
                    {cycle.current_strike && (
                      <>
                        <div>
                          <p className="text-gray-500">Current Strike</p>
                          <p className="text-gray-300">${cycle.current_strike}</p>
                        </div>
                        <div>
                          <p className="text-gray-500">Expiration</p>
                          <p className="text-gray-300">{cycle.current_expiration}</p>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
