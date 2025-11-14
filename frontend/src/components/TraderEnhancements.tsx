'use client'

import { useState } from 'react'
import { X, Brain, Target, AlertTriangle, TrendingUp } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface TradeExplainerProps {
  tradeId: string
  onClose: () => void
}

function TradeExplainer({ tradeId, onClose }: TradeExplainerProps) {
  const [explanation, setExplanation] = useState<string>('')
  const [loading, setLoading] = useState(true)

  useState(() => {
    const fetchExplanation = async () => {
      try {
        const response = await apiClient.explainTrade(tradeId)
        if (response.data.success) {
          setExplanation(response.data.data.explanation)
        }
      } catch (err) {
        setExplanation('Unable to load trade explanation.')
      } finally {
        setLoading(false)
      }
    }
    fetchExplanation()
  })

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-background-primary rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden border border-border">
        <div className="flex items-center justify-between p-6 border-b border-border">
          <div className="flex items-center gap-2">
            <Brain className="w-6 h-6 text-primary" />
            <h2 className="text-2xl font-bold text-text-primary">🧠 AI Trade Breakdown</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-background-hover rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto max-h-[calc(90vh-100px)]">
          {loading ? (
            <div className="animate-pulse space-y-4">
              {[...Array(8)].map((_, i) => (
                <div key={i} className="h-4 bg-background-hover rounded w-full"></div>
              ))}
            </div>
          ) : (
            <div className="prose prose-invert max-w-none">
              <div className="text-text-primary whitespace-pre-wrap leading-relaxed">
                {explanation}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

interface PositionGuidanceProps {
  tradeId: string
  onClose: () => void
}

function PositionGuidance({ tradeId, onClose }: PositionGuidanceProps) {
  const [guidance, setGuidance] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [currentStatus, setCurrentStatus] = useState<any>(null)

  useState(() => {
    const fetchGuidance = async () => {
      try {
        const response = await apiClient.getPositionGuidance(tradeId)
        if (response.data.success) {
          setGuidance(response.data.data.guidance)
          setCurrentStatus(response.data.data.current_status)
        }
      } catch (err) {
        setGuidance('Unable to load position guidance.')
      } finally {
        setLoading(false)
      }
    }
    fetchGuidance()
  })

  const isProfitable = currentStatus?.pnl_pct >= 0

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-background-primary rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden border border-border">
        <div className="flex items-center justify-between p-6 border-b border-border">
          <div className="flex items-center gap-2">
            <Target className="w-6 h-6 text-warning" />
            <h2 className="text-2xl font-bold text-text-primary">🎯 Position Management</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-background-hover rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        {currentStatus && (
          <div className={`p-4 border-b border-border ${isProfitable ? 'bg-success/10' : 'bg-danger/10'}`}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-text-secondary">Current P&L</p>
                <p className={`text-2xl font-bold ${isProfitable ? 'text-success' : 'text-danger'}`}>
                  ${currentStatus.total_pnl?.toFixed(2)} ({isProfitable ? '+' : ''}{currentStatus.pnl_pct?.toFixed(1)}%)
                </p>
              </div>
              <div className={`p-4 rounded-lg ${isProfitable ? 'bg-success/20' : 'bg-danger/20'}`}>
                {isProfitable ? (
                  <TrendingUp className="w-8 h-8 text-success" />
                ) : (
                  <AlertTriangle className="w-8 h-8 text-danger" />
                )}
              </div>
            </div>
          </div>
        )}

        <div className="p-6 overflow-y-auto max-h-[calc(90vh-220px)]">
          {loading ? (
            <div className="animate-pulse space-y-4">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="h-4 bg-background-hover rounded w-full"></div>
              ))}
            </div>
          ) : (
            <div className="prose prose-invert max-w-none">
              <div className="text-text-primary whitespace-pre-wrap leading-relaxed">
                {guidance}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

interface TraderEnhancementsProps {
  trades: any[]
  openPositions: any[]
}

export default function TraderEnhancements({ trades, openPositions }: TraderEnhancementsProps) {
  const [selectedTradeForExplanation, setSelectedTradeForExplanation] = useState<string | null>(null)
  const [selectedTradeForGuidance, setSelectedTradeForGuidance] = useState<string | null>(null)

  return (
    <>
      {/* Add "Explain" button to recent trades */}
      {trades.map((trade, idx) => (
        <button
          key={trade.id || idx}
          onClick={() => setSelectedTradeForExplanation(trade.id || trade.timestamp)}
          className="text-xs text-primary hover:underline font-medium"
        >
          🧠 Explain
        </button>
      ))}

      {/* Add "Manage" button to open positions */}
      {openPositions.map((pos, idx) => (
        <button
          key={pos.id || idx}
          onClick={() => setSelectedTradeForGuidance(pos.id || pos.timestamp)}
          className="text-xs text-warning hover:underline font-medium"
        >
          🎯 Manage
        </button>
      ))}

      {/* Trade Explainer Modal */}
      {selectedTradeForExplanation && (
        <TradeExplainer
          tradeId={selectedTradeForExplanation}
          onClose={() => setSelectedTradeForExplanation(null)}
        />
      )}

      {/* Position Guidance Modal */}
      {selectedTradeForGuidance && (
        <PositionGuidance
          tradeId={selectedTradeForGuidance}
          onClose={() => setSelectedTradeForGuidance(null)}
        />
      )}
    </>
  )
}

export { TradeExplainer, PositionGuidance }
