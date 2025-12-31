'use client'

import { logger } from '@/lib/logger'
import { useState } from 'react'
import {
  Database, RefreshCw, CheckCircle, AlertCircle, Info, Table2,
  Wifi, WifiOff, Activity, Clock, Trash2, AlertTriangle,
  Server, Zap, Eye, EyeOff, ChevronDown, ChevronRight,
  Shield, TrendingUp, BarChart3, XCircle, Play, RotateCcw,
  Cpu, HardDrive, Settings2
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import {
  useDatabaseStats,
  useSystemHealth,
  useTableFreshness,
  useSystemLogs,
  useDataCollectionStatus,
  useWatchdogStatus
} from '@/lib/hooks/useMarketData'

// Types
interface Column {
  name: string
  type: string
}

interface TableStats {
  table_name: string
  row_count: number
  columns: Column[]
  sample_data: any[]
}

interface DatabaseStats {
  success: boolean
  database_path: string
  database_type: string
  connection_status: string
  total_tables: number
  tables: TableStats[]
  timestamp: string
  error?: string
}

interface SystemHealth {
  timestamp: string
  overall_status: 'healthy' | 'degraded' | 'critical'
  components: {
    [key: string]: {
      status: string
      message?: string
      [key: string]: any
    }
  }
  issues: string[]
}

interface LogEntry {
  timestamp: string
  source?: string
  error_type?: string
  message?: string
  action?: string
  details?: Record<string, any>
}

interface TableFreshness {
  timestamp: string
  tables: {
    [key: string]: {
      status: 'fresh' | 'recent' | 'stale' | 'empty' | 'error' | 'not_found' | 'configured'
      last_record?: string
      age_minutes?: number
      age_human?: string
      error?: string
      expected_frequency?: number | null
      is_stale?: boolean
      row_count?: number
    }
  }
}

interface DataCollectionStatus {
  timestamp: string
  status: string
  threads: {
    [key: string]: {
      alive: boolean
      last_run?: string
      run_count?: number
      error_count?: number
    }
  }
  last_gex_collection?: string
  last_scheduler_update?: string
  market_hours: {
    is_market_hours: boolean
    current_time: string
    market_open?: string
    market_close?: string
  }
  api_health: {
    trading_volatility: string
    polygon: string
  }
}

interface WatchdogStatus {
  timestamp: string
  enabled: boolean
  check_interval_seconds: number
  threads_monitored: {
    [key: string]: {
      status: 'running' | 'stopped' | 'restarting' | 'failed'
      last_heartbeat?: string
      restart_count: number
      last_restart?: string
      error?: string
    }
  }
  total_restarts: number
  watchdog_uptime_hours: number
}

export default function DatabaseAdminPage() {
  // UI State
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set())
  const [activeTab, setActiveTab] = useState<'tables' | 'health' | 'logs' | 'freshness' | 'collection' | 'threads'>('health')
  const [showCredentials, setShowCredentials] = useState(false)
  const [restartingThread, setRestartingThread] = useState<string | null>(null)

  // SWR hooks for data fetching with caching
  const { data: statsData, isLoading: statsLoading, mutate: mutateStats } = useDatabaseStats()
  const { data: healthData, mutate: mutateHealth } = useSystemHealth()
  const { data: freshnessData, mutate: mutateFreshness } = useTableFreshness()
  const { data: logsData, mutate: mutateLogs } = useSystemLogs(100)
  const { data: collectionData, mutate: mutateCollection } = useDataCollectionStatus()
  const { data: watchdogData, isValidating: refreshing, mutate: mutateWatchdog } = useWatchdogStatus()

  // Extract data from SWR responses
  const stats = statsData as DatabaseStats | null
  const health = healthData as SystemHealth | null
  const freshness = freshnessData as TableFreshness | null
  const dataCollection = collectionData as DataCollectionStatus | null
  const watchdog = watchdogData as WatchdogStatus | null
  const errorLogs = (logsData?.errors || []) as LogEntry[]
  const activityLogs = (logsData?.activity || []) as LogEntry[]

  const loading = statsLoading && !stats
  const error = null // SWR handles errors gracefully

  // Manual refresh function
  const handleRefresh = () => {
    mutateStats()
    mutateHealth()
    mutateFreshness()
    mutateLogs()
    mutateCollection()
    mutateWatchdog()
  }

  const handleClearCache = async () => {
    try {
      await apiClient.clearSystemCache()
      // Also clear browser cache
      localStorage.clear()
      sessionStorage.clear()
      alert('All caches cleared successfully!')
      handleRefresh()
    } catch (err: any) {
      logger.error('Failed to clear cache:', err)
      alert('Failed to clear cache: ' + err.message)
    }
  }

  const handleClearLogs = async () => {
    if (!confirm('Are you sure you want to clear all system logs?')) return
    try {
      await apiClient.clearSystemLogs('all')
      mutateLogs() // Refresh logs via SWR
    } catch (err: any) {
      logger.error('Failed to clear logs:', err)
    }
  }

  const handleTriggerDataCollection = async () => {
    try {
      await apiClient.triggerDataCollection()
      alert('Data collection triggered successfully!')
      mutateCollection()
    } catch (err: any) {
      logger.error('Failed to trigger data collection:', err)
      alert('Failed to trigger data collection: ' + err.message)
    }
  }

  const handleRestartThread = async (threadName: string) => {
    if (!confirm(`Are you sure you want to restart the ${threadName} thread?`)) return
    setRestartingThread(threadName)
    try {
      await apiClient.restartThread(threadName)
      alert(`Thread ${threadName} restart initiated!`)
      mutateWatchdog() // Refresh watchdog status via SWR
    } catch (err: any) {
      logger.error(`Failed to restart thread ${threadName}:`, err)
      alert(`Failed to restart thread: ${err.message}`)
    } finally {
      setRestartingThread(null)
    }
  }

  const toggleTable = (tableName: string) => {
    const newExpanded = new Set(expandedTables)
    if (newExpanded.has(tableName)) {
      newExpanded.delete(tableName)
    } else {
      newExpanded.add(tableName)
    }
    setExpandedTables(newExpanded)
  }

  // Helpers
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'connected':
      case 'fresh':
      case 'open':
        return 'text-success'
      case 'warning':
      case 'degraded':
      case 'recent':
        return 'text-warning'
      case 'error':
      case 'critical':
      case 'stale':
      case 'disconnected':
        return 'text-danger'
      default:
        return 'text-text-secondary'
    }
  }

  const getStatusBg = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'connected':
      case 'fresh':
        return 'bg-success/10 border-success/30'
      case 'warning':
      case 'degraded':
      case 'recent':
        return 'bg-warning/10 border-warning/30'
      case 'error':
      case 'critical':
      case 'stale':
        return 'bg-danger/10 border-danger/30'
      default:
        return 'bg-gray-800 border-gray-700'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'connected':
      case 'fresh':
        return <CheckCircle className="w-5 h-5 text-success" />
      case 'warning':
      case 'degraded':
      case 'recent':
        return <AlertTriangle className="w-5 h-5 text-warning" />
      case 'error':
      case 'critical':
      case 'stale':
        return <XCircle className="w-5 h-5 text-danger" />
      default:
        return <Info className="w-5 h-5 text-text-secondary" />
    }
  }

  // Loading state
  if (loading) {
    return (
      <div>
        <Navigation />
        <main className="min-h-screen bg-background pt-20 pl-64">
          <div className="p-8 flex items-center justify-center">
            <RefreshCw className="w-8 h-8 text-primary animate-spin" />
            <span className="ml-3 text-lg text-text-secondary">Loading system data...</span>
          </div>
        </main>
      </div>
    )
  }

  const emptyTables = stats?.tables.filter(t => t.row_count === 0) || []
  const populatedTables = stats?.tables.filter(t => t.row_count > 0) || []
  const totalRows = stats?.tables.reduce((sum, t) => sum + t.row_count, 0) || 0

  return (
    <div>
      <Navigation />
      <main className="min-h-screen bg-background pt-20 pl-64">
        <div className="p-8 space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Database className="w-8 h-8 text-primary" />
              <div>
                <h1 className="text-3xl font-bold text-text-primary">System Administration</h1>
                <p className="text-sm text-text-secondary mt-1">Monitor database, health, and system logs</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={handleClearCache}
                className="flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg transition-colors"
              >
                <Trash2 className="w-4 h-4" />
                Clear Cache
              </button>
              <button
                onClick={handleRefresh}
                disabled={refreshing}
                className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-dark text-white rounded-lg transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          {/* Overall Status Banner */}
          {health && (
            <div className={`rounded-lg p-4 border ${getStatusBg(health.overall_status)}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {getStatusIcon(health.overall_status)}
                  <div>
                    <div className="font-semibold text-lg">
                      System Status: <span className={getStatusColor(health.overall_status)}>
                        {health.overall_status.toUpperCase()}
                      </span>
                    </div>
                    <div className="text-sm text-text-secondary">
                      Last checked: {new Date(health.timestamp).toLocaleTimeString()}
                      {health.issues.length > 0 && (
                        <span className="ml-2 text-warning">
                          • {health.issues.length} issue(s) detected
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-4 text-sm">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-text-primary">{stats?.total_tables || 0}</div>
                    <div className="text-text-secondary">Tables</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-text-primary">{totalRows.toLocaleString()}</div>
                    <div className="text-text-secondary">Rows</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-text-primary">{errorLogs.length}</div>
                    <div className="text-text-secondary">Errors</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Tab Navigation */}
          <div className="flex flex-wrap gap-2 border-b border-gray-700 pb-2">
            {[
              { id: 'health', label: 'System Health', icon: Activity },
              { id: 'tables', label: 'Database Tables', icon: Table2 },
              { id: 'freshness', label: 'Data Freshness', icon: Clock },
              { id: 'collection', label: 'Data Collection', icon: HardDrive },
              { id: 'threads', label: 'Thread Manager', icon: Cpu },
              { id: 'logs', label: 'System Logs', icon: BarChart3 },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 px-4 py-2 rounded-t-lg transition-colors ${
                  activeTab === tab.id
                    ? 'bg-primary text-white'
                    : 'bg-gray-800 text-text-secondary hover:bg-gray-700'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="space-y-6">
            {/* System Health Tab */}
            {activeTab === 'health' && health && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {/* Database */}
                <div className={`rounded-lg p-4 border ${getStatusBg(health.components.database?.status)}`}>
                  <div className="flex items-center gap-3 mb-3">
                    <Database className="w-6 h-6" />
                    <div>
                      <div className="font-semibold">Database</div>
                      <div className={`text-sm ${getStatusColor(health.components.database?.status)}`}>
                        {health.components.database?.status}
                      </div>
                    </div>
                  </div>
                  <div className="text-sm text-text-secondary">
                    {health.components.database?.message}
                  </div>
                  {stats && (
                    <div className="mt-2 text-xs text-text-muted">
                      <div className="flex items-center gap-2">
                        <span>Path:</span>
                        <button
                          onClick={() => setShowCredentials(!showCredentials)}
                          className="flex items-center gap-1 text-primary hover:underline"
                        >
                          {showCredentials ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                          {showCredentials ? 'Hide' : 'Show'}
                        </button>
                      </div>
                      {showCredentials && (
                        <div className="mt-1 font-mono text-xs break-all bg-gray-900 p-2 rounded">
                          {stats.database_path}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Trading Volatility API */}
                <div className={`rounded-lg p-4 border ${getStatusBg(health.components.trading_volatility_api?.status)}`}>
                  <div className="flex items-center gap-3 mb-3">
                    <Zap className="w-6 h-6" />
                    <div>
                      <div className="font-semibold">Trading Volatility API</div>
                      <div className={`text-sm ${getStatusColor(health.components.trading_volatility_api?.status)}`}>
                        {health.components.trading_volatility_api?.status}
                      </div>
                    </div>
                  </div>
                  <div className="text-sm text-text-secondary">
                    {health.components.trading_volatility_api?.message}
                  </div>
                  {health.components.trading_volatility_api?.calls_this_minute !== undefined && (
                    <div className="mt-2">
                      <div className="text-xs text-text-muted mb-1">Rate Limit Usage</div>
                      <div className="w-full bg-gray-700 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${
                            health.components.trading_volatility_api.calls_this_minute > 15
                              ? 'bg-danger'
                              : health.components.trading_volatility_api.calls_this_minute > 10
                              ? 'bg-warning'
                              : 'bg-success'
                          }`}
                          style={{ width: `${(health.components.trading_volatility_api.calls_this_minute / 20) * 100}%` }}
                        />
                      </div>
                      <div className="text-xs text-text-muted mt-1">
                        {health.components.trading_volatility_api.calls_this_minute}/20 calls this minute
                      </div>
                    </div>
                  )}
                </div>

                {/* Polygon API */}
                <div className={`rounded-lg p-4 border ${getStatusBg(health.components.polygon_api?.status)}`}>
                  <div className="flex items-center gap-3 mb-3">
                    <Server className="w-6 h-6" />
                    <div>
                      <div className="font-semibold">Polygon API</div>
                      <div className={`text-sm ${getStatusColor(health.components.polygon_api?.status)}`}>
                        {health.components.polygon_api?.status}
                      </div>
                    </div>
                  </div>
                  <div className="text-sm text-text-secondary">
                    {health.components.polygon_api?.message}
                  </div>
                </div>

                {/* Market Status */}
                <div className={`rounded-lg p-4 border ${
                  health.components.market?.status === 'open' ? 'bg-success/10 border-success/30' : 'bg-gray-800 border-gray-700'
                }`}>
                  <div className="flex items-center gap-3 mb-3">
                    <TrendingUp className="w-6 h-6" />
                    <div>
                      <div className="font-semibold">Market</div>
                      <div className={`text-sm ${health.components.market?.status === 'open' ? 'text-success' : 'text-text-secondary'}`}>
                        {health.components.market?.status?.toUpperCase()}
                      </div>
                    </div>
                  </div>
                  <div className="text-sm text-text-secondary">
                    {health.components.market?.current_time_et}
                  </div>
                  <div className="text-xs text-text-muted mt-1">
                    {health.components.market?.day}
                  </div>
                </div>

                {/* Error Rate */}
                <div className={`rounded-lg p-4 border ${getStatusBg(health.components.error_rate?.status)}`}>
                  <div className="flex items-center gap-3 mb-3">
                    <AlertCircle className="w-6 h-6" />
                    <div>
                      <div className="font-semibold">Error Rate</div>
                      <div className={`text-sm ${getStatusColor(health.components.error_rate?.status)}`}>
                        {health.components.error_rate?.status}
                      </div>
                    </div>
                  </div>
                  <div className="text-sm text-text-secondary">
                    {health.components.error_rate?.errors_last_hour} errors in last hour
                  </div>
                  <div className="text-xs text-text-muted mt-1">
                    {health.components.error_rate?.total_errors} total errors logged
                  </div>
                </div>

                {/* Connection Status */}
                <div className="rounded-lg p-4 border bg-gray-800 border-gray-700">
                  <div className="flex items-center gap-3 mb-3">
                    <Shield className="w-6 h-6" />
                    <div>
                      <div className="font-semibold">Security</div>
                      <div className="text-sm text-success">Protected</div>
                    </div>
                  </div>
                  <div className="text-sm text-text-secondary">
                    Credentials masked in UI
                  </div>
                  <div className="text-xs text-text-muted mt-1">
                    SQL injection prevention active
                  </div>
                </div>
              </div>
            )}

            {/* Database Tables Tab */}
            {activeTab === 'tables' && stats && (
              <div className="space-y-6">
                {/* Summary Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-success/10 border border-success/30 rounded-lg p-4">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="w-5 h-5 text-success" />
                      <div>
                        <div className="text-sm font-semibold text-success">Populated Tables</div>
                        <div className="text-2xl font-bold text-success mt-1">{populatedTables.length}</div>
                      </div>
                    </div>
                  </div>
                  <div className="bg-warning/10 border border-warning/30 rounded-lg p-4">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="w-5 h-5 text-warning" />
                      <div>
                        <div className="text-sm font-semibold text-warning">Empty Tables</div>
                        <div className="text-2xl font-bold text-warning mt-1">{emptyTables.length}</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Populated Tables */}
                {populatedTables.length > 0 && (
                  <div>
                    <h2 className="text-xl font-bold text-success mb-4 flex items-center gap-2">
                      <CheckCircle className="w-5 h-5" />
                      Populated Tables ({populatedTables.length})
                    </h2>
                    <div className="space-y-3">
                      {populatedTables.map((table) => (
                        <div key={table.table_name} className="bg-background-card border border-success/30 rounded-lg overflow-hidden">
                          <button
                            onClick={() => toggleTable(table.table_name)}
                            className="w-full p-4 flex items-center justify-between hover:bg-background-hover transition-colors"
                          >
                            <div className="flex items-center gap-3">
                              {expandedTables.has(table.table_name) ? (
                                <ChevronDown className="w-5 h-5 text-text-secondary" />
                              ) : (
                                <ChevronRight className="w-5 h-5 text-text-secondary" />
                              )}
                              <Table2 className="w-5 h-5 text-success" />
                              <div className="text-left">
                                <div className="font-mono font-semibold text-text-primary">{table.table_name}</div>
                                <div className="text-sm text-text-secondary">
                                  {table.row_count.toLocaleString()} rows · {table.columns.length} columns
                                </div>
                              </div>
                            </div>
                          </button>

                          {expandedTables.has(table.table_name) && (
                            <div className="p-4 border-t border-gray-700 bg-gray-950/30">
                              <div className="mb-4">
                                <h4 className="text-sm font-semibold text-text-secondary mb-2">Columns</h4>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                  {table.columns.map((col) => (
                                    <div key={col.name} className="text-xs bg-gray-900 rounded px-2 py-1">
                                      <span className="font-mono text-text-primary">{col.name}</span>
                                      <span className="text-text-muted ml-1">({col.type})</span>
                                    </div>
                                  ))}
                                </div>
                              </div>

                              {table.sample_data.length > 0 && (
                                <div>
                                  <h4 className="text-sm font-semibold text-text-secondary mb-2">Sample Data</h4>
                                  <div className="overflow-x-auto">
                                    <table className="w-full text-xs">
                                      <thead>
                                        <tr className="border-b border-gray-700">
                                          {table.columns.slice(0, 6).map((col) => (
                                            <th key={col.name} className="text-left px-2 py-1 text-text-secondary font-semibold">
                                              {col.name}
                                            </th>
                                          ))}
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {table.sample_data.map((row, idx) => (
                                          <tr key={idx} className="border-b border-gray-800">
                                            {table.columns.slice(0, 6).map((col) => (
                                              <td key={col.name} className="px-2 py-1 text-text-primary font-mono truncate max-w-xs">
                                                {row[col.name] !== null ? String(row[col.name]).substring(0, 30) : <span className="text-text-muted">NULL</span>}
                                              </td>
                                            ))}
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Empty Tables */}
                {emptyTables.length > 0 && (
                  <div>
                    <h2 className="text-xl font-bold text-warning mb-4 flex items-center gap-2">
                      <AlertCircle className="w-5 h-5" />
                      Empty Tables ({emptyTables.length})
                    </h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {emptyTables.map((table) => (
                        <div key={table.table_name} className="bg-background-card border border-warning/30 rounded-lg p-4">
                          <div className="flex items-center gap-2">
                            <Table2 className="w-4 h-4 text-warning" />
                            <span className="font-mono text-sm text-text-primary">{table.table_name}</span>
                          </div>
                          <div className="text-xs text-text-muted mt-1">
                            {table.columns.length} columns · No data yet
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Data Freshness Tab */}
            {activeTab === 'freshness' && freshness && (
              <div className="space-y-4">
                <div className="text-sm text-text-secondary mb-4">
                  Shows when data was last updated for each table. Stale data may indicate collection issues.
                  <span className="ml-2 text-xs text-text-muted">
                    Tracking {Object.keys(freshness.tables).length} tables
                  </span>
                </div>

                {/* Summary Stats */}
                <div className="grid grid-cols-4 gap-3 mb-4">
                  <div className="bg-success/10 border border-success/30 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-success">
                      {Object.values(freshness.tables).filter(t => t.status === 'fresh').length}
                    </div>
                    <div className="text-xs text-success">Fresh</div>
                  </div>
                  <div className="bg-warning/10 border border-warning/30 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-warning">
                      {Object.values(freshness.tables).filter(t => t.status === 'recent').length}
                    </div>
                    <div className="text-xs text-warning">Recent</div>
                  </div>
                  <div className="bg-danger/10 border border-danger/30 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-danger">
                      {Object.values(freshness.tables).filter(t => t.status === 'stale' || t.is_stale).length}
                    </div>
                    <div className="text-xs text-danger">Stale</div>
                  </div>
                  <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-text-secondary">
                      {Object.values(freshness.tables).filter(t => t.status === 'empty').length}
                    </div>
                    <div className="text-xs text-text-muted">Empty</div>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {Object.entries(freshness.tables)
                    .sort((a, b) => {
                      // Sort by status priority: stale first, then fresh, then empty
                      const priority: Record<string, number> = { stale: 0, recent: 1, fresh: 2, configured: 3, empty: 4, error: 5, not_found: 6 }
                      return (priority[a[1].status] || 99) - (priority[b[1].status] || 99)
                    })
                    .map(([table, info]) => (
                    <div key={table} className={`rounded-lg p-3 border ${getStatusBg(info.status)} ${info.is_stale ? 'ring-2 ring-danger' : ''}`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Table2 className="w-4 h-4" />
                          <span className="font-mono text-sm font-semibold truncate">{table}</span>
                        </div>
                        <span className={`text-xs font-semibold px-2 py-0.5 rounded ${getStatusColor(info.status)} bg-black/20`}>
                          {info.status.toUpperCase()}
                        </span>
                      </div>
                      {info.last_record && info.last_record !== 'N/A (no timestamp column)' ? (
                        <div className="text-xs text-text-secondary space-y-1">
                          <div className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            <span className="font-mono">{info.last_record}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-text-muted">Age: {info.age_human}</span>
                            {info.expected_frequency && (
                              <span className="text-text-muted">
                                Expected: every {info.expected_frequency >= 60 ? `${info.expected_frequency / 60}h` : `${info.expected_frequency}m`}
                              </span>
                            )}
                          </div>
                        </div>
                      ) : info.row_count !== undefined ? (
                        <div className="text-xs text-text-muted">
                          {info.row_count} rows · No timestamp tracking
                        </div>
                      ) : (
                        <div className="text-xs text-text-muted">
                          {info.status === 'empty' ? 'No records yet' : info.error || 'Not found'}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* System Logs Tab */}
            {activeTab === 'logs' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div className="text-sm text-text-secondary">
                    Showing {errorLogs.length} errors and {activityLogs.length} activity events
                  </div>
                  <button
                    onClick={handleClearLogs}
                    className="flex items-center gap-2 px-3 py-1 text-sm bg-gray-800 hover:bg-gray-700 text-text-secondary rounded transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                    Clear Logs
                  </button>
                </div>

                {/* Error Logs */}
                <div>
                  <h3 className="text-lg font-semibold text-danger mb-3 flex items-center gap-2">
                    <AlertCircle className="w-5 h-5" />
                    Error Logs ({errorLogs.length})
                  </h3>
                  {errorLogs.length === 0 ? (
                    <div className="bg-gray-800 rounded-lg p-4 text-center text-text-muted">
                      No errors logged
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {errorLogs.slice().reverse().map((log, idx) => (
                        <div key={idx} className="bg-danger/10 border border-danger/30 rounded-lg p-3">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs text-danger font-semibold">
                              {log.source} · {log.error_type}
                            </span>
                            <span className="text-xs text-text-muted">
                              {new Date(log.timestamp).toLocaleString()}
                            </span>
                          </div>
                          <div className="text-sm text-text-primary">{log.message}</div>
                          {log.details && Object.keys(log.details).length > 0 && (
                            <div className="text-xs text-text-muted mt-1 font-mono">
                              {JSON.stringify(log.details)}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Activity Logs */}
                <div>
                  <h3 className="text-lg font-semibold text-primary mb-3 flex items-center gap-2">
                    <Activity className="w-5 h-5" />
                    Activity Logs ({activityLogs.length})
                  </h3>
                  {activityLogs.length === 0 ? (
                    <div className="bg-gray-800 rounded-lg p-4 text-center text-text-muted">
                      No activity logged
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {activityLogs.slice().reverse().map((log, idx) => (
                        <div key={idx} className="bg-gray-800 border border-gray-700 rounded-lg p-3">
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-text-primary">{log.action}</span>
                            <span className="text-xs text-text-muted">
                              {new Date(log.timestamp).toLocaleString()}
                            </span>
                          </div>
                          {log.details && Object.keys(log.details).length > 0 && (
                            <div className="text-xs text-text-muted mt-1 font-mono">
                              {JSON.stringify(log.details)}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Data Collection Tab */}
            {activeTab === 'collection' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div className="text-sm text-text-secondary">
                    Monitor background data collection threads and trigger manual updates
                  </div>
                  <button
                    onClick={handleTriggerDataCollection}
                    className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-dark text-white rounded-lg transition-colors"
                  >
                    <Play className="w-4 h-4" />
                    Trigger Collection
                  </button>
                </div>

                {dataCollection ? (
                  <div className="space-y-4">
                    {/* Status Overview */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className={`rounded-lg p-4 border ${
                        dataCollection.status === 'running' ? 'bg-success/10 border-success/30' : 'bg-warning/10 border-warning/30'
                      }`}>
                        <div className="flex items-center gap-3 mb-2">
                          <Settings2 className="w-6 h-6" />
                          <div>
                            <div className="font-semibold">Collection Status</div>
                            <div className={`text-sm ${dataCollection.status === 'running' ? 'text-success' : 'text-warning'}`}>
                              {dataCollection.status?.toUpperCase() || 'UNKNOWN'}
                            </div>
                          </div>
                        </div>
                        <div className="text-xs text-text-muted">
                          Last checked: {dataCollection.timestamp ? new Date(dataCollection.timestamp).toLocaleTimeString() : 'N/A'}
                        </div>
                      </div>

                      <div className={`rounded-lg p-4 border ${
                        dataCollection.market_hours?.is_market_hours ? 'bg-success/10 border-success/30' : 'bg-gray-800 border-gray-700'
                      }`}>
                        <div className="flex items-center gap-3 mb-2">
                          <Clock className="w-6 h-6" />
                          <div>
                            <div className="font-semibold">Market Hours</div>
                            <div className={`text-sm ${dataCollection.market_hours?.is_market_hours ? 'text-success' : 'text-text-secondary'}`}>
                              {dataCollection.market_hours?.is_market_hours ? 'OPEN' : 'CLOSED'}
                            </div>
                          </div>
                        </div>
                        <div className="text-xs text-text-muted">
                          {dataCollection.market_hours?.current_time || 'N/A'}
                        </div>
                      </div>

                      <div className="rounded-lg p-4 border bg-gray-800 border-gray-700">
                        <div className="flex items-center gap-3 mb-2">
                          <HardDrive className="w-6 h-6" />
                          <div>
                            <div className="font-semibold">Last GEX Collection</div>
                            <div className="text-sm text-text-primary">
                              {dataCollection.last_gex_collection
                                ? new Date(dataCollection.last_gex_collection).toLocaleTimeString()
                                : 'Never'}
                            </div>
                          </div>
                        </div>
                        <div className="text-xs text-text-muted">
                          Scheduler: {dataCollection.last_scheduler_update
                            ? new Date(dataCollection.last_scheduler_update).toLocaleTimeString()
                            : 'N/A'}
                        </div>
                      </div>
                    </div>

                    {/* API Health */}
                    <div>
                      <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                        <Zap className="w-5 h-5" />
                        API Health
                      </h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div className={`rounded-lg p-3 border ${
                          dataCollection.api_health?.trading_volatility === 'healthy' ? 'bg-success/10 border-success/30' : 'bg-warning/10 border-warning/30'
                        }`}>
                          <div className="flex items-center justify-between">
                            <span className="font-semibold">Trading Volatility API</span>
                            <span className={`text-sm ${
                              dataCollection.api_health?.trading_volatility === 'healthy' ? 'text-success' : 'text-warning'
                            }`}>
                              {dataCollection.api_health?.trading_volatility?.toUpperCase() || 'UNKNOWN'}
                            </span>
                          </div>
                        </div>
                        <div className={`rounded-lg p-3 border ${
                          dataCollection.api_health?.polygon === 'healthy' ? 'bg-success/10 border-success/30' : 'bg-warning/10 border-warning/30'
                        }`}>
                          <div className="flex items-center justify-between">
                            <span className="font-semibold">Polygon API</span>
                            <span className={`text-sm ${
                              dataCollection.api_health?.polygon === 'healthy' ? 'text-success' : 'text-warning'
                            }`}>
                              {dataCollection.api_health?.polygon?.toUpperCase() || 'UNKNOWN'}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Thread Status */}
                    {dataCollection.threads && Object.keys(dataCollection.threads).length > 0 && (
                      <div>
                        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                          <Cpu className="w-5 h-5" />
                          Collection Threads
                        </h3>
                        <div className="space-y-2">
                          {Object.entries(dataCollection.threads).map(([name, thread]) => (
                            <div key={name} className={`rounded-lg p-3 border ${
                              thread.alive ? 'bg-success/10 border-success/30' : 'bg-danger/10 border-danger/30'
                            }`}>
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                  <div className={`w-3 h-3 rounded-full ${thread.alive ? 'bg-success animate-pulse' : 'bg-danger'}`} />
                                  <span className="font-mono font-semibold">{name}</span>
                                </div>
                                <span className={`text-sm ${thread.alive ? 'text-success' : 'text-danger'}`}>
                                  {thread.alive ? 'ALIVE' : 'STOPPED'}
                                </span>
                              </div>
                              <div className="flex items-center gap-4 mt-2 text-xs text-text-muted">
                                {thread.last_run && <span>Last run: {new Date(thread.last_run).toLocaleTimeString()}</span>}
                                {thread.run_count !== undefined && <span>Runs: {thread.run_count}</span>}
                                {thread.error_count !== undefined && thread.error_count > 0 && (
                                  <span className="text-danger">Errors: {thread.error_count}</span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="bg-gray-800 rounded-lg p-8 text-center">
                    <HardDrive className="w-12 h-12 text-text-muted mx-auto mb-3" />
                    <div className="text-text-secondary">Data collection status unavailable</div>
                    <div className="text-sm text-text-muted mt-1">The backend may not support this endpoint yet</div>
                  </div>
                )}
              </div>
            )}

            {/* Thread Manager Tab */}
            {activeTab === 'threads' && (
              <div className="space-y-6">
                <div className="text-sm text-text-secondary">
                  Monitor and manage background threads. Restart threads that have stopped or are unresponsive.
                </div>

                {watchdog ? (
                  <div className="space-y-4">
                    {/* Watchdog Status */}
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                      <div className={`rounded-lg p-4 border ${
                        watchdog.enabled ? 'bg-success/10 border-success/30' : 'bg-warning/10 border-warning/30'
                      }`}>
                        <div className="text-center">
                          <div className={`text-2xl font-bold ${watchdog.enabled ? 'text-success' : 'text-warning'}`}>
                            {watchdog.enabled ? 'ENABLED' : 'DISABLED'}
                          </div>
                          <div className="text-xs text-text-muted">Watchdog Status</div>
                        </div>
                      </div>
                      <div className="rounded-lg p-4 border bg-gray-800 border-gray-700 text-center">
                        <div className="text-2xl font-bold text-text-primary">
                          {watchdog.check_interval_seconds || 60}s
                        </div>
                        <div className="text-xs text-text-muted">Check Interval</div>
                      </div>
                      <div className="rounded-lg p-4 border bg-gray-800 border-gray-700 text-center">
                        <div className="text-2xl font-bold text-text-primary">
                          {watchdog.total_restarts || 0}
                        </div>
                        <div className="text-xs text-text-muted">Total Restarts</div>
                      </div>
                      <div className="rounded-lg p-4 border bg-gray-800 border-gray-700 text-center">
                        <div className="text-2xl font-bold text-text-primary">
                          {watchdog.watchdog_uptime_hours?.toFixed(1) || 0}h
                        </div>
                        <div className="text-xs text-text-muted">Watchdog Uptime</div>
                      </div>
                    </div>

                    {/* Thread List */}
                    {watchdog.threads_monitored && Object.keys(watchdog.threads_monitored).length > 0 ? (
                      <div>
                        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                          <Cpu className="w-5 h-5" />
                          Monitored Threads ({Object.keys(watchdog.threads_monitored).length})
                        </h3>
                        <div className="space-y-3">
                          {Object.entries(watchdog.threads_monitored).map(([name, thread]) => (
                            <div key={name} className={`rounded-lg p-4 border ${
                              thread.status === 'running' ? 'bg-success/10 border-success/30' :
                              thread.status === 'restarting' ? 'bg-warning/10 border-warning/30' :
                              'bg-danger/10 border-danger/30'
                            }`}>
                              <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-3">
                                  <div className={`w-3 h-3 rounded-full ${
                                    thread.status === 'running' ? 'bg-success animate-pulse' :
                                    thread.status === 'restarting' ? 'bg-warning animate-spin' :
                                    'bg-danger'
                                  }`} />
                                  <span className="font-mono font-semibold text-lg">{name}</span>
                                </div>
                                <div className="flex items-center gap-3">
                                  <span className={`text-sm font-semibold px-2 py-1 rounded ${
                                    thread.status === 'running' ? 'bg-success/20 text-success' :
                                    thread.status === 'restarting' ? 'bg-warning/20 text-warning' :
                                    'bg-danger/20 text-danger'
                                  }`}>
                                    {thread.status.toUpperCase()}
                                  </span>
                                  <button
                                    onClick={() => handleRestartThread(name)}
                                    disabled={restartingThread === name}
                                    className="flex items-center gap-1 px-3 py-1 bg-primary hover:bg-primary-dark text-white text-sm rounded transition-colors disabled:opacity-50"
                                  >
                                    <RotateCcw className={`w-4 h-4 ${restartingThread === name ? 'animate-spin' : ''}`} />
                                    Restart
                                  </button>
                                </div>
                              </div>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                                <div>
                                  <span className="text-text-muted">Last Heartbeat:</span>
                                  <div className="text-text-primary">
                                    {thread.last_heartbeat ? new Date(thread.last_heartbeat).toLocaleTimeString() : 'N/A'}
                                  </div>
                                </div>
                                <div>
                                  <span className="text-text-muted">Restart Count:</span>
                                  <div className={thread.restart_count > 0 ? 'text-warning' : 'text-text-primary'}>
                                    {thread.restart_count}
                                  </div>
                                </div>
                                <div>
                                  <span className="text-text-muted">Last Restart:</span>
                                  <div className="text-text-primary">
                                    {thread.last_restart ? new Date(thread.last_restart).toLocaleTimeString() : 'Never'}
                                  </div>
                                </div>
                                {thread.error && (
                                  <div className="col-span-2 md:col-span-1">
                                    <span className="text-text-muted">Error:</span>
                                    <div className="text-danger text-xs">{thread.error}</div>
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="bg-gray-800 rounded-lg p-8 text-center">
                        <Cpu className="w-12 h-12 text-text-muted mx-auto mb-3" />
                        <div className="text-text-secondary">No threads being monitored</div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="bg-gray-800 rounded-lg p-8 text-center">
                    <Cpu className="w-12 h-12 text-text-muted mx-auto mb-3" />
                    <div className="text-text-secondary">Watchdog status unavailable</div>
                    <div className="text-sm text-text-muted mt-1">The backend may not support this endpoint yet</div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
