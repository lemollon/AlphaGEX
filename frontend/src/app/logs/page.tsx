'use client'

import { useState, useEffect } from 'react'
import { FileText, Download, Filter, RefreshCw, Search, Calendar, Bot } from 'lucide-react'
import Navigation from '@/components/Navigation'
import DecisionLogViewer from '@/components/trader/DecisionLogViewer'
import { apiClient } from '@/lib/api'

interface BotSummary {
  name: string
  decisions: number
  trades: number
  pnl: number
}

interface LogSummary {
  total_decisions: number
  trades_executed: number
  total_pnl: number
  by_bot: Record<string, number>
  by_type: Record<string, number>
}

export default function LogsPage() {
  const [summary, setSummary] = useState<LogSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeBot, setActiveBot] = useState<string>('all')
  const [dateRange, setDateRange] = useState({ start: '', end: '' })
  const [exporting, setExporting] = useState(false)

  const bots = [
    { id: 'all', name: 'All Bots', color: 'bg-gray-600' },
    { id: 'PHOENIX', name: 'PHOENIX (0DTE)', color: 'bg-orange-500' },
    { id: 'ATLAS', name: 'ATLAS (Wheel)', color: 'bg-blue-500' },
    { id: 'ARES', name: 'ARES (Iron Condor)', color: 'bg-red-500' },
    { id: 'HERMES', name: 'HERMES (Manual)', color: 'bg-purple-500' },
    { id: 'ORACLE', name: 'ORACLE (Advisory)', color: 'bg-green-500' },
  ]

  useEffect(() => {
    loadSummary()
  }, [])

  const loadSummary = async () => {
    setLoading(true)
    try {
      const response = await apiClient.getDecisionSummary({ days: 30 })
      if (response.data?.success) {
        setSummary(response.data.data?.summary || response.data.data)
      }
    } catch (error) {
      console.error('Error loading summary:', error)
    }
    setLoading(false)
  }

  const handleExportCSV = async () => {
    setExporting(true)
    try {
      const response = await apiClient.exportDecisionLogsCSV({
        bot: activeBot === 'all' ? undefined : activeBot,
        start_date: dateRange.start || undefined,
        end_date: dateRange.end || undefined,
      })

      const blob = new Blob([response.data], { type: 'text/csv' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `alphagex-logs-${activeBot}-${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Error exporting:', error)
    }
    setExporting(false)
  }

  const handleExportJSON = async () => {
    setExporting(true)
    try {
      const response = await apiClient.get('/api/trader/logs/decisions', {
        params: {
          bot: activeBot === 'all' ? undefined : activeBot,
          start_date: dateRange.start || undefined,
          end_date: dateRange.end || undefined,
          limit: 1000
        }
      })

      if (response.data?.success) {
        const blob = new Blob([JSON.stringify(response.data.data.decisions, null, 2)], { type: 'application/json' })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `alphagex-logs-${activeBot}-${new Date().toISOString().split('T')[0]}.json`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
      }
    } catch (error) {
      console.error('Error exporting JSON:', error)
    }
    setExporting(false)
  }

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />
      <main className="lg:pl-64 pt-16 lg:pt-0">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <FileText className="w-8 h-8 text-blue-500" />
              <div>
                <h1 className="text-2xl font-bold text-white">Decision Transparency Logs</h1>
                <p className="text-gray-400">Complete audit trail - What, Why, How for every bot decision</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={loadSummary}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          {/* Summary Cards */}
          {summary && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <p className="text-gray-400 text-sm">Total Decisions (30d)</p>
                <p className="text-3xl font-bold text-white">{summary.total_decisions || 0}</p>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <p className="text-gray-400 text-sm">Trades Executed</p>
                <p className="text-3xl font-bold text-green-400">{summary.trades_executed || 0}</p>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <p className="text-gray-400 text-sm">Total P&L</p>
                <p className={`text-3xl font-bold ${(summary.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  ${(summary.total_pnl || 0).toLocaleString()}
                </p>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <p className="text-gray-400 text-sm">Active Bots</p>
                <p className="text-3xl font-bold text-blue-400">
                  {Object.keys(summary.by_bot || {}).length}
                </p>
              </div>
            </div>
          )}

          {/* Bot Filter Tabs */}
          <div className="flex flex-wrap gap-2 mb-4">
            {bots.map((bot) => (
              <button
                key={bot.id}
                onClick={() => setActiveBot(bot.id)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeBot === bot.id
                    ? `${bot.color} text-white`
                    : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'
                }`}
              >
                {bot.name}
                {summary?.by_bot?.[bot.id] && (
                  <span className="ml-2 px-2 py-0.5 bg-black/20 rounded">
                    {summary.by_bot[bot.id]}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Filters & Export Row */}
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 mb-4">
            <div className="flex flex-wrap items-center gap-4">
              {/* Date Range Filter */}
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-gray-400" />
                <input
                  type="date"
                  value={dateRange.start}
                  onChange={(e) => setDateRange(prev => ({ ...prev, start: e.target.value }))}
                  className="bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white"
                  placeholder="Start Date"
                />
                <span className="text-gray-500">to</span>
                <input
                  type="date"
                  value={dateRange.end}
                  onChange={(e) => setDateRange(prev => ({ ...prev, end: e.target.value }))}
                  className="bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white"
                  placeholder="End Date"
                />
                {(dateRange.start || dateRange.end) && (
                  <button
                    onClick={() => setDateRange({ start: '', end: '' })}
                    className="text-xs text-gray-400 hover:text-white"
                  >
                    Clear
                  </button>
                )}
              </div>

              <div className="flex-1" />

              {/* Export Buttons */}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleExportCSV}
                  disabled={exporting}
                  className="flex items-center gap-2 px-3 py-1.5 bg-green-600 hover:bg-green-500 text-white rounded text-sm font-medium disabled:opacity-50"
                >
                  <Download className="w-4 h-4" />
                  Export CSV
                </button>
                <button
                  onClick={handleExportJSON}
                  disabled={exporting}
                  className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm font-medium disabled:opacity-50"
                >
                  <Download className="w-4 h-4" />
                  Export JSON
                </button>
              </div>
            </div>
          </div>

          {/* Decision Log Viewer */}
          <DecisionLogViewer
            defaultBot={activeBot === 'all' ? undefined : activeBot}
            hideFilter={true}
          />

          {/* Per-Bot Breakdown */}
          {summary?.by_bot && Object.keys(summary.by_bot).length > 0 && (
            <div className="mt-6 bg-gray-800 rounded-lg p-4 border border-gray-700">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Bot className="w-5 h-5 text-blue-500" />
                Decisions by Bot (Last 30 Days)
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                {Object.entries(summary.by_bot).map(([botName, count]) => {
                  const bot = bots.find(b => b.id === botName)
                  return (
                    <div
                      key={botName}
                      className={`rounded-lg p-3 border ${
                        bot?.color.replace('bg-', 'border-').replace('500', '500/50') || 'border-gray-600'
                      } bg-gray-900/50`}
                    >
                      <p className="text-gray-400 text-xs">{botName}</p>
                      <p className="text-2xl font-bold text-white">{count}</p>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="mt-6 text-center text-sm text-gray-500">
            Decision logs provide complete transparency on every bot decision including entry/exit reasoning,
            market context, and outcome tracking for continuous improvement.
          </div>
        </div>
      </main>
    </div>
  )
}
