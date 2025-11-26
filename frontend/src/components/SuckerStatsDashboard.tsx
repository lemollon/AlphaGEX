'use client'

import { useState, useEffect } from 'react'
import { AlertTriangle, TrendingDown, Target, Percent, BarChart3, RefreshCw, Info } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface SuckerStat {
  scenario_type: string
  total_occurrences: number
  newbie_fade_failed: number
  newbie_fade_succeeded: number
  failure_rate: number
  avg_price_change_when_failed?: number
  avg_days_to_resolution?: number
  last_updated: string
}

interface SuckerStatsData {
  statistics: SuckerStat[]
  summary: {
    total_scenarios: number
    avg_failure_rate: number
    most_dangerous_trap: string
    safest_fade: string
  }
}

export default function SuckerStatsDashboard() {
  const [stats, setStats] = useState<SuckerStatsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchStats = async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await apiClient.getPsychologyStatistics()

      // Handle both success:true pattern and direct data response
      if (response.data.success !== false) {
        const data = response.data.data || response.data
        setStats(data)
      } else {
        throw new Error('Failed to load statistics')
      }
    } catch (err: any) {
      console.error('Error fetching sucker stats:', err)
      setError(err.message || 'Failed to load statistics')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
  }, [])

  const getScenarioIcon = (scenarioType: string) => {
    if (scenarioType.includes('CALL_WALL')) return <TrendingDown className="w-5 h-5" />
    if (scenarioType.includes('PUT_WALL')) return <Target className="w-5 h-5" />
    return <AlertTriangle className="w-5 h-5" />
  }

  const getScenarioColor = (failureRate: number) => {
    if (failureRate >= 70) return 'text-red-500 bg-red-500/10 border-red-500/30'
    if (failureRate >= 50) return 'text-orange-500 bg-orange-500/10 border-orange-500/30'
    if (failureRate >= 30) return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/30'
    return 'text-green-500 bg-green-500/10 border-green-500/30'
  }

  const formatScenarioName = (scenarioType: string) => {
    return scenarioType
      .replace(/_/g, ' ')
      .toLowerCase()
      .replace(/\b\w/g, (l) => l.toUpperCase())
  }

  if (loading) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-orange-500" />
            Sucker Statistics
          </h2>
        </div>
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
        </div>
      </div>
    )
  }

  if (error || !stats) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-orange-500" />
            Sucker Statistics
          </h2>
        </div>
        <div className="bg-red-500/10 border border-red-500/30 rounded p-4">
          <p className="text-red-400 text-sm">
            {error || 'No statistics available yet. Data accumulates over time as signals are tracked.'}
          </p>
          <button
            onClick={fetchStats}
            className="mt-2 px-3 py-1 text-xs bg-red-500/20 hover:bg-red-500/30 rounded"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-orange-500/30 bg-gradient-to-br from-orange-500/5 to-red-500/5 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <AlertTriangle className="w-6 h-6 text-orange-500" />
            Sucker Statistics
          </h2>
          <p className="text-sm text-gray-400 mt-1">
            How often newbie logic fails vs. succeeds
          </p>
        </div>
        <button
          onClick={fetchStats}
          className="p-2 rounded-lg hover:bg-white/5 transition-colors"
          title="Refresh statistics"
        >
          <RefreshCw className="w-5 h-5 text-gray-400 hover:text-white" />
        </button>
      </div>

      {/* Summary Cards */}
      {stats.summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="text-xs text-gray-400 mb-1">Total Scenarios</div>
            <div className="text-2xl font-bold text-white">
              {stats.summary.total_scenarios}
            </div>
          </div>

          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="text-xs text-gray-400 mb-1">Avg Failure Rate</div>
            <div className="text-2xl font-bold text-red-400">
              {stats.summary.avg_failure_rate.toFixed(0)}%
            </div>
          </div>

          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="text-xs text-gray-400 mb-1">Most Dangerous</div>
            <div className="text-xs font-semibold text-red-400 truncate" title={formatScenarioName(stats.summary.most_dangerous_trap)}>
              {formatScenarioName(stats.summary.most_dangerous_trap)}
            </div>
          </div>

          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="text-xs text-gray-400 mb-1">Safest Fade</div>
            <div className="text-xs font-semibold text-green-400 truncate" title={formatScenarioName(stats.summary.safest_fade)}>
              {formatScenarioName(stats.summary.safest_fade)}
            </div>
          </div>
        </div>
      )}

      {/* Info Banner */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 mb-6 flex items-start gap-3">
        <Info className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-blue-200">
          <strong>What this means:</strong> These statistics show how often "obvious" trading setups actually trap retail traders.
          A high failure rate means fading that setup historically loses money.
        </div>
      </div>

      {/* Statistics Grid */}
      <div className="space-y-3">
        {stats.statistics.length === 0 ? (
          <div className="bg-gray-800/30 rounded-lg p-8 text-center">
            <BarChart3 className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-400 text-sm">
              No statistics available yet.
            </p>
            <p className="text-gray-500 text-xs mt-2">
              Data accumulates as regime signals are tracked over time. Check back after a few weeks of operation.
            </p>
          </div>
        ) : (
          stats.statistics.map((stat, idx) => (
            <div
              key={idx}
              className={`rounded-lg border p-4 ${getScenarioColor(stat.failure_rate)}`}
            >
              <div className="flex items-start justify-between gap-4">
                {/* Left: Scenario Info */}
                <div className="flex items-start gap-3 flex-1">
                  <div className="mt-1">
                    {getScenarioIcon(stat.scenario_type)}
                  </div>
                  <div className="flex-1">
                    <div className="font-semibold text-white mb-1">
                      {formatScenarioName(stat.scenario_type)}
                    </div>
                    <div className="text-xs text-gray-400 space-y-1">
                      <div>Total occurrences: <span className="text-white">{stat.total_occurrences}</span></div>
                      {stat.avg_price_change_when_failed && (
                        <div>Avg loss when wrong: <span className="text-red-400">{stat.avg_price_change_when_failed.toFixed(2)}%</span></div>
                      )}
                      {stat.avg_days_to_resolution && (
                        <div>Avg time to resolution: <span className="text-white">{stat.avg_days_to_resolution.toFixed(1)} days</span></div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Right: Failure Rate */}
                <div className="text-right flex-shrink-0">
                  <div className="text-3xl font-bold mb-1">
                    {stat.failure_rate.toFixed(0)}%
                  </div>
                  <div className="text-xs text-gray-400">
                    Failure Rate
                  </div>
                  <div className="mt-2 text-xs">
                    <span className="text-red-400">{stat.newbie_fade_failed} failed</span>
                    {' / '}
                    <span className="text-green-400">{stat.newbie_fade_succeeded} succeeded</span>
                  </div>
                </div>
              </div>

              {/* Interpretation */}
              <div className="mt-3 pt-3 border-t border-current/20">
                <p className="text-xs text-gray-300">
                  {stat.failure_rate >= 70 && (
                    <><strong className="text-red-400">Extreme Danger:</strong> Fading this setup is almost always wrong. Don't fight it.</>
                  )}
                  {stat.failure_rate >= 50 && stat.failure_rate < 70 && (
                    <><strong className="text-orange-400">High Risk:</strong> More likely to fail than succeed. Requires extreme caution.</>
                  )}
                  {stat.failure_rate >= 30 && stat.failure_rate < 50 && (
                    <><strong className="text-yellow-400">Moderate Risk:</strong> Mixed results. Consider market structure before fading.</>
                  )}
                  {stat.failure_rate < 30 && (
                    <><strong className="text-green-400">Safer Fade:</strong> Historically fading this setup works more often than not.</>
                  )}
                </p>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer Note */}
      <div className="mt-6 text-xs text-gray-500 text-center">
        Last updated: {stats.statistics[0]?.last_updated ? new Date(stats.statistics[0].last_updated).toLocaleString() : 'N/A'}
      </div>
    </div>
  )
}
