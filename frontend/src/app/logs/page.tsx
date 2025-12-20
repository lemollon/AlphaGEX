'use client'

import { useState, useEffect } from 'react'
import {
  FileText, Download, RefreshCw, Calendar, Bot, Brain,
  Activity, Database, Eye, BarChart3, Zap, TrendingUp,
  ChevronDown, ChevronUp, AlertCircle, CheckCircle
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import DecisionLogViewer from '@/components/trader/DecisionLogViewer'
import { apiClient, api } from '@/lib/api'
import { useLogsSummary, useMLLogs, useAutonomousLogs, useOraclePredictions } from '@/lib/hooks/useMarketData'

interface TableSummary {
  display_name: string
  exists: boolean
  total_count: number
  recent_count: number
  latest_entry: string | null
  error?: string
}

interface LogsSummary {
  total_records_all_tables: number
  days_analyzed: number
  tables: Record<string, TableSummary>
  generated_at: string
}

interface MLLog {
  id: number
  timestamp: string
  action: string
  symbol: string
  details: any
  ml_score: number | null
  recommendation: string | null
  reasoning: string | null
}

interface OraclePrediction {
  id: number
  trade_date: string
  bot_name: string
  advice: string
  win_probability: number
  confidence: number
  reasoning: string
  actual_outcome: string | null
  actual_pnl: number | null
}

interface AutonomousLog {
  id: number
  timestamp: string
  log_type: string
  symbol: string
  pattern_detected: string
  confidence_score: number
  ai_thought_process: string
  reasoning_summary: string
}

type LogCategory = 'trading' | 'ml' | 'oracle' | 'autonomous' | 'psychology' | 'wheel' | 'gex' | 'all'

export default function LogsPage() {
  // SWR hooks for data fetching with caching
  const { data: summaryRes, error: summaryError, isLoading: summaryLoading, isValidating: summaryValidating, mutate: mutateSummary } = useLogsSummary(30)
  const { data: mlLogsRes, isLoading: mlLoading, isValidating: mlValidating, mutate: mutateML } = useMLLogs(50)
  const { data: oracleRes, isLoading: oracleLoading, isValidating: oracleValidating, mutate: mutateOracle } = useOraclePredictions()
  const { data: autonomousRes, isLoading: autonomousLoading, isValidating: autonomousValidating, mutate: mutateAutonomous } = useAutonomousLogs(50)

  // Extract data from responses
  const summary = summaryRes?.data as LogsSummary | undefined
  const mlLogs = (mlLogsRes?.data?.logs || []) as MLLog[]
  const oraclePredictions = (oracleRes?.data?.predictions || []) as OraclePrediction[]
  const autonomousLogs = (autonomousRes?.data?.logs || []) as AutonomousLog[]

  const loading = summaryLoading && !summary
  const isRefreshing = summaryValidating || mlValidating || oracleValidating || autonomousValidating

  // UI State
  const [activeCategory, setActiveCategory] = useState<LogCategory>('trading')
  const [activeBot, setActiveBot] = useState<string>('all')
  const [dateRange, setDateRange] = useState({ start: '', end: '' })
  const [exporting, setExporting] = useState(false)
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({})

  const categories = [
    { id: 'trading', name: 'Trading Decisions', icon: FileText, color: 'bg-blue-500', tables: ['trading_decisions'] },
    { id: 'ml', name: 'ML/AI Logs', icon: Brain, color: 'bg-purple-500', tables: ['ml_decision_logs', 'ml_predictions', 'ares_ml_outcomes', 'spx_wheel_ml_outcomes'] },
    { id: 'oracle', name: 'Oracle Predictions', icon: Eye, color: 'bg-green-500', tables: ['oracle_predictions'] },
    { id: 'autonomous', name: 'Autonomous Trader', icon: Bot, color: 'bg-orange-500', tables: ['autonomous_trader_logs', 'autonomous_trade_log'] },
    { id: 'psychology', name: 'Psychology Analysis', icon: Activity, color: 'bg-pink-500', tables: ['psychology_analysis', 'pattern_learning'] },
    { id: 'wheel', name: 'Wheel Activity', icon: TrendingUp, color: 'bg-cyan-500', tables: ['wheel_activity_log'] },
    { id: 'gex', name: 'GEX Changes', icon: Zap, color: 'bg-yellow-500', tables: ['gex_change_log'] },
    { id: 'all', name: 'All Tables', icon: Database, color: 'bg-gray-500', tables: [] },
  ]

  const bots = [
    { id: 'all', name: 'All Bots', color: 'bg-gray-600' },
    { id: 'PHOENIX', name: 'PHOENIX', color: 'bg-orange-500' },
    { id: 'ATLAS', name: 'ATLAS', color: 'bg-blue-500' },
    { id: 'ARES', name: 'ARES', color: 'bg-red-500' },
    { id: 'HERMES', name: 'HERMES', color: 'bg-purple-500' },
    { id: 'ORACLE', name: 'ORACLE', color: 'bg-green-500' },
  ]

  // Refresh function
  const loadSummary = () => {
    mutateSummary()
    mutateML()
    mutateOracle()
    mutateAutonomous()
  }

  // Loading states for specific tabs
  const loadingLogs = (activeCategory === 'ml' && mlLoading) ||
                     (activeCategory === 'oracle' && oracleLoading) ||
                     (activeCategory === 'autonomous' && autonomousLoading)

  const getTableCount = (tableNames: string[]) => {
    if (!summary?.tables) return 0
    return tableNames.reduce((sum, name) => sum + (summary.tables[name]?.total_count || 0), 0)
  }

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }))
  }

  // Export functions
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
      a.download = `alphagex-${activeCategory}-logs-${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Error exporting CSV:', error)
    }
    setExporting(false)
  }

  const handleExportJSON = async () => {
    setExporting(true)
    try {
      let data: any[] = []
      if (activeCategory === 'trading') {
        const response = await api.get('/api/trader/logs/decisions', {
          params: { bot: activeBot === 'all' ? undefined : activeBot, limit: 1000 }
        })
        data = response.data?.data?.decisions || []
      } else if (activeCategory === 'ml') {
        data = mlLogs
      } else if (activeCategory === 'oracle') {
        data = oraclePredictions
      } else if (activeCategory === 'autonomous') {
        data = autonomousLogs
      }

      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `alphagex-${activeCategory}-logs-${new Date().toISOString().split('T')[0]}.json`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Error exporting JSON:', error)
    }
    setExporting(false)
  }

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />
      <main className="lg:pl-16 pt-24">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Database className="w-8 h-8 text-blue-500" />
              <div>
                <h1 className="text-2xl font-bold text-white">Master Logs Dashboard</h1>
                <p className="text-gray-400">Complete audit trail across ALL 22 logging tables</p>
              </div>
            </div>
            <button
              onClick={loadSummary}
              disabled={isRefreshing}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {/* Global Summary */}
          {summary && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <p className="text-gray-400 text-sm">Total Records (All Tables)</p>
                <p className="text-3xl font-bold text-white">{summary.total_records_all_tables?.toLocaleString() || 0}</p>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <p className="text-gray-400 text-sm">Tables with Data</p>
                <p className="text-3xl font-bold text-green-400">
                  {Object.values(summary.tables || {}).filter(t => t.total_count > 0).length}
                </p>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <p className="text-gray-400 text-sm">Recent Activity (7d)</p>
                <p className="text-3xl font-bold text-blue-400">
                  {Object.values(summary.tables || {}).reduce((sum, t) => sum + (t.recent_count || 0), 0).toLocaleString()}
                </p>
              </div>
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <p className="text-gray-400 text-sm">Tables Tracked</p>
                <p className="text-3xl font-bold text-purple-400">{Object.keys(summary.tables || {}).length}</p>
              </div>
            </div>
          )}

          {/* Category Tabs */}
          <div className="flex flex-wrap gap-2 mb-6">
            {categories.map((cat) => {
              const Icon = cat.icon
              const count = cat.id === 'all'
                ? summary?.total_records_all_tables || 0
                : getTableCount(cat.tables)
              return (
                <button
                  key={cat.id}
                  onClick={() => setActiveCategory(cat.id as LogCategory)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activeCategory === cat.id
                      ? `${cat.color} text-white`
                      : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {cat.name}
                  {count > 0 && (
                    <span className="ml-1 px-2 py-0.5 bg-black/20 rounded text-xs">
                      {count.toLocaleString()}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Filters & Export Bar */}
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 mb-6">
            <div className="flex flex-wrap items-center gap-4">
              {/* Date Range Filter */}
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-gray-400" />
                <input
                  type="date"
                  value={dateRange.start}
                  onChange={(e) => setDateRange(prev => ({ ...prev, start: e.target.value }))}
                  className="bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white"
                />
                <span className="text-gray-500">to</span>
                <input
                  type="date"
                  value={dateRange.end}
                  onChange={(e) => setDateRange(prev => ({ ...prev, end: e.target.value }))}
                  className="bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white"
                />
                {(dateRange.start || dateRange.end) && (
                  <button
                    onClick={() => setDateRange({ start: '', end: '' })}
                    className="text-xs text-gray-400 hover:text-white px-2"
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

          {/* Trading Decisions View */}
          {activeCategory === 'trading' && (
            <div className="space-y-4">
              {/* Bot Filter */}
              <div className="flex flex-wrap gap-2">
                {bots.map((bot) => (
                  <button
                    key={bot.id}
                    onClick={() => setActiveBot(bot.id)}
                    className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                      activeBot === bot.id
                        ? `${bot.color} text-white`
                        : 'bg-gray-800 text-gray-400 hover:text-white'
                    }`}
                  >
                    {bot.name}
                  </button>
                ))}
              </div>
              <DecisionLogViewer
                defaultBot={activeBot === 'all' ? undefined : activeBot}
                hideFilter={true}
              />
            </div>
          )}

          {/* ML/AI Logs View */}
          {activeCategory === 'ml' && (
            <div className="bg-gray-800 rounded-lg border border-gray-700">
              <div className="p-4 border-b border-gray-700 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Brain className="w-5 h-5 text-purple-500" />
                  ML Decision Logs
                </h3>
                <span className="text-gray-400 text-sm">{mlLogs.length} entries</span>
              </div>
              {loadingLogs ? (
                <div className="p-8 text-center text-gray-400">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
                  Loading ML logs...
                </div>
              ) : mlLogs.length === 0 ? (
                <div className="p-8 text-center text-gray-400">
                  <Brain className="w-12 h-12 mx-auto mb-3 text-gray-600" />
                  <p>No ML logs yet</p>
                  <p className="text-sm mt-1">ML activity will appear here as bots make decisions</p>
                </div>
              ) : (
                <div className="divide-y divide-gray-700 max-h-96 overflow-y-auto">
                  {mlLogs.map((log) => (
                    <div key={log.id} className="p-4 hover:bg-gray-700/50">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            log.action === 'SCORE_TRADE' ? 'bg-blue-500/30 text-blue-300' :
                            log.action === 'AUTO_TRAIN' ? 'bg-purple-500/30 text-purple-300' :
                            'bg-gray-700 text-gray-300'
                          }`}>
                            {log.action}
                          </span>
                          {log.recommendation && (
                            <span className={`px-2 py-0.5 rounded text-xs ${
                              log.recommendation === 'TRADE' ? 'bg-green-500/30 text-green-300' :
                              log.recommendation === 'SKIP' ? 'bg-red-500/30 text-red-300' :
                              'bg-yellow-500/30 text-yellow-300'
                            }`}>
                              {log.recommendation}
                            </span>
                          )}
                          {log.ml_score !== null && (
                            <span className="text-xs text-gray-400">
                              Score: {(log.ml_score * 100).toFixed(1)}%
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-gray-500">
                          {new Date(log.timestamp).toLocaleString()}
                        </span>
                      </div>
                      {log.reasoning && (
                        <p className="text-sm text-gray-300">{log.reasoning}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Oracle Predictions View */}
          {activeCategory === 'oracle' && (
            <div className="bg-gray-800 rounded-lg border border-gray-700">
              <div className="p-4 border-b border-gray-700 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Eye className="w-5 h-5 text-green-500" />
                  Oracle ML Predictions
                </h3>
                <span className="text-gray-400 text-sm">{oraclePredictions.length} predictions</span>
              </div>
              {loadingLogs ? (
                <div className="p-8 text-center text-gray-400">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
                  Loading Oracle predictions...
                </div>
              ) : oraclePredictions.length === 0 ? (
                <div className="p-8 text-center text-gray-400">
                  <Eye className="w-12 h-12 mx-auto mb-3 text-gray-600" />
                  <p>No Oracle predictions yet</p>
                  <p className="text-sm mt-1">Run Oracle analysis to generate predictions</p>
                </div>
              ) : (
                <div className="divide-y divide-gray-700 max-h-96 overflow-y-auto">
                  {oraclePredictions.map((pred) => (
                    <div key={pred.id} className="p-4 hover:bg-gray-700/50">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 bg-gray-700 rounded text-xs text-gray-300">
                            {pred.bot_name}
                          </span>
                          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            pred.advice === 'TRADE' ? 'bg-green-500/30 text-green-300' :
                            pred.advice === 'SKIP' ? 'bg-red-500/30 text-red-300' :
                            'bg-yellow-500/30 text-yellow-300'
                          }`}>
                            {pred.advice}
                          </span>
                          <span className="text-xs text-gray-400">
                            Win Prob: {(pred.win_probability * 100).toFixed(1)}%
                          </span>
                          <span className="text-xs text-gray-400">
                            Conf: {(pred.confidence * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          {pred.actual_outcome && (
                            <span className={`flex items-center gap-1 text-xs ${
                              pred.actual_outcome === 'WIN' ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {pred.actual_outcome === 'WIN' ? <CheckCircle className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                              {pred.actual_outcome}
                            </span>
                          )}
                          <span className="text-xs text-gray-500">{pred.trade_date}</span>
                        </div>
                      </div>
                      {pred.reasoning && (
                        <p className="text-sm text-gray-300">{pred.reasoning}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Autonomous Trader Logs View */}
          {activeCategory === 'autonomous' && (
            <div className="bg-gray-800 rounded-lg border border-gray-700">
              <div className="p-4 border-b border-gray-700 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Bot className="w-5 h-5 text-orange-500" />
                  Autonomous Trader Scan Logs
                </h3>
                <span className="text-gray-400 text-sm">{autonomousLogs.length} entries</span>
              </div>
              {loadingLogs ? (
                <div className="p-8 text-center text-gray-400">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
                  Loading autonomous logs...
                </div>
              ) : autonomousLogs.length === 0 ? (
                <div className="p-8 text-center text-gray-400">
                  <Bot className="w-12 h-12 mx-auto mb-3 text-gray-600" />
                  <p>No autonomous trader logs yet</p>
                  <p className="text-sm mt-1">Start the autonomous trader to see scan logs</p>
                </div>
              ) : (
                <div className="divide-y divide-gray-700 max-h-96 overflow-y-auto">
                  {autonomousLogs.map((log) => (
                    <div key={log.id} className="p-4 hover:bg-gray-700/50">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            log.log_type === 'TRADE_DECISION' ? 'bg-green-500/30 text-green-300' :
                            log.log_type === 'SCAN_START' ? 'bg-blue-500/30 text-blue-300' :
                            log.log_type === 'ERROR' ? 'bg-red-500/30 text-red-300' :
                            'bg-gray-700 text-gray-300'
                          }`}>
                            {log.log_type}
                          </span>
                          {log.symbol && (
                            <span className="text-xs text-gray-400">{log.symbol}</span>
                          )}
                          {log.pattern_detected && (
                            <span className="px-2 py-0.5 bg-purple-500/30 text-purple-300 rounded text-xs">
                              {log.pattern_detected}
                            </span>
                          )}
                          {log.confidence_score > 0 && (
                            <span className="text-xs text-gray-400">
                              Conf: {log.confidence_score}%
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-gray-500">
                          {new Date(log.timestamp).toLocaleString()}
                        </span>
                      </div>
                      {log.reasoning_summary && (
                        <p className="text-sm text-gray-300">{log.reasoning_summary}</p>
                      )}
                      {log.ai_thought_process && (
                        <p className="text-xs text-gray-500 mt-1 italic">{log.ai_thought_process}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* All Tables Overview */}
          {activeCategory === 'all' && summary?.tables && (
            <div className="bg-gray-800 rounded-lg border border-gray-700">
              <div className="p-4 border-b border-gray-700">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Database className="w-5 h-5 text-gray-400" />
                  All Logging Tables Status
                </h3>
              </div>
              <div className="divide-y divide-gray-700">
                {Object.entries(summary.tables).map(([tableName, info]) => (
                  <div key={tableName} className="p-4 hover:bg-gray-700/50">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        {info.exists && info.total_count > 0 ? (
                          <CheckCircle className="w-5 h-5 text-green-500" />
                        ) : info.exists ? (
                          <AlertCircle className="w-5 h-5 text-yellow-500" />
                        ) : (
                          <AlertCircle className="w-5 h-5 text-red-500" />
                        )}
                        <div>
                          <p className="font-medium text-white">{info.display_name}</p>
                          <p className="text-xs text-gray-500">{tableName}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-bold text-white">{info.total_count?.toLocaleString() || 0}</p>
                        <p className="text-xs text-gray-500">
                          {info.recent_count || 0} in last 7d
                        </p>
                      </div>
                    </div>
                    {info.latest_entry && (
                      <p className="text-xs text-gray-500 mt-1">
                        Latest: {new Date(info.latest_entry).toLocaleString()}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Psychology/Wheel/GEX placeholders */}
          {(activeCategory === 'psychology' || activeCategory === 'wheel' || activeCategory === 'gex') && (
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center">
              <Activity className="w-12 h-12 mx-auto mb-3 text-gray-600" />
              <p className="text-gray-400">
                {activeCategory === 'psychology' && 'Psychology analysis logs - view pattern detection and regime analysis'}
                {activeCategory === 'wheel' && 'Wheel strategy activity logs - view CSP/CC execution history'}
                {activeCategory === 'gex' && 'GEX change logs - view gamma exposure shifts and velocity trends'}
              </p>
              <p className="text-sm text-gray-500 mt-2">
                Data will appear as the system collects it
              </p>
            </div>
          )}

          {/* Footer */}
          <div className="mt-6 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
            <h4 className="font-medium text-white mb-2">Log Categories Explained:</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-blue-400 font-medium">Trading Decisions</p>
                <p className="text-gray-500">Every entry/exit with full reasoning</p>
              </div>
              <div>
                <p className="text-purple-400 font-medium">ML/AI Logs</p>
                <p className="text-gray-500">Model predictions, scores, training</p>
              </div>
              <div>
                <p className="text-green-400 font-medium">Oracle Predictions</p>
                <p className="text-gray-500">AI advisory with win probabilities</p>
              </div>
              <div>
                <p className="text-orange-400 font-medium">Autonomous Trader</p>
                <p className="text-gray-500">Scan cycles, patterns, thought process</p>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
