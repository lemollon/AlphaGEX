'use client'

import { useState } from 'react'
import {
  Download, FileSpreadsheet, FileText, ChevronDown,
  TrendingUp, Brain, RotateCcw, FileCheck, Loader2
} from 'lucide-react'
import { apiClient } from '@/lib/api'

interface ExportButtonsProps {
  symbol?: string
  startDate?: string
  endDate?: string
}

type ExportType = 'trades' | 'pnl-attribution' | 'decision-logs' | 'wheel-cycles' | 'full-audit'

export default function ExportButtons({ symbol = 'SPY', startDate, endDate }: ExportButtonsProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [loading, setLoading] = useState<ExportType | null>(null)

  const exports: { type: ExportType; label: string; description: string; icon: React.ReactNode }[] = [
    {
      type: 'trades',
      label: 'Trade History',
      description: 'Complete trade log with P&L',
      icon: <TrendingUp className="w-4 h-4" />
    },
    {
      type: 'pnl-attribution',
      label: 'P&L Attribution',
      description: 'See how each trade contributed',
      icon: <FileSpreadsheet className="w-4 h-4" />
    },
    {
      type: 'decision-logs',
      label: 'Decision Logs',
      description: 'AI reasoning and analysis',
      icon: <Brain className="w-4 h-4" />
    },
    {
      type: 'wheel-cycles',
      label: 'Wheel Cycles',
      description: 'Wheel strategy history',
      icon: <RotateCcw className="w-4 h-4" />
    },
    {
      type: 'full-audit',
      label: 'Full Audit Package',
      description: 'Everything in one file',
      icon: <FileCheck className="w-4 h-4" />
    }
  ]

  const handleExport = async (type: ExportType) => {
    setLoading(type)
    try {
      // Use centralized API client for export
      const response = await apiClient.exportData(type, {
        symbol,
        start_date: startDate,
        end_date: endDate
      })

      const blob = response.data
      const contentDisposition = response.headers?.['content-disposition']
      let filename = `${type}_${symbol}_export.xlsx`

      if (contentDisposition) {
        const match = contentDisposition.match(/filename=(.+)/)
        if (match) {
          filename = match[1].replace(/"/g, '')
        }
      }

      // Create download link
      const downloadUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(downloadUrl)
      document.body.removeChild(a)

      setIsOpen(false)
    } catch (error) {
      console.error('Export error:', error)
      alert('Export failed. Please try again.')
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors border border-slate-600"
      >
        <Download className="w-4 h-4 text-gray-400" />
        <span className="text-sm text-white">Export to Excel</span>
        <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />

          {/* Dropdown */}
          <div className="absolute right-0 top-full mt-2 w-72 bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-20 overflow-hidden">
            <div className="p-3 border-b border-slate-700">
              <h3 className="text-sm font-medium text-white">Export Trade Data</h3>
              <p className="text-xs text-gray-400 mt-1">Download your data for analysis</p>
            </div>

            <div className="py-1">
              {exports.map((exp) => (
                <button
                  key={exp.type}
                  onClick={() => handleExport(exp.type)}
                  disabled={loading !== null}
                  className="w-full px-4 py-3 flex items-start gap-3 hover:bg-slate-700/50 transition-colors disabled:opacity-50"
                >
                  <div className="p-2 bg-slate-700 rounded-lg text-gray-400">
                    {loading === exp.type ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      exp.icon
                    )}
                  </div>
                  <div className="text-left">
                    <p className="text-sm font-medium text-white">{exp.label}</p>
                    <p className="text-xs text-gray-400">{exp.description}</p>
                  </div>
                </button>
              ))}
            </div>

            <div className="p-3 border-t border-slate-700 bg-slate-800/50">
              <p className="text-xs text-gray-500 flex items-center gap-1">
                <FileSpreadsheet className="w-3 h-3" />
                All exports include full P&L breakdown
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
