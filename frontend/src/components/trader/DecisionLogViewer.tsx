'use client'

import React, { useState, useEffect } from 'react'
import { apiClient } from '@/lib/api'

interface TradeLeg {
  leg_id: number
  action: string
  option_type: string
  strike: number
  expiration: string
  entry_price: number
  exit_price: number
  contracts: number
  premium_per_contract: number
  delta: number
  gamma: number
  theta: number
  iv: number
  order_id: string
  realized_pnl: number
}

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
  timestamp: string
  // Trade details
  strike?: number
  expiration?: string
  spot_price?: number
  vix?: number
  actual_pnl?: number
  // Full decision data including legs
  full_decision?: {
    legs?: TradeLeg[]
    underlying_price_at_entry?: number
    underlying_price_at_exit?: number
    order_id?: string
    position_size_contracts?: number
    position_size_dollars?: number
  }
  data?: Record<string, unknown>
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

interface DecisionLogViewerProps {
  defaultBot?: string  // Lock to specific bot (e.g., 'ARES')
  hideFilter?: boolean // Hide the bot filter dropdown
}

export default function DecisionLogViewer({ defaultBot, hideFilter = false }: DecisionLogViewerProps) {
  const [logs, setLogs] = useState<DecisionLog[]>([])
  const [summary, setSummary] = useState<DecisionSummary | null>(null)
  const [bots, setBots] = useState<Record<string, BotStatus>>({})
  const [selectedBot, setSelectedBot] = useState<string>(defaultBot || 'all')
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
        // Backend returns { data: { decisions: [...] } }
        setLogs(logsRes.data.data?.decisions || logsRes.data.data || [])
      }
      if (summaryRes.data?.success) {
        // Backend returns { data: { summary: {...} } }
        setSummary(summaryRes.data.data?.summary || summaryRes.data.data)
      }
      if (botsRes.data?.success) {
        setBots(botsRes.data.data?.bots || {})
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
      'ORACLE': 'text-green-400',
      'ARES': 'text-red-400'
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
          {/* Bot Filter - Hidden when defaultBot is set */}
          {!hideFilter && !defaultBot && (
            <select
              value={selectedBot}
              onChange={(e) => setSelectedBot(e.target.value)}
              className="bg-gray-700 border border-gray-600 rounded px-3 py-1 text-sm text-white"
            >
              <option value="all">All Bots</option>
              <option value="PHOENIX">PHOENIX (0DTE)</option>
              <option value="ATLAS">ATLAS (Wheel)</option>
              <option value="ARES">ARES (Aggressive IC)</option>
              <option value="HERMES">HERMES (Manual)</option>
              <option value="ORACLE">ORACLE (Advisory)</option>
            </select>
          )}

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
            className="bg-gray-700 hover:bg-gray-600 border border-gray-600 text-white px-3 py-1 rounded text-sm"
          >
            {loading ? '...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-4 gap-4 mb-4">
          <div className="bg-gray-700 rounded-lg p-3 border border-gray-600">
            <p className="text-gray-400 text-xs">Total Decisions</p>
            <p className="text-xl font-bold text-white">{summary.total_decisions}</p>
          </div>
          <div className="bg-gray-700 rounded-lg p-3 border border-gray-600">
            <p className="text-gray-400 text-xs">Trades Executed</p>
            <p className="text-xl font-bold text-green-400">{summary.trades_executed}</p>
          </div>
          <div className="bg-gray-700 rounded-lg p-3 border border-gray-600">
            <p className="text-gray-400 text-xs">Total P&L</p>
            <p className={`text-xl font-bold ${summary.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              ${summary.total_pnl?.toLocaleString() || '0'}
            </p>
          </div>
          <div className="bg-gray-700 rounded-lg p-3 border border-gray-600">
            <p className="text-gray-400 text-xs">Active Bots</p>
            <p className="text-xl font-bold text-blue-400">
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
              className="bg-gray-700 rounded-lg border border-gray-600 p-3 hover:border-blue-500/50 cursor-pointer transition-colors"
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

                  {/* Trade Details - Strike, Entry, Exit, Expiration */}
                  {(log.strike || log.spot_price || log.vix) && (
                    <div className="bg-background-secondary rounded p-2 mt-2">
                      <span className="text-accent-primary text-xs font-medium">TRADE DETAILS:</span>
                      <div className="grid grid-cols-4 gap-2 mt-1 text-xs">
                        {log.strike && (
                          <div>
                            <span className="text-text-muted">Strike:</span>
                            <span className="text-text-primary ml-1">${log.strike}</span>
                          </div>
                        )}
                        {log.expiration && (
                          <div>
                            <span className="text-text-muted">Exp:</span>
                            <span className="text-text-primary ml-1">{log.expiration}</span>
                          </div>
                        )}
                        {log.spot_price && (
                          <div>
                            <span className="text-text-muted">Spot:</span>
                            <span className="text-text-primary ml-1">${log.spot_price?.toFixed(2)}</span>
                          </div>
                        )}
                        {log.vix && (
                          <div>
                            <span className="text-text-muted">VIX:</span>
                            <span className="text-text-primary ml-1">{log.vix?.toFixed(1)}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Trade Legs - ALL leg data for multi-leg strategies */}
                  {log.full_decision?.legs && log.full_decision.legs.length > 0 && (
                    <div className="bg-background-secondary rounded p-2 mt-2">
                      <span className="text-purple-400 text-xs font-medium">
                        TRADE LEGS ({log.full_decision.legs.length}):
                      </span>
                      <div className="mt-2 space-y-2">
                        {log.full_decision.legs.map((leg, idx) => (
                          <div key={idx} className="bg-background-tertiary rounded p-2 text-xs">
                            <div className="flex justify-between items-center mb-1">
                              <span className="font-medium text-text-primary">
                                Leg {leg.leg_id}: {leg.action} {leg.option_type?.toUpperCase()}
                              </span>
                              {leg.realized_pnl !== 0 && (
                                <span className={leg.realized_pnl > 0 ? 'text-green-400' : 'text-red-400'}>
                                  P&L: ${leg.realized_pnl?.toFixed(2)}
                                </span>
                              )}
                            </div>
                            <div className="grid grid-cols-4 gap-2 text-text-secondary">
                              <div><span className="text-text-muted">Strike:</span> ${leg.strike}</div>
                              <div><span className="text-text-muted">Exp:</span> {leg.expiration}</div>
                              <div><span className="text-text-muted">Entry:</span> ${leg.entry_price?.toFixed(2)}</div>
                              <div><span className="text-text-muted">Exit:</span> ${leg.exit_price?.toFixed(2) || '-'}</div>
                              <div><span className="text-text-muted">Contracts:</span> {leg.contracts}</div>
                              <div><span className="text-text-muted">Delta:</span> {leg.delta?.toFixed(2)}</div>
                              <div><span className="text-text-muted">IV:</span> {(leg.iv * 100)?.toFixed(1)}%</div>
                              <div><span className="text-text-muted">Order:</span> {leg.order_id || '-'}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Outcome */}
                  {log.outcome && (
                    <div>
                      <span className="text-green-400 text-xs font-medium">OUTCOME: </span>
                      <span className="text-text-secondary text-sm">{log.outcome}</span>
                    </div>
                  )}

                  {/* P&L if available */}
                  {log.actual_pnl != null && log.actual_pnl !== 0 && (
                    <div>
                      <span className="text-text-muted text-xs font-medium">REALIZED P&L: </span>
                      <span className={`text-sm font-bold ${log.actual_pnl > 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${log.actual_pnl?.toLocaleString()}
                      </span>
                    </div>
                  )}

                  {/* Raw Data - collapsed by default */}
                  {log.data && Object.keys(log.data).length > 0 && (
                    <details className="bg-background-secondary rounded p-2 mt-2">
                      <summary className="text-text-muted text-xs font-medium cursor-pointer">
                        RAW DATA (click to expand)
                      </summary>
                      <pre className="text-text-secondary text-xs mt-1 overflow-x-auto">
                        {JSON.stringify(log.data, null, 2)}
                      </pre>
                    </details>
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
