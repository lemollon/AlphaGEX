'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { Power, PowerOff, PlayCircle, StopCircle, RefreshCw, AlertCircle, CheckCircle, Activity, Database, Wifi, WifiOff, Clock, Zap } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { logger } from '@/lib/logger'

interface TraderStatus {
  trader_running: boolean
  trader_pid: number | null
  autostart_enabled: boolean
  watchdog_enabled: boolean
  last_log_entry: string | null
  uptime: string | null
  platform?: string
  autostart_type?: string
}

interface DataSourceStatus {
  tradier: {
    connected: boolean
    response_time_ms: number
    last_price?: number
    symbol?: string
    error?: string
  }
  polygon: {
    connected: boolean
    response_time_ms: number
    vix_value?: number
    error?: string
  }
  vix_source: string
  options_source: string
  timestamp: string
}

export default function SystemSettings() {
  const [status, setStatus] = useState<TraderStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null)
  const [dataSourceStatus, setDataSourceStatus] = useState<DataSourceStatus | null>(null)
  const [dataSourceLoading, setDataSourceLoading] = useState(false)

  const fetchStatus = async () => {
    try {
      const response = await apiClient.getSystemTraderStatus()
      const respData = response.data.data || response.data

      if (respData.success !== false) {
        setStatus(respData.status)
      }
    } catch (error) {
      logger.error('Error fetching trader status:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchDataSources = async () => {
    setDataSourceLoading(true)
    try {
      const response = await apiClient.testConnections()
      const data = response.data.data || response.data

      if (data.results) {
        setDataSourceStatus({
          tradier: {
            connected: data.results.trading_volatility?.status === 'connected',
            response_time_ms: data.results.trading_volatility?.response_time_ms || 0,
            last_price: data.results.trading_volatility?.sample_data?.spot_price,
            symbol: data.results.trading_volatility?.test_symbol,
            error: data.results.trading_volatility?.error
          },
          polygon: {
            connected: data.results.polygon?.status === 'connected',
            response_time_ms: data.results.polygon?.response_time_ms || 0,
            vix_value: data.results.polygon?.vix_value,
            error: data.results.polygon?.error
          },
          vix_source: data.results.trading_volatility?.status === 'connected' ? 'Tradier (Real-time)' :
                      data.results.polygon?.status === 'connected' ? 'Polygon (Fallback)' : 'Default (18.0)',
          options_source: data.results.trading_volatility?.status === 'connected' ? 'Tradier (Real-time)' : 'Trading Volatility API',
          timestamp: data.results.timestamp || new Date().toISOString()
        })
      }
    } catch (error) {
      logger.error('Error fetching data sources:', error)
    } finally {
      setDataSourceLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
    fetchDataSources()

    // Auto-refresh every 10 seconds for trader status
    const interval = setInterval(fetchStatus, 10000)
    return () => clearInterval(interval)
  }, [])

  const enableAutoStart = async () => {
    setActionLoading(true)
    setMessage(null)

    try {
      const response = await apiClient.enableTraderAutostart()
      const data = response.data.data || response.data

      if (data.success !== false) {
        setMessage({ type: 'success', text: data.message || 'Auto-start enabled' })
        fetchStatus()
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to enable auto-start' })
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || 'Network error. Please try again.' })
    } finally {
      setActionLoading(false)
    }
  }

  const disableAutoStart = async () => {
    setActionLoading(true)
    setMessage(null)

    try {
      const response = await apiClient.disableTraderAutostart()
      const data = response.data.data || response.data

      if (data.success !== false) {
        setMessage({ type: 'success', text: data.message || 'Auto-start disabled' })
        fetchStatus()
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to disable auto-start' })
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || 'Network error. Please try again.' })
    } finally {
      setActionLoading(false)
    }
  }

  const startTraderHandler = async () => {
    setActionLoading(true)
    setMessage(null)

    try {
      const response = await apiClient.startTrader()
      const data = response.data.data || response.data

      if (data.success !== false) {
        setMessage({ type: 'success', text: data.message || 'Trader started' })
        setTimeout(fetchStatus, 2000) // Wait 2s for trader to start
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to start trader' })
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || 'Network error. Please try again.' })
    } finally {
      setActionLoading(false)
    }
  }

  const stopTraderHandler = async () => {
    if (!confirm('Are you sure you want to stop the autonomous trader?')) {
      return
    }

    setActionLoading(true)
    setMessage(null)

    try {
      const response = await apiClient.stopTrader()
      const data = response.data.data || response.data

      if (data.success !== false) {
        setMessage({ type: 'success', text: data.message || 'Trader stopped' })
        setTimeout(fetchStatus, 1000)
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to stop trader' })
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || 'Network error. Please try again.' })
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-black text-white">
      <Navigation />

      <div className="p-8 pt-20 lg:pt-8 max-w-6xl mx-auto">
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2">System Settings</h1>
          <p className="text-gray-400">Manage autonomous trader and system configuration</p>
        </div>

        {/* Status Message */}
        {message && (
          <div className={`mb-6 p-4 rounded-lg border ${
            message.type === 'success'
              ? 'bg-green-900/20 border-green-500 text-green-400'
              : 'bg-red-900/20 border-red-500 text-red-400'
          }`}>
            <div className="flex items-center gap-2">
              {message.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
              <span>{message.text}</span>
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
          </div>
        ) : (
          <>
            {/* Autonomous Trader Status */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-6">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <Activity className="w-6 h-6 text-blue-500" />
                  <h2 className="text-2xl font-bold">Autonomous Trader</h2>
                </div>
                <button
                  onClick={fetchStatus}
                  className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
                  title="Refresh status"
                >
                  <RefreshCw className="w-5 h-5" />
                </button>
              </div>

              {/* Status Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
                  <div className="text-sm text-gray-400 mb-1">Trader Status</div>
                  <div className="flex items-center gap-2">
                    {status?.trader_running ? (
                      <>
                        <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                        <span className="text-lg font-semibold text-green-400">Running</span>
                        {status.trader_pid && (
                          <span className="text-sm text-gray-500">(PID: {status.trader_pid})</span>
                        )}
                      </>
                    ) : (
                      <>
                        <div className="w-3 h-3 bg-red-500 rounded-full"></div>
                        <span className="text-lg font-semibold text-red-400">Stopped</span>
                      </>
                    )}
                  </div>
                </div>

                <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
                  <div className="text-sm text-gray-400 mb-1">Auto-Start</div>
                  <div className="flex items-center gap-2">
                    {status?.autostart_enabled ? (
                      <>
                        <CheckCircle className="w-5 h-5 text-green-400" />
                        <span className="text-lg font-semibold text-green-400">Enabled</span>
                      </>
                    ) : (
                      <>
                        <AlertCircle className="w-5 h-5 text-yellow-400" />
                        <span className="text-lg font-semibold text-yellow-400">Disabled</span>
                      </>
                    )}
                  </div>
                </div>

                <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
                  <div className="text-sm text-gray-400 mb-1">Watchdog</div>
                  <div className="flex items-center gap-2">
                    {status?.watchdog_enabled ? (
                      <>
                        <CheckCircle className="w-5 h-5 text-green-400" />
                        <span className="text-lg font-semibold text-green-400">Active</span>
                        <span className="text-sm text-gray-500">(checks every minute)</span>
                      </>
                    ) : (
                      <>
                        <AlertCircle className="w-5 h-5 text-gray-400" />
                        <span className="text-lg font-semibold text-gray-400">Inactive</span>
                      </>
                    )}
                  </div>
                </div>

                {status?.last_log_entry && (
                  <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Last Activity</div>
                    <div className="text-sm text-gray-300 truncate">{status.last_log_entry}</div>
                  </div>
                )}
              </div>

              {/* Control Buttons */}
              <div className="space-y-4">
                {/* Auto-Start Section */}
                <div className="border-t border-gray-800 pt-4">
                  <h3 className="text-lg font-semibold mb-3">🚀 Permanent Auto-Start Setup</h3>

                  {status?.platform === 'render' ? (
                    // Render-specific messaging
                    <div className="space-y-3">
                      <div className="p-4 bg-green-900/20 border border-green-500 rounded-lg">
                        <div className="flex items-center gap-2 text-green-400 mb-2">
                          <CheckCircle className="w-5 h-5" />
                          <span className="font-semibold">Auto-Start Enabled (Render Worker Service)</span>
                        </div>
                        <ul className="text-sm text-gray-300 space-y-1 ml-7">
                          <li>✅ Managed via render.yaml configuration</li>
                          <li>✅ Runs as dedicated background worker</li>
                          <li>✅ Auto-restarts if crashed (Render manages this)</li>
                          <li>✅ No manual setup required</li>
                        </ul>
                      </div>
                      <div className="text-xs text-gray-500 italic">
                        Note: On Render, the autonomous trader runs as a separate worker service. Check the "alphagex-trader" service in your Render dashboard to see logs and status.
                      </div>
                    </div>
                  ) : (
                    // Local/VPS messaging
                    <>
                      <p className="text-gray-400 text-sm mb-4">
                        Click once to enable auto-start on boot + crash recovery watchdog. The trader will run forever automatically.
                      </p>

                      {!status?.autostart_enabled ? (
                        <button
                          onClick={enableAutoStart}
                          disabled={actionLoading}
                          className="w-full px-6 py-4 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 disabled:from-gray-700 disabled:to-gray-700 rounded-xl font-semibold text-lg transition-all duration-300 transform hover:scale-105 disabled:scale-100 flex items-center justify-center gap-3 shadow-lg"
                        >
                          {actionLoading ? (
                            <>
                              <RefreshCw className="w-6 h-6 animate-spin" />
                              Enabling Auto-Start...
                            </>
                          ) : (
                            <>
                              <Power className="w-6 h-6" />
                              Enable Auto-Start (One-Click Permanent Solution)
                            </>
                          )}
                        </button>
                      ) : (
                        <div className="space-y-3">
                          <div className="p-4 bg-green-900/20 border border-green-500 rounded-lg">
                            <div className="flex items-center gap-2 text-green-400 mb-2">
                              <CheckCircle className="w-5 h-5" />
                              <span className="font-semibold">Auto-Start Enabled</span>
                            </div>
                            <ul className="text-sm text-gray-300 space-y-1 ml-7">
                              <li>✅ Starts automatically on boot</li>
                              <li>✅ Watchdog checks every minute</li>
                              <li>✅ Auto-restarts if crashed</li>
                              <li>✅ No manual intervention needed</li>
                            </ul>
                          </div>

                          <button
                            onClick={disableAutoStart}
                            disabled={actionLoading}
                            className="w-full px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 rounded-lg transition-colors flex items-center justify-center gap-2 text-sm"
                          >
                            <PowerOff className="w-4 h-4" />
                            Disable Auto-Start
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>

                {/* Manual Control Section */}
                <div className="border-t border-gray-800 pt-4">
                  <h3 className="text-lg font-semibold mb-3">Manual Control</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <button
                      onClick={startTraderHandler}
                      disabled={actionLoading || status?.trader_running}
                      className="px-6 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 rounded-lg font-semibold transition-colors flex items-center justify-center gap-2"
                    >
                      <PlayCircle className="w-5 h-5" />
                      Start Trader Now
                    </button>

                    <button
                      onClick={stopTraderHandler}
                      disabled={actionLoading || !status?.trader_running}
                      className="px-6 py-3 bg-red-600 hover:bg-red-500 disabled:bg-gray-700 rounded-lg font-semibold transition-colors flex items-center justify-center gap-2"
                    >
                      <StopCircle className="w-5 h-5" />
                      Stop Trader
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Data Sources Section */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-6">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <Database className="w-6 h-6 text-purple-500" />
                  <h2 className="text-2xl font-bold">Data Sources</h2>
                </div>
                <button
                  onClick={fetchDataSources}
                  disabled={dataSourceLoading}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 rounded-lg transition-colors flex items-center gap-2"
                >
                  <RefreshCw className={`w-4 h-4 ${dataSourceLoading ? 'animate-spin' : ''}`} />
                  Test Connections
                </button>
              </div>

              {dataSourceStatus ? (
                <div className="space-y-4">
                  {/* Active Data Sources */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <Zap className="w-4 h-4 text-yellow-400" />
                        <span className="text-sm text-gray-400">VIX Data Source</span>
                      </div>
                      <div className="text-lg font-semibold text-white">{dataSourceStatus.vix_source}</div>
                    </div>
                    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <Activity className="w-4 h-4 text-blue-400" />
                        <span className="text-sm text-gray-400">Options Data Source</span>
                      </div>
                      <div className="text-lg font-semibold text-white">{dataSourceStatus.options_source}</div>
                    </div>
                  </div>

                  {/* API Status Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Tradier/Trading Volatility API */}
                    <div className={`border rounded-lg p-4 ${
                      dataSourceStatus.tradier.connected
                        ? 'border-green-500/30 bg-green-900/10'
                        : 'border-red-500/30 bg-red-900/10'
                    }`}>
                      <div className="flex items-center gap-2 mb-3">
                        {dataSourceStatus.tradier.connected ? (
                          <Wifi className="w-5 h-5 text-green-400" />
                        ) : (
                          <WifiOff className="w-5 h-5 text-red-400" />
                        )}
                        <span className="font-semibold">Trading Volatility API</span>
                      </div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Status:</span>
                          <span className={dataSourceStatus.tradier.connected ? 'text-green-400' : 'text-red-400'}>
                            {dataSourceStatus.tradier.connected ? 'Connected' : 'Disconnected'}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Response Time:</span>
                          <span>{dataSourceStatus.tradier.response_time_ms}ms</span>
                        </div>
                        {dataSourceStatus.tradier.last_price && (
                          <div className="flex justify-between">
                            <span className="text-gray-400">SPY Price:</span>
                            <span className="text-green-400">${dataSourceStatus.tradier.last_price.toFixed(2)}</span>
                          </div>
                        )}
                        {dataSourceStatus.tradier.error && (
                          <div className="mt-2 p-2 bg-red-900/20 border border-red-500/30 rounded text-xs text-red-400">
                            {dataSourceStatus.tradier.error}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Polygon API */}
                    <div className={`border rounded-lg p-4 ${
                      dataSourceStatus.polygon.connected
                        ? 'border-green-500/30 bg-green-900/10'
                        : 'border-yellow-500/30 bg-yellow-900/10'
                    }`}>
                      <div className="flex items-center gap-2 mb-3">
                        {dataSourceStatus.polygon.connected ? (
                          <Wifi className="w-5 h-5 text-green-400" />
                        ) : (
                          <WifiOff className="w-5 h-5 text-yellow-400" />
                        )}
                        <span className="font-semibold">Polygon API (Fallback)</span>
                      </div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Status:</span>
                          <span className={dataSourceStatus.polygon.connected ? 'text-green-400' : 'text-yellow-400'}>
                            {dataSourceStatus.polygon.connected ? 'Connected' : 'Not Configured'}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Response Time:</span>
                          <span>{dataSourceStatus.polygon.response_time_ms}ms</span>
                        </div>
                        {dataSourceStatus.polygon.vix_value && (
                          <div className="flex justify-between">
                            <span className="text-gray-400">VIX Value:</span>
                            <span>{dataSourceStatus.polygon.vix_value.toFixed(2)}</span>
                          </div>
                        )}
                        {dataSourceStatus.polygon.error && (
                          <div className="mt-2 p-2 bg-yellow-900/20 border border-yellow-500/30 rounded text-xs text-yellow-400">
                            {dataSourceStatus.polygon.error}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Last Updated */}
                  <div className="flex items-center gap-2 text-xs text-gray-500 mt-4">
                    <Clock className="w-3 h-3" />
                    <span>Last tested: {new Date(dataSourceStatus.timestamp).toLocaleString()}</span>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-gray-400">
                  <Database className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>Click "Test Connections" to check data source status</p>
                </div>
              )}
            </div>

            {/* Info Section */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <h3 className="text-xl font-bold mb-4">How It Works</h3>
              <div className="space-y-3 text-gray-300">
                <div className="flex gap-3">
                  <div className="text-blue-500 mt-1">1.</div>
                  <div>
                    <strong>Click "Enable Auto-Start"</strong> - Sets up crontab entries for boot + watchdog
                  </div>
                </div>
                <div className="flex gap-3">
                  <div className="text-blue-500 mt-1">2.</div>
                  <div>
                    <strong>On Boot</strong> - Trader starts automatically when system restarts
                  </div>
                </div>
                <div className="flex gap-3">
                  <div className="text-blue-500 mt-1">3.</div>
                  <div>
                    <strong>Every Minute</strong> - Watchdog checks if running, restarts if crashed
                  </div>
                </div>
                <div className="flex gap-3">
                  <div className="text-blue-500 mt-1">4.</div>
                  <div>
                    <strong>Forever</strong> - Runs permanently, no manual intervention needed
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
