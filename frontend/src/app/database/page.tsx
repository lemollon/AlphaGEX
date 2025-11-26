'use client'

import { useState, useEffect } from 'react'
import { Database, RefreshCw, CheckCircle, AlertCircle, Info, Table2, FileText, Wifi, WifiOff } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

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
  total_tables: number
  tables: TableStats[]
  timestamp: string
}

interface APITestResults {
  timestamp: string
  trading_volatility: {
    status: string
    response_time_ms: number
    error: string | null
    data_quality: string | null
    test_symbol: string
    fields_received: string[]
    sample_data?: any
  }
  polygon: {
    status: string
    response_time_ms: number
    error: string | null
    data_quality: string | null
    test_symbol: string
    vix_value: number | null
    sample_data?: any
  }
  overall_status: string
}

export default function DatabaseAdminPage() {
  const [stats, setStats] = useState<DatabaseStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set())
  const [testResults, setTestResults] = useState<APITestResults | null>(null)
  const [testingAPIs, setTestingAPIs] = useState(false)
  const [showTestResults, setShowTestResults] = useState(false)

  const fetchStats = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await apiClient.getDatabaseStats()
      setStats(response.data)
    } catch (err: any) {
      setError(err.message || 'Failed to fetch database stats')
    } finally {
      setLoading(false)
    }
  }

  const testAPIConnections = async () => {
    setTestingAPIs(true)
    setShowTestResults(true)

    try {
      const response = await apiClient.testConnections()
      setTestResults(response.data.results)
    } catch (err: any) {
      setError(err.message || 'Failed to test API connections')
    } finally {
      setTestingAPIs(false)
    }
  }

  useEffect(() => {
    fetchStats()
  }, [])

  const toggleTable = (tableName: string) => {
    const newExpanded = new Set(expandedTables)
    if (newExpanded.has(tableName)) {
      newExpanded.delete(tableName)
    } else {
      newExpanded.add(tableName)
    }
    setExpandedTables(newExpanded)
  }

  if (loading) {
    return (
      <div>
        <Navigation />
        <main className="min-h-screen bg-background pt-20 pl-64">
          <div className="p-8">
            <div className="flex items-center justify-center">
              <RefreshCw className="w-8 h-8 text-primary animate-spin" />
              <span className="ml-3 text-lg text-text-secondary">Loading database stats...</span>
            </div>
          </div>
        </main>
      </div>
    )
  }

  if (error) {
    return (
      <div>
        <Navigation />
        <main className="min-h-screen bg-background pt-20 pl-64">
          <div className="p-8">
            <div className="bg-danger/10 border border-danger rounded-lg p-6">
              <div className="flex items-center gap-3">
                <AlertCircle className="w-6 h-6 text-danger" />
                <div>
                  <h3 className="text-lg font-semibold text-danger">Error Loading Database Stats</h3>
                  <p className="text-sm text-text-secondary mt-1">{error}</p>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    )
  }

  if (!stats) return null

  const emptyTables = stats.tables.filter(t => t.row_count === 0)
  const populatedTables = stats.tables.filter(t => t.row_count > 0)
  const totalRows = stats.tables.reduce((sum, t) => sum + t.row_count, 0)

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
              <h1 className="text-3xl font-bold text-text-primary">Database Administration</h1>
              <p className="text-sm text-text-secondary mt-1">Monitor data collection and table statistics</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={testAPIConnections}
              disabled={testingAPIs}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {testingAPIs ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Testing...
                </>
              ) : (
                <>
                  <Wifi className="w-4 h-4" />
                  Test API Connections
                </>
              )}
            </button>
            <button
              onClick={fetchStats}
              className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-dark text-white rounded-lg transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
          </div>
        </div>

        {/* Database Info Card */}
        <div className="bg-background-card border border-gray-700 rounded-lg p-6">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-text-secondary">Database Path</div>
              <div className="text-sm text-text-primary font-mono mt-1 break-all">{stats.database_path}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary">Total Tables</div>
              <div className="text-2xl font-bold text-text-primary mt-1">{stats.total_tables}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary">Total Rows</div>
              <div className="text-2xl font-bold text-text-primary mt-1">{totalRows.toLocaleString()}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary">Last Updated</div>
              <div className="text-sm text-text-primary mt-1">
                {new Date(stats.timestamp).toLocaleTimeString()}
              </div>
            </div>
          </div>
        </div>

        {/* API Connection Test Results */}
        {showTestResults && testResults && (
          <div className="bg-background-card border border-gray-700 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-text-primary flex items-center gap-2">
                <Wifi className="w-5 h-5" />
                API Connection Test Results
              </h2>
              <button
                onClick={() => setShowTestResults(false)}
                className="text-text-secondary hover:text-text-primary text-sm"
              >
                Hide
              </button>
            </div>

            {/* Overall Status */}
            <div className={`rounded-lg p-4 mb-4 ${
              testResults.overall_status === 'all_systems_operational' ? 'bg-success/10 border border-success/30' :
              testResults.overall_status === 'all_systems_down' ? 'bg-danger/10 border border-danger/30' :
              'bg-warning/10 border border-warning/30'
            }`}>
              <div className="flex items-center gap-2">
                {testResults.overall_status === 'all_systems_operational' ? (
                  <CheckCircle className="w-5 h-5 text-success" />
                ) : testResults.overall_status === 'all_systems_down' ? (
                  <WifiOff className="w-5 h-5 text-danger" />
                ) : (
                  <AlertCircle className="w-5 h-5 text-warning" />
                )}
                <span className="font-semibold">
                  {testResults.overall_status === 'all_systems_operational' ? 'All Systems Operational' :
                   testResults.overall_status === 'all_systems_down' ? 'All Systems Down' :
                   testResults.overall_status === 'trading_volatility_only' ? 'Trading Volatility Only' :
                   'Polygon Only'}
                </span>
              </div>
              <div className="text-xs text-text-muted mt-1">
                Tested at {new Date(testResults.timestamp).toLocaleString()}
              </div>
            </div>

            {/* API Results Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Trading Volatility API */}
              <div className={`border rounded-lg p-4 ${
                testResults.trading_volatility.status === 'connected' ? 'border-success/30 bg-success/5' : 'border-danger/30 bg-danger/5'
              }`}>
                <div className="flex items-center gap-2 mb-3">
                  {testResults.trading_volatility.status === 'connected' ? (
                    <CheckCircle className="w-5 h-5 text-success" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-danger" />
                  )}
                  <div>
                    <div className="font-semibold text-text-primary">Trading Volatility API</div>
                    <div className="text-xs text-text-muted">Test Symbol: {testResults.trading_volatility.test_symbol}</div>
                  </div>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Status:</span>
                    <span className={testResults.trading_volatility.status === 'connected' ? 'text-success' : 'text-danger'}>
                      {testResults.trading_volatility.status}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Response Time:</span>
                    <span className="text-text-primary">{testResults.trading_volatility.response_time_ms}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Data Quality:</span>
                    <span className="text-text-primary">{testResults.trading_volatility.data_quality || 'N/A'}</span>
                  </div>
                  {testResults.trading_volatility.fields_received.length > 0 && (
                    <div>
                      <div className="text-text-secondary mb-1">Fields Received:</div>
                      <div className="flex flex-wrap gap-1">
                        {testResults.trading_volatility.fields_received.slice(0, 5).map((field) => (
                          <span key={field} className="text-xs bg-gray-800 px-2 py-1 rounded">{field}</span>
                        ))}
                        {testResults.trading_volatility.fields_received.length > 5 && (
                          <span className="text-xs text-text-muted">+{testResults.trading_volatility.fields_received.length - 5} more</span>
                        )}
                      </div>
                    </div>
                  )}
                  {testResults.trading_volatility.sample_data && (
                    <div className="mt-2 p-2 bg-gray-900/50 rounded text-xs">
                      <div className="text-text-secondary mb-1">Sample Data:</div>
                      <div className="text-text-primary font-mono">
                        Price: ${testResults.trading_volatility.sample_data.spot_price}
                      </div>
                      <div className="text-text-primary font-mono">
                        Net GEX: {testResults.trading_volatility.sample_data.net_gex}
                      </div>
                    </div>
                  )}
                  {testResults.trading_volatility.error && (
                    <div className="mt-2 p-2 bg-danger/10 border border-danger/30 rounded text-xs text-danger">
                      {testResults.trading_volatility.error}
                    </div>
                  )}
                </div>
              </div>

              {/* Polygon API */}
              <div className={`border rounded-lg p-4 ${
                testResults.polygon.status === 'connected' ? 'border-success/30 bg-success/5' :
                testResults.polygon.status === 'not_configured' ? 'border-warning/30 bg-warning/5' :
                'border-danger/30 bg-danger/5'
              }`}>
                <div className="flex items-center gap-2 mb-3">
                  {testResults.polygon.status === 'connected' ? (
                    <CheckCircle className="w-5 h-5 text-success" />
                  ) : testResults.polygon.status === 'not_configured' ? (
                    <Info className="w-5 h-5 text-warning" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-danger" />
                  )}
                  <div>
                    <div className="font-semibold text-text-primary">Polygon API</div>
                    <div className="text-xs text-text-muted">Test Symbol: {testResults.polygon.test_symbol}</div>
                  </div>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Status:</span>
                    <span className={
                      testResults.polygon.status === 'connected' ? 'text-success' :
                      testResults.polygon.status === 'not_configured' ? 'text-warning' :
                      'text-danger'
                    }>
                      {testResults.polygon.status}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Response Time:</span>
                    <span className="text-text-primary">{testResults.polygon.response_time_ms}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Data Quality:</span>
                    <span className="text-text-primary">{testResults.polygon.data_quality || 'N/A'}</span>
                  </div>
                  {testResults.polygon.vix_value && (
                    <div className="flex justify-between">
                      <span className="text-text-secondary">VIX Value:</span>
                      <span className="text-text-primary font-mono">{testResults.polygon.vix_value}</span>
                    </div>
                  )}
                  {testResults.polygon.sample_data && (
                    <div className="mt-2 p-2 bg-gray-900/50 rounded text-xs">
                      <div className="text-text-secondary mb-1">Sample Data:</div>
                      <div className="text-text-primary font-mono">
                        Close: ${testResults.polygon.sample_data.close}
                      </div>
                      <div className="text-text-primary font-mono">
                        Volume: {testResults.polygon.sample_data.volume?.toLocaleString()}
                      </div>
                    </div>
                  )}
                  {testResults.polygon.error && (
                    <div className="mt-2 p-2 bg-danger/10 border border-danger/30 rounded text-xs text-danger">
                      {testResults.polygon.error}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Status Overview */}
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

        {/* Populated Tables Section */}
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
                      <Table2 className="w-5 h-5 text-success" />
                      <div className="text-left">
                        <div className="font-mono font-semibold text-text-primary">{table.table_name}</div>
                        <div className="text-sm text-text-secondary">
                          {table.row_count.toLocaleString()} rows · {table.columns.length} columns
                        </div>
                      </div>
                    </div>
                    <div className="text-sm text-text-secondary">
                      {expandedTables.has(table.table_name) ? '▼' : '▶'}
                    </div>
                  </button>

                  {expandedTables.has(table.table_name) && (
                    <div className="p-4 border-t border-gray-700 bg-gray-950/30">
                      {/* Columns */}
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

                      {/* Sample Data */}
                      {table.sample_data.length > 0 && (
                        <div>
                          <h4 className="text-sm font-semibold text-text-secondary mb-2">Sample Data (First 5 Rows)</h4>
                          <div className="overflow-x-auto">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="border-b border-gray-700">
                                  {table.columns.map((col) => (
                                    <th key={col.name} className="text-left px-2 py-1 text-text-secondary font-semibold">
                                      {col.name}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {table.sample_data.map((row, idx) => (
                                  <tr key={idx} className="border-b border-gray-800 hover:bg-gray-900/50">
                                    {table.columns.map((col) => (
                                      <td key={col.name} className="px-2 py-1 text-text-primary font-mono">
                                        {row[col.name] !== null ? String(row[col.name]).substring(0, 50) : <span className="text-text-muted">NULL</span>}
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

        {/* Empty Tables Section */}
        {emptyTables.length > 0 && (
          <div>
            <h2 className="text-xl font-bold text-warning mb-4 flex items-center gap-2">
              <AlertCircle className="w-5 h-5" />
              Empty Tables ({emptyTables.length})
            </h2>
            <div className="space-y-3">
              {emptyTables.map((table) => (
                <div key={table.table_name} className="bg-background-card border border-warning/30 rounded-lg overflow-hidden">
                  <button
                    onClick={() => toggleTable(table.table_name)}
                    className="w-full p-4 flex items-center justify-between hover:bg-background-hover transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <Table2 className="w-5 h-5 text-warning" />
                      <div className="text-left">
                        <div className="font-mono font-semibold text-text-primary">{table.table_name}</div>
                        <div className="text-sm text-warning">
                          0 rows · {table.columns.length} columns · No data collected yet
                        </div>
                      </div>
                    </div>
                    <div className="text-sm text-text-secondary">
                      {expandedTables.has(table.table_name) ? '▼' : '▶'}
                    </div>
                  </button>

                  {expandedTables.has(table.table_name) && (
                    <div className="p-4 border-t border-gray-700 bg-gray-950/30">
                      {/* Columns */}
                      <div>
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
                      <div className="mt-3 text-sm text-warning">
                        ⚠️ This table exists but has no data. Data collection may need to be triggered.
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Data Collection Guide */}
        <div className="bg-gradient-to-br from-purple-900/20 to-blue-900/20 border border-purple-500/30 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <Info className="w-5 h-5 text-purple-400 mt-1 flex-shrink-0" />
            <div className="w-full">
              <h3 className="text-lg font-semibold text-purple-400 mb-4">Data Collection Guide</h3>

              {/* Data Collection Status Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
                <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
                  <h4 className="font-semibold text-white mb-2">Market Data</h4>
                  <ul className="text-sm text-gray-300 space-y-1">
                    <li className="flex items-center gap-2">
                      <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                      GEX/Gamma data (real-time)
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                      VIX data (Tradier/Polygon)
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                      Price data (auto-fetched)
                    </li>
                  </ul>
                </div>

                <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
                  <h4 className="font-semibold text-white mb-2">Trading Data</h4>
                  <ul className="text-sm text-gray-300 space-y-1">
                    <li className="flex items-center gap-2">
                      <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></span>
                      Autonomous trades (on execution)
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></span>
                      Position tracking (auto-updated)
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></span>
                      Trade logs (every 5 min scan)
                    </li>
                  </ul>
                </div>

                <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4">
                  <h4 className="font-semibold text-white mb-2">Analytics Data</h4>
                  <ul className="text-sm text-gray-300 space-y-1">
                    <li className="flex items-center gap-2">
                      <span className="w-2 h-2 bg-yellow-500 rounded-full"></span>
                      Psychology patterns (on page visit)
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="w-2 h-2 bg-yellow-500 rounded-full"></span>
                      Backtest results (on run)
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="w-2 h-2 bg-yellow-500 rounded-full"></span>
                      AI recommendations (on request)
                    </li>
                  </ul>
                </div>
              </div>

              <div className="text-sm text-gray-300 space-y-2">
                <p><strong>Empty Tables:</strong> These tables exist but have no data yet. Data collection happens when you use features:</p>
                <ul className="list-disc list-inside ml-4 space-y-1">
                  <li><strong>regime_signals</strong> - Populated when you visit Psychology Trap Detection page</li>
                  <li><strong>historical_open_interest</strong> - Daily gamma snapshots (auto-saved)</li>
                  <li><strong>autonomous_trader_logs</strong> - Populated when Autonomous Trader executes trades</li>
                  <li><strong>backtest_results</strong> - Populated by running backtests</li>
                  <li><strong>recommendations</strong> - AI trade recommendations (auto-saved)</li>
                </ul>
                <p className="mt-3"><strong>To populate empty tables:</strong> Use the corresponding features in AlphaGEX (visit pages, run backtests, execute trades).</p>
              </div>
            </div>
          </div>
        </div>
        </div>
      </main>
    </div>
  )
}
