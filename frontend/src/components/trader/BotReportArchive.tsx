'use client'

/**
 * Bot Report Archive Component
 *
 * Lists all historical reports for a bot with pagination.
 * Follows the Daily Manna archive pattern.
 *
 * Created: January 2025
 */

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { apiClient } from '@/lib/api'
import {
  Archive,
  Calendar,
  TrendingUp,
  TrendingDown,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  ArrowLeft,
  Target,
  Loader2
} from 'lucide-react'

interface ArchiveItem {
  report_date: string
  total_pnl: number
  trade_count: number
  win_count: number
  loss_count: number
  generated_at: string
  daily_summary?: string
  lessons_learned?: string[]
}

interface ArchiveStats {
  total_reports: number
  total_pnl: number
  total_trades: number
  total_wins: number
  total_losses: number
  best_day: { date: string; pnl: number } | null
  worst_day: { date: string; pnl: number } | null
  date_range: { oldest: string; newest: string } | null
}

interface BotReportArchiveProps {
  botName: 'ARES' | 'ATHENA' | 'ICARUS' | 'TITAN' | 'PEGASUS'
  botDisplayName: string
  brandColor: string
  backLink: string
}

const BRAND_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  amber: { bg: 'bg-amber-500/10', border: 'border-amber-500/30', text: 'text-amber-400' },
  cyan: { bg: 'bg-cyan-500/10', border: 'border-cyan-500/30', text: 'text-cyan-400' },
  orange: { bg: 'bg-orange-500/10', border: 'border-orange-500/30', text: 'text-orange-400' },
  violet: { bg: 'bg-violet-500/10', border: 'border-violet-500/30', text: 'text-violet-400' },
  blue: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', text: 'text-blue-400' }
}

const PAGE_SIZE = 20

function formatCurrency(value: number): string {
  const formatted = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(value))
  return value < 0 ? `-${formatted}` : formatted
}

function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr)
    return new Intl.DateTimeFormat('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    }).format(date)
  } catch {
    return dateStr
  }
}

export default function BotReportArchive({
  botName,
  botDisplayName,
  brandColor,
  backLink
}: BotReportArchiveProps) {
  const [archive, setArchive] = useState<ArchiveItem[]>([])
  const [stats, setStats] = useState<ArchiveStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)

  const colors = BRAND_COLORS[brandColor] || BRAND_COLORS.blue

  useEffect(() => {
    fetchArchive()
    fetchStats()
  }, [botName, page])

  const fetchArchive = async () => {
    try {
      setLoading(true)
      const response = await apiClient.getBotReportArchive(
        botName.toLowerCase(),
        PAGE_SIZE,
        page * PAGE_SIZE
      )
      if (response.data.success) {
        setArchive(response.data.data.archive || [])
        setTotal(response.data.data.total || 0)
      }
    } catch (err) {
      console.error('Error fetching archive:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchStats = async () => {
    try {
      const response = await apiClient.getBotReportStats(botName.toLowerCase())
      if (response.data.success) {
        setStats(response.data.data)
      }
    } catch (err) {
      console.error('Error fetching stats:', err)
    }
  }

  const handleDownloadAll = async () => {
    setDownloading(true)
    try {
      const response = await apiClient.downloadAllBotReports(botName.toLowerCase())
      const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${botName.toLowerCase()}_all_reports.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Download error:', err)
    } finally {
      setDownloading(false)
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const overallWinRate = stats && stats.total_trades > 0
    ? ((stats.total_wins / stats.total_trades) * 100).toFixed(1)
    : '0'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            href={`${backLink}/reports`}
            className="p-2 rounded-lg hover:bg-gray-800 transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-gray-400" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <Archive className={`w-6 h-6 ${colors.text}`} />
              <h1 className="text-2xl font-bold text-white">{botDisplayName} Report Archive</h1>
            </div>
            <p className="text-gray-400 mt-1">
              {total} reports saved
            </p>
          </div>
        </div>

        <button
          onClick={handleDownloadAll}
          disabled={downloading || total === 0}
          className={`px-4 py-2 rounded-lg ${colors.bg} ${colors.border} border ${colors.text} hover:opacity-80 transition-opacity flex items-center gap-2 disabled:opacity-50`}
        >
          {downloading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Downloading...
            </>
          ) : (
            <>
              <Download className="w-4 h-4" />
              Download All (JSON)
            </>
          )}
        </button>
      </div>

      {/* Stats Overview */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className={`rounded-lg border ${colors.border} ${colors.bg} p-4`}>
            <div className="text-gray-400 text-sm">Total P&L</div>
            <div className={`text-xl font-bold ${stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {formatCurrency(stats.total_pnl)}
            </div>
          </div>

          <div className={`rounded-lg border ${colors.border} ${colors.bg} p-4`}>
            <div className="text-gray-400 text-sm">Total Trades</div>
            <div className="text-xl font-bold text-white">{stats.total_trades}</div>
          </div>

          <div className={`rounded-lg border ${colors.border} ${colors.bg} p-4`}>
            <div className="text-gray-400 text-sm">Win Rate</div>
            <div className={`text-xl font-bold ${parseFloat(overallWinRate) >= 50 ? 'text-green-400' : 'text-red-400'}`}>
              {overallWinRate}%
            </div>
          </div>

          <div className={`rounded-lg border ${colors.border} ${colors.bg} p-4`}>
            <div className="text-gray-400 text-sm">Best Day</div>
            <div className="text-xl font-bold text-green-400">
              {stats.best_day ? formatCurrency(stats.best_day.pnl) : '-'}
            </div>
            {stats.best_day && (
              <div className="text-xs text-gray-500">{formatDate(stats.best_day.date)}</div>
            )}
          </div>

          <div className={`rounded-lg border ${colors.border} ${colors.bg} p-4`}>
            <div className="text-gray-400 text-sm">Worst Day</div>
            <div className="text-xl font-bold text-red-400">
              {stats.worst_day ? formatCurrency(stats.worst_day.pnl) : '-'}
            </div>
            {stats.worst_day && (
              <div className="text-xs text-gray-500">{formatDate(stats.worst_day.date)}</div>
            )}
          </div>
        </div>
      )}

      {/* Archive List */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-16">
          <Loader2 className={`w-12 h-12 ${colors.text} animate-spin mb-4`} />
          <p className="text-gray-400">Loading archive...</p>
        </div>
      ) : archive.length === 0 ? (
        <div className={`rounded-lg border ${colors.border} ${colors.bg} p-8 text-center`}>
          <FileText className={`w-12 h-12 ${colors.text} mx-auto mb-4 opacity-50`} />
          <h2 className="text-xl font-semibold text-white mb-2">No Reports Yet</h2>
          <p className="text-gray-400 mb-4">
            Reports will appear here as they are generated after each trading day.
          </p>
          <Link
            href={`${backLink}/reports`}
            className={`px-4 py-2 rounded-lg ${colors.bg} ${colors.border} border ${colors.text} hover:opacity-80 transition-opacity inline-flex items-center gap-2`}
          >
            <FileText className="w-4 h-4" />
            View Today&apos;s Report
          </Link>
        </div>
      ) : (
        <div className="space-y-2">
          {archive.map((item) => {
            const winRate = item.trade_count > 0
              ? ((item.win_count / item.trade_count) * 100).toFixed(0)
              : '0'

            return (
              <Link
                key={item.report_date}
                href={`${backLink}/reports?date=${item.report_date}`}
                className={`block rounded-lg border ${colors.border} bg-gray-800/30 hover:bg-gray-800/50 transition-colors p-4`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`p-2 rounded-lg ${colors.bg}`}>
                      <Calendar className={`w-5 h-5 ${colors.text}`} />
                    </div>
                    <div>
                      <div className="font-medium text-white">
                        {formatDate(item.report_date)}
                      </div>
                      <div className="text-sm text-gray-500">
                        {item.trade_count} trades | {winRate}% win rate
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-6">
                    <div className="text-right">
                      <div className={`font-bold ${item.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {formatCurrency(item.total_pnl)}
                      </div>
                      <div className="text-sm text-gray-500">
                        <span className="text-green-400">{item.win_count}W</span>
                        <span className="mx-1">/</span>
                        <span className="text-red-400">{item.loss_count}L</span>
                      </div>
                    </div>

                    {item.total_pnl >= 0 ? (
                      <TrendingUp className="w-5 h-5 text-green-400" />
                    ) : (
                      <TrendingDown className="w-5 h-5 text-red-400" />
                    )}
                  </div>
                </div>

                {/* Preview of lessons if available */}
                {item.lessons_learned && item.lessons_learned.length > 0 && (
                  <div className="mt-3 text-sm text-gray-400 italic truncate">
                    &ldquo;{item.lessons_learned[0]}&rdquo;
                  </div>
                )}
              </Link>
            )
          })}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            className="p-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-400 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>

          <span className="text-gray-400">
            Page {page + 1} of {totalPages}
          </span>

          <button
            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="p-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-400 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>
      )}
    </div>
  )
}
