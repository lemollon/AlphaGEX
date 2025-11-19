'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { Power, PowerOff, PlayCircle, StopCircle, RefreshCw, AlertCircle, CheckCircle, Activity } from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface TraderStatus {
  trader_running: boolean
  trader_pid: number | null
  autostart_enabled: boolean
  watchdog_enabled: boolean
  last_log_entry: string | null
  uptime: string | null
}

export default function SystemSettings() {
  const [status, setStatus] = useState<TraderStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null)

  const fetchStatus = async () => {
    try {
      const response = await fetch(`${API_URL}/api/system/trader-status`)
      const data = await response.json()

      if (data.success) {
        setStatus(data.status)
      }
    } catch (error) {
      console.error('Error fetching trader status:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()

    // Auto-refresh every 10 seconds
    const interval = setInterval(fetchStatus, 10000)
    return () => clearInterval(interval)
  }, [])

  const enableAutoStart = async () => {
    setActionLoading(true)
    setMessage(null)

    try {
      const response = await fetch(`${API_URL}/api/system/enable-autostart`, {
        method: 'POST'
      })
      const data = await response.json()

      if (data.success) {
        setMessage({ type: 'success', text: data.message })
        fetchStatus()
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to enable auto-start' })
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Network error. Please try again.' })
    } finally {
      setActionLoading(false)
    }
  }

  const disableAutoStart = async () => {
    setActionLoading(true)
    setMessage(null)

    try {
      const response = await fetch(`${API_URL}/api/system/disable-autostart`, {
        method: 'POST'
      })
      const data = await response.json()

      if (data.success) {
        setMessage({ type: 'success', text: data.message })
        fetchStatus()
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to disable auto-start' })
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Network error. Please try again.' })
    } finally {
      setActionLoading(false)
    }
  }

  const startTrader = async () => {
    setActionLoading(true)
    setMessage(null)

    try {
      const response = await fetch(`${API_URL}/api/system/start-trader`, {
        method: 'POST'
      })
      const data = await response.json()

      if (data.success) {
        setMessage({ type: 'success', text: data.message })
        setTimeout(fetchStatus, 2000) // Wait 2s for trader to start
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to start trader' })
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Network error. Please try again.' })
    } finally {
      setActionLoading(false)
    }
  }

  const stopTrader = async () => {
    if (!confirm('Are you sure you want to stop the autonomous trader?')) {
      return
    }

    setActionLoading(true)
    setMessage(null)

    try {
      const response = await fetch(`${API_URL}/api/system/stop-trader`, {
        method: 'POST'
      })
      const data = await response.json()

      if (data.success) {
        setMessage({ type: 'success', text: data.message })
        setTimeout(fetchStatus, 1000)
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to stop trader' })
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Network error. Please try again.' })
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-black text-white">
      <Navigation />

      <div className="p-8 max-w-6xl mx-auto">
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
                </div>

                {/* Manual Control Section */}
                <div className="border-t border-gray-800 pt-4">
                  <h3 className="text-lg font-semibold mb-3">Manual Control</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <button
                      onClick={startTrader}
                      disabled={actionLoading || status?.trader_running}
                      className="px-6 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 rounded-lg font-semibold transition-colors flex items-center justify-center gap-2"
                    >
                      <PlayCircle className="w-5 h-5" />
                      Start Trader Now
                    </button>

                    <button
                      onClick={stopTrader}
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
