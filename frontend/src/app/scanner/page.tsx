'use client'

import { useState, useEffect } from 'react'
import { Search, TrendingUp, TrendingDown, Target, DollarSign, Clock, CheckCircle, XCircle, AlertCircle, History, BarChart3, RefreshCw } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { useDataCache } from '@/hooks/useDataCache'

interface ScanSetup {
  symbol: string
  strategy: string
  confidence: number
  net_gex: number
  spot_price: number
  flip_point: number
  call_wall: number
  put_wall: number
  entry_price: number
  target_price: number | null
  stop_price: number | null
  risk_reward: number
  expected_move: string
  win_rate: number
  money_making_plan: string
  reasoning: string
}

interface ScanRun {
  id: string
  timestamp: string
  symbols_scanned: string
  total_symbols: number
  opportunities_found: number
  scan_duration_seconds: number
}

export default function MultiSymbolScanner() {
  const [loading, setLoading] = useState(false)
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(['SPY', 'QQQ', 'IWM'])
  const [customSymbol, setCustomSymbol] = useState('')
  const [scanResults, setScanResults] = useState<ScanSetup[]>([])
  const [currentScanId, setCurrentScanId] = useState<string | null>(null)
  const [scanHistory, setScanHistory] = useState<ScanRun[]>([])
  const [selectedSetup, setSelectedSetup] = useState<ScanSetup | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [scanningStatus, setScanningStatus] = useState<{ symbol: string, progress: string } | null>(null)
  const [scanWarning, setScanWarning] = useState<string | null>(null)

  const popularSymbols = [
    'SPY', 'QQQ', 'IWM', 'DIA',
    'AAPL', 'TSLA', 'NVDA', 'AMD', 'MSFT', 'AMZN', 'GOOGL', 'META',
    'XLE', 'XLF', 'XLK', 'GLD', 'SLV', 'TLT'
  ]

  // Cache for scan results (10 minutes TTL for scanner)
  const scanCache = useDataCache<ScanSetup[]>({
    key: `scanner-results-${selectedSymbols.sort().join('-')}`,
    ttl: 10 * 60 * 1000 // 10 minutes - scans are expensive
  })

  useEffect(() => {
    fetchScanHistory()

    // Load cached scan results from persistent storage
    const cachedResults = dataStore.get<ScanSetup[]>('scanner_results')
    if (cachedResults) {
      setScanResults(cachedResults)
      console.log(`📦 Loaded ${cachedResults.length} cached scan results`)
    }
  }, [])

  const fetchScanHistory = async () => {
    try {
      const response = await apiClient.getScannerHistory(20)
      if (response.data.success) {
        setScanHistory(response.data.data)
      }
    } catch (error) {
      console.error('Error fetching scan history:', error)
    }
  }

  const handleScan = async () => {
    if (selectedSymbols.length === 0) {
      setError('Please select at least one symbol to scan')
      return
    }

    // Warn if too many symbols
    if (selectedSymbols.length > 10) {
      setScanWarning(`⚠️ Scanning ${selectedSymbols.length} symbols will take ~${Math.ceil(selectedSymbols.length * 0.5)} minutes due to API rate limiting. Consider scanning fewer symbols.`)
    } else {
      setScanWarning(null)
    }

    setLoading(true)
    setError(null)
    setScanResults([]) // Clear old results
    setScanningStatus({ symbol: 'Starting scan...', progress: '0%' })

    try {
      console.log('🔍 Starting scan for symbols:', selectedSymbols)
      console.log('📡 API URL:', process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000')
      console.log(`⏱️ Estimated time: ~${selectedSymbols.length * 20}s with rate limiting`)

      // Scan symbols ONE AT A TIME and show results as they come in
      const allResults: ScanSetup[] = []

      for (let i = 0; i < selectedSymbols.length; i++) {
        const symbol = selectedSymbols[i]
        const progress = Math.round(((i + 1) / selectedSymbols.length) * 100)

        setScanningStatus({
          symbol: `Scanning ${symbol}...`,
          progress: `${i + 1}/${selectedSymbols.length} (${progress}%)`
        })

        try {
          // Scan one symbol at a time
          const response = await apiClient.scanSymbols([symbol])

          if (response.data.success && response.data.results.length > 0) {
            // Add new results immediately
            allResults.push(...response.data.results)
            setScanResults([...allResults]) // Update UI with new results
            console.log(`✅ ${symbol}: Found ${response.data.results.length} opportunities`)
          } else {
            console.log(`⚠️ ${symbol}: No opportunities found`)
          }
        } catch (err) {
          console.error(`❌ ${symbol}: Scan failed`, err)
          // Continue scanning other symbols even if one fails
        }
      }

      console.log(`✅ Scan complete: ${allResults.length} total opportunities`)
      setScanningStatus(null)
      setScanWarning(null)

      // Cache the final results (persists across navigation)
      if (allResults.length > 0) {
        dataStore.set('scanner_results', allResults, 10 * 60 * 1000) // 10 min cache
      } else {
        setError(`No trading opportunities found for ${selectedSymbols.join(', ')}. Try different symbols or check if market is open.`)
      }

      // Refresh history
      await fetchScanHistory()

    } catch (error: any) {
      console.error('❌ Error scanning symbols:', error)

      let errorMessage = 'Scan failed. '

      if (error.code === 'ECONNREFUSED' || error.message?.includes('Network Error')) {
        errorMessage += 'Backend is not running. Start it with: python -m uvicorn backend.main:app --port 8000'
      } else if (error.response) {
        errorMessage += `Backend error: ${error.response.data?.detail || error.response.statusText}`
      } else {
        errorMessage += error.message || 'Unknown error'
      }

      setError(errorMessage)
      setScanResults([])
      setScanningStatus(null)
    } finally {
      setLoading(false)
    }
  }

  const handleLoadHistoricalScan = async (scanId: string) => {
    try {
      const response = await apiClient.getScanResults(scanId)
      if (response.data.success) {
        setScanResults(response.data.data)
        setCurrentScanId(scanId)
        setShowHistory(false)
      }
    } catch (error) {
      console.error('Error loading historical scan:', error)
    }
  }

  const toggleSymbol = (symbol: string) => {
    setSelectedSymbols(prev =>
      prev.includes(symbol)
        ? prev.filter(s => s !== symbol)
        : [...prev, symbol]
    )
  }

  const addCustomSymbol = () => {
    if (customSymbol && !selectedSymbols.includes(customSymbol.toUpperCase())) {
      setSelectedSymbols([...selectedSymbols, customSymbol.toUpperCase()])
      setCustomSymbol('')
    }
  }

  const formatTime = (timestamp: string) => {
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZone: 'America/Chicago'
    }).format(new Date(timestamp))
  }

  const getStrategyColor = (strategy: string) => {
    switch (strategy) {
      case 'NEGATIVE_GEX_SQUEEZE':
        return 'text-success border-success/30 bg-success/10'
      case 'POSITIVE_GEX_BREAKDOWN':
        return 'text-danger border-danger/30 bg-danger/10'
      case 'IRON_CONDOR':
        return 'text-primary border-primary/30 bg-primary/10'
      case 'PREMIUM_SELLING':
        return 'text-warning border-warning/30 bg-warning/10'
      default:
        return 'text-text-secondary border-border bg-background-hover'
    }
  }

  const getStrategyIcon = (strategy: string) => {
    switch (strategy) {
      case 'NEGATIVE_GEX_SQUEEZE':
        return <TrendingUp className="w-4 h-4" />
      case 'POSITIVE_GEX_BREAKDOWN':
        return <TrendingDown className="w-4 h-4" />
      case 'IRON_CONDOR':
        return <Target className="w-4 h-4" />
      case 'PREMIUM_SELLING':
        return <DollarSign className="w-4 h-4" />
      default:
        return <AlertCircle className="w-4 h-4" />
    }
  }

  return (
    <div className="min-h-screen">
      <Navigation />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-text-primary">Multi-Symbol Scanner</h1>
          <p className="text-text-secondary mt-1">Scan multiple symbols for trading opportunities using ALL 4 strategies</p>
          <p className="text-sm text-warning mt-2">
            💡 <strong>HOW TO MAKE MONEY:</strong> Find high-probability setups across all tickers, then execute the specific trade plan shown for each setup
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* Scanner Controls */}
          <div className="lg:col-span-1">
            <div className="card">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Search className="w-5 h-5 text-primary" />
                Select Symbols
              </h3>

              {/* Popular Symbols */}
              <div className="mb-4">
                <p className="text-sm text-text-muted mb-2">Popular Symbols:</p>
                <div className="flex flex-wrap gap-2">
                  {popularSymbols.map(symbol => (
                    <button
                      key={symbol}
                      onClick={() => toggleSymbol(symbol)}
                      className={`px-3 py-1 rounded text-sm font-medium transition-all ${
                        selectedSymbols.includes(symbol)
                          ? 'bg-primary text-white'
                          : 'bg-background-hover text-text-secondary hover:bg-background-deep'
                      }`}
                    >
                      {symbol}
                    </button>
                  ))}
                </div>
              </div>

              {/* Custom Symbol */}
              <div className="mb-4">
                <p className="text-sm text-text-muted mb-2">Add Custom Symbol:</p>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={customSymbol}
                    onChange={(e) => setCustomSymbol(e.target.value.toUpperCase())}
                    onKeyDown={(e) => e.key === 'Enter' && addCustomSymbol()}
                    placeholder="AAPL"
                    className="input flex-1"
                  />
                  <button onClick={addCustomSymbol} className="btn-secondary">
                    Add
                  </button>
                </div>
              </div>

              {/* Selected Symbols */}
              <div className="mb-4">
                <p className="text-sm text-text-muted mb-2">Selected ({selectedSymbols.length}):</p>
                <div className="flex flex-wrap gap-1">
                  {selectedSymbols.map(symbol => (
                    <span
                      key={symbol}
                      className="px-2 py-1 bg-primary/20 text-primary rounded text-xs font-medium flex items-center gap-1"
                    >
                      {symbol}
                      <button
                        onClick={() => toggleSymbol(symbol)}
                        className="hover:text-danger"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              {/* Warning Message */}
              {scanWarning && (
                <div className="mb-4 p-3 bg-warning/10 border border-warning/30 rounded-lg">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-warning text-xs">{scanWarning}</p>
                    </div>
                    <button
                      onClick={() => setScanWarning(null)}
                      className="text-warning hover:text-warning/70"
                    >
                      ×
                    </button>
                  </div>
                </div>
              )}

              {/* Error Message */}
              {error && (
                <div className="mb-4 p-3 bg-danger/10 border border-danger/30 rounded-lg">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="w-5 h-5 text-danger flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-danger text-sm font-semibold">Scanner Error</p>
                      <p className="text-danger/80 text-xs mt-1">{error}</p>
                    </div>
                    <button
                      onClick={() => setError(null)}
                      className="text-danger hover:text-danger/70"
                    >
                      ×
                    </button>
                  </div>
                </div>
              )}

              {/* Scanning Status Bar */}
              {scanningStatus && (
                <div className="mb-4 p-3 bg-primary/10 border border-primary/30 rounded-lg">
                  <div className="flex items-center gap-3">
                    <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin flex-shrink-0" />
                    <div className="flex-1">
                      <p className="text-primary text-sm font-semibold">{scanningStatus.symbol}</p>
                      <p className="text-primary/70 text-xs mt-0.5">Progress: {scanningStatus.progress}</p>
                    </div>
                  </div>
                  {/* Progress bar */}
                  <div className="mt-2 h-1.5 bg-background-deep rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all duration-300"
                      style={{ width: scanningStatus.progress.match(/\d+/)?.[0] + '%' || '0%' }}
                    />
                  </div>
                </div>
              )}

              {/* Scan Button */}
              <button
                onClick={handleScan}
                disabled={loading || selectedSymbols.length === 0}
                className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Scanning...
                  </>
                ) : (
                  <>
                    <Search className="w-4 h-4" />
                    Scan {selectedSymbols.length} Symbol{selectedSymbols.length !== 1 ? 's' : ''}
                  </>
                )}
              </button>

              {/* History Button */}
              <button
                onClick={() => setShowHistory(!showHistory)}
                className="btn-secondary w-full mt-2 flex items-center justify-center gap-2"
              >
                <History className="w-4 h-4" />
                {showHistory ? 'Hide' : 'View'} Scan History
              </button>

              {/* Scan Info */}
              {currentScanId && (
                <div className="mt-4 p-3 bg-background-hover rounded-lg">
                  <p className="text-xs text-text-muted">Current Scan:</p>
                  <p className="text-xs font-mono text-text-secondary">{currentScanId}</p>
                  <p className="text-xs text-text-muted mt-1">{formatTime(new Date().toISOString())}</p>
                </div>
              )}
            </div>
          </div>

          {/* Results */}
          <div className="lg:col-span-2">
            {showHistory ? (
              /* Scan History */
              <div className="card">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <History className="w-5 h-5 text-primary" />
                  Scan History
                </h3>

                <div className="space-y-2">
                  {scanHistory.length === 0 ? (
                    <p className="text-text-muted text-center py-8">No scan history yet. Run your first scan above!</p>
                  ) : (
                    scanHistory.map((run) => (
                      <div
                        key={run.id}
                        onClick={() => handleLoadHistoricalScan(run.id)}
                        className="p-4 bg-background-hover hover:bg-background-deep rounded-lg cursor-pointer transition-all"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <p className="font-medium text-text-primary">{run.opportunities_found} Opportunities Found</p>
                            <p className="text-sm text-text-muted">
                              Scanned: {run.symbols_scanned}
                            </p>
                            <p className="text-xs text-text-muted mt-1">
                              {formatTime(run.timestamp)} • {run.scan_duration_seconds.toFixed(1)}s
                            </p>
                          </div>
                          <div className="text-right">
                            <span className={`px-2 py-1 rounded text-xs font-medium ${
                              run.opportunities_found > 0 ? 'bg-success/20 text-success' : 'bg-text-muted/20 text-text-muted'
                            }`}>
                              {run.total_symbols} symbols
                            </span>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            ) : (
              /* Scan Results */
              <div className="card">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-primary" />
                  Opportunities Found ({scanResults.length})
                </h3>

                {scanResults.length === 0 ? (
                  <div className="text-center py-12">
                    <Search className="w-16 h-16 mx-auto text-text-muted opacity-50 mb-4" />
                    <p className="text-text-muted">No results yet. Select symbols and click "Scan" to find opportunities</p>
                    <p className="text-sm text-text-secondary mt-2">
                      The scanner checks ALL 4 strategies: Negative GEX Squeeze, Positive GEX Breakdown, Iron Condor, and Premium Selling
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {scanResults.map((setup, idx) => (
                      <div
                        key={idx}
                        onClick={() => setSelectedSetup(selectedSetup?.symbol === setup.symbol && selectedSetup?.strategy === setup.strategy ? null : setup)}
                        className={`p-4 rounded-lg border-2 transition-all cursor-pointer ${
                          selectedSetup?.symbol === setup.symbol && selectedSetup?.strategy === setup.strategy
                            ? 'border-primary bg-primary/5'
                            : 'border-border hover:border-border/50'
                        }`}
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-lg border ${getStrategyColor(setup.strategy)}`}>
                              {getStrategyIcon(setup.strategy)}
                            </div>
                            <div>
                              <h4 className="font-bold text-lg text-text-primary">{setup.symbol}</h4>
                              <p className="text-sm text-text-secondary">{setup.strategy.replace(/_/g, ' ')}</p>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="flex items-center gap-1 text-sm font-semibold text-success">
                              <CheckCircle className="w-4 h-4" />
                              {(setup.confidence * 100).toFixed(0)}% Confidence
                            </div>
                            <p className="text-xs text-text-muted">Win Rate: {(setup.win_rate * 100).toFixed(0)}%</p>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
                          <div>
                            <p className="text-xs text-text-muted">Price</p>
                            <p className="font-mono text-sm">${setup.spot_price.toFixed(2)}</p>
                          </div>
                          <div>
                            <p className="text-xs text-text-muted">Entry</p>
                            <p className="font-mono text-sm">${setup.entry_price.toFixed(2)}</p>
                          </div>
                          <div>
                            <p className="text-xs text-text-muted">Target</p>
                            <p className="font-mono text-sm text-success">
                              {setup.target_price ? `$${setup.target_price.toFixed(2)}` : 'Range'}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs text-text-muted">R:R</p>
                            <p className="font-mono text-sm">{setup.risk_reward.toFixed(1)}:1</p>
                          </div>
                        </div>

                        <p className="text-sm text-text-secondary">{setup.reasoning}</p>

                        {selectedSetup?.symbol === setup.symbol && selectedSetup?.strategy === setup.strategy && (
                          <div className="mt-4 pt-4 border-t border-border">
                            <h5 className="font-bold text-text-primary mb-2 flex items-center gap-2">
                              <DollarSign className="w-5 h-5 text-success" />
                              HOW TO MAKE MONEY WITH THIS SETUP
                            </h5>
                            <div className="bg-background-deep p-4 rounded-lg">
                              <pre className="whitespace-pre-wrap text-sm text-text-primary font-sans leading-relaxed">
                                {setup.money_making_plan}
                              </pre>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Strategy Guide */}
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">📚 Strategy Guide - How Each Setup Makes Money</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 bg-success/10 border border-success/30 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="w-5 h-5 text-success" />
                <h4 className="font-bold text-success">Negative GEX Squeeze</h4>
              </div>
              <p className="text-sm text-text-primary mb-2"><strong>Win Rate: 68%</strong> | R:R 3:1</p>
              <p className="text-sm text-text-secondary">
                <strong>When:</strong> Negative GEX + price near flip point<br />
                <strong>Trade:</strong> Buy CALL when price breaks flip<br />
                <strong>Why it works:</strong> MMs chase price UP creating squeeze<br />
                <strong>Exit:</strong> Call wall or 100% profit
              </p>
            </div>

            <div className="p-4 bg-danger/10 border border-danger/30 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <TrendingDown className="w-5 h-5 text-danger" />
                <h4 className="font-bold text-danger">Positive GEX Breakdown</h4>
              </div>
              <p className="text-sm text-text-primary mb-2"><strong>Win Rate: 62%</strong> | R:R 2.5:1</p>
              <p className="text-sm text-text-secondary">
                <strong>When:</strong> Positive GEX + breakdown below flip<br />
                <strong>Trade:</strong> Buy PUT when price breaks flip down<br />
                <strong>Why it works:</strong> MMs fade the move creating cascade<br />
                <strong>Exit:</strong> Put wall or 75% profit
              </p>
            </div>

            <div className="p-4 bg-primary/10 border border-primary/30 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Target className="w-5 h-5 text-primary" />
                <h4 className="font-bold text-primary">Iron Condor</h4>
              </div>
              <p className="text-sm text-text-primary mb-2"><strong>Win Rate: 72%</strong> | R:R 0.3:1</p>
              <p className="text-sm text-text-secondary">
                <strong>When:</strong> Positive GEX with wide walls<br />
                <strong>Trade:</strong> Sell Iron Condor at walls (5-10 DTE)<br />
                <strong>Why it works:</strong> Positive GEX pins price in range<br />
                <strong>Exit:</strong> 50% profit (close early!) or breach
              </p>
            </div>

            <div className="p-4 bg-warning/10 border border-warning/30 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <DollarSign className="w-5 h-5 text-warning" />
                <h4 className="font-bold text-warning">Premium Selling</h4>
              </div>
              <p className="text-sm text-text-primary mb-2"><strong>Win Rate: 65%</strong> | R:R 0.5:1</p>
              <p className="text-sm text-text-secondary">
                <strong>When:</strong> Price approaching wall<br />
                <strong>Trade:</strong> Sell CALL/PUT at wall (0-2 DTE)<br />
                <strong>Why it works:</strong> Walls reject price, theta works for you<br />
                <strong>Exit:</strong> 50-70% profit in 1 day or wall break
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
