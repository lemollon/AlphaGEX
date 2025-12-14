'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { Activity, AlertTriangle, CheckCircle, XCircle, ChevronDown, ChevronUp, RefreshCw } from 'lucide-react'
import Navigation from '@/components/Navigation'
import DecisionFilterPanel from './DecisionFilterPanel'
import ClaudeConversationViewer from './ClaudeConversationViewer'
import ExecutionTimeline from './ExecutionTimeline'
import apiClient from '@/lib/api'

interface Decision {
  decision_id: string
  bot_name: string
  session_id: string
  scan_cycle: number
  decision_sequence: number
  timestamp: string
  decision_type: string
  action: string
  symbol: string
  strategy: string
  strike: number
  expiration: string
  option_type: string
  contracts: number
  spot_price: number
  vix: number
  net_gex: number
  gex_regime: string
  flip_point: number
  call_wall: number
  put_wall: number
  trend: string
  claude_prompt: string
  claude_response: string
  claude_model: string
  claude_tokens_used: number
  claude_response_time_ms: number
  langchain_chain: string
  ai_confidence: string
  ai_warnings: string[]
  entry_reasoning: string
  strike_reasoning: string
  size_reasoning: string
  exit_reasoning: string
  alternatives_considered: any[]
  other_strategies_considered: string[]
  psychology_pattern: string
  liberation_setup: boolean
  false_floor_detected: boolean
  forward_magnets: Record<string, number>
  kelly_pct: number
  position_size_dollars: number
  max_risk_dollars: number
  backtest_win_rate: number
  backtest_expectancy: number
  backtest_sharpe: number
  risk_checks_performed: any[]
  passed_all_checks: boolean
  blocked_reason: string
  order_submitted_at: string
  order_filled_at: string
  broker_order_id: string
  expected_fill_price: number
  actual_fill_price: number
  slippage_pct: number
  broker_status: string
  execution_notes: string
  actual_pnl: number
  exit_triggered_by: string
  exit_timestamp: string
  exit_price: number
  exit_slippage_pct: number
  outcome_correct: boolean
  outcome_notes: string
  api_calls_made: any[]
  errors_encountered: any[]
  processing_time_ms: number
  created_at: string
}

interface Stats {
  total_decisions: number
  total_sessions: number
  entry_decisions: number
  exit_decisions: number
  skip_decisions: number
  profitable_trades: number
  losing_trades: number
  closed_trades: number
  avg_pnl: number
  total_pnl: number
  win_rate: number
  avg_slippage_pct: number
  avg_claude_response_ms: number
  decisions_with_errors: number
}

interface FilterState {
  bot: string
  decisionType: string
  outcome: string
  startDate: string
  endDate: string
  search: string
  confidenceLevel: string
}

interface BotLogsPageProps {
  botName: string
  botColor: string
  botDescription: string
}

export default function BotLogsPage({ botName, botColor, botDescription }: BotLogsPageProps) {
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [isExporting, setIsExporting] = useState(false)
  const [expandedDecision, setExpandedDecision] = useState<string | null>(null)
  const [filters, setFilters] = useState<FilterState>({
    bot: botName,
    decisionType: 'all',
    outcome: 'all',
    startDate: '',
    endDate: '',
    search: '',
    confidenceLevel: 'all'
  })

  const fetchDecisions = useCallback(async () => {
    setLoading(true)
    try {
      const response = await apiClient.getBotDecisions({
        bot: botName,
        limit: 100,
        decision_type: filters.decisionType !== 'all' ? filters.decisionType : undefined,
        outcome: filters.outcome !== 'all' ? filters.outcome : undefined,
        start_date: filters.startDate || undefined,
        end_date: filters.endDate || undefined,
        search: filters.search || undefined,
      })
      setDecisions(response.data?.data?.decisions || [])
    } catch (error) {
      console.error('Error fetching decisions:', error)
    }
    setLoading(false)
  }, [botName, filters])

  const fetchStats = useCallback(async () => {
    try {
      const response = await apiClient.getBotDecisionStats(botName, 30)
      setStats(response.data?.data?.stats || null)
    } catch (error) {
      console.error('Error fetching stats:', error)
    }
  }, [botName])

  useEffect(() => {
    fetchDecisions()
    fetchStats()
  }, [fetchDecisions, fetchStats])

  const handleExport = async (format: 'csv' | 'json' | 'excel') => {
    setIsExporting(true)
    try {
      const response = await apiClient.exportBotDecisions({
        bot: botName,
        format,
        days: 30
      })

      if (format === 'json') {
        const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${botName.toLowerCase()}-decisions-${new Date().toISOString().split('T')[0]}.json`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
      } else {
        const blob = response.data
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${botName.toLowerCase()}-decisions-${new Date().toISOString().split('T')[0]}.${format === 'excel' ? 'xlsx' : 'csv'}`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
      }
    } catch (error) {
      console.error('Error exporting:', error)
    }
    setIsExporting(false)
  }

  const formatTime = (timestamp: string) => {
    if (!timestamp) return '-'
    try {
      return new Date(timestamp).toLocaleString()
    } catch {
      return timestamp
    }
  }

  const getDecisionTypeColor = (type: string) => {
    switch (type?.toUpperCase()) {
      case 'ENTRY': return 'bg-green-800/50 text-green-300'
      case 'EXIT': return 'bg-red-800/50 text-red-300'
      case 'SKIP': return 'bg-yellow-800/50 text-yellow-300'
      case 'ADJUSTMENT': return 'bg-blue-800/50 text-blue-300'
      default: return 'bg-gray-800/50 text-gray-300'
    }
  }

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />
      <main className="lg:pl-64 pt-16 lg:pt-0">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className={`text-2xl font-bold ${botColor}`}>{botName} Decision Logs</h1>
              <p className="text-gray-400 text-sm mt-1">{botDescription}</p>
            </div>
            <button
              onClick={() => { fetchDecisions(); fetchStats(); }}
              className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {/* Stats Cards */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-6">
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <div className="text-2xl font-bold text-white">{stats.total_decisions}</div>
                <div className="text-sm text-gray-400">Total Decisions</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <div className="text-2xl font-bold text-green-400">{stats.win_rate.toFixed(1)}%</div>
                <div className="text-sm text-gray-400">Win Rate</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <div className={`text-2xl font-bold ${stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  ${stats.total_pnl.toFixed(2)}
                </div>
                <div className="text-sm text-gray-400">Total P&L</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <div className="text-2xl font-bold text-blue-400">{stats.total_sessions}</div>
                <div className="text-sm text-gray-400">Sessions</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <div className="text-2xl font-bold text-yellow-400">{stats.avg_slippage_pct.toFixed(2)}%</div>
                <div className="text-sm text-gray-400">Avg Slippage</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <div className="text-2xl font-bold text-purple-400">{stats.avg_claude_response_ms.toFixed(0)}ms</div>
                <div className="text-sm text-gray-400">Avg Claude Time</div>
              </div>
            </div>
          )}

          {/* Filters */}
          <DecisionFilterPanel
            filters={filters}
            onFiltersChange={(f) => setFilters({ ...f, bot: botName })}
            onExport={handleExport}
            isExporting={isExporting}
            className="mb-6"
          />

          {/* Decisions List */}
          {loading ? (
            <div className="text-center text-gray-400 py-12">Loading decisions...</div>
          ) : decisions.length === 0 ? (
            <div className="text-center text-gray-400 py-12">
              <Activity className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>No decisions found for {botName}</p>
              <p className="text-sm mt-2">Decisions will appear here when the bot starts trading</p>
            </div>
          ) : (
            <div className="space-y-4">
              {decisions.map((decision) => (
                <div
                  key={decision.decision_id}
                  className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden"
                >
                  {/* Decision Header */}
                  <button
                    onClick={() => setExpandedDecision(
                      expandedDecision === decision.decision_id ? null : decision.decision_id
                    )}
                    className="w-full p-4 flex items-center justify-between hover:bg-gray-750 transition-colors"
                  >
                    <div className="flex items-center gap-4">
                      {/* Status Icon */}
                      {decision.actual_pnl !== null && decision.actual_pnl !== undefined ? (
                        decision.actual_pnl > 0 ? (
                          <CheckCircle className="w-6 h-6 text-green-400" />
                        ) : (
                          <XCircle className="w-6 h-6 text-red-400" />
                        )
                      ) : decision.passed_all_checks === false ? (
                        <AlertTriangle className="w-6 h-6 text-yellow-400" />
                      ) : (
                        <Activity className="w-6 h-6 text-blue-400" />
                      )}

                      <div className="text-left">
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-0.5 rounded text-xs ${getDecisionTypeColor(decision.decision_type)}`}>
                            {decision.decision_type}
                          </span>
                          <span className="font-medium text-white">
                            {decision.action} {decision.symbol}
                          </span>
                          {decision.strike > 0 && (
                            <span className="text-gray-400">
                              ${decision.strike} {decision.option_type}
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-gray-400 mt-1">
                          {formatTime(decision.timestamp)} | Session: {decision.session_id}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-4">
                      {/* P&L Badge */}
                      {decision.actual_pnl !== null && decision.actual_pnl !== undefined && (
                        <span className={`font-bold ${decision.actual_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {decision.actual_pnl >= 0 ? '+' : ''}${decision.actual_pnl.toFixed(2)}
                        </span>
                      )}

                      {/* Confidence Badge */}
                      {decision.ai_confidence && (
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          decision.ai_confidence === 'HIGH' ? 'bg-green-800/50 text-green-300' :
                          decision.ai_confidence === 'MEDIUM' ? 'bg-yellow-800/50 text-yellow-300' :
                          'bg-red-800/50 text-red-300'
                        }`}>
                          {decision.ai_confidence}
                        </span>
                      )}

                      {expandedDecision === decision.decision_id ? (
                        <ChevronUp className="w-5 h-5 text-gray-400" />
                      ) : (
                        <ChevronDown className="w-5 h-5 text-gray-400" />
                      )}
                    </div>
                  </button>

                  {/* Expanded Content */}
                  {expandedDecision === decision.decision_id && (
                    <div className="p-4 border-t border-gray-700 space-y-6">
                      {/* Reasoning */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {decision.entry_reasoning && (
                          <div className="bg-gray-900/50 rounded-lg p-3">
                            <div className="text-sm font-medium text-green-400 mb-1">Entry Reasoning</div>
                            <div className="text-sm text-gray-300">{decision.entry_reasoning}</div>
                          </div>
                        )}
                        {decision.strike_reasoning && (
                          <div className="bg-gray-900/50 rounded-lg p-3">
                            <div className="text-sm font-medium text-blue-400 mb-1">Strike Selection</div>
                            <div className="text-sm text-gray-300">{decision.strike_reasoning}</div>
                          </div>
                        )}
                        {decision.size_reasoning && (
                          <div className="bg-gray-900/50 rounded-lg p-3">
                            <div className="text-sm font-medium text-purple-400 mb-1">Position Sizing</div>
                            <div className="text-sm text-gray-300">{decision.size_reasoning}</div>
                          </div>
                        )}
                        {decision.exit_reasoning && (
                          <div className="bg-gray-900/50 rounded-lg p-3">
                            <div className="text-sm font-medium text-red-400 mb-1">Exit Reasoning</div>
                            <div className="text-sm text-gray-300">{decision.exit_reasoning}</div>
                          </div>
                        )}
                      </div>

                      {/* Market Context */}
                      <div className="bg-gray-900/50 rounded-lg p-4">
                        <div className="text-sm font-medium text-gray-400 mb-3">Market Context</div>
                        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4 text-sm">
                          <div>
                            <div className="text-gray-500">Spot</div>
                            <div className="text-white font-medium">${decision.spot_price?.toFixed(2)}</div>
                          </div>
                          <div>
                            <div className="text-gray-500">VIX</div>
                            <div className="text-white font-medium">{decision.vix?.toFixed(2)}</div>
                          </div>
                          <div>
                            <div className="text-gray-500">Net GEX</div>
                            <div className="text-white font-medium">{(decision.net_gex / 1e9)?.toFixed(2)}B</div>
                          </div>
                          <div>
                            <div className="text-gray-500">Regime</div>
                            <div className="text-white font-medium">{decision.gex_regime}</div>
                          </div>
                          <div>
                            <div className="text-gray-500">Flip</div>
                            <div className="text-white font-medium">${decision.flip_point?.toFixed(0)}</div>
                          </div>
                          <div>
                            <div className="text-gray-500">Call Wall</div>
                            <div className="text-white font-medium">${decision.call_wall?.toFixed(0)}</div>
                          </div>
                          <div>
                            <div className="text-gray-500">Put Wall</div>
                            <div className="text-white font-medium">${decision.put_wall?.toFixed(0)}</div>
                          </div>
                          <div>
                            <div className="text-gray-500">Trend</div>
                            <div className="text-white font-medium">{decision.trend}</div>
                          </div>
                        </div>
                      </div>

                      {/* Alternatives Considered */}
                      {decision.alternatives_considered && decision.alternatives_considered.length > 0 && (
                        <div className="bg-gray-900/50 rounded-lg p-4">
                          <div className="text-sm font-medium text-gray-400 mb-3">Alternatives Considered</div>
                          <div className="space-y-2">
                            {decision.alternatives_considered.map((alt: any, i: number) => (
                              <div key={i} className="flex items-center gap-4 text-sm">
                                <span className="text-gray-400">${alt.strike}</span>
                                <span className="text-red-400">Rejected: {alt.reason_rejected}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Claude Conversation */}
                      <ClaudeConversationViewer
                        prompt={decision.claude_prompt}
                        response={decision.claude_response}
                        model={decision.claude_model}
                        tokensUsed={decision.claude_tokens_used}
                        responseTimeMs={decision.claude_response_time_ms}
                        chainName={decision.langchain_chain}
                        confidence={decision.ai_confidence}
                        warnings={decision.ai_warnings}
                      />

                      {/* Execution Timeline */}
                      <ExecutionTimeline
                        orderSubmittedAt={decision.order_submitted_at}
                        orderFilledAt={decision.order_filled_at}
                        brokerOrderId={decision.broker_order_id}
                        expectedFillPrice={decision.expected_fill_price}
                        actualFillPrice={decision.actual_fill_price}
                        slippagePct={decision.slippage_pct}
                        brokerStatus={decision.broker_status}
                        executionNotes={decision.execution_notes}
                        exitTimestamp={decision.exit_timestamp}
                        exitPrice={decision.exit_price}
                        exitSlippagePct={decision.exit_slippage_pct}
                        exitTriggeredBy={decision.exit_triggered_by}
                        actualPnl={decision.actual_pnl}
                      />

                      {/* Risk Checks */}
                      {decision.risk_checks_performed && decision.risk_checks_performed.length > 0 && (
                        <div className="bg-gray-900/50 rounded-lg p-4">
                          <div className="text-sm font-medium text-gray-400 mb-3">Risk Checks</div>
                          <div className="space-y-2">
                            {decision.risk_checks_performed.map((check: any, i: number) => (
                              <div key={i} className="flex items-center gap-3 text-sm">
                                {check.passed ? (
                                  <CheckCircle className="w-4 h-4 text-green-400" />
                                ) : (
                                  <XCircle className="w-4 h-4 text-red-400" />
                                )}
                                <span className={check.passed ? 'text-gray-300' : 'text-red-300'}>
                                  {check.check_name}: {check.current_value?.toFixed(2)} / {check.limit_value?.toFixed(2)}
                                </span>
                              </div>
                            ))}
                          </div>
                          {!decision.passed_all_checks && decision.blocked_reason && (
                            <div className="mt-3 text-sm text-red-400">
                              Blocked: {decision.blocked_reason}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Errors */}
                      {decision.errors_encountered && decision.errors_encountered.length > 0 && (
                        <div className="bg-red-900/20 border border-red-700/50 rounded-lg p-4">
                          <div className="text-sm font-medium text-red-400 mb-3">Errors Encountered</div>
                          <div className="space-y-2">
                            {decision.errors_encountered.map((error: any, i: number) => (
                              <div key={i} className="text-sm text-red-300">
                                [{error.timestamp}] {error.error}
                                {error.retried && <span className="text-yellow-400 ml-2">(retried)</span>}
                                {error.resolved && <span className="text-green-400 ml-2">(resolved)</span>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
