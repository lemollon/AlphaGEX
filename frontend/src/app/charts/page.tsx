'use client'

import { useState } from 'react'
import Navigation from '@/components/Navigation'
import TradingViewWidget from '@/components/TradingViewWidget'
import { TrendingUp, BarChart3, Activity } from 'lucide-react'

export default function ChartsPage() {
  const [symbol, setSymbol] = useState('SPY')
  const [interval, setInterval] = useState('D')

  const symbols = ['SPY', 'QQQ', 'IWM', 'DIA', 'VIX']
  const intervals = [
    { value: '1', label: '1min' },
    { value: '5', label: '5min' },
    { value: '15', label: '15min' },
    { value: '60', label: '1H' },
    { value: 'D', label: 'Daily' },
    { value: 'W', label: 'Weekly' }
  ]

  return (
    <div className="min-h-screen">
      <Navigation />

      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Activity className="w-8 h-8 text-primary" />
                <div>
                  <h1 className="text-3xl font-bold text-text-primary">Advanced Charts</h1>
                  <p className="text-sm text-text-secondary mt-1">
                    Full TradingView Pro experience with all indicators and drawing tools
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Controls */}
          <div className="card mb-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div>
                  <label className="text-xs text-text-secondary mb-1 block">Symbol</label>
                  <div className="flex gap-2">
                    {symbols.map((sym) => (
                      <button
                        key={sym}
                        onClick={() => setSymbol(sym)}
                        className={`px-4 py-2 rounded-lg font-semibold transition-colors ${
                          symbol === sym
                            ? 'bg-primary text-white'
                            : 'bg-background-hover text-text-secondary hover:text-text-primary'
                        }`}
                      >
                        {sym}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-xs text-text-secondary mb-1 block">Timeframe</label>
                  <div className="flex gap-2">
                    {intervals.map((int) => (
                      <button
                        key={int.value}
                        onClick={() => setInterval(int.value)}
                        className={`px-3 py-2 rounded-lg text-sm font-semibold transition-colors ${
                          interval === int.value
                            ? 'bg-primary text-white'
                            : 'bg-background-hover text-text-secondary hover:text-text-primary'
                        }`}
                      >
                        {int.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* TradingView Widget - Full Screen */}
          <div className="card">
            <div className="bg-background-deep rounded-lg overflow-hidden" style={{ height: 'calc(100vh - 400px)', minHeight: '600px' }}>
              <TradingViewWidget
                symbol={symbol}
                interval={interval}
                theme="dark"
                height={'100%'}
                autosize={true}
              />
            </div>
          </div>

          {/* Info Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">
            <div className="card">
              <div className="flex items-center gap-3 mb-3">
                <TrendingUp className="w-5 h-5 text-primary" />
                <h3 className="font-semibold">Real-Time Data</h3>
              </div>
              <p className="text-sm text-text-secondary">
                Access your TradingView Pro subscription with real-time market data and advanced charting tools.
              </p>
            </div>

            <div className="card">
              <div className="flex items-center gap-3 mb-3">
                <BarChart3 className="w-5 h-5 text-primary" />
                <h3 className="font-semibold">Full Indicators</h3>
              </div>
              <p className="text-sm text-text-secondary">
                All TradingView indicators, drawing tools, and custom scripts available for deep technical analysis.
              </p>
            </div>

            <div className="card">
              <div className="flex items-center gap-3 mb-3">
                <Activity className="w-5 h-5 text-primary" />
                <h3 className="font-semibold">Multiple Timeframes</h3>
              </div>
              <p className="text-sm text-text-secondary">
                Switch between 1-minute to weekly timeframes to analyze market structure at any scale.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
