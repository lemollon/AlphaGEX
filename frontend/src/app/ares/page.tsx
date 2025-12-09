'use client'

import { useState, useEffect } from 'react'
import { Sword, RefreshCw, TrendingUp, DollarSign, Clock, Target, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface ARESStatus {
  mode: string
  capital: number
  total_pnl: number
  trade_count: number
  win_rate: number
  open_positions: number
  closed_positions: number
  traded_today: boolean
  in_trading_window: boolean
  high_water_mark: number
  current_time: string
  config: {
    risk_per_trade: number
    spread_width: number
    sd_multiplier: number
    ticker: string
    production_ticker: string
    sandbox_ticker: string
  }
}

export default function ARESPage() {
  const [status, setStatus] = useState<ARESStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [runningCycle, setRunningCycle] = useState(false)
  const [cycleResult, setCycleResult] = useState<any>(null)

  const fetchStatus = async () => {
    try {
      setLoading(true)
      const response = await apiClient.getARESStatus()
      if (response.data) {
        setStatus(response.data)
        setError(null)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch ARES status')
    } finally {
      setLoading(false)
    }
  }

  const runDailyCycle = async () => {
    try {
      setRunningCycle(true)
      setCycleResult(null)
      const response = await apiClient.runARESCycle()
      if (response.data) {
        setCycleResult(response.data)
        // Refresh status after running
        await fetchStatus()
      }
    } catch (err: any) {
      setCycleResult({ error: err.message || 'Failed to run daily cycle' })
    } finally {
      setRunningCycle(false)
    }
  }

  useEffect(() => {
    fetchStatus()
    // Refresh every 30 seconds
    const interval = setInterval(fetchStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-red-500/20 rounded-xl">
            <Sword className="w-8 h-8 text-red-400" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-white">ARES</h1>
            <p className="text-gray-400">Aggressive Iron Condor Trading Bot</p>
          </div>
        </div>
        <div className="flex gap-3">
          <button
            onClick={fetchStatus}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={runDailyCycle}
            disabled={runningCycle || !status?.in_trading_window}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-500 rounded-lg transition-colors disabled:opacity-50"
          >
            <Target className="w-4 h-4" />
            {runningCycle ? 'Running...' : 'Run Daily Cycle'}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400" />
          <span className="text-red-300">{error}</span>
        </div>
      )}

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {/* Mode */}
        <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Mode</span>
            <span className={`px-2 py-1 rounded text-xs font-semibold ${
              status?.mode === 'paper' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'
            }`}>
              {status?.mode?.toUpperCase() || 'UNKNOWN'}
            </span>
          </div>
          <div className="text-2xl font-bold text-white">
            {status?.config?.ticker || 'SPY'}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {status?.mode === 'paper' ? 'Sandbox Trading' : 'Live Trading'}
          </div>
        </div>

        {/* Capital */}
        <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Capital</span>
            <DollarSign className="w-4 h-4 text-green-400" />
          </div>
          <div className="text-2xl font-bold text-white">
            ${status?.capital?.toLocaleString() || '0'}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {status?.config?.risk_per_trade || 10}% risk per trade
          </div>
        </div>

        {/* Trading Window */}
        <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Trading Window</span>
            <Clock className="w-4 h-4 text-blue-400" />
          </div>
          <div className="flex items-center gap-2">
            {status?.in_trading_window ? (
              <>
                <CheckCircle2 className="w-5 h-5 text-green-400" />
                <span className="text-xl font-bold text-green-400">OPEN</span>
              </>
            ) : (
              <>
                <AlertTriangle className="w-5 h-5 text-yellow-400" />
                <span className="text-xl font-bold text-yellow-400">CLOSED</span>
              </>
            )}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            9:35 AM - 3:30 PM ET
          </div>
        </div>

        {/* Traded Today */}
        <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Traded Today</span>
            <Target className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-2xl font-bold text-white">
            {status?.traded_today ? 'YES' : 'NO'}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {status?.trade_count || 0} total trades
          </div>
        </div>
      </div>

      {/* Strategy Info */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Configuration */}
        <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-red-400" />
            Strategy Configuration
          </h2>
          <div className="space-y-3">
            <div className="flex justify-between py-2 border-b border-gray-700">
              <span className="text-gray-400">Strategy</span>
              <span className="text-white font-mono">Iron Condor (1 SD)</span>
            </div>
            <div className="flex justify-between py-2 border-b border-gray-700">
              <span className="text-gray-400">Trading Ticker</span>
              <span className="text-white font-mono">{status?.config?.ticker || 'SPY'}</span>
            </div>
            <div className="flex justify-between py-2 border-b border-gray-700">
              <span className="text-gray-400">Spread Width</span>
              <span className="text-white font-mono">${status?.config?.spread_width || 2}</span>
            </div>
            <div className="flex justify-between py-2 border-b border-gray-700">
              <span className="text-gray-400">SD Multiplier</span>
              <span className="text-white font-mono">{status?.config?.sd_multiplier || 1.0}</span>
            </div>
            <div className="flex justify-between py-2 border-b border-gray-700">
              <span className="text-gray-400">Risk Per Trade</span>
              <span className="text-white font-mono">{status?.config?.risk_per_trade || 10}%</span>
            </div>
            <div className="flex justify-between py-2">
              <span className="text-gray-400">Target</span>
              <span className="text-green-400 font-mono">10% Monthly</span>
            </div>
          </div>
        </div>

        {/* Performance */}
        <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-green-400" />
            Performance
          </h2>
          <div className="space-y-3">
            <div className="flex justify-between py-2 border-b border-gray-700">
              <span className="text-gray-400">Total P&L</span>
              <span className={`font-mono font-semibold ${(status?.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${status?.total_pnl?.toLocaleString() || '0'}
              </span>
            </div>
            <div className="flex justify-between py-2 border-b border-gray-700">
              <span className="text-gray-400">Win Rate</span>
              <span className="text-white font-mono">{status?.win_rate?.toFixed(1) || 0}%</span>
            </div>
            <div className="flex justify-between py-2 border-b border-gray-700">
              <span className="text-gray-400">Total Trades</span>
              <span className="text-white font-mono">{status?.trade_count || 0}</span>
            </div>
            <div className="flex justify-between py-2 border-b border-gray-700">
              <span className="text-gray-400">Open Positions</span>
              <span className="text-white font-mono">{status?.open_positions || 0}</span>
            </div>
            <div className="flex justify-between py-2">
              <span className="text-gray-400">High Water Mark</span>
              <span className="text-white font-mono">${status?.high_water_mark?.toLocaleString() || '0'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Cycle Result */}
      {cycleResult && (
        <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Daily Cycle Result</h2>
          <pre className="bg-gray-900 p-4 rounded-lg overflow-x-auto text-sm text-gray-300">
            {JSON.stringify(cycleResult, null, 2)}
          </pre>
        </div>
      )}

      {/* How It Works */}
      <div className="mt-8 bg-gray-800/30 border border-gray-700/50 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">How ARES Works</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-sm">
          <div>
            <h3 className="text-red-400 font-semibold mb-2">1. Daily Analysis</h3>
            <p className="text-gray-400">
              At 10:15 AM ET, ARES analyzes SPY price and calculates the 1 standard deviation expected move using VIX.
            </p>
          </div>
          <div>
            <h3 className="text-red-400 font-semibold mb-2">2. Strike Selection</h3>
            <p className="text-gray-400">
              Finds optimal Iron Condor strikes: sells puts and calls at 1 SD, buys wings $2 wide for protection.
            </p>
          </div>
          <div>
            <h3 className="text-red-400 font-semibold mb-2">3. Execution</h3>
            <p className="text-gray-400">
              Places the Iron Condor order on Tradier. Uses 10% of capital per trade. Lets options expire (0DTE).
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
