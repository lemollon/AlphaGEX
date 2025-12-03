'use client'

import React, { useState, useEffect } from 'react'
import { apiClient } from '@/lib/api'

interface DecisionLog {
  id: number
  bot_name: string
  symbol: string
  decision_type: string
  action: string
  what: string
  why: string
  how: string
  outcome: string
  data: Record<string, unknown>
  timestamp: string
}

interface DecisionSummary {
  total_decisions: number
  decisions_by_type: Record<string, number>
  decisions_by_bot: Record<string, number>
  trades_executed: number
  total_pnl: number
}

interface BotStatus {
  name: string
  description: string
  type: string
  scheduled: boolean
  schedule: string
  capital_allocation: number
  capital_pct: number
  strategy: string
  data_sources?: string[]
  last_7_days: {
    decisions: number
    trades: number
    pnl: number
  }
}

export default function DecisionLogViewer() {
  const [logs, setLogs] = useState<DecisionLog[]>([])
  const [summary, setSummary] = useState<DecisionSummary | null>(null)
  const [bots, setBots] = useState<Record<string, BotStatus>>({})
  const [selectedBot, setSelectedBot] = useState<string>('all')
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [expandedLog, setExpandedLog] = useState<number | null>(null)

  useEffect(() => {
    loadData()
  }, [selectedBot])

  const loadData = async () => {
    setLoading(true)
    try {
      const [logsRes, summaryRes, botsRes] = await Promise.all([
        apiClient.getRecentDecisions({
          bot: selectedBot === 'all' ? undefined : selectedBot,
          limit: 50
        }),
        apiClient.getDecisionSummary({
          bot: selectedBot === 'all' ? undefined : selectedBot,
          days: 7
        }),
        apiClient.getBotsStatus()
      ])

      if (logsRes.data?.success) {
        setLogs(logsRes.data.data || [])
      }
      if (summaryRes.data?.success) {
        setSummary(summaryRes.data.data)
      }
      if (botsRes.data?.success) {
        setBots(botsRes.data.data.bots || {})
      }
    } catch (error) {
      console.error('Error loading decision logs:', error)
    }
    setLoading(false)
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const response = await apiClient.exportDecisionLogsCSV({
        bot: selectedBot === 'all' ? undefined : selectedBot
      })

      // Create download link
      const blob = new Blob([response.data], { type: 'text/csv' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `decision-logs-${selectedBot}-${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Error exporting logs:', error)
    }
    setExporting(false)
  }

  const getBotColor = (botName: string) => {
    const colors: Record<string, string> = {
      'PHOENIX': 'text-orange-400',
      'ATLAS': 'text-blue-400',
      'HERMES': 'text-purple-400',
      'ORACLE': 'text-green-400'
    }
    return colors[botName] || 'text-gray-400'
  }

  const getActionColor = (action: string) => {
    if (action?.includes('BUY') || action?.includes('OPEN')) return 'text-green-400'
    if (action?.includes('SELL') || action?.includes('CLOSE')) return 'text-red-400'
    if (action?.includes('SKIP') || action?.includes('NO_TRADE')) return 'text-yellow-400'
    return 'text-text-secondary'
  }

  return (
    <div className="bg-background-card rounded-xl border border-border-primary p-4">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <div>
          <h3 className="text-lg font-bold text-text-primary">Decision Transparency Log</h3>
          <p className="text-sm text-text-muted">What, Why, How for every bot decision</p>
        </div>

        <div className="flex gap-2">
          {/* Bot Filter */}
          <select
            value={selectedBot}
            onChange={(e) => setSelectedBot(e.target.value)}
            className="bg-background-tertiary border border-border-secondary rounded px-3 py-1 text-sm text-text-primary"
          >
            <option value="all">All Bots</option>
            <option value="PHOENIX">PHOENIX (0DTE)</option>
            <option value="ATLAS">ATLAS (Wheel)</option>
            <option value="HERMES">HERMES (Manual)</option>
            <option value="ORACLE">ORACLE (Advisory)</option>
          </select>

          {/* Export Button */}
          <button
            onClick={handleExport}
            disabled={exporting}
            className="bg-accent-primary hover:bg-accent-primary/80 text-white px-3 py-1 rounded text-sm font-medium disabled:opacity-50"
          >
            {exporting ? 'Exporting...' : 'Export CSV'}
          </button>

          {/* Refresh Button */}
          <button
            onClick={loadData}
            disabled={loading}
            className="bg-background-tertiary hover:bg-background-hover border border-border-secondary text-text-primary px-3 py-1 rounded text-sm"
          >
            {loading ? '...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-4 gap-4 mb-4">
          <div className="bg-background-tertiary rounded-lg p-3 border border-border-secondary">
            <p className="text-text-muted text-xs">Total Decisions</p>
            <p className="text-xl font-bold text-text-primary">{summary.total_decisions}</p>
          </div>
          <div className="bg-background-tertiary rounded-lg p-3 border border-border-secondary">
            <p className="text-text-muted text-xs">Trades Executed</p>
            <p className="text-xl font-bold text-green-400">{summary.trades_executed}</p>
          </div>
          <div className="bg-background-tertiary rounded-lg p-3 border border-border-secondary">
            <p className="text-text-muted text-xs">Total P&L</p>
            <p className={`text-xl font-bold ${summary.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              ${summary.total_pnl?.toLocaleString() || '0'}
            </p>
          </div>
          <div className="bg-background-tertiary rounded-lg p-3 border border-border-secondary">
            <p className="text-text-muted text-xs">Active Bots</p>
            <p className="text-xl font-bold text-accent-primary">
              {Object.values(bots).filter(b => b.scheduled).length}
            </p>
          </div>
        </div>
      )}

      {/* Decision Log List */}
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {loading ? (
          <div className="text-center py-8 text-text-muted">Loading decisions...</div>
        ) : logs.length === 0 ? (
          <div className="text-center py-8 text-text-muted">No decisions recorded yet</div>
        ) : (
          logs.map((log) => (
            <div
              key={log.id}
              className="bg-background-tertiary rounded-lg border border-border-secondary p-3 hover:border-accent-primary/50 cursor-pointer transition-colors"
              onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
            >
              {/* Log Header */}
              <div className="flex justify-between items-start mb-2">
                <div className="flex items-center gap-2">
                  <span className={`font-bold ${getBotColor(log.bot_name)}`}>
                    {log.bot_name}
                  </span>
                  <span className="text-text-muted text-sm">{log.symbol}</span>
                  <span className={`text-sm font-medium ${getActionColor(log.action)}`}>
                    {log.action}
                  </span>
                </div>
                <span className="text-text-muted text-xs">
                  {new Date(log.timestamp).toLocaleString()}
                </span>
              </div>

              {/* What */}
              <div className="mb-2">
                <span className="text-text-muted text-xs">WHAT: </span>
                <span className="text-text-primary text-sm">{log.what}</span>
              </div>

              {/* Expanded Details */}
              {expandedLog === log.id && (
                <div className="mt-3 pt-3 border-t border-border-secondary space-y-2">
                  {/* Why */}
                  <div>
                    <span className="text-yellow-400 text-xs font-medium">WHY: </span>
                    <span className="text-text-secondary text-sm">{log.why || 'Not specified'}</span>
                  </div>

                  {/* How */}
                  <div>
                    <span className="text-blue-400 text-xs font-medium">HOW: </span>
                    <span className="text-text-secondary text-sm">{log.how || 'Not specified'}</span>
                  </div>

                  {/* Outcome */}
                  {log.outcome && (
                    <div>
                      <span className="text-green-400 text-xs font-medium">OUTCOME: </span>
                      <span className="text-text-secondary text-sm">{log.outcome}</span>
                    </div>
                  )}

                  {/* Data */}
                  {log.data && Object.keys(log.data).length > 0 && (
                    <div className="bg-background-secondary rounded p-2 mt-2">
                      <span className="text-text-muted text-xs font-medium">DATA:</span>
                      <pre className="text-text-secondary text-xs mt-1 overflow-x-auto">
                        {JSON.stringify(log.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Bot Status Footer */}
      <div className="mt-4 pt-4 border-t border-border-secondary">
        <p className="text-xs text-text-muted mb-2">Active Bots:</p>
        <div className="flex gap-2 flex-wrap">
          {Object.values(bots).map((bot) => (
            <div
              key={bot.name}
              className={`text-xs px-2 py-1 rounded ${
                bot.scheduled
                  ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                  : 'bg-gray-500/20 text-gray-400 border border-gray-500/30'
              }`}
            >
              {bot.name}: ${(bot.capital_allocation / 1000).toFixed(0)}K ({bot.capital_pct}%)
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
