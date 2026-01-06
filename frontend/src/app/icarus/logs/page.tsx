'use client'

import { useState, useEffect } from 'react'
import { Activity, AlertTriangle, Info, Bug, RefreshCw, ChevronDown, ChevronUp, Filter, Flame } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

interface LogEntry {
  id: number
  created_at: string
  level: string
  message: string
  details: Record<string, any> | null
}

type LogLevel = 'ALL' | 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'

export default function IcarusLogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<LogLevel>('ALL')
  const [limit, setLimit] = useState(100)
  const [expandedLogs, setExpandedLogs] = useState<Set<number>>(new Set())
  const [autoRefresh, setAutoRefresh] = useState(true)

  const fetchLogs = async () => {
    try {
      setLoading(true)
      const levelFilter = filter === 'ALL' ? undefined : filter
      const res = await apiClient.getICARUSLogs(levelFilter, limit)
      if (res.data?.data) {
        setLogs(res.data.data)
      }
      setError(null)
    } catch (err) {
      setError('Failed to fetch logs')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLogs()
    if (autoRefresh) {
      const interval = setInterval(fetchLogs, 10000) // Refresh every 10s
      return () => clearInterval(interval)
    }
  }, [filter, limit, autoRefresh])

  const toggleExpand = (id: number) => {
    setExpandedLogs(prev => {
      const newSet = new Set(prev)
      if (newSet.has(id)) {
        newSet.delete(id)
      } else {
        newSet.add(id)
      }
      return newSet
    })
  }

  const getLevelIcon = (level: string) => {
    switch (level) {
      case 'ERROR':
        return <AlertTriangle className="w-4 h-4 text-red-500" />
      case 'WARNING':
        return <AlertTriangle className="w-4 h-4 text-yellow-500" />
      case 'INFO':
        return <Info className="w-4 h-4 text-orange-500" />
      case 'DEBUG':
        return <Bug className="w-4 h-4 text-gray-500" />
      default:
        return <Activity className="w-4 h-4 text-gray-400" />
    }
  }

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'ERROR':
        return 'bg-red-900/30 border-red-700'
      case 'WARNING':
        return 'bg-yellow-900/30 border-yellow-700'
      case 'INFO':
        return 'bg-orange-900/20 border-orange-800'
      case 'DEBUG':
        return 'bg-gray-800 border-gray-700'
      default:
        return 'bg-gray-800 border-gray-700'
    }
  }

  const stats = {
    total: logs.length,
    errors: logs.filter(l => l.level === 'ERROR').length,
    warnings: logs.filter(l => l.level === 'WARNING').length,
    info: logs.filter(l => l.level === 'INFO').length,
  }

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />
      <main className="lg:pl-16 pt-24">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Flame className="w-8 h-8 text-orange-500" />
              <div>
                <h1 className="text-2xl font-bold text-white">ICARUS Logs</h1>
                <p className="text-gray-400 text-sm">Aggressive Directional Strategy Activity</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-sm text-gray-400">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                  className="rounded bg-gray-700 border-gray-600"
                />
                Auto-refresh
              </label>
              <button
                onClick={fetchLogs}
                className="p-2 bg-gray-800 rounded-lg hover:bg-gray-700 transition"
              >
                <RefreshCw className={`w-5 h-5 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* Stats Bar */}
          <div className="grid grid-cols-4 gap-4 mb-6">
            <div className="bg-gray-800 rounded-lg p-4 border border-orange-900">
              <p className="text-gray-400 text-sm">Total Logs</p>
              <p className="text-2xl font-bold text-orange-400">{stats.total}</p>
            </div>
            <div className="bg-gray-800 rounded-lg p-4 border border-red-900">
              <p className="text-gray-400 text-sm">Errors</p>
              <p className="text-2xl font-bold text-red-400">{stats.errors}</p>
            </div>
            <div className="bg-gray-800 rounded-lg p-4 border border-yellow-900">
              <p className="text-gray-400 text-sm">Warnings</p>
              <p className="text-2xl font-bold text-yellow-400">{stats.warnings}</p>
            </div>
            <div className="bg-gray-800 rounded-lg p-4 border border-orange-900">
              <p className="text-gray-400 text-sm">Info</p>
              <p className="text-2xl font-bold text-orange-400">{stats.info}</p>
            </div>
          </div>

          {/* Filters */}
          <div className="flex gap-4 mb-6">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-gray-400" />
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value as LogLevel)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm"
              >
                <option value="ALL">All Levels</option>
                <option value="ERROR">Errors Only</option>
                <option value="WARNING">Warnings</option>
                <option value="INFO">Info</option>
                <option value="DEBUG">Debug</option>
              </select>
            </div>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm"
            >
              <option value={50}>Last 50</option>
              <option value={100}>Last 100</option>
              <option value={200}>Last 200</option>
              <option value={500}>Last 500</option>
            </select>
          </div>

          {error && (
            <div className="bg-red-900/50 border border-red-700 rounded-lg p-4 mb-6">
              <p className="text-red-400">{error}</p>
            </div>
          )}

          {/* Logs List */}
          <div className="space-y-2">
            {logs.map((log) => (
              <div
                key={log.id}
                className={`rounded-lg border ${getLevelColor(log.level)} overflow-hidden`}
              >
                <div
                  className="flex items-center gap-3 p-3 cursor-pointer hover:bg-white/5"
                  onClick={() => log.details && toggleExpand(log.id)}
                >
                  {getLevelIcon(log.level)}
                  <span className="text-xs text-gray-500 font-mono w-36 flex-shrink-0">
                    {new Date(log.created_at).toLocaleString()}
                  </span>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                    log.level === 'ERROR' ? 'bg-red-900 text-red-300' :
                    log.level === 'WARNING' ? 'bg-yellow-900 text-yellow-300' :
                    log.level === 'INFO' ? 'bg-orange-900 text-orange-300' :
                    'bg-gray-700 text-gray-300'
                  }`}>
                    {log.level}
                  </span>
                  <span className="text-gray-200 flex-1 truncate">{log.message}</span>
                  {log.details && (
                    expandedLogs.has(log.id) ?
                      <ChevronUp className="w-4 h-4 text-gray-500" /> :
                      <ChevronDown className="w-4 h-4 text-gray-500" />
                  )}
                </div>
                {log.details && expandedLogs.has(log.id) && (
                  <div className="px-3 pb-3 pt-1 border-t border-gray-700/50">
                    <pre className="text-xs text-gray-400 bg-gray-900 rounded p-3 overflow-x-auto">
                      {JSON.stringify(log.details, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))}
            {logs.length === 0 && !loading && (
              <div className="text-center py-12 text-gray-500">
                No logs found for selected filter
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
