'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import {
  Target,
  TrendingUp,
  DollarSign,
  Clock,
  AlertCircle,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Save,
  RefreshCw,
  BarChart3
} from 'lucide-react'

interface TradeSetup {
  id?: number
  symbol: string
  setup_type: string
  confidence: number
  entry_price: number
  target_price: number
  stop_price: number
  risk_reward: number
  position_size: number
  max_risk_dollars: number
  time_horizon: string
  catalyst: string
  money_making_plan: string
  market_data?: {
    net_gex: number
    spot_price: number
    flip_point: number
    call_wall: number
    put_wall: number
  }
  generated_at?: string
  timestamp?: string
  status?: string
}

export default function TradeSetupsPage() {
  const [loading, setLoading] = useState(false)
  const [currentSetups, setCurrentSetups] = useState<TradeSetup[]>([])
  const [savedSetups, setSavedSetups] = useState<TradeSetup[]>([])
  const [expandedSetup, setExpandedSetup] = useState<number | null>(null)
  const [selectedTab, setSelectedTab] = useState<'current' | 'saved'>('current')

  // Settings
  const [symbols, setSymbols] = useState<string[]>(['SPY'])
  const [accountSize, setAccountSize] = useState(50000)
  const [riskPct, setRiskPct] = useState(2.0)
  const [showSettings, setShowSettings] = useState(false)

  const popularSymbols = ['SPY', 'QQQ', 'IWM', 'AAPL', 'TSLA', 'NVDA', 'META', 'AMZN', 'GOOGL', 'MSFT']

  useEffect(() => {
    fetchSavedSetups()
  }, [])

  const fetchSavedSetups = async () => {
    try {
      const response = await apiClient.getSetups(20, 'active')
      if (response.data.success) {
        setSavedSetups(response.data.data)
      }
    } catch (error) {
      console.error('Error fetching saved setups:', error)
    }
  }

  const handleGenerateSetups = async () => {
    setLoading(true)
    try {
      const response = await apiClient.generateSetups({
        symbols,
        account_size: accountSize,
        risk_pct: riskPct
      })

      if (response.data.success) {
        setCurrentSetups(response.data.setups)
        setSelectedTab('current')
      }
    } catch (error) {
      console.error('Error generating setups:', error)
      alert('Failed to generate setups. Make sure the backend is running.')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveSetup = async (setup: TradeSetup) => {
    try {
      const response = await apiClient.saveSetup(setup)
      if (response.data.success) {
        alert('Setup saved successfully!')
        await fetchSavedSetups()
      }
    } catch (error) {
      console.error('Error saving setup:', error)
      alert('Failed to save setup')
    }
  }

  const toggleSymbol = (symbol: string) => {
    setSymbols(prev =>
      prev.includes(symbol)
        ? prev.filter(s => s !== symbol)
        : [...prev, symbol]
    )
  }

  const getSetupTypeColor = (type: string) => {
    if (type.includes('CALL') || type.includes('SQUEEZE')) return 'text-success'
    if (type.includes('PUT') || type.includes('BREAKDOWN')) return 'text-danger'
    return 'text-warning'
  }

  const getSetupTypeBadge = (type: string) => {
    if (type.includes('CALL') || type.includes('SQUEEZE')) return 'bg-success/20 text-success'
    if (type.includes('PUT') || type.includes('BREAKDOWN')) return 'bg-danger/20 text-danger'
    return 'bg-warning/20 text-warning'
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value)
  }

  const formatTimestamp = (timestamp?: string) => {
    if (!timestamp) return 'Just now'
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

  const renderSetup = (setup: TradeSetup, index: number, isSaved: boolean = false) => {
    const isExpanded = expandedSetup === index

    return (
      <div key={index} className="bg-background-hover rounded-lg border border-gray-800 overflow-hidden">
        {/* Setup Header */}
        <div className="p-4 cursor-pointer hover:bg-background-deep transition-colors"
             onClick={() => setExpandedSetup(isExpanded ? null : index)}>
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center space-x-3">
              <div className="text-2xl font-bold text-primary">{setup.symbol}</div>
              <div className={`px-3 py-1 rounded-full text-xs font-semibold ${getSetupTypeBadge(setup.setup_type)}`}>
                {setup.setup_type.replace(/_/g, ' ')}
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <div className="text-right">
                <div className="text-xs text-text-muted">Confidence</div>
                <div className="text-lg font-bold text-success">{(setup.confidence * 100).toFixed(0)}%</div>
              </div>
              {isExpanded ? (
                <ChevronUp className="w-5 h-5 text-text-secondary" />
              ) : (
                <ChevronDown className="w-5 h-5 text-text-secondary" />
              )}
            </div>
          </div>

          {/* Quick Stats */}
          <div className="grid grid-cols-4 gap-4 mb-3">
            <div>
              <div className="text-xs text-text-muted">Entry</div>
              <div className="font-semibold text-text-primary">{formatCurrency(setup.entry_price)}</div>
            </div>
            <div>
              <div className="text-xs text-text-muted">Target</div>
              <div className={`font-semibold ${getSetupTypeColor(setup.setup_type)}`}>
                {formatCurrency(setup.target_price)}
              </div>
            </div>
            <div>
              <div className="text-xs text-text-muted">R:R</div>
              <div className="font-semibold text-warning">{setup.risk_reward.toFixed(1)}:1</div>
            </div>
            <div>
              <div className="text-xs text-text-muted">Risk</div>
              <div className="font-semibold text-danger">{formatCurrency(setup.max_risk_dollars)}</div>
            </div>
          </div>

          {/* Catalyst Preview */}
          <div className="text-sm text-text-secondary line-clamp-2">
            {setup.catalyst}
          </div>

          {/* Timestamp */}
          <div className="flex items-center justify-between mt-3 text-xs text-text-muted">
            <div className="flex items-center space-x-1">
              <Clock className="w-3 h-3" />
              <span>{formatTimestamp(setup.generated_at || setup.timestamp)}</span>
            </div>
            {!isSaved && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handleSaveSetup(setup)
                }}
                className="flex items-center space-x-1 text-primary hover:text-primary-light transition-colors"
              >
                <Save className="w-3 h-3" />
                <span>Save</span>
              </button>
            )}
          </div>
        </div>

        {/* Expanded Content - Money Making Plan */}
        {isExpanded && (
          <div className="border-t border-gray-800 bg-background-deep p-6">
            <div className="prose prose-invert max-w-none">
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-text-primary bg-background-card p-6 rounded-lg">
                {setup.money_making_plan}
              </pre>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center space-x-3 mt-6">
              {!isSaved && (
                <button
                  onClick={() => handleSaveSetup(setup)}
                  className="btn-primary flex items-center space-x-2"
                >
                  <Save className="w-4 h-4" />
                  <span>Save This Setup</span>
                </button>
              )}
              <button
                onClick={() => {
                  // Copy to clipboard
                  navigator.clipboard.writeText(setup.money_making_plan)
                  alert('Setup copied to clipboard!')
                }}
                className="btn-secondary"
              >
                Copy to Clipboard
              </button>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <Navigation />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-3xl font-bold text-text-primary flex items-center space-x-3">
              <Target className="w-8 h-8 text-primary" />
              <span>AI Trade Setups</span>
            </h1>
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="btn-secondary text-sm"
            >
              {showSettings ? 'Hide' : 'Show'} Settings
            </button>
          </div>
          <p className="text-text-secondary">
            AI-generated trade recommendations based on current GEX data and market conditions
          </p>
        </div>

        {/* Settings Panel */}
        {showSettings && (
          <div className="card mb-6">
            <h3 className="text-lg font-semibold mb-4">Generation Settings</h3>

            {/* Symbol Selection */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-text-secondary mb-2">
                Select Symbols ({symbols.length} selected)
              </label>
              <div className="flex flex-wrap gap-2">
                {popularSymbols.map(symbol => (
                  <button
                    key={symbol}
                    onClick={() => toggleSymbol(symbol)}
                    className={`px-4 py-2 rounded-lg font-medium transition-all ${
                      symbols.includes(symbol)
                        ? 'bg-primary text-white'
                        : 'bg-background-hover text-text-secondary hover:bg-background-deep'
                    }`}
                  >
                    {symbol}
                  </button>
                ))}
              </div>
            </div>

            {/* Account Settings */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Account Size
                </label>
                <input
                  type="number"
                  value={accountSize}
                  onChange={(e) => setAccountSize(Number(e.target.value))}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Risk per Trade (%)
                </label>
                <input
                  type="number"
                  step="0.5"
                  value={riskPct}
                  onChange={(e) => setRiskPct(Number(e.target.value))}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary"
                />
              </div>
            </div>

            <div className="mt-4 text-sm text-text-muted">
              Max risk per trade: {formatCurrency(accountSize * (riskPct / 100))}
            </div>
          </div>
        )}

        {/* Generate Button */}
        <div className="card mb-6">
          <button
            onClick={handleGenerateSetups}
            disabled={loading || symbols.length === 0}
            className="btn-primary w-full flex items-center justify-center space-x-2 py-4 text-lg disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <RefreshCw className="w-5 h-5 animate-spin" />
                <span>Generating AI Setups...</span>
              </>
            ) : (
              <>
                <BarChart3 className="w-5 h-5" />
                <span>Generate Trade Setups ({symbols.length} symbol{symbols.length !== 1 ? 's' : ''})</span>
              </>
            )}
          </button>
          {symbols.length === 0 && (
            <p className="text-center text-danger text-sm mt-2">
              Please select at least one symbol
            </p>
          )}
        </div>

        {/* Tabs */}
        <div className="flex items-center space-x-4 mb-6 border-b border-gray-800">
          <button
            onClick={() => setSelectedTab('current')}
            className={`px-4 py-3 font-medium transition-colors ${
              selectedTab === 'current'
                ? 'text-primary border-b-2 border-primary'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            Current Setups ({currentSetups.length})
          </button>
          <button
            onClick={() => setSelectedTab('saved')}
            className={`px-4 py-3 font-medium transition-colors ${
              selectedTab === 'saved'
                ? 'text-primary border-b-2 border-primary'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            Saved Setups ({savedSetups.length})
          </button>
        </div>

        {/* Setups List */}
        <div className="space-y-4">
          {selectedTab === 'current' ? (
            currentSetups.length === 0 ? (
              <div className="card text-center py-12">
                <Target className="w-16 h-16 mx-auto mb-4 text-text-muted opacity-50" />
                <p className="text-text-muted mb-2">No setups generated yet</p>
                <p className="text-sm text-text-secondary">
                  Click "Generate Trade Setups" to get AI-powered recommendations
                </p>
              </div>
            ) : (
              currentSetups.map((setup, idx) => renderSetup(setup, idx, false))
            )
          ) : (
            savedSetups.length === 0 ? (
              <div className="card text-center py-12">
                <Save className="w-16 h-16 mx-auto mb-4 text-text-muted opacity-50" />
                <p className="text-text-muted mb-2">No saved setups</p>
                <p className="text-sm text-text-secondary">
                  Save setups from the "Current Setups" tab to track them here
                </p>
              </div>
            ) : (
              savedSetups.map((setup, idx) => renderSetup(setup, idx + 1000, true))
            )
          )}
        </div>

        {/* Info Card */}
        <div className="card mt-8 bg-primary/10 border-primary/30">
          <div className="flex items-start space-x-3">
            <AlertCircle className="w-5 h-5 text-primary mt-1 flex-shrink-0" />
            <div className="text-sm text-text-secondary">
              <p className="font-semibold text-text-primary mb-2">How to Use AI Trade Setups:</p>
              <ul className="space-y-1 list-disc list-inside">
                <li>Select symbols and configure your account settings</li>
                <li>Click "Generate Trade Setups" to get AI recommendations based on current market conditions</li>
                <li>Each setup includes specific entry, exit, stop loss, and position sizing</li>
                <li>Save setups you want to track and execute</li>
                <li>All setups are based on real-time GEX data and proven strategies</li>
              </ul>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
