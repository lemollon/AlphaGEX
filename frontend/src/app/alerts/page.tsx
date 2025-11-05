'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import {
  Bell,
  Plus,
  Trash2,
  Clock,
  TrendingUp,
  AlertCircle,
  CheckCircle,
  X,
  RefreshCw
} from 'lucide-react'

interface Alert {
  id: number
  created_at: string
  symbol: string
  alert_type: string
  condition: string
  threshold: number
  message: string
  status: string
  triggered_at?: string
  triggered_value?: number
}

interface AlertHistory {
  id: number
  alert_id: number
  triggered_at: string
  symbol: string
  alert_type: string
  condition: string
  threshold: number
  actual_value: number
  message: string
}

export default function AlertsPage() {
  const [activeAlerts, setActiveAlerts] = useState<Alert[]>([])
  const [alertHistory, setAlertHistory] = useState<AlertHistory[]>([])
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(false)

  // Create alert form
  const [symbol, setSymbol] = useState('SPY')
  const [alertType, setAlertType] = useState('price')
  const [condition, setCondition] = useState('above')
  const [threshold, setThreshold] = useState('')
  const [customMessage, setCustomMessage] = useState('')

  const popularSymbols = ['SPY', 'QQQ', 'IWM', 'AAPL', 'TSLA', 'NVDA', 'META', 'AMZN']

  useEffect(() => {
    fetchActiveAlerts()
    fetchAlertHistory()

    // Auto-check alerts every 2 minutes
    const interval = setInterval(() => {
      checkAlerts()
    }, 120000)

    return () => clearInterval(interval)
  }, [])

  const fetchActiveAlerts = async () => {
    try {
      const response = await apiClient.getAlerts('active')
      if (response.data.success) {
        setActiveAlerts(response.data.data)
      }
    } catch (error) {
      console.error('Error fetching alerts:', error)
    }
  }

  const fetchAlertHistory = async () => {
    try {
      const response = await apiClient.getAlertHistory(20)
      if (response.data.success) {
        setAlertHistory(response.data.data)
      }
    } catch (error) {
      console.error('Error fetching alert history:', error)
    }
  }

  const checkAlerts = async () => {
    setChecking(true)
    try {
      const response = await apiClient.checkAlerts()
      if (response.data.success && response.data.triggered > 0) {
        // Refresh alerts if any were triggered
        await fetchActiveAlerts()
        await fetchAlertHistory()

        // Show notification
        alert(`${response.data.triggered} alert(s) triggered!`)
      }
    } catch (error) {
      console.error('Error checking alerts:', error)
    } finally {
      setChecking(false)
    }
  }

  const handleCreateAlert = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      const response = await apiClient.createAlert({
        symbol: symbol.toUpperCase(),
        alert_type: alertType,
        condition,
        threshold: parseFloat(threshold),
        message: customMessage || undefined
      })

      if (response.data.success) {
        alert('Alert created successfully!')
        setShowCreateModal(false)
        resetForm()
        await fetchActiveAlerts()
      }
    } catch (error) {
      console.error('Error creating alert:', error)
      alert('Failed to create alert')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteAlert = async (alertId: number) => {
    if (!confirm('Are you sure you want to delete this alert?')) return

    try {
      const response = await apiClient.deleteAlert(alertId)
      if (response.data.success) {
        await fetchActiveAlerts()
      }
    } catch (error) {
      console.error('Error deleting alert:', error)
      alert('Failed to delete alert')
    }
  }

  const resetForm = () => {
    setSymbol('SPY')
    setAlertType('price')
    setCondition('above')
    setThreshold('')
    setCustomMessage('')
  }

  const formatTime = (timestamp: string) => {
    try {
      return new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        timeZone: 'America/Chicago'
      }).format(new Date(timestamp))
    } catch {
      return timestamp
    }
  }

  const getAlertTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      price: 'Price',
      net_gex: 'Net GEX',
      flip_point: 'Flip Point'
    }
    return labels[type] || type
  }

  const getConditionLabel = (condition: string) => {
    const labels: Record<string, string> = {
      above: 'Above',
      below: 'Below',
      crosses_above: 'Crosses Above',
      crosses_below: 'Crosses Below'
    }
    return labels[condition] || condition
  }

  const formatValue = (value: number, type: string) => {
    if (type === 'price') {
      return `$${value.toFixed(2)}`
    } else if (type === 'net_gex') {
      return `$${(value / 1e9).toFixed(1)}B`
    }
    return value.toFixed(2)
  }

  return (
    <div className="min-h-screen">
      <Navigation />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-text-primary flex items-center space-x-3">
              <Bell className="w-8 h-8 text-primary" />
              <span>Alerts</span>
            </h1>
            <p className="text-text-secondary mt-2">
              Get notified when price or GEX thresholds are hit
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <button
              onClick={checkAlerts}
              disabled={checking}
              className="btn-secondary flex items-center space-x-2"
            >
              <RefreshCw className={`w-4 h-4 ${checking ? 'animate-spin' : ''}`} />
              <span>Check Now</span>
            </button>
            <button
              onClick={() => setShowCreateModal(true)}
              className="btn-primary flex items-center space-x-2"
            >
              <Plus className="w-4 h-4" />
              <span>Create Alert</span>
            </button>
          </div>
        </div>

        {/* Active Alerts */}
        <div className="card mb-8">
          <h2 className="text-xl font-semibold mb-4 flex items-center space-x-2">
            <Bell className="w-5 h-5 text-success animate-pulse" />
            <span>Active Alerts ({activeAlerts.length})</span>
          </h2>

          {activeAlerts.length === 0 ? (
            <div className="text-center py-12">
              <Bell className="w-16 h-16 mx-auto mb-4 text-text-muted opacity-50" />
              <p className="text-text-muted mb-2">No active alerts</p>
              <p className="text-sm text-text-secondary">
                Create an alert to get notified of market opportunities 24/7
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {activeAlerts.map((alert) => (
                <div
                  key={alert.id}
                  className="flex items-center justify-between p-4 bg-background-hover rounded-lg hover:bg-background-deep transition-colors"
                >
                  <div className="flex items-center space-x-4">
                    <div className="w-2 h-2 rounded-full bg-success animate-pulse"></div>
                    <div>
                      <div className="flex items-center space-x-2 mb-1">
                        <span className="font-semibold text-primary">{alert.symbol}</span>
                        <span className="text-xs px-2 py-1 bg-primary/20 text-primary rounded">
                          {getAlertTypeLabel(alert.alert_type)}
                        </span>
                      </div>
                      <div className="text-sm text-text-secondary">
                        Alert when {getConditionLabel(alert.condition)}{' '}
                        <span className="font-mono text-text-primary">
                          {formatValue(alert.threshold, alert.alert_type)}
                        </span>
                      </div>
                      <div className="text-xs text-text-muted mt-1">
                        Created {formatTime(alert.created_at)}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteAlert(alert.id)}
                    className="p-2 hover:bg-danger/20 rounded-lg transition-colors"
                  >
                    <Trash2 className="w-4 h-4 text-danger" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Alert History */}
        <div className="card">
          <h2 className="text-xl font-semibold mb-4 flex items-center space-x-2">
            <Clock className="w-5 h-5 text-warning" />
            <span>Recent Triggers</span>
          </h2>

          {alertHistory.length === 0 ? (
            <div className="text-center py-12">
              <Clock className="w-16 h-16 mx-auto mb-4 text-text-muted opacity-50" />
              <p className="text-text-muted">No triggered alerts yet</p>
            </div>
          ) : (
            <div className="space-y-3">
              {alertHistory.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-4 bg-success/10 border border-success/30 rounded-lg"
                >
                  <div className="flex items-center space-x-4">
                    <CheckCircle className="w-5 h-5 text-success" />
                    <div>
                      <div className="flex items-center space-x-2 mb-1">
                        <span className="font-semibold text-success">{item.symbol}</span>
                        <span className="text-xs px-2 py-1 bg-success/20 text-success rounded">
                          {getAlertTypeLabel(item.alert_type)}
                        </span>
                      </div>
                      <div className="text-sm text-text-primary">
                        {item.message}
                      </div>
                      <div className="text-xs text-text-muted mt-1">
                        Triggered at {formatValue(item.actual_value, item.alert_type)} •{' '}
                        {formatTime(item.triggered_at)}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Info Card */}
        <div className="card mt-8 bg-primary/10 border-primary/30">
          <div className="flex items-start space-x-3">
            <AlertCircle className="w-5 h-5 text-primary mt-1 flex-shrink-0" />
            <div className="text-sm text-text-secondary">
              <p className="font-semibold text-text-primary mb-2">How Alerts Work:</p>
              <ul className="space-y-1 list-disc list-inside">
                <li>Create price alerts for any symbol (e.g., "Alert when SPY hits $600")</li>
                <li>Set GEX threshold alerts to catch regime changes</li>
                <li>Flip point alerts notify you of critical crossovers</li>
                <li>Alerts are checked automatically every 2 minutes during market hours</li>
                <li>Triggered alerts move to history and can be recreated</li>
              </ul>
            </div>
          </div>
        </div>
      </main>

      {/* Create Alert Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-background-card border border-gray-800 rounded-lg p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-semibold text-text-primary">Create New Alert</h3>
              <button
                onClick={() => {
                  setShowCreateModal(false)
                  resetForm()
                }}
                className="p-2 hover:bg-background-hover rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-text-secondary" />
              </button>
            </div>

            <form onSubmit={handleCreateAlert} className="space-y-4">
              {/* Symbol */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Symbol
                </label>
                <div className="flex space-x-2 mb-2">
                  {popularSymbols.map((sym) => (
                    <button
                      key={sym}
                      type="button"
                      onClick={() => setSymbol(sym)}
                      className={`px-3 py-1 rounded text-sm ${
                        symbol === sym
                          ? 'bg-primary text-white'
                          : 'bg-background-hover text-text-secondary'
                      }`}
                    >
                      {sym}
                    </button>
                  ))}
                </div>
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary"
                  placeholder="Enter symbol"
                />
              </div>

              {/* Alert Type */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Alert Type
                </label>
                <select
                  value={alertType}
                  onChange={(e) => setAlertType(e.target.value)}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary"
                >
                  <option value="price">Price</option>
                  <option value="net_gex">Net GEX</option>
                  <option value="flip_point">Flip Point Cross</option>
                </select>
              </div>

              {/* Condition */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Condition
                </label>
                <select
                  value={condition}
                  onChange={(e) => setCondition(e.target.value)}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary"
                >
                  {alertType === 'flip_point' ? (
                    <>
                      <option value="crosses_above">Crosses Above</option>
                      <option value="crosses_below">Crosses Below</option>
                    </>
                  ) : (
                    <>
                      <option value="above">Above</option>
                      <option value="below">Below</option>
                    </>
                  )}
                </select>
              </div>

              {/* Threshold */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Threshold {alertType === 'net_gex' && '(in billions)'}
                </label>
                <input
                  type="number"
                  step={alertType === 'net_gex' ? '0.1' : '0.01'}
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary"
                  placeholder={alertType === 'price' ? '600.00' : '-2.0'}
                  required
                />
              </div>

              {/* Custom Message (Optional) */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Custom Message (Optional)
                </label>
                <input
                  type="text"
                  value={customMessage}
                  onChange={(e) => setCustomMessage(e.target.value)}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary"
                  placeholder="Leave empty for auto-generated message"
                />
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={loading || !threshold}
                className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Creating...' : 'Create Alert'}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
