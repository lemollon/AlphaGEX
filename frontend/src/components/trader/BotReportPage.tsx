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
  direction: string
  entry_time: string
  exit_time: string
  entry_price: number
  exit_price: number
  pnl: number
  win: boolean
  analysis: string
  key_moments: string[]
  market_context: string
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
  market_context?: {
    vix_open?: number
    vix_close?: number
    spy_open?: number
    spy_close?: number
    regime?: string
  }
}

interface BotReportPageProps {
  botName: 'ARES' | 'ATHENA' | 'ICARUS' | 'TITAN' | 'PEGASUS'
  botDisplayName: string
  brandColor: string  // e.g., 'amber', 'cyan', 'orange', 'violet', 'blue'
  backLink: string    // e.g., '/ares'
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
  backLink
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
  }, [botName])

  const fetchReport = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await apiClient.getBotReportToday(botName.toLowerCase())
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
        </div>
      </div>

      {error && !report && (
        <div className={`rounded-lg border ${colors.border} ${colors.bg} p-8 text-center`}>
          <AlertCircle className={`w-12 h-12 ${colors.text} mx-auto mb-4`} />
          <h2 className="text-xl font-semibold text-white mb-2">No Report Available</h2>
          <p className="text-gray-400 mb-4">{error}</p>
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
          {report.market_context && (
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
              <h3 className="text-white font-medium mb-3 flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-gray-400" />
                Market Context
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                {report.market_context.vix_open !== undefined && (
                  <div>
                    <span className="text-gray-500">VIX Open:</span>
                    <span className="text-white ml-2">{report.market_context.vix_open?.toFixed(2)}</span>
                  </div>
                )}
                {report.market_context.vix_close !== undefined && (
                  <div>
                    <span className="text-gray-500">VIX Close:</span>
                    <span className="text-white ml-2">{report.market_context.vix_close?.toFixed(2)}</span>
                  </div>
                )}
                {report.market_context.regime && (
                  <div>
                    <span className="text-gray-500">Regime:</span>
                    <span className={`ml-2 ${report.market_context.regime === 'POSITIVE' ? 'text-green-400' : 'text-red-400'}`}>
                      {report.market_context.regime}
                    </span>
                  </div>
                )}
              </div>
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
                  report.trade_analyses.map((trade, idx) => (
                    <div
                      key={trade.position_id || idx}
                      className={`rounded-lg border ${trade.win ? 'border-green-500/30 bg-green-500/5' : 'border-red-500/30 bg-red-500/5'} overflow-hidden`}
                    >
                      <button
                        onClick={() => toggleTrade(trade.position_id || String(idx))}
                        className="w-full p-3 flex items-center justify-between hover:bg-gray-800/20 transition-colors"
                      >
                        <div className="flex items-center gap-3">
                          {trade.win ? (
                            <CheckCircle className="w-5 h-5 text-green-400" />
                          ) : (
                            <XCircle className="w-5 h-5 text-red-400" />
                          )}
                          <div className="text-left">
                            <div className="flex items-center gap-2">
                              <span className={`font-medium ${trade.win ? 'text-green-400' : 'text-red-400'}`}>
                                {trade.direction?.toUpperCase()} Trade
                              </span>
                              <span className={`font-bold ${trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {formatCurrency(trade.pnl)}
                              </span>
                            </div>
                            <div className="text-gray-500 text-sm">
                              {formatTime(trade.entry_time)} - {formatTime(trade.exit_time)}
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
                        <div className="px-3 pb-3 border-t border-gray-700/50">
                          {/* Trade Details */}
                          <div className="grid grid-cols-2 gap-2 text-sm mt-3 mb-3">
                            <div>
                              <span className="text-gray-500">Entry:</span>
                              <span className="text-white ml-2">${trade.entry_price?.toFixed(2)}</span>
                            </div>
                            <div>
                              <span className="text-gray-500">Exit:</span>
                              <span className="text-white ml-2">${trade.exit_price?.toFixed(2)}</span>
                            </div>
                          </div>

                          {/* Analysis */}
                          {trade.analysis && (
                            <div className="mb-3">
                              <h4 className="text-gray-400 text-sm font-medium mb-1">Analysis</h4>
                              <p className="text-gray-300 text-sm whitespace-pre-wrap">{trade.analysis}</p>
                            </div>
                          )}

                          {/* Key Moments */}
                          {trade.key_moments && trade.key_moments.length > 0 && (
                            <div className="mb-3">
                              <h4 className="text-gray-400 text-sm font-medium mb-1">Key Moments</h4>
                              <ul className="space-y-1">
                                {trade.key_moments.map((moment, i) => (
                                  <li key={i} className="text-gray-300 text-sm flex items-start gap-2">
                                    <Clock className="w-3 h-3 mt-1 text-gray-500 flex-shrink-0" />
                                    {moment}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Market Context */}
                          {trade.market_context && (
                            <div>
                              <h4 className="text-gray-400 text-sm font-medium mb-1">Market Context</h4>
                              <p className="text-gray-300 text-sm">{trade.market_context}</p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))
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
          <div className="text-center text-xs text-gray-500">
            Generated at {formatTime(report.generated_at)} using {report.generation_model || 'Claude AI'}
          </div>
        </>
      )}
    </div>
  )
}
