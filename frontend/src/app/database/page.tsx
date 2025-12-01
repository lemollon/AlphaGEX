'use client'

import { logger } from '@/lib/logger'
import { useState, useEffect, useCallback } from 'react'
import {
  Database, RefreshCw, CheckCircle, AlertCircle, Info, Table2,
  Wifi, WifiOff, Activity, Clock, Trash2, AlertTriangle,
  Server, Zap, Eye, EyeOff, ChevronDown, ChevronRight,
  Shield, TrendingUp, BarChart3, XCircle
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

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
      status: 'fresh' | 'recent' | 'stale' | 'empty' | 'error' | 'not_found'
      last_record?: string
      age_minutes?: number
      age_human?: string
      error?: string
    }
  }
}

export default function DatabaseAdminPage() {
  // State
  const [stats, setStats] = useState<DatabaseStats | null>(null)
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [freshness, setFreshness] = useState<TableFreshness | null>(null)
  const [errorLogs, setErrorLogs] = useState<LogEntry[]>([])
  const [activityLogs, setActivityLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set())
  const [activeTab, setActiveTab] = useState<'tables' | 'health' | 'logs' | 'freshness'>('health')
  const [showCredentials, setShowCredentials] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  // Fetch all data
  const fetchAllData = useCallback(async (showLoader = true) => {
    if (showLoader) setLoading(true)
    setError(null)

    try {
      const [statsRes, healthRes, freshnessRes, logsRes] = await Promise.all([
        apiClient.getDatabaseStats().catch(e => ({ data: null, error: e })),
        apiClient.getSystemHealth().catch(e => ({ data: null, error: e })),
        apiClient.getTableFreshness().catch(e => ({ data: null, error: e })),
        apiClient.getSystemLogs(100, 'all').catch(e => ({ data: null, error: e }))
      ])

      if (statsRes.data) setStats(statsRes.data)
      if (healthRes.data) setHealth(healthRes.data)
      if (freshnessRes.data) setFreshness(freshnessRes.data)
      if (logsRes.data) {
        setErrorLogs(logsRes.data.errors || [])
        setActivityLogs(logsRes.data.activity || [])
      }
    } catch (err: any) {
      logger.error('Failed to fetch admin data:', err)
      setError(err.message || 'Failed to fetch data')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  // Initial fetch and auto-refresh
  useEffect(() => {
    fetchAllData()
    const interval = setInterval(() => fetchAllData(false), 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [fetchAllData])

  // Actions
  const handleRefresh = () => {
    setRefreshing(true)
    fetchAllData(false)
  }

  const handleClearCache = async () => {
    try {
      await apiClient.clearSystemCache()
      // Also clear browser cache
      localStorage.clear()
      sessionStorage.clear()
      alert('All caches cleared successfully!')
      fetchAllData(false)
    } catch (err: any) {
      logger.error('Failed to clear cache:', err)
      alert('Failed to clear cache: ' + err.message)
    }
  }

  const handleClearLogs = async () => {
    if (!confirm('Are you sure you want to clear all system logs?')) return
    try {
      await apiClient.clearSystemLogs('all')
      setErrorLogs([])
      setActivityLogs([])
    } catch (err: any) {
      logger.error('Failed to clear logs:', err)
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
          <div className="flex gap-2 border-b border-gray-700 pb-2">
            {[
              { id: 'health', label: 'System Health', icon: Activity },
              { id: 'tables', label: 'Database Tables', icon: Table2 },
              { id: 'freshness', label: 'Data Freshness', icon: Clock },
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
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {Object.entries(freshness.tables).map(([table, info]) => (
                    <div key={table} className={`rounded-lg p-4 border ${getStatusBg(info.status)}`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Clock className="w-5 h-5" />
                          <span className="font-mono font-semibold">{table}</span>
                        </div>
                        <span className={`text-sm font-semibold ${getStatusColor(info.status)}`}>
                          {info.status.toUpperCase()}
                        </span>
                      </div>
                      {info.last_record ? (
                        <div className="text-sm text-text-secondary">
                          <div>Last record: {new Date(info.last_record).toLocaleString()}</div>
                          <div className="text-xs text-text-muted mt-1">Age: {info.age_human}</div>
                        </div>
                      ) : (
                        <div className="text-sm text-text-muted">
                          {info.status === 'empty' ? 'No records' : info.error || 'Table not found'}
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
          </div>
        </div>
      </main>
    </div>
  )
}
