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

// Interface matching actual API response from /api/oracle/strategy-recommendation
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

// Helper to format timestamp in Central Time
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
  const [expanded, setExpanded] = useState(true)
  const [loading, setLoading] = useState(true)
  const [recommendation, setRecommendation] = useState<OracleAPIResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<string>('')

  const fetchRecommendation = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.get('/api/oracle/strategy-recommendation')
      // API returns object directly (not wrapped in success/data)
      const data = response.data
      if (data && (data.recommended_strategy || data.strategy)) {
        // Normalize the response - handle both field names
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
    const interval = setInterval(fetchRecommendation, 60000) // Refresh every minute
    return () => clearInterval(interval)
  }, [])

  const getStrategyConfig = (strategy: string) => {
    switch (strategy) {
      case 'IC':
        return {
          label: 'Iron Condor',
          description: 'Sell premium with ARES/PEGASUS',
          icon: <Shield className="w-5 h-5" />,
          color: 'success',
          bg: 'bg-success/10',
          border: 'border-success/30',
          text: 'text-success'
        }
      case 'DIRECTIONAL':
        return {
          label: 'Directional Spread',
          description: 'Follow trend with ATHENA',
          icon: <TrendingUp className="w-5 h-5" />,
          color: 'primary',
          bg: 'bg-primary/10',
          border: 'border-primary/30',
          text: 'text-primary'
        }
      case 'HOLD':
      default:
        return {
          label: 'Hold / Wait',
          description: 'Market conditions unclear',
          icon: <Minus className="w-5 h-5" />,
          color: 'warning',
          bg: 'bg-warning/10',
          border: 'border-warning/30',
          text: 'text-warning'
        }
    }
  }

  const config = recommendation ? getStrategyConfig(recommendation.recommended_strategy) : null

  return (
    <div className={`card bg-gradient-to-r from-info/5 to-transparent border border-info/20`}>
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
                  <span>{recommendation.confidence}% confidence</span>
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
        <div className="mt-4 pt-4 border-t border-border/50 animate-fade-in">
          {loading ? (
            <div className="space-y-3">
              <div className="h-16 bg-background-hover animate-pulse rounded-lg" />
              <div className="h-12 bg-background-hover animate-pulse rounded-lg" />
            </div>
          ) : error ? (
            <div className="p-4 bg-warning/10 border border-warning/20 rounded-lg">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-warning" />
                <span className="text-sm text-warning">{error}</span>
              </div>
              <button
                onClick={fetchRecommendation}
                className="mt-2 text-xs text-primary hover:underline"
              >
                Retry
              </button>
            </div>
          ) : recommendation && config ? (
            <div className="space-y-4">
              {/* Main Recommendation */}
              <div className={`p-4 rounded-lg ${config.bg} border ${config.border}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className={config.text}>
                      {config.icon}
                    </div>
                    <div>
                      <h4 className={`font-bold ${config.text}`}>{config.label}</h4>
                      <p className="text-xs text-text-muted">{config.description}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-2xl font-bold ${config.text}`}>
                      {recommendation.confidence}%
                    </div>
                    <div className="text-xs text-text-muted">confidence</div>
                  </div>
                </div>

                {recommendation.reasoning && (
                  <div className="p-3 bg-background-card/50 rounded-lg">
                    <p className="text-sm text-text-secondary">{recommendation.reasoning}</p>
                  </div>
                )}
              </div>

              {/* Market Regimes */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-background-hover rounded-lg">
                  <div className="text-xs text-text-muted mb-1">VIX Regime</div>
                  <div className={`text-sm font-semibold ${
                    recommendation.vix_regime?.includes('HIGH') ? 'text-danger' :
                    recommendation.vix_regime?.includes('ELEVATED') ? 'text-warning' :
                    'text-success'
                  }`}>
                    {recommendation.vix_regime?.replace(/_/g, ' ') || 'Unknown'}
                  </div>
                </div>
                <div className="p-3 bg-background-hover rounded-lg">
                  <div className="text-xs text-text-muted mb-1">GEX Regime</div>
                  <div className={`text-sm font-semibold ${
                    recommendation.gex_regime?.includes('NEGATIVE') ? 'text-danger' :
                    recommendation.gex_regime?.includes('POSITIVE') ? 'text-success' :
                    'text-warning'
                  }`}>
                    {recommendation.gex_regime?.replace(/_/g, ' ') || 'Unknown'}
                  </div>
                </div>
              </div>

              {/* Suitability Scores */}
              {(recommendation.ic_suitability !== undefined || recommendation.dir_suitability !== undefined) && (
                <div className="grid grid-cols-2 gap-3">
                  {recommendation.ic_suitability !== undefined && (
                    <div className="p-3 bg-background-hover rounded-lg">
                      <div className="text-xs text-text-muted mb-1">IC Suitability</div>
                      <div className={`text-sm font-semibold ${recommendation.ic_suitability >= 0.6 ? 'text-success' : recommendation.ic_suitability >= 0.4 ? 'text-warning' : 'text-danger'}`}>
                        {(recommendation.ic_suitability * 100).toFixed(0)}%
                      </div>
                    </div>
                  )}
                  {recommendation.dir_suitability !== undefined && (
                    <div className="p-3 bg-background-hover rounded-lg">
                      <div className="text-xs text-text-muted mb-1">Directional Suitability</div>
                      <div className={`text-sm font-semibold ${recommendation.dir_suitability >= 0.6 ? 'text-success' : recommendation.dir_suitability >= 0.4 ? 'text-warning' : 'text-danger'}`}>
                        {(recommendation.dir_suitability * 100).toFixed(0)}%
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Last Updated Time */}
              {lastUpdated && (
                <div className="flex items-center gap-2 text-xs text-text-muted">
                  <Clock className="w-3 h-3" />
                  <span>Updated: {lastUpdated}</span>
                </div>
              )}

              {/* Link to Oracle page */}
              <Link
                href="/oracle"
                className="flex items-center justify-center gap-2 px-4 py-2 bg-info/10 text-info rounded-lg hover:bg-info/20 transition-colors text-sm font-medium"
              >
                <Brain className="w-4 h-4" />
                View Full Oracle Analysis
              </Link>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
