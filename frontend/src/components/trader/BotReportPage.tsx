'use client'

/**
 * Bot Report Page Component
 *
 * Displays end-of-day analysis reports for trading bots.
 * Shows per-trade analysis with timestamps and Claude AI explanations.
 * Follows the Daily Manna archive pattern.
 *
 * Created: January 2025
 */

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { apiClient } from '@/lib/api'
import {
  FileText,
  Calendar,
  Download,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Clock,
  AlertCircle,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  Archive,
  ArrowLeft,
  DollarSign,
  Target,
  Zap,
  BookOpen,
  Brain,
  BarChart3
} from 'lucide-react'

interface TradeAnalysis {
  position_id: string
  pnl: number
  entry_analysis?: {
    quality: string
    reasoning: string
  }
  price_action_summary?: string
  exit_analysis?: {
    was_optimal: boolean
    reasoning: string
  }
  why_won_or_lost?: string
  lesson?: string
  key_timestamps?: Array<{
    time: string
    event: string
    price: number
  }>
  _generated_by?: string
}

interface ReportData {
  report_date: string
  trades_data: any[]
  trade_analyses: TradeAnalysis[]
  daily_summary: string
  lessons_learned: string[]
  total_pnl: number
  trade_count: number
  win_count: number
  loss_count: number
  generated_at: string
  generation_model: string
  generation_duration_ms?: number
  input_tokens?: number
  output_tokens?: number
  total_tokens?: number
  estimated_cost_usd?: number
  market_context?: {
    summary?: {
      vix_open?: number
      vix_close?: number
      vix_high?: number
      vix_low?: number
      dominant_regime?: string
    }
    events?: Array<{ type: string; timestamp: string }>
  }
}

interface BotReportPageProps {
  botName: 'ARES' | 'ATHENA' | 'ICARUS' | 'TITAN' | 'PEGASUS'
  botDisplayName: string
  brandColor: string  // e.g., 'amber', 'cyan', 'orange', 'violet', 'blue'
  backLink: string    // e.g., '/ares'
  date?: string | null  // Optional date for viewing historical reports (YYYY-MM-DD format)
}

const BRAND_COLORS: Record<string, { bg: string; border: string; text: string; gradient: string }> = {
  amber: {
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/30',
    text: 'text-amber-400',
    gradient: 'from-amber-500/20 to-transparent'
  },
  cyan: {
    bg: 'bg-cyan-500/10',
    border: 'border-cyan-500/30',
    text: 'text-cyan-400',
    gradient: 'from-cyan-500/20 to-transparent'
  },
  orange: {
    bg: 'bg-orange-500/10',
    border: 'border-orange-500/30',
    text: 'text-orange-400',
    gradient: 'from-orange-500/20 to-transparent'
  },
  violet: {
    bg: 'bg-violet-500/10',
    border: 'border-violet-500/30',
    text: 'text-violet-400',
    gradient: 'from-violet-500/20 to-transparent'
  },
  blue: {
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/30',
    text: 'text-blue-400',
    gradient: 'from-blue-500/20 to-transparent'
  }
}

function formatCurrency(value: number): string {
  const formatted = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(value))
  return value < 0 ? `-${formatted}` : formatted
}

function formatDateTime(dateStr: string): string {
  try {
    const date = new Date(dateStr)
    return new Intl.DateTimeFormat('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    }).format(date)
  } catch {
    return dateStr
  }
}

function formatTime(dateStr: string): string {
  try {
    const date = new Date(dateStr)
    return new Intl.DateTimeFormat('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short'
    }).format(date)
  } catch {
    return ''
  }
}

export default function BotReportPage({
  botName,
  botDisplayName,
  brandColor,
  backLink,
  date
}: BotReportPageProps) {
  const [report, setReport] = useState<ReportData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [expandedTrades, setExpandedTrades] = useState<Set<string>>(new Set())
  const [expandedSections, setExpandedSections] = useState({
    summary: true,
    trades: true,
    lessons: true
  })

  const colors = BRAND_COLORS[brandColor] || BRAND_COLORS.blue

  useEffect(() => {
    fetchReport()
  }, [botName, date])

  const fetchReport = async () => {
    try {
      setLoading(true)
      setError(null)

      // Use date-specific API if viewing historical report, otherwise get today's
      const response = date
        ? await apiClient.getBotReportByDate(botName.toLowerCase(), date)
        : await apiClient.getBotReportToday(botName.toLowerCase())

      if (response.data.success && response.data.data) {
        setReport(response.data.data)
      } else if (response.data.message) {
        // No report available message
        setReport(null)
        setError(response.data.message)
      }
    } catch (err: any) {
      console.error('Error fetching report:', err)
      setError(err.response?.data?.detail || 'Failed to load report')
    } finally {
      setLoading(false)
    }
  }

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const response = await apiClient.generateBotReport(botName.toLowerCase())
      if (response.data.success) {
        if (response.data.data) {
          setReport(response.data.data)
          setError(null)
        } else {
          // No trades case - data is null but success is true
          setReport(null)
          setError(response.data.message || 'No trades found - no report generated')
        }
      } else {
        setError(response.data.detail || 'Failed to generate report')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate report')
    } finally {
      setGenerating(false)
    }
  }

  const handleDownload = async (format: 'json' | 'pdf') => {
    if (!report) return

    try {
      const response = await apiClient.downloadBotReport(
        botName.toLowerCase(),
        report.report_date,
        format
      )

      if (format === 'json') {
        // Download as JSON file
        const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${botName.toLowerCase()}_report_${report.report_date}.json`
        a.click()
        URL.revokeObjectURL(url)
      } else {
        // Download as markdown (PDF-friendly)
        const content = response.data.markdown || response.data
        const blob = new Blob([content], { type: 'text/markdown' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${botName.toLowerCase()}_report_${report.report_date}.md`
        a.click()
        URL.revokeObjectURL(url)
      }
    } catch (err) {
      console.error('Download error:', err)
    }
  }

  const toggleTrade = (positionId: string) => {
    const newExpanded = new Set(expandedTrades)
    if (newExpanded.has(positionId)) {
      newExpanded.delete(positionId)
    } else {
      newExpanded.add(positionId)
    }
    setExpandedTrades(newExpanded)
  }

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }))
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <Brain className={`w-12 h-12 ${colors.text} animate-pulse mb-4`} />
        <p className="text-text-secondary">Loading report...</p>
      </div>
    )
  }

  const winRate = report && report.trade_count > 0
    ? ((report.win_count / report.trade_count) * 100).toFixed(1)
    : '0'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            href={backLink}
            className="p-2 rounded-lg hover:bg-gray-800 transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-gray-400" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <FileText className={`w-6 h-6 ${colors.text}`} />
              <h1 className="text-2xl font-bold text-white">{botDisplayName} Daily Report</h1>
            </div>
            {report && (
              <p className="text-gray-400 mt-1">
                {formatDateTime(report.report_date)}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Link
            href={`${backLink}/reports/archive`}
            className={`px-3 py-2 rounded-lg ${colors.bg} ${colors.border} border ${colors.text} hover:opacity-80 transition-opacity flex items-center gap-2`}
          >
            <Archive className="w-4 h-4" />
            Archive
          </Link>

          {report && (
            <>
              <button
                onClick={() => handleDownload('pdf')}
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700 transition-colors flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                Markdown
              </button>
              <button
                onClick={() => handleDownload('json')}
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700 transition-colors flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                JSON
              </button>
            </>
          )}

          {/* Only show Generate button for today's report, not historical */}
          {!date && (
            <button
              onClick={handleGenerate}
              disabled={generating}
              className={`px-4 py-2 rounded-lg ${colors.bg} ${colors.border} border ${colors.text} hover:opacity-80 transition-opacity flex items-center gap-2 disabled:opacity-50`}
            >
              {generating ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Brain className="w-4 h-4" />
                  Generate Report
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {error && !report && (
        <div className={`rounded-lg border ${colors.border} ${colors.bg} p-8 text-center`}>
          <AlertCircle className={`w-12 h-12 ${colors.text} mx-auto mb-4`} />
          <h2 className="text-xl font-semibold text-white mb-2">
            {date ? 'Historical Report Not Found' : 'No Report Available'}
          </h2>
          <p className="text-gray-400 mb-4">{error}</p>
          {/* Only show Generate button for today's report, not historical */}
          {!date ? (
            <button
              onClick={handleGenerate}
              disabled={generating}
              className={`px-4 py-2 rounded-lg ${colors.bg} ${colors.border} border ${colors.text} hover:opacity-80 transition-opacity inline-flex items-center gap-2`}
            >
              {generating ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Brain className="w-4 h-4" />
                  Generate Report Now
                </>
              )}
            </button>
          ) : (
            <Link
              href={`${backLink}/reports`}
              className={`px-4 py-2 rounded-lg ${colors.bg} ${colors.border} border ${colors.text} hover:opacity-80 transition-opacity inline-flex items-center gap-2`}
            >
              <ArrowLeft className="w-4 h-4" />
              View Today&apos;s Report
            </Link>
          )}
        </div>
      )}

      {report && (
        <>
          {/* Stats Overview */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className={`rounded-lg border ${colors.border} ${colors.bg} p-4`}>
              <div className="flex items-center gap-2 mb-1">
                <DollarSign className="w-4 h-4 text-gray-400" />
                <span className="text-gray-400 text-sm">Total P&L</span>
              </div>
              <div className={`text-2xl font-bold ${report.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {formatCurrency(report.total_pnl)}
              </div>
            </div>

            <div className={`rounded-lg border ${colors.border} ${colors.bg} p-4`}>
              <div className="flex items-center gap-2 mb-1">
                <BarChart3 className="w-4 h-4 text-gray-400" />
                <span className="text-gray-400 text-sm">Trades</span>
              </div>
              <div className="text-2xl font-bold text-white">
                {report.trade_count}
              </div>
            </div>

            <div className={`rounded-lg border ${colors.border} ${colors.bg} p-4`}>
              <div className="flex items-center gap-2 mb-1">
                <Target className="w-4 h-4 text-gray-400" />
                <span className="text-gray-400 text-sm">Win Rate</span>
              </div>
              <div className={`text-2xl font-bold ${parseFloat(winRate) >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                {winRate}%
              </div>
            </div>

            <div className={`rounded-lg border ${colors.border} ${colors.bg} p-4`}>
              <div className="flex items-center gap-2 mb-1">
                <Zap className="w-4 h-4 text-gray-400" />
                <span className="text-gray-400 text-sm">Record</span>
              </div>
              <div className="text-2xl font-bold text-white">
                <span className="text-green-400">{report.win_count}W</span>
                <span className="text-gray-500 mx-1">/</span>
                <span className="text-red-400">{report.loss_count}L</span>
              </div>
            </div>
          </div>

          {/* Market Context */}
          {report.market_context?.summary && (
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
              <h3 className="text-white font-medium mb-3 flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-gray-400" />
                Market Context
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                {report.market_context.summary.vix_open !== undefined && (
                  <div>
                    <span className="text-gray-500">VIX Open:</span>
                    <span className="text-white ml-2">{report.market_context.summary.vix_open?.toFixed(2)}</span>
                  </div>
                )}
                {report.market_context.summary.vix_close !== undefined && (
                  <div>
                    <span className="text-gray-500">VIX Close:</span>
                    <span className="text-white ml-2">{report.market_context.summary.vix_close?.toFixed(2)}</span>
                  </div>
                )}
                {report.market_context.summary.vix_high !== undefined && (
                  <div>
                    <span className="text-gray-500">VIX High:</span>
                    <span className="text-white ml-2">{report.market_context.summary.vix_high?.toFixed(2)}</span>
                  </div>
                )}
                {report.market_context.summary.vix_low !== undefined && (
                  <div>
                    <span className="text-gray-500">VIX Low:</span>
                    <span className="text-white ml-2">{report.market_context.summary.vix_low?.toFixed(2)}</span>
                  </div>
                )}
                {report.market_context.summary.dominant_regime && (
                  <div>
                    <span className="text-gray-500">Regime:</span>
                    <span className={`ml-2 ${report.market_context.summary.dominant_regime === 'POSITIVE' ? 'text-green-400' : 'text-red-400'}`}>
                      {report.market_context.summary.dominant_regime}
                    </span>
                  </div>
                )}
              </div>
              {report.market_context.events && report.market_context.events.length > 0 && (
                <div className="mt-3 text-sm">
                  <span className="text-gray-500">Events:</span>
                  <span className="text-white ml-2">
                    {report.market_context.events.map(e => e.type).join(', ')}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Daily Summary */}
          <div className="bg-gray-800/50 rounded-lg border border-gray-700 overflow-hidden">
            <button
              onClick={() => toggleSection('summary')}
              className="w-full p-4 flex items-center justify-between hover:bg-gray-800/50 transition-colors"
            >
              <h3 className="text-white font-medium flex items-center gap-2">
                <Brain className={`w-5 h-5 ${colors.text}`} />
                Daily Summary
              </h3>
              {expandedSections.summary ? (
                <ChevronUp className="w-5 h-5 text-gray-400" />
              ) : (
                <ChevronDown className="w-5 h-5 text-gray-400" />
              )}
            </button>
            {expandedSections.summary && report.daily_summary && (
              <div className="px-4 pb-4">
                <div className="prose prose-invert max-w-none text-gray-300 whitespace-pre-wrap">
                  {report.daily_summary}
                </div>
              </div>
            )}
          </div>

          {/* Trade Analyses */}
          <div className="bg-gray-800/50 rounded-lg border border-gray-700 overflow-hidden">
            <button
              onClick={() => toggleSection('trades')}
              className="w-full p-4 flex items-center justify-between hover:bg-gray-800/50 transition-colors"
            >
              <h3 className="text-white font-medium flex items-center gap-2">
                <BarChart3 className={`w-5 h-5 ${colors.text}`} />
                Trade-by-Trade Analysis ({report.trade_count} trades)
              </h3>
              {expandedSections.trades ? (
                <ChevronUp className="w-5 h-5 text-gray-400" />
              ) : (
                <ChevronDown className="w-5 h-5 text-gray-400" />
              )}
            </button>
            {expandedSections.trades && (
              <div className="px-4 pb-4 space-y-3">
                {report.trade_analyses && report.trade_analyses.length > 0 ? (
                  report.trade_analyses.map((trade, idx) => {
                    const isWin = trade.pnl >= 0
                    return (
                      <div
                        key={trade.position_id || idx}
                        className={`rounded-lg border ${isWin ? 'border-green-500/30 bg-green-500/5' : 'border-red-500/30 bg-red-500/5'} overflow-hidden`}
                      >
                        <button
                          onClick={() => toggleTrade(trade.position_id || String(idx))}
                          className="w-full p-3 flex items-center justify-between hover:bg-gray-800/20 transition-colors"
                        >
                          <div className="flex items-center gap-3">
                            {isWin ? (
                              <CheckCircle className="w-5 h-5 text-green-400" />
                            ) : (
                              <XCircle className="w-5 h-5 text-red-400" />
                            )}
                            <div className="text-left">
                              <div className="flex items-center gap-2">
                                <span className={`font-medium ${isWin ? 'text-green-400' : 'text-red-400'}`}>
                                  Trade #{idx + 1}
                                </span>
                                <span className={`font-bold ${trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                  {formatCurrency(trade.pnl)}
                                </span>
                                {trade.entry_analysis?.quality && (
                                  <span className={`text-xs px-2 py-0.5 rounded ${
                                    trade.entry_analysis.quality === 'GOOD' ? 'bg-green-500/20 text-green-400' :
                                    trade.entry_analysis.quality === 'POOR' ? 'bg-red-500/20 text-red-400' :
                                    'bg-yellow-500/20 text-yellow-400'
                                  }`}>
                                    {trade.entry_analysis.quality}
                                  </span>
                                )}
                              </div>
                              <div className="text-gray-500 text-sm">
                                {trade.position_id || `Position ${idx + 1}`}
                              </div>
                            </div>
                          </div>
                          {expandedTrades.has(trade.position_id || String(idx)) ? (
                            <ChevronUp className="w-5 h-5 text-gray-400" />
                          ) : (
                            <ChevronDown className="w-5 h-5 text-gray-400" />
                          )}
                        </button>

                        {expandedTrades.has(trade.position_id || String(idx)) && (
                          <div className="px-3 pb-3 border-t border-gray-700/50 mt-0 pt-3 space-y-3">
                            {/* Entry Analysis */}
                            {trade.entry_analysis && (
                              <div>
                                <h4 className="text-gray-400 text-sm font-medium mb-1">Entry Analysis</h4>
                                <p className="text-gray-300 text-sm">{trade.entry_analysis.reasoning}</p>
                              </div>
                            )}

                            {/* Price Action Summary */}
                            {trade.price_action_summary && (
                              <div>
                                <h4 className="text-gray-400 text-sm font-medium mb-1">Price Action</h4>
                                <p className="text-gray-300 text-sm whitespace-pre-wrap">{trade.price_action_summary}</p>
                              </div>
                            )}

                            {/* Exit Analysis */}
                            {trade.exit_analysis && (
                              <div>
                                <h4 className="text-gray-400 text-sm font-medium mb-1">Exit Analysis</h4>
                                <div className="flex items-center gap-2 mb-1">
                                  <span className={`text-xs px-2 py-0.5 rounded ${trade.exit_analysis.was_optimal ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                                    {trade.exit_analysis.was_optimal ? 'Optimal Exit' : 'Could Be Better'}
                                  </span>
                                </div>
                                <p className="text-gray-300 text-sm">{trade.exit_analysis.reasoning}</p>
                              </div>
                            )}

                            {/* Why Won or Lost */}
                            {trade.why_won_or_lost && (
                              <div>
                                <h4 className="text-gray-400 text-sm font-medium mb-1">Why {isWin ? 'Won' : 'Lost'}</h4>
                                <p className="text-gray-300 text-sm">{trade.why_won_or_lost}</p>
                              </div>
                            )}

                            {/* Key Timestamps */}
                            {trade.key_timestamps && trade.key_timestamps.length > 0 && (
                              <div>
                                <h4 className="text-gray-400 text-sm font-medium mb-1">Key Moments</h4>
                                <ul className="space-y-1">
                                  {trade.key_timestamps.map((ts, i) => (
                                    <li key={i} className="text-gray-300 text-sm flex items-start gap-2">
                                      <Clock className="w-3 h-3 mt-1 text-gray-500 flex-shrink-0" />
                                      <span>
                                        <span className="text-gray-500">{ts.time}</span>
                                        {' - '}{ts.event}
                                        {ts.price > 0 && <span className="text-gray-500"> (${ts.price.toFixed(2)})</span>}
                                      </span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {/* Lesson */}
                            {trade.lesson && (
                              <div className="mt-3 p-2 bg-gray-800/50 rounded">
                                <h4 className="text-gray-400 text-sm font-medium mb-1">Lesson</h4>
                                <p className="text-gray-300 text-sm italic">{trade.lesson}</p>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })
                ) : (
                  <p className="text-gray-500 text-center py-4">No trade analyses available</p>
                )}
              </div>
            )}
          </div>

          {/* Lessons Learned */}
          <div className="bg-gray-800/50 rounded-lg border border-gray-700 overflow-hidden">
            <button
              onClick={() => toggleSection('lessons')}
              className="w-full p-4 flex items-center justify-between hover:bg-gray-800/50 transition-colors"
            >
              <h3 className="text-white font-medium flex items-center gap-2">
                <BookOpen className={`w-5 h-5 ${colors.text}`} />
                Lessons Learned
              </h3>
              {expandedSections.lessons ? (
                <ChevronUp className="w-5 h-5 text-gray-400" />
              ) : (
                <ChevronDown className="w-5 h-5 text-gray-400" />
              )}
            </button>
            {expandedSections.lessons && (
              <div className="px-4 pb-4">
                {report.lessons_learned && report.lessons_learned.length > 0 ? (
                  <ul className="space-y-2">
                    {report.lessons_learned.map((lesson, idx) => (
                      <li key={idx} className="text-gray-300 flex items-start gap-2">
                        <CheckCircle className={`w-4 h-4 mt-1 ${colors.text} flex-shrink-0`} />
                        {lesson}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-gray-500">No lessons recorded for this day.</p>
                )}
              </div>
            )}
          </div>

          {/* Generation Info */}
          <div className="text-center text-xs text-gray-500 space-y-1">
            <div>
              Generated at {formatTime(report.generated_at)} using {report.generation_model || 'Claude AI'}
              {report.generation_duration_ms && ` in ${(report.generation_duration_ms / 1000).toFixed(1)}s`}
            </div>
            {(report.total_tokens || report.estimated_cost_usd) && (
              <div className="flex items-center justify-center gap-3">
                {report.total_tokens > 0 && (
                  <span>{report.total_tokens.toLocaleString()} tokens</span>
                )}
                {report.estimated_cost_usd > 0 && (
                  <span className="text-amber-400/70">
                    ${report.estimated_cost_usd.toFixed(4)} estimated cost
                  </span>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
