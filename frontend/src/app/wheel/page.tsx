'use client'

import { useState, useEffect } from 'react'
import {
  RotateCcw, RefreshCw, Plus, ArrowRight, DollarSign,
  TrendingUp, TrendingDown, CheckCircle, AlertCircle,
  Calendar, Target, Clock, ChevronDown, CircleDot
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import WheelDashboard from '@/components/trader/WheelDashboard'
import ExportButtons from '@/components/trader/ExportButtons'
import { api } from '@/lib/api'

interface WheelPhaseInfo {
  id: string
  name: string
  description: string
  next_if_otm?: string
  next_if_itm?: string
  cost_basis?: string
  next?: string
  total_profit?: string
}

interface StartWheelForm {
  symbol: string
  strike: string
  expiration_date: string
  contracts: string
  premium: string
  underlying_price: string
  delta: string
}

export default function WheelPage() {
  const [phases, setPhases] = useState<WheelPhaseInfo[]>([])
  const [showStartForm, setShowStartForm] = useState(false)
  const [formData, setFormData] = useState<StartWheelForm>({
    symbol: 'SPY',
    strike: '',
    expiration_date: '',
    contracts: '1',
    premium: '',
    underlying_price: '',
    delta: '0.30'
  })
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    fetchPhases()
  }, [])

  const fetchPhases = async () => {
    try {
      const res = await api.get('/api/wheel/phases')
      setPhases(res.data.data.phases || [])
    } catch (err) {
      console.error('Error fetching phases:', err)
    }
  }

  const handleStartWheel = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setMessage(null)

    try {
      const payload = {
        symbol: formData.symbol,
        strike: parseFloat(formData.strike),
        expiration_date: formData.expiration_date,
        contracts: parseInt(formData.contracts),
        premium: parseFloat(formData.premium),
        underlying_price: parseFloat(formData.underlying_price),
        delta: parseFloat(formData.delta)
      }

      const res = await api.post('/api/wheel/start', payload)

      if (res.data.success) {
        setMessage({ type: 'success', text: `Started wheel cycle #${res.data.data.cycle_id}` })
        setShowStartForm(false)
        setFormData({
          symbol: 'SPY',
          strike: '',
          expiration_date: '',
          contracts: '1',
          premium: '',
          underlying_price: '',
          delta: '0.30'
        })
        // Refresh the dashboard
        window.location.reload()
      }
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Failed to start wheel cycle' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-900">
      <Navigation />

      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-purple-500/20 rounded-xl">
              <RotateCcw className="w-8 h-8 text-purple-400" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-white">Wheel Strategy</h1>
              <p className="text-gray-400">Premium income through systematic options selling</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <ExportButtons symbol="SPY" />
            <button
              onClick={() => setShowStartForm(!showStartForm)}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg transition-colors"
            >
              <Plus className="w-4 h-4" />
              <span>Start New Wheel</span>
            </button>
          </div>
        </div>

        {/* Messages */}
        {message && (
          <div className={`mb-6 p-4 rounded-lg flex items-center gap-2 ${
            message.type === 'success' ? 'bg-green-500/10 border border-green-500/50 text-green-400' : 'bg-red-500/10 border border-red-500/50 text-red-400'
          }`}>
            {message.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
            <span>{message.text}</span>
          </div>
        )}

        {/* Start Wheel Form */}
        {showStartForm && (
          <div className="mb-8 bg-slate-800/50 rounded-lg p-6 border border-slate-700">
            <h2 className="text-xl font-semibold text-white mb-4">Start New Wheel Cycle (Sell CSP)</h2>
            <form onSubmit={handleStartWheel} className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Symbol</label>
                <input
                  type="text"
                  value={formData.symbol}
                  onChange={(e) => setFormData({ ...formData, symbol: e.target.value.toUpperCase() })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-purple-500 focus:outline-none"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Strike Price</label>
                <input
                  type="number"
                  step="0.5"
                  value={formData.strike}
                  onChange={(e) => setFormData({ ...formData, strike: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-purple-500 focus:outline-none"
                  placeholder="e.g., 450"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Expiration Date</label>
                <input
                  type="date"
                  value={formData.expiration_date}
                  onChange={(e) => setFormData({ ...formData, expiration_date: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-purple-500 focus:outline-none"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Contracts</label>
                <input
                  type="number"
                  min="1"
                  value={formData.contracts}
                  onChange={(e) => setFormData({ ...formData, contracts: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-purple-500 focus:outline-none"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Premium (per contract)</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.premium}
                  onChange={(e) => setFormData({ ...formData, premium: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-purple-500 focus:outline-none"
                  placeholder="e.g., 2.50"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Current Price (underlying)</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.underlying_price}
                  onChange={(e) => setFormData({ ...formData, underlying_price: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-purple-500 focus:outline-none"
                  placeholder="e.g., 455.50"
                  required
                />
              </div>
              <div className="md:col-span-3 flex gap-3">
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-6 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-purple-800 disabled:cursor-not-allowed rounded-lg transition-colors flex items-center gap-2"
                >
                  {submitting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Starting...
                    </>
                  ) : (
                    <>
                      <Plus className="w-4 h-4" />
                      Start Wheel (Sell CSP)
                    </>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => setShowStartForm(false)}
                  className="px-6 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {/* How The Wheel Works */}
        <div className="mb-8 bg-slate-800/50 rounded-lg p-6 border border-slate-700">
          <h2 className="text-xl font-semibold text-white mb-4">How The Wheel Works</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {phases.map((phase, index) => (
              <div key={phase.id} className="relative">
                <div className={`p-4 rounded-lg border ${
                  phase.id === 'CSP' ? 'bg-blue-500/10 border-blue-500/30' :
                  phase.id === 'ASSIGNED' ? 'bg-yellow-500/10 border-yellow-500/30' :
                  phase.id === 'COVERED_CALL' ? 'bg-purple-500/10 border-purple-500/30' :
                  'bg-green-500/10 border-green-500/30'
                }`}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                      phase.id === 'CSP' ? 'bg-blue-500 text-white' :
                      phase.id === 'ASSIGNED' ? 'bg-yellow-500 text-black' :
                      phase.id === 'COVERED_CALL' ? 'bg-purple-500 text-white' :
                      'bg-green-500 text-white'
                    }`}>
                      {index + 1}
                    </span>
                    <h3 className="font-medium text-white">{phase.name}</h3>
                  </div>
                  <p className="text-sm text-gray-400 mb-3">{phase.description}</p>
                  {phase.next_if_otm && (
                    <div className="text-xs text-gray-500">
                      <p className="text-green-400">If OTM: {phase.next_if_otm}</p>
                      {phase.next_if_itm && <p className="text-yellow-400">If ITM: {phase.next_if_itm}</p>}
                    </div>
                  )}
                  {phase.cost_basis && (
                    <p className="text-xs text-gray-500 mt-2">Cost basis: {phase.cost_basis}</p>
                  )}
                </div>
                {index < phases.length - 1 && (
                  <div className="hidden md:block absolute top-1/2 -right-2 transform -translate-y-1/2 z-10">
                    <ArrowRight className="w-4 h-4 text-gray-600" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Main Dashboard */}
        <WheelDashboard />
      </main>
    </div>
  )
}
