'use client'

import { useState, useEffect } from 'react'
import { X, Scale, CheckCircle, XCircle, AlertTriangle, HelpCircle } from 'lucide-react'
import { apiClient } from '@/lib/api'

// ============================================================================
// STRATEGY COMPARISON MODAL
// ============================================================================

interface StrategyComparisonProps {
  isOpen: boolean
  onClose: () => void
}

export function StrategyComparison({ isOpen, onClose }: StrategyComparisonProps) {
  const [comparison, setComparison] = useState<string>('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (isOpen) {
      const fetchComparison = async () => {
        try {
          setLoading(true)
          const response = await apiClient.compareAvailableStrategies()
          if (response.data.success) {
            setComparison(response.data.data.comparison)
          }
        } catch (err) {
          setComparison('Unable to load strategy comparison.')
        } finally {
          setLoading(false)
        }
      }
      fetchComparison()
    }
  }, [isOpen])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-background-primary rounded-lg max-w-5xl w-full max-h-[90vh] overflow-hidden border border-border">
        <div className="flex items-center justify-between p-6 border-b border-border">
          <div className="flex items-center gap-2">
            <Scale className="w-6 h-6 text-primary" />
            <h2 className="text-2xl font-bold text-text-primary">⚖️ Strategy Comparison</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-background-hover rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto max-h-[calc(90vh-100px)]">
          {loading ? (
            <div className="animate-pulse space-y-4">
              {[...Array(10)].map((_, i) => (
                <div key={i} className="h-4 bg-background-hover rounded w-full"></div>
              ))}
            </div>
          ) : (
            <div className="prose prose-invert max-w-none">
              <div className="text-text-primary whitespace-pre-wrap leading-relaxed">
                {comparison}
              </div>
            </div>
          )}
        </div>

        <div className="p-6 border-t border-border bg-background-hover">
          <p className="text-sm text-text-secondary">
            AI-powered analysis by Claude Haiku 4.5 • Compares directional, iron condor, and wait strategies based on current market conditions
          </p>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// PRE-TRADE SAFETY CHECKLIST
// ============================================================================

interface PreTradeChecklistProps {
  isOpen: boolean
  onClose: () => void
  tradeData: {
    symbol: string
    strike: number
    option_type: string
    contracts: number
    cost_per_contract: number
    pattern_type?: string
    confidence?: number
  }
  onApprove?: () => void
}

export function PreTradeChecklist({ isOpen, onClose, tradeData, onApprove }: PreTradeChecklistProps) {
  const [checklist, setChecklist] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (isOpen && tradeData) {
      const fetchChecklist = async () => {
        try {
          setLoading(true)
          const response = await apiClient.generatePreTradeChecklist(tradeData)
          if (response.data.success) {
            setChecklist(response.data.data)
          }
        } catch (err) {
          setChecklist({ verdict: 'ERROR', analysis: 'Unable to load checklist.' })
        } finally {
          setLoading(false)
        }
      }
      fetchChecklist()
    }
  }, [isOpen, tradeData])

  if (!isOpen) return null

  const verdict = checklist?.checklist?.verdict || 'UNKNOWN'
  const isApproved = verdict === 'APPROVED'
  const isRejected = verdict === 'REJECTED'
  const isCaution = verdict === 'PROCEED_WITH_CAUTION'

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-background-primary rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden border border-border">
        <div className="flex items-center justify-between p-6 border-b border-border">
          <div className="flex items-center gap-2">
            {isApproved && <CheckCircle className="w-6 h-6 text-success" />}
            {isRejected && <XCircle className="w-6 h-6 text-danger" />}
            {isCaution && <AlertTriangle className="w-6 h-6 text-warning" />}
            <h2 className="text-2xl font-bold text-text-primary">✅ Pre-Trade Safety Checklist</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-background-hover rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto max-h-[calc(90vh-220px)]">
          {loading ? (
            <div className="animate-pulse space-y-4">
              {[...Array(12)].map((_, i) => (
                <div key={i} className="h-4 bg-background-hover rounded w-full"></div>
              ))}
            </div>
          ) : (
            <>
              {/* Trade Summary */}
              <div className="mb-6 p-4 bg-background-hover rounded-lg">
                <h3 className="font-semibold text-text-primary mb-2">Trade Summary</h3>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div><span className="text-text-secondary">Symbol:</span> <span className="text-text-primary font-semibold">{tradeData.symbol}</span></div>
                  <div><span className="text-text-secondary">Strike:</span> <span className="text-text-primary font-semibold">${tradeData.strike}</span></div>
                  <div><span className="text-text-secondary">Type:</span> <span className="text-text-primary font-semibold">{tradeData.option_type}</span></div>
                  <div><span className="text-text-secondary">Contracts:</span> <span className="text-text-primary font-semibold">{tradeData.contracts}</span></div>
                  <div><span className="text-text-secondary">Total Cost:</span> <span className="text-text-primary font-semibold">${(tradeData.contracts * tradeData.cost_per_contract * 100).toFixed(2)}</span></div>
                  {tradeData.confidence && (
                    <div><span className="text-text-secondary">Confidence:</span> <span className="text-text-primary font-semibold">{tradeData.confidence}%</span></div>
                  )}
                </div>
              </div>

              {/* Verdict */}
              <div className={`mb-6 p-6 rounded-lg border-2 ${
                isApproved ? 'bg-success/10 border-success' :
                isRejected ? 'bg-danger/10 border-danger' :
                'bg-warning/10 border-warning'
              }`}>
                <div className="flex items-center gap-3">
                  {isApproved && <CheckCircle className="w-8 h-8 text-success" />}
                  {isRejected && <XCircle className="w-8 h-8 text-danger" />}
                  {isCaution && <AlertTriangle className="w-8 h-8 text-warning" />}
                  <div>
                    <p className={`text-2xl font-bold ${
                      isApproved ? 'text-success' :
                      isRejected ? 'text-danger' :
                      'text-warning'
                    }`}>
                      {isApproved && '✅ TRADE APPROVED'}
                      {isRejected && '❌ TRADE REJECTED'}
                      {isCaution && '⚠️ PROCEED WITH CAUTION'}
                    </p>
                    <p className="text-sm text-text-secondary mt-1">
                      {isApproved && 'All 20 safety checks passed. Safe to execute.'}
                      {isRejected && 'Critical risk violations detected. Do not execute.'}
                      {isCaution && 'Some yellow flags detected. Review warnings before proceeding.'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Full Analysis */}
              <div className="prose prose-invert max-w-none">
                <div className="text-text-primary whitespace-pre-wrap leading-relaxed">
                  {checklist?.checklist?.analysis || JSON.stringify(checklist?.checklist, null, 2)}
                </div>
              </div>

              {/* Trade Metrics */}
              {checklist?.trade_metrics && (
                <div className="mt-6 p-4 bg-background-hover rounded-lg">
                  <h3 className="font-semibold text-text-primary mb-3">Risk Metrics</h3>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <span className="text-text-secondary">Position Size:</span>
                      <span className={`ml-2 font-semibold ${checklist.trade_metrics.position_size_pct < 20 ? 'text-success' : 'text-danger'}`}>
                        {checklist.trade_metrics.position_size_pct?.toFixed(1)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-text-secondary">Daily Loss:</span>
                      <span className={`ml-2 font-semibold ${checklist.trade_metrics.daily_loss_pct < 5 ? 'text-success' : 'text-danger'}`}>
                        {checklist.trade_metrics.daily_loss_pct?.toFixed(1)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-text-secondary">Total Exposure:</span>
                      <span className={`ml-2 font-semibold ${checklist.trade_metrics.total_exposure_pct < 50 ? 'text-success' : 'text-danger'}`}>
                        {checklist.trade_metrics.total_exposure_pct?.toFixed(1)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-text-secondary">Pattern Win Rate:</span>
                      <span className={`ml-2 font-semibold ${checklist.trade_metrics.pattern_win_rate >= 60 ? 'text-success' : 'text-warning'}`}>
                        {checklist.trade_metrics.pattern_win_rate?.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-6 border-t border-border bg-background-hover flex items-center justify-between">
          <p className="text-sm text-text-secondary">
            AI-powered safety analysis • 20+ validation checks
          </p>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg border border-border hover:bg-background-hover transition-colors"
            >
              Cancel
            </button>
            {isApproved && onApprove && (
              <button
                onClick={onApprove}
                className="px-6 py-2 bg-success hover:bg-success/80 text-white rounded-lg font-semibold transition-colors"
              >
                Execute Trade
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// GREEK EXPLAINER TOOLTIP
// ============================================================================

interface GreekTooltipProps {
  greek: 'delta' | 'theta' | 'gamma' | 'vega'
  value: number
  strike: number
  currentPrice: number
  contracts: number
  optionType: string
  daysToExpiration?: number
  children: React.ReactNode
}

export function GreekTooltip({
  greek,
  value,
  strike,
  currentPrice,
  contracts,
  optionType,
  daysToExpiration = 3,
  children
}: GreekTooltipProps) {
  const [explanation, setExplanation] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [show, setShow] = useState(false)

  const fetchExplanation = async () => {
    if (explanation) return // Already loaded

    try {
      setLoading(true)
      const response = await apiClient.explainGreek({
        greek,
        value,
        strike,
        current_price: currentPrice,
        contracts,
        option_type: optionType,
        days_to_expiration: daysToExpiration
      })

      if (response.data.success) {
        setExplanation(response.data.data.explanation)
      }
    } catch (err) {
      setExplanation('Unable to load explanation.')
    } finally {
      setLoading(false)
    }
  }

  const handleMouseEnter = () => {
    setShow(true)
    fetchExplanation()
  }

  return (
    <div className="relative inline-block">
      <div
        onMouseEnter={handleMouseEnter}
        onMouseLeave={() => setShow(false)}
        className="cursor-help border-b border-dashed border-text-secondary"
      >
        {children}
      </div>

      {show && (
        <div className="absolute z-50 w-96 p-4 bg-background-primary border border-border rounded-lg shadow-xl left-0 top-full mt-2">
          <div className="flex items-center gap-2 mb-2">
            <HelpCircle className="w-4 h-4 text-primary" />
            <span className="font-semibold text-primary uppercase">{greek}</span>
            <span className="text-text-primary font-bold">{value}</span>
          </div>

          {loading ? (
            <div className="animate-pulse space-y-2">
              <div className="h-3 bg-background-hover rounded w-full"></div>
              <div className="h-3 bg-background-hover rounded w-5/6"></div>
              <div className="h-3 bg-background-hover rounded w-4/6"></div>
            </div>
          ) : (
            <div className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">
              {explanation}
            </div>
          )}

          <div className="mt-3 pt-3 border-t border-border">
            <p className="text-xs text-text-muted">AI-powered context-aware explanation</p>
          </div>
        </div>
      )}
    </div>
  )
}
