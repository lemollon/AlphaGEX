'use client'

/**
 * AllBotReportsSummary Component
 *
 * Displays a summary of today's trading reports for all bots.
 * Only fetches CACHED reports from database - NO Claude API calls.
 * Links to individual bot report pages for report generation.
 *
 * This prevents duplicate Claude API charges when viewing dashboard.
 */

import { useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import {
  FileText,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  ExternalLink,
  RefreshCw,
  Brain,
  CheckCircle,
  XCircle,
  Clock,
  DollarSign,
  Target,
} from 'lucide-react'
import { BOT_BRANDS, BotName } from '@/components/trader/BotBranding'

interface ReportSummary {
  report_date: string
  total_pnl: number
  trade_count: number
  win_count: number
  loss_count: number
  daily_summary?: string
  lessons_learned?: string[]
  generated_at: string
  estimated_cost_usd?: number
}

interface ReportResponse {
  success: boolean
  data?: ReportSummary
  message?: string
}

// Use lightweight summary endpoint - much faster than full report
const LIVE_BOTS: { name: BotName; endpoint: string; reportLink: string; brandColor: string }[] = [
  { name: 'FORTRESS', endpoint: '/api/trader/fortress/reports/today/summary', reportLink: '/fortress/reports', brandColor: 'amber' },
  { name: 'SOLOMON', endpoint: '/api/trader/solomon/reports/today/summary', reportLink: '/solomon/reports', brandColor: 'cyan' },
  { name: 'ICARUS', endpoint: '/api/trader/icarus/reports/today/summary', reportLink: '/icarus/reports', brandColor: 'orange' },
  { name: 'PEGASUS', endpoint: '/api/trader/pegasus/reports/today/summary', reportLink: '/pegasus/reports', brandColor: 'blue' },
  { name: 'SAMSON', endpoint: '/api/trader/samson/reports/today/summary', reportLink: '/samson/reports', brandColor: 'violet' },
]

// Fetches cached report from database - NO Claude API call
const fetcher = async (url: string): Promise<ReportResponse> => {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}${url}`)
    if (!res.ok) return { success: false, message: 'Failed to fetch' }
    return res.json()
  } catch {
    return { success: false, message: 'Network error' }
  }
}

export default function AllBotReportsSummary() {
  const [selectedBot, setSelectedBot] = useState<BotName>('FORTRESS')

  // Fetch all reports using SWR (deduped, cached)
  // These are READ-ONLY calls to the database - no Claude API charges
  const { data: aresReport, isLoading: aresLoading } = useSWR(LIVE_BOTS[0].endpoint, fetcher, { refreshInterval: 300000 })
  const { data: solomonReport, isLoading: solomonLoading } = useSWR(LIVE_BOTS[1].endpoint, fetcher, { refreshInterval: 300000 })
  const { data: icarusReport, isLoading: icarusLoading } = useSWR(LIVE_BOTS[2].endpoint, fetcher, { refreshInterval: 300000 })
  const { data: pegasusReport, isLoading: pegasusLoading } = useSWR(LIVE_BOTS[3].endpoint, fetcher, { refreshInterval: 300000 })
  const { data: titanReport, isLoading: titanLoading } = useSWR(LIVE_BOTS[4].endpoint, fetcher, { refreshInterval: 300000 })

  const isLoading = aresLoading || solomonLoading || icarusLoading || pegasusLoading || titanLoading

  const reportMap: Record<BotName, ReportResponse | undefined> = {
    FORTRESS: aresReport,
    SOLOMON: solomonReport,
    ICARUS: icarusReport,
    PEGASUS: pegasusReport,
    SAMSON: titanReport,
    PHOENIX: undefined,
    ATLAS: undefined,
    PROMETHEUS: undefined,
    HERACLES: undefined,
    AGAPE: undefined,
  }

  // Calculate aggregate stats
  const aggregateStats = LIVE_BOTS.reduce(
    (acc, bot) => {
      const report = reportMap[bot.name]
      if (report?.success && report.data) {
        acc.totalPnl += report.data.total_pnl
        acc.totalTrades += report.data.trade_count
        acc.totalWins += report.data.win_count
        acc.totalLosses += report.data.loss_count
        acc.botsWithReports++
      }
      return acc
    },
    { totalPnl: 0, totalTrades: 0, totalWins: 0, totalLosses: 0, botsWithReports: 0 }
  )

  const selectedBotConfig = LIVE_BOTS.find(b => b.name === selectedBot)
  const selectedReport = reportMap[selectedBot]
  const brand = BOT_BRANDS[selectedBot]

  return (
    <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain className="w-5 h-5 text-primary" />
          <div>
            <h3 className="font-semibold text-white">Today's Trading Reports</h3>
            <p className="text-xs text-gray-500">
              {aggregateStats.botsWithReports}/5 bots have reports •
              {aggregateStats.totalTrades} trades •
              {aggregateStats.totalPnl >= 0 ? '+' : ''}${aggregateStats.totalPnl.toFixed(0)} total P&L
            </p>
          </div>
        </div>
        {isLoading && <RefreshCw className="w-4 h-4 text-gray-500 animate-spin" />}
      </div>

      {/* Bot Selector Tabs */}
      <div className="px-4 py-2 border-b border-gray-800 flex gap-2 overflow-x-auto">
        {LIVE_BOTS.map(bot => {
          const botBrand = BOT_BRANDS[bot.name]
          const report = reportMap[bot.name]
          const hasReport = report?.success && report.data

          return (
            <button
              key={bot.name}
              onClick={() => setSelectedBot(bot.name)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm whitespace-nowrap transition-all ${
                selectedBot === bot.name
                  ? 'bg-opacity-20 border'
                  : 'bg-gray-800 border border-gray-700 opacity-70 hover:opacity-100'
              }`}
              style={{
                backgroundColor: selectedBot === bot.name ? `${botBrand.hexPrimary}20` : undefined,
                borderColor: selectedBot === bot.name ? botBrand.hexPrimary : undefined,
              }}
            >
              <span style={{ color: selectedBot === bot.name ? botBrand.hexPrimary : '#9ca3af' }}>
                {bot.name}
              </span>
              {hasReport ? (
                <CheckCircle className="w-3 h-3 text-green-400" />
              ) : (
                <AlertCircle className="w-3 h-3 text-gray-500" />
              )}
            </button>
          )
        })}
      </div>

      {/* Selected Bot Report */}
      <div className="p-4">
        {selectedReport?.success && selectedReport.data ? (
          <div className="space-y-4">
            {/* Stats Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-gray-900/50 rounded-lg p-3">
                <div className="flex items-center gap-1 mb-1">
                  <DollarSign className="w-3 h-3 text-gray-500" />
                  <span className="text-xs text-gray-500">P&L</span>
                </div>
                <div className={`text-lg font-bold ${selectedReport.data.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {selectedReport.data.total_pnl >= 0 ? '+' : ''}${selectedReport.data.total_pnl.toFixed(0)}
                </div>
              </div>

              <div className="bg-gray-900/50 rounded-lg p-3">
                <div className="flex items-center gap-1 mb-1">
                  <Target className="w-3 h-3 text-gray-500" />
                  <span className="text-xs text-gray-500">Trades</span>
                </div>
                <div className="text-lg font-bold text-white">
                  {selectedReport.data.trade_count}
                </div>
              </div>

              <div className="bg-gray-900/50 rounded-lg p-3">
                <div className="flex items-center gap-1 mb-1">
                  <TrendingUp className="w-3 h-3 text-gray-500" />
                  <span className="text-xs text-gray-500">Record</span>
                </div>
                <div className="text-lg font-bold">
                  <span className="text-green-400">{selectedReport.data.win_count}W</span>
                  <span className="text-gray-500">/</span>
                  <span className="text-red-400">{selectedReport.data.loss_count}L</span>
                </div>
              </div>

              <div className="bg-gray-900/50 rounded-lg p-3">
                <div className="flex items-center gap-1 mb-1">
                  <Clock className="w-3 h-3 text-gray-500" />
                  <span className="text-xs text-gray-500">Generated</span>
                </div>
                <div className="text-sm font-medium text-gray-300">
                  {new Date(selectedReport.data.generated_at).toLocaleTimeString('en-US', {
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: true,
                  })}
                </div>
              </div>
            </div>

            {/* Daily Summary Preview */}
            {selectedReport.data.daily_summary && (
              <div className="bg-gray-900/30 rounded-lg p-3">
                <h4 className="text-sm font-medium text-gray-400 mb-2">Summary</h4>
                <p className="text-sm text-gray-300 line-clamp-3">
                  {selectedReport.data.daily_summary}
                </p>
              </div>
            )}

            {/* Lessons Preview */}
            {selectedReport.data.lessons_learned && selectedReport.data.lessons_learned.length > 0 && (
              <div className="bg-gray-900/30 rounded-lg p-3">
                <h4 className="text-sm font-medium text-gray-400 mb-2">Key Lessons</h4>
                <ul className="space-y-1">
                  {selectedReport.data.lessons_learned.slice(0, 2).map((lesson, idx) => (
                    <li key={idx} className="text-sm text-gray-300 flex items-start gap-2">
                      <CheckCircle className="w-3 h-3 mt-1 text-green-400 flex-shrink-0" />
                      <span className="line-clamp-1">{lesson}</span>
                    </li>
                  ))}
                  {selectedReport.data.lessons_learned.length > 2 && (
                    <li className="text-xs text-gray-500">
                      +{selectedReport.data.lessons_learned.length - 2} more lessons
                    </li>
                  )}
                </ul>
              </div>
            )}

            {/* View Full Report Link */}
            <Link
              href={selectedBotConfig?.reportLink || '#'}
              className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg border transition-colors hover:opacity-80"
              style={{
                backgroundColor: `${brand.hexPrimary}10`,
                borderColor: `${brand.hexPrimary}40`,
                color: brand.hexPrimary,
              }}
            >
              <FileText className="w-4 h-4" />
              View Full {selectedBot} Report
              <ExternalLink className="w-3 h-3" />
            </Link>
          </div>
        ) : (
          <div className="text-center py-8">
            <AlertCircle className="w-10 h-10 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-400 mb-2">No report available for {selectedBot}</p>
            <p className="text-xs text-gray-500 mb-4">
              Reports are generated from the individual bot pages
            </p>
            <Link
              href={selectedBotConfig?.reportLink || '#'}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border transition-colors hover:opacity-80"
              style={{
                backgroundColor: `${brand.hexPrimary}10`,
                borderColor: `${brand.hexPrimary}40`,
                color: brand.hexPrimary,
              }}
            >
              <Brain className="w-4 h-4" />
              Go to {selectedBot} Reports
              <ExternalLink className="w-3 h-3" />
            </Link>
          </div>
        )}
      </div>

      {/* Footer note about Claude API */}
      <div className="px-4 py-2 border-t border-gray-800 bg-gray-900/30">
        <p className="text-xs text-gray-500 text-center">
          Reports are cached from database • Generate new reports from individual bot pages to avoid duplicate charges
        </p>
      </div>
    </div>
  )
}
