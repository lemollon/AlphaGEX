'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Eye,
  Brain,
  TrendingUp,
  Minus,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Shield,
  Clock
} from 'lucide-react'
import { api } from '@/lib/api'

interface OracleAPIResponse {
  recommended_strategy: 'IC' | 'DIRECTIONAL' | 'HOLD'
  confidence: number
  reasoning: string
  vix_regime: string
  gex_regime: string
  ic_suitability?: number
  dir_suitability?: number
  size_multiplier?: number
  market_data?: {
    spot_price: number
    vix: number
    call_wall: number
    put_wall: number
  }
  timestamp?: string
}

function formatCentralTime(timestamp?: string): string {
  if (!timestamp) return ''
  try {
    const date = new Date(timestamp)
    return date.toLocaleTimeString('en-US', {
      timeZone: 'America/Chicago',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    }) + ' CT'
  } catch {
    return ''
  }
}

export default function OracleRecommendationWidget() {
  const [expanded, setExpanded] = useState(false) // Default collapsed
  const [loading, setLoading] = useState(true)
  const [recommendation, setRecommendation] = useState<OracleAPIResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<string>('')

  const fetchRecommendation = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.get('/api/oracle/strategy-recommendation')
      const data = response.data
      if (data && (data.recommended_strategy || data.strategy)) {
        const normalized: OracleAPIResponse = {
          recommended_strategy: data.recommended_strategy || data.strategy || 'HOLD',
          confidence: data.confidence || 0,
          reasoning: data.reasoning || '',
          vix_regime: data.vix_regime || 'UNKNOWN',
          gex_regime: data.gex_regime || 'UNKNOWN',
          ic_suitability: data.ic_suitability,
          dir_suitability: data.dir_suitability,
          size_multiplier: data.size_multiplier,
          market_data: data.market_data,
          timestamp: data.timestamp
        }
        setRecommendation(normalized)
        setLastUpdated(formatCentralTime(data.timestamp) || new Date().toLocaleTimeString('en-US', {
          timeZone: 'America/Chicago',
          hour: '2-digit',
          minute: '2-digit',
          hour12: true
        }) + ' CT')
      } else {
        setError('No recommendation available')
      }
    } catch (err) {
      setError('Failed to load Oracle recommendation')
      console.error('Oracle recommendation error:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchRecommendation()
    const interval = setInterval(fetchRecommendation, 60000)
    return () => clearInterval(interval)
  }, [])

  const getStrategyConfig = (strategy: string) => {
    switch (strategy) {
      case 'IC':
        return {
          label: 'Iron Condor',
          icon: <Shield className="w-4 h-4" />,
          text: 'text-success'
        }
      case 'DIRECTIONAL':
        return {
          label: 'Directional',
          icon: <TrendingUp className="w-4 h-4" />,
          text: 'text-primary'
        }
      case 'HOLD':
      default:
        return {
          label: 'Hold / Wait',
          icon: <Minus className="w-4 h-4" />,
          text: 'text-warning'
        }
    }
  }

  const config = recommendation ? getStrategyConfig(recommendation.recommended_strategy) : null

  return (
    <div className="card bg-gradient-to-r from-info/5 to-transparent border border-info/20">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-info/10">
            <Eye className="w-5 h-5 text-info" />
          </div>
          <div className="text-left">
            <h3 className="text-sm font-semibold text-text-primary">Oracle Strategy</h3>
            <div className="flex items-center gap-2 text-xs text-text-muted">
              {loading ? (
                <span>Loading...</span>
              ) : recommendation ? (
                <>
                  <span className={config?.text}>{config?.label}</span>
                  <span className="opacity-50">|</span>
                  <span>{Math.round(recommendation.confidence)}%</span>
                </>
              ) : (
                <span>Unavailable</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation()
              fetchRecommendation()
            }}
            className={`p-1.5 rounded-lg hover:bg-info/10 transition-colors ${loading ? 'animate-spin' : ''}`}
          >
            <RefreshCw className="w-4 h-4 text-info" />
          </button>
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-info" />
          ) : (
            <ChevronDown className="w-5 h-5 text-info" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-border/50 animate-fade-in">
          {loading ? (
            <div className="h-12 bg-background-hover animate-pulse rounded-lg" />
          ) : error ? (
            <div className="p-2 bg-warning/10 border border-warning/20 rounded-lg flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-warning" />
              <span className="text-xs text-warning">{error}</span>
            </div>
          ) : recommendation && config ? (
            <div className="space-y-2">
              {/* Compact stats row */}
              <div className="grid grid-cols-4 gap-2 text-center">
                <div className="p-2 bg-background-hover rounded">
                  <div className="text-[10px] text-text-muted">VIX</div>
                  <div className={`text-xs font-semibold ${
                    recommendation.vix_regime?.includes('HIGH') ? 'text-danger' :
                    recommendation.vix_regime?.includes('ELEVATED') ? 'text-warning' :
                    'text-success'
                  }`}>
                    {recommendation.vix_regime?.split('_')[0] || '?'}
                  </div>
                </div>
                <div className="p-2 bg-background-hover rounded">
                  <div className="text-[10px] text-text-muted">GEX</div>
                  <div className={`text-xs font-semibold ${
                    recommendation.gex_regime?.includes('NEGATIVE') ? 'text-danger' :
                    recommendation.gex_regime?.includes('POSITIVE') ? 'text-success' :
                    'text-warning'
                  }`}>
                    {recommendation.gex_regime?.split('_')[0] || '?'}
                  </div>
                </div>
                <div className="p-2 bg-background-hover rounded">
                  <div className="text-[10px] text-text-muted">IC</div>
                  <div className={`text-xs font-semibold ${
                    (recommendation.ic_suitability || 0) >= 0.6 ? 'text-success' :
                    (recommendation.ic_suitability || 0) >= 0.4 ? 'text-warning' : 'text-danger'
                  }`}>
                    {recommendation.ic_suitability !== undefined ? `${(recommendation.ic_suitability * 100).toFixed(0)}%` : '-'}
                  </div>
                </div>
                <div className="p-2 bg-background-hover rounded">
                  <div className="text-[10px] text-text-muted">DIR</div>
                  <div className={`text-xs font-semibold ${
                    (recommendation.dir_suitability || 0) >= 0.6 ? 'text-success' :
                    (recommendation.dir_suitability || 0) >= 0.4 ? 'text-warning' : 'text-danger'
                  }`}>
                    {recommendation.dir_suitability !== undefined ? `${(recommendation.dir_suitability * 100).toFixed(0)}%` : '-'}
                  </div>
                </div>
              </div>

              {/* Oracle Reasoning (includes Solomon info) */}
              {recommendation.reasoning && (
                <div className="p-2 bg-background-hover rounded text-xs">
                  <div className="text-[10px] text-text-muted mb-1 font-semibold">Oracle Reasoning</div>
                  <div className="text-text-secondary leading-relaxed">
                    {recommendation.reasoning.split(' | ').map((part, i) => (
                      <span key={i} className={`${
                        part.includes('SOLOMON INFO') ? 'text-amber-400' :
                        part.includes('RESULT') ? 'text-info font-medium' :
                        ''
                      }`}>
                        {i > 0 && <span className="text-text-muted mx-1">|</span>}
                        {part}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Footer row */}
              <div className="flex items-center justify-between">
                {lastUpdated && (
                  <div className="flex items-center gap-1 text-[10px] text-text-muted">
                    <Clock className="w-3 h-3" />
                    <span>{lastUpdated}</span>
                  </div>
                )}
                <Link
                  href="/oracle"
                  className="flex items-center gap-1 px-2 py-1 bg-info/10 text-info rounded hover:bg-info/20 transition-colors text-xs font-medium"
                >
                  <Brain className="w-3 h-3" />
                  Full Analysis
                </Link>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
