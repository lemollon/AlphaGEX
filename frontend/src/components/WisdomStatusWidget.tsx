'use client'

import { useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { api } from '@/lib/api'
import {
  Brain,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Target,
  Activity,
  TrendingUp
} from 'lucide-react'

const fetcher = (url: string) => api.get(url).then(res => res.data)

interface SAGEStatus {
  ml_library_available: boolean
  model_trained: boolean
  model_version: string | null
  training_data_available: number
  can_train: boolean
  should_trust_predictions: boolean
  honest_assessment: string
  training_metrics?: {
    accuracy: number
    precision: number
    recall: number
    f1: number
    auc_roc: number
  }
}

interface BotMLStatus {
  bot_name: string
  ml_enabled: boolean
  min_win_probability: number
  last_prediction?: {
    win_probability: number
    advice: string
    confidence: number
    timestamp: string
  }
}

export default function WisdomStatusWidget() {
  const [expanded, setExpanded] = useState(true)

  const { data: statusData, isLoading, mutate } = useSWR<SAGEStatus>(
    '/api/ml/wisdom/status',
    fetcher,
    { refreshInterval: 30000 }
  )

  const { data: botStatusData } = useSWR<{ data: { bots: BotMLStatus[] } }>(
    '/api/ml/bot-status',
    fetcher,
    { refreshInterval: 30000 }
  )

  const status = statusData
  const bots = botStatusData?.data?.bots || []
  const activeBots = bots.filter(b => b.ml_enabled).length

  // Calculate overall health
  const isHealthy = status?.model_trained && status?.should_trust_predictions
  const needsTraining = status?.can_train && !status?.model_trained
  const accuracy = status?.training_metrics?.accuracy || 0

  if (isLoading) {
    return (
      <div className="card bg-gradient-to-r from-purple-500/5 to-transparent border border-purple-500/20 animate-pulse">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-background-hover rounded-lg" />
          <div className="flex-1">
            <div className="h-4 w-32 bg-background-hover rounded mb-2" />
            <div className="h-3 w-24 bg-background-hover rounded" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="card bg-gradient-to-r from-purple-500/5 to-transparent border border-purple-500/20">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-purple-500/10">
            <Brain className="w-5 h-5 text-purple-500" />
          </div>
          <div className="text-left">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              WISDOM ML Advisor
              {isHealthy && <Sparkles className="w-3 h-3 text-purple-400" />}
            </h3>
            <div className="flex items-center gap-3 text-xs text-text-muted">
              {status?.model_trained ? (
                <span className="flex items-center gap-1 text-success">
                  <CheckCircle className="w-3 h-3" />
                  Trained
                </span>
              ) : needsTraining ? (
                <span className="flex items-center gap-1 text-warning">
                  <AlertTriangle className="w-3 h-3" />
                  Needs Training
                </span>
              ) : (
                <span className="flex items-center gap-1 text-text-muted">
                  <XCircle className="w-3 h-3" />
                  Not Ready
                </span>
              )}
              {accuracy > 0 && (
                <span className="text-purple-400">
                  {(accuracy * 100).toFixed(0)}% accuracy
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation()
              mutate()
            }}
            className="p-1.5 rounded-lg hover:bg-purple-500/10 transition-colors"
          >
            <RefreshCw className="w-4 h-4 text-purple-500" />
          </button>
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-purple-500" />
          ) : (
            <ChevronDown className="w-5 h-5 text-purple-500" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border/50 animate-fade-in">
          {/* Status Grid */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="p-3 bg-background-hover rounded-lg text-center">
              <div className="text-xs text-text-muted mb-1">Model</div>
              <div className="text-sm font-bold text-text-primary">
                {status?.model_version || 'None'}
              </div>
            </div>
            <div className="p-3 bg-background-hover rounded-lg text-center">
              <div className="text-xs text-text-muted mb-1">Training Data</div>
              <div className="text-sm font-bold text-text-primary">
                {status?.training_data_available || 0}
              </div>
            </div>
            <div className="p-3 bg-background-hover rounded-lg text-center">
              <div className="text-xs text-text-muted mb-1">Active Bots</div>
              <div className="text-sm font-bold text-purple-400">
                {activeBots}/{bots.length}
              </div>
            </div>
          </div>

          {/* Metrics Row */}
          {status?.training_metrics && (
            <div className="grid grid-cols-4 gap-2 mb-4">
              <div className="p-2 bg-purple-500/10 rounded text-center">
                <div className="text-[10px] text-text-muted">Accuracy</div>
                <div className="text-xs font-bold text-purple-400">
                  {(status.training_metrics.accuracy * 100).toFixed(1)}%
                </div>
              </div>
              <div className="p-2 bg-purple-500/10 rounded text-center">
                <div className="text-[10px] text-text-muted">Precision</div>
                <div className="text-xs font-bold text-purple-400">
                  {(status.training_metrics.precision * 100).toFixed(1)}%
                </div>
              </div>
              <div className="p-2 bg-purple-500/10 rounded text-center">
                <div className="text-[10px] text-text-muted">Recall</div>
                <div className="text-xs font-bold text-purple-400">
                  {(status.training_metrics.recall * 100).toFixed(1)}%
                </div>
              </div>
              <div className="p-2 bg-purple-500/10 rounded text-center">
                <div className="text-[10px] text-text-muted">AUC-ROC</div>
                <div className="text-xs font-bold text-purple-400">
                  {(status.training_metrics.auc_roc * 100).toFixed(1)}%
                </div>
              </div>
            </div>
          )}

          {/* Trust Assessment */}
          <div className={`p-3 rounded-lg mb-4 ${
            status?.should_trust_predictions
              ? 'bg-success/10 border border-success/30'
              : 'bg-warning/10 border border-warning/30'
          }`}>
            <div className="flex items-start gap-2">
              {status?.should_trust_predictions ? (
                <CheckCircle className="w-4 h-4 text-success mt-0.5" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-warning mt-0.5" />
              )}
              <div className="text-xs text-text-secondary">
                {status?.honest_assessment || 'ML system initializing...'}
              </div>
            </div>
          </div>

          {/* Quick Link */}
          <Link
            href="/wisdom"
            className="flex items-center justify-center gap-2 w-full px-4 py-2 text-sm font-medium text-purple-400 bg-purple-500/10 rounded-lg hover:bg-purple-500/20 transition-colors"
          >
            <Brain className="w-4 h-4" />
            Open WISDOM Dashboard
          </Link>
        </div>
      )}
    </div>
  )
}
