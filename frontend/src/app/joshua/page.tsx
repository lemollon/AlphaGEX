'use client'

/**
 * JOSHUA (HELIOS internal) - 1DTE Directional Spreads dashboard.
 *
 * Mirrors the SOLOMON page layout (StatCards + tabs + portfolio/positions/scans
 * /trades/diagnose) but consumes the /api/joshua/* HELIOS routes. Built as a
 * self-contained page to avoid extending the platform-wide BotName union and
 * the existing trader components that gate on it. Colour palette: emerald.
 */

import React, { useState } from 'react'
import dynamic from 'next/dynamic'
import useSWR, { SWRConfiguration } from 'swr'
import {
  Target, TrendingUp, Activity, DollarSign,
  ChevronDown, ChevronUp, Server, Clock, Zap,
  Shield, Crosshair, Settings, Wallet, History, LayoutDashboard,
  Download, FileText, RotateCcw, AlertTriangle, RefreshCw, Power,
  PlayCircle, StopCircle, Search, AlertCircle, Sun,
} from 'lucide-react'

import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api'

// Lazy-load Recharts via the chart component to keep the route bundle slim
// (per common-mistakes.md rule 9.2 "Lazy-load heavy pages").
const JoshuaEquityChart = dynamic(() => import('./components/JoshuaEquityChart'), {
  ssr: false,
  loading: () => (
    <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 p-6">
      <div className="animate-pulse space-y-4">
        <div className="h-6 bg-gray-800 rounded w-1/3" />
        <div className="h-64 bg-gray-800/50 rounded" />
      </div>
    </div>
  ),
})

// ==============================================================================
// SWR + FETCHERS - thin wrappers around /api/joshua/*
// ==============================================================================

const swrCfg: SWRConfiguration = {
  revalidateOnFocus: false,
  revalidateOnReconnect: false,
  dedupingInterval: 60_000,
  errorRetryCount: 3,
  errorRetryInterval: 5_000,
  keepPreviousData: true,
}

async function fetchJSON(url: string) {
  try {
    const res = await api.get(url)
    return res.data
  } catch {
    return { success: false, data: null }
  }
}

const useJoshuaStatus = () =>
  useSWR('joshua-status', () => fetchJSON('/api/joshua/status'),
    { ...swrCfg, refreshInterval: 30_000 })

const useJoshuaPositions = () =>
  useSWR('joshua-positions', () => fetchJSON('/api/joshua/positions'),
    { ...swrCfg, refreshInterval: 30_000 })

const useJoshuaPerformance = () =>
  useSWR('joshua-performance', () => fetchJSON('/api/joshua/performance'),
    { ...swrCfg, refreshInterval: 60_000 })

const useJoshuaScanActivity = (limit: number = 100) =>
  useSWR(`joshua-scan-activity-${limit}`, () => fetchJSON(`/api/joshua/scan-activity?limit=${limit}`),
    { ...swrCfg, refreshInterval: 30_000 })

const useJoshuaSignals = (limit: number = 100) =>
  useSWR(`joshua-signals-${limit}`, () => fetchJSON(`/api/joshua/signals?limit=${limit}`),
    { ...swrCfg, refreshInterval: 30_000 })

const useJoshuaTrades = (limit: number = 200) =>
  useSWR(`joshua-trades-${limit}`, () => fetchJSON(`/api/joshua/trades?limit=${limit}`),
    { ...swrCfg, refreshInterval: 60_000 })

const useJoshuaDiagnose = () =>
  useSWR('joshua-diagnose', () => fetchJSON('/api/joshua/diagnose-trade'),
    { ...swrCfg, refreshInterval: 60_000 })

// ==============================================================================
// INTERFACES (loose; backend null-guarded everywhere)
// ==============================================================================

interface JoshuaStatus {
  bot?: string
  internal_name?: string
  ticker?: string
  mode?: string
  enabled?: boolean
  config_loaded?: boolean
  starting_capital?: number
  realized_pnl?: number
  unrealized_pnl?: number
  current_equity?: number
  open_positions?: number
  trades_today?: number
  in_trading_window?: boolean
  trading_window?: string
  current_time?: string
  heartbeat?: string | null
}

interface JoshuaPosition {
  id?: number
  spread_type?: string
  long_symbol?: string
  short_symbol?: string
  long_strike?: number
  short_strike?: number
  expiration_date?: string
  contracts?: number
  debit?: number
  status?: string
  open_time?: string
  close_time?: string
  close_price?: number
  realized_pnl?: number
  exit_reason?: string
  mark?: number | null
  unrealized_pnl?: number | null
}

interface JoshuaSignal {
  id?: number
  cycle_at_ct?: string | null
  cycle_at?: string | null
  action?: string | null
  spread_type?: string | null
  long_strike?: number | null
  short_strike?: number | null
  skip_reason?: string | null
  detail?: any
  spot?: number | null
  vix?: number | null
}

interface JoshuaScanRow {
  id?: number
  cycle_at_ct?: string | null
  cycle_at?: string | null
  outcome?: string | null
  detail?: any
}

interface JoshuaTrade extends JoshuaPosition {
  open_time_ct?: string
  close_time_ct?: string
}

// ==============================================================================
// TABS
// ==============================================================================

const JOSHUA_TABS = [
  { id: 'portfolio' as const, label: 'Portfolio', icon: Wallet },
  { id: 'overview' as const, label: 'Overview', icon: LayoutDashboard },
  { id: 'activity' as const, label: 'Activity', icon: Activity },
  { id: 'history' as const, label: 'History', icon: History },
  { id: 'diagnose' as const, label: 'Diagnose', icon: Search },
  { id: 'config' as const, label: 'Config', icon: Settings },
] as const
type JoshuaTabId = typeof JOSHUA_TABS[number]['id']

// ==============================================================================
// HELPERS
// ==============================================================================

function formatCurrency(value: number | null | undefined): string {
  const v = typeof value === 'number' && !isNaN(value) ? value : 0
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(v)
}

function formatCurrencyDetail(value: number | null | undefined): string {
  const v = typeof value === 'number' && !isNaN(value) ? value : 0
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v)
}

function formatTimeCT(ts: string | null | undefined): string {
  if (!ts) return 'N/A'
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      timeZone: 'America/Chicago',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    }) + ' CT'
  } catch {
    return ts
  }
}

function formatDateTimeCT(ts: string | null | undefined): string {
  if (!ts) return 'N/A'
  try {
    return new Date(ts).toLocaleString('en-US', {
      timeZone: 'America/Chicago',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    }) + ' CT'
  } catch {
    return ts
  }
}

function exportTradesToCSV(rows: JoshuaTrade[], filename: string) {
  const headers = [
    'ID', 'Spread', 'Long Strike', 'Short Strike', 'Expiry',
    'Contracts', 'Debit', 'Close Price', 'P&L', 'Exit Reason', 'Open', 'Close',
  ]
  const data = rows.map(r => [
    r.id ?? '',
    r.spread_type ?? '',
    r.long_strike ?? '',
    r.short_strike ?? '',
    r.expiration_date ?? '',
    r.contracts ?? '',
    r.debit ?? '',
    r.close_price ?? '',
    r.realized_pnl ?? '',
    r.exit_reason ?? '',
    r.open_time_ct ?? r.open_time ?? '',
    r.close_time_ct ?? r.close_time ?? '',
  ])
  const csv = [headers, ...data].map(row => row.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
}

// ==============================================================================
// SMALL UI PRIMITIVES (kept inline so the page is self-contained)
// ==============================================================================

function StatCard({ label, value, icon, tone = 'neutral' }: {
  label: string; value: string; icon: React.ReactNode;
  tone?: 'neutral' | 'positive' | 'negative' | 'warning'
}) {
  const toneClass = {
    neutral: 'text-emerald-300',
    positive: 'text-green-400',
    negative: 'text-red-400',
    warning: 'text-yellow-400',
  }[tone]
  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-gray-500 text-xs uppercase tracking-wide">{label}</span>
        <span className={toneClass}>{icon}</span>
      </div>
      <div className={`text-2xl font-bold ${toneClass}`}>{value}</div>
    </div>
  )
}

function SectionCard({ title, icon, children, headerRight }: {
  title: string; icon: React.ReactNode; children: React.ReactNode;
  headerRight?: React.ReactNode;
}) {
  return (
    <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-3 text-emerald-400">
          {icon}
          <h3 className="font-semibold text-white">{title}</h3>
        </div>
        {headerRight}
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}

function Empty({ title, description, icon }: { title: string; description: string; icon: React.ReactNode }) {
  return (
    <div className="text-center py-8 px-4">
      <div className="flex justify-center mb-3 text-gray-600">{icon}</div>
      <h4 className="text-lg font-medium text-gray-300 mb-1">{title}</h4>
      <p className="text-sm text-gray-500">{description}</p>
    </div>
  )
}

// ==============================================================================
// POSITION CARD (open + closed)
// ==============================================================================

function PositionCard({ position, isOpen }: { position: JoshuaPosition; isOpen: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const isBullish = (position?.spread_type || '').toUpperCase().includes('BULL')
  const liveUnrealized = position?.unrealized_pnl ?? 0
  const realized = position?.realized_pnl ?? 0
  const displayPnl = isOpen ? liveUnrealized : realized
  const pnlColor = displayPnl >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <div className={`bg-gray-800/50 rounded-lg border ${isOpen ? 'border-emerald-500/30' : 'border-gray-700'} overflow-hidden`}>
      <div
        className="p-4 cursor-pointer hover:bg-gray-700/30 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`w-2 h-2 rounded-full ${isOpen ? 'bg-emerald-400 animate-pulse' : 'bg-gray-500'}`} />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-white font-bold">{position?.long_symbol ? 'SPY' : 'SPY'}</span>
                <span className={`text-xs px-2 py-0.5 rounded ${isBullish ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                  {position?.spread_type || (isBullish ? 'BULL CALL' : 'BEAR PUT')}
                </span>
              </div>
              <span className="text-gray-400 text-sm">
                {position?.long_strike ?? '?'}/{position?.short_strike ?? '?'} - Exp: {position?.expiration_date ?? 'N/A'}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className={`font-bold ${pnlColor}`}>
              {displayPnl >= 0 ? '+' : ''}{formatCurrencyDetail(displayPnl)}
            </span>
            {isOpen && (
              <span className="text-emerald-400 text-sm">
                {position?.contracts ?? 0} ct
              </span>
            )}
            {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
          </div>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-700 p-4 space-y-4">
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <Target className="w-4 h-4 text-emerald-400" />
              <span className="text-gray-400 font-medium text-sm">Position Details</span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div>
                <span className="text-gray-500 block">Debit</span>
                <span className="text-white font-bold">${(position?.debit ?? 0).toFixed(2)}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Mark</span>
                <span className="text-white font-bold">
                  {position?.mark != null ? `$${position.mark.toFixed(4)}` : 'N/A'}
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">Contracts</span>
                <span className="text-white font-bold">{position?.contracts ?? 0}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Long Sym</span>
                <span className="text-white font-mono text-[10px]">{position?.long_symbol ?? 'N/A'}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Short Sym</span>
                <span className="text-white font-mono text-[10px]">{position?.short_symbol ?? 'N/A'}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Open</span>
                <span className="text-white">{formatDateTimeCT(position?.open_time)}</span>
              </div>
            </div>
          </div>

          {!isOpen && position?.exit_reason && (
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <History className="w-4 h-4 text-gray-400" />
                <span className="text-gray-400 font-medium text-sm">Close Details</span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-gray-500 block">Exit Reason</span>
                  <span className="text-white">{position.exit_reason}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Close Time</span>
                  <span className="text-white">{formatDateTimeCT(position?.close_time)}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Close Price</span>
                  <span className="text-white">
                    {position?.close_price != null ? `$${position.close_price.toFixed(2)}` : 'N/A'}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 block">P&L</span>
                  <span className={`font-bold ${pnlColor}`}>
                    {displayPnl >= 0 ? '+' : ''}{formatCurrencyDetail(displayPnl)}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ==============================================================================
// SCAN ACTIVITY LIST (lightweight, JOSHUA-shape only)
// ==============================================================================

function outcomeStyle(outcome: string | null | undefined): { bg: string; text: string; label: string } {
  const o = (outcome || '').toUpperCase()
  if (o === 'TRADE' || o === 'OPENED') return { bg: 'bg-green-500/15', text: 'text-green-400', label: 'TRADE' }
  if (o === 'CLOSED') return { bg: 'bg-blue-500/15', text: 'text-blue-400', label: 'CLOSED' }
  if (o === 'NO_TRADE' || o === 'SKIPPED' || o === 'SKIP') return { bg: 'bg-gray-500/15', text: 'text-gray-400', label: 'NO TRADE' }
  if (o === 'ERROR' || o === 'EXCEPTION') return { bg: 'bg-red-500/15', text: 'text-red-400', label: 'ERROR' }
  if (o === 'BLOCKED') return { bg: 'bg-yellow-500/15', text: 'text-yellow-400', label: 'BLOCKED' }
  if (o) return { bg: 'bg-emerald-500/10', text: 'text-emerald-300', label: o }
  return { bg: 'bg-gray-500/10', text: 'text-gray-400', label: 'UNKNOWN' }
}

function ScanActivityList({ rows, isLoading }: { rows: JoshuaScanRow[]; isLoading: boolean }) {
  if (isLoading) {
    return <div className="text-gray-500 text-sm flex items-center gap-2">
      <RefreshCw className="w-4 h-4 animate-spin" /> Loading scans...
    </div>
  }
  if (!rows || rows.length === 0) {
    return <Empty title="No scans yet" description="Scan activity will appear here as JOSHUA runs" icon={<Activity className="w-8 h-8" />} />
  }
  return (
    <div className="space-y-2 max-h-[600px] overflow-y-auto">
      {rows.map((scan) => {
        const style = outcomeStyle(scan.outcome)
        const detail = typeof scan.detail === 'object' && scan.detail !== null ? scan.detail : {}
        const reason = (detail as any)?.skip_reason || (detail as any)?.reason || (detail as any)?.message
        return (
          <div key={scan.id ?? `${scan.cycle_at ?? Math.random()}`}
               className="bg-gray-900/40 border border-gray-800 rounded-lg p-3 hover:bg-gray-900/60 transition-colors">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <span className={`text-[10px] px-2 py-0.5 rounded font-medium ${style.bg} ${style.text}`}>
                  {style.label}
                </span>
                <span className="text-gray-500 text-xs flex items-center gap-1 flex-shrink-0">
                  <Clock className="w-3 h-3" /> {formatTimeCT(scan.cycle_at_ct ?? scan.cycle_at)}
                </span>
                {reason && (
                  <span className="text-gray-300 text-sm truncate">{String(reason)}</span>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ==============================================================================
// MAIN PAGE
// ==============================================================================

export default function JoshuaPage() {
  const sidebarPadding = useSidebarPadding()
  const [activeTab, setActiveTab] = useState<JoshuaTabId>('portfolio')
  const { addToast } = useToast()

  const { data: statusResp, error: statusError, isLoading: statusLoading, mutate: refreshStatus } = useJoshuaStatus()
  const { data: positionsResp, isLoading: positionsLoading } = useJoshuaPositions()
  const { data: performanceResp } = useJoshuaPerformance()
  const { data: scanResp, isLoading: scansLoading } = useJoshuaScanActivity(100)
  const { data: signalsResp } = useJoshuaSignals(50)
  const { data: tradesResp } = useJoshuaTrades(200)
  const { data: diagnoseResp } = useJoshuaDiagnose()

  const status: JoshuaStatus = (statusResp?.data ?? {}) as JoshuaStatus
  const positions: JoshuaPosition[] = Array.isArray(positionsResp?.data) ? positionsResp.data : []
  const performance: any = performanceResp?.data ?? {}
  const scans: JoshuaScanRow[] = Array.isArray(scanResp?.data) ? scanResp.data : []
  const signals: JoshuaSignal[] = Array.isArray(signalsResp?.data) ? signalsResp.data : []
  const trades: JoshuaTrade[] = Array.isArray(tradesResp?.data) ? tradesResp.data : []
  const diagnose: any = diagnoseResp?.data ?? {}

  const openPositions = positions.filter(p => (p?.status ?? '').toUpperCase() === 'OPEN')
  const startingCapital = status?.starting_capital ?? 0
  const realizedPnL = performance?.total_pnl ?? status?.realized_pnl ?? 0
  const unrealizedPnL = status?.unrealized_pnl ?? 0
  const currentEquity = status?.current_equity ?? (startingCapital + realizedPnL + unrealizedPnL)
  const winRate = performance?.win_rate ?? 0
  const tradeCount = performance?.total_trades ?? 0

  const isActive = !!status?.enabled
  const hasLivePricing = unrealizedPnL !== 0 || openPositions.length === 0

  const handleRefresh = async () => {
    await refreshStatus()
    addToast({ type: 'success', title: 'Refreshed', message: 'JOSHUA data refreshed' })
  }

  const handleToggle = async () => {
    try {
      const next = !isActive
      const res = await api.post(`/api/joshua/toggle?active=${next}`)
      if (res.data?.success) {
        addToast({ type: 'success', title: next ? 'Bot Enabled' : 'Bot Disabled',
                   message: `JOSHUA is now ${next ? 'ENABLED' : 'DISABLED'}` })
        refreshStatus()
      } else {
        addToast({ type: 'error', title: 'Toggle Failed', message: res.data?.error || 'Unknown error' })
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to toggle'
      addToast({ type: 'error', title: 'Toggle Failed', message: msg })
    }
  }

  const handleForceTrade = async () => {
    try {
      const res = await api.post('/api/joshua/force-trade')
      if (res.data?.success) {
        addToast({ type: 'success', title: 'Cycle Triggered', message: 'Force-trade cycle ran' })
        refreshStatus()
      } else {
        addToast({ type: 'error', title: 'Force-Trade Failed', message: res.data?.error || 'Unknown error' })
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed'
      addToast({ type: 'error', title: 'Force-Trade Failed', message: msg })
    }
  }

  const handleForceClose = async () => {
    if (openPositions.length === 0) {
      addToast({ type: 'warning', title: 'No Open Position', message: 'Nothing to close' })
      return
    }
    try {
      const res = await api.post('/api/joshua/force-close')
      if (res.data?.success) {
        const inner = res.data?.data
        if (inner?.closed) {
          addToast({ type: 'success', title: 'Position Closed',
                     message: `P&L: ${formatCurrencyDetail(inner?.realized_pnl ?? 0)}` })
        } else {
          addToast({ type: 'warning', title: 'No Action', message: 'No open position to close' })
        }
        refreshStatus()
      } else {
        addToast({ type: 'error', title: 'Force-Close Failed', message: res.data?.error || 'Unknown error' })
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed'
      addToast({ type: 'error', title: 'Force-Close Failed', message: msg })
    }
  }

  if (statusLoading && !statusResp) {
    return (
      <>
        <Navigation />
        <div className="flex items-center justify-center h-screen text-gray-400">
          <RefreshCw className="w-6 h-6 animate-spin mr-3" />
          Loading JOSHUA...
        </div>
      </>
    )
  }

  return (
    <>
      <Navigation />
      <main className={`min-h-screen bg-black text-white px-4 pb-4 md:px-6 md:pb-6 pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-7xl mx-auto space-y-6">

          {/* Header - emerald gradient, mirrors SOLOMON's BotPageHeader shape */}
          <div className="bg-gradient-to-r from-emerald-700 to-emerald-950 rounded-xl p-6 mb-6">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-black/30 rounded-xl">
                  <Sun className="w-8 h-8 text-white" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-white">JOSHUA - 1DTE Directional</h1>
                  <p className="text-white/70">1DTE Directional Spread Strategy</p>
                  <div className="mt-2 max-w-xl">
                    <p className="text-white/60 text-sm italic">
                      &quot;Have I not commanded you? Be strong and courageous. Do not be afraid; do not be discouraged, for the LORD your God will be with you wherever you go.&quot;
                    </p>
                    <p className="text-white/40 text-xs mt-1">- Joshua 1:9</p>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded-full ${isActive ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`} />
                  <span className="text-white/80 text-sm">{isActive ? 'Active' : 'Inactive'}</span>
                </div>
                <button
                  onClick={handleRefresh}
                  className="p-2 rounded-lg bg-black/30 hover:bg-black/50 transition-colors"
                  title="Refresh"
                >
                  <RefreshCw className={`w-4 h-4 text-white/80 ${statusLoading ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>
          </div>

          {statusError && (
            <div className="bg-red-900/30 border border-red-500/50 rounded-lg p-4 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="text-red-400 font-semibold">Status load error</h3>
                <p className="text-gray-300 text-sm mt-1">{String(statusError)}</p>
              </div>
            </div>
          )}

          {/* Default-capital warning (mirror SOLOMON pattern) */}
          {startingCapital === 0 && (
            <div className="bg-yellow-900/30 border border-yellow-500/50 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-yellow-400 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <h3 className="text-yellow-400 font-semibold">Starting capital not set</h3>
                  <p className="text-gray-300 text-sm mt-1">
                    JOSHUA does not yet have a starting capital configured. P&L returns will not compute correctly.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* JOSHUA strategy banner (mirror of SOLOMON's vs-GIDEON banner) */}
          <div className="bg-emerald-900/20 border border-emerald-500/30 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <Shield className="w-5 h-5 text-emerald-400 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <h3 className="text-emerald-400 font-semibold">JOSHUA: 1DTE Directional Spreads</h3>
                <p className="text-gray-400 text-sm mt-1">
                  HELIOS bot trades next-day-expiring SPY directional debit spreads, max 1 open position.
                </p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3 text-sm">
                  <div>
                    <span className="text-gray-500">Ticker:</span>
                    <span className="text-emerald-400 ml-2">{status?.ticker ?? 'SPY'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Mode:</span>
                    <span className="text-emerald-400 ml-2">{(status?.mode ?? 'paper').toUpperCase()}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">DTE:</span>
                    <span className="text-emerald-400 ml-2">1</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Max Positions:</span>
                    <span className="text-emerald-400 ml-2">1</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Quick stats */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <StatCard
              label={hasLivePricing ? 'Current Equity' : 'Realized Equity'}
              value={formatCurrency(currentEquity)}
              icon={<DollarSign className="w-4 h-4" />}
              tone="neutral"
            />
            <StatCard
              label="Realized P&L"
              value={`${realizedPnL >= 0 ? '+' : ''}${formatCurrency(realizedPnL)}`}
              icon={<TrendingUp className="w-4 h-4" />}
              tone={realizedPnL >= 0 ? 'positive' : 'negative'}
            />
            <StatCard
              label="Win Rate"
              value={`${(winRate ?? 0).toFixed(1)}%`}
              icon={<Target className="w-4 h-4" />}
              tone={winRate >= 60 ? 'positive' : winRate >= 50 ? 'warning' : 'negative'}
            />
            <StatCard
              label="Trades"
              value={String(tradeCount ?? 0)}
              icon={<Activity className="w-4 h-4" />}
              tone="neutral"
            />
            <StatCard
              label="Open Positions"
              value={String(openPositions.length)}
              icon={<Crosshair className="w-4 h-4" />}
              tone="neutral"
            />
          </div>

          {/* Tabs */}
          <div className="flex gap-2 border-b border-gray-800 pb-2 overflow-x-auto">
            {JOSHUA_TABS.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors flex-shrink-0 ${
                    activeTab === tab.id
                      ? 'bg-emerald-900/20 text-emerald-400 border border-emerald-700/50'
                      : 'text-gray-400 hover:text-white hover:bg-gray-800'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span className="text-sm font-medium">{tab.label}</span>
                </button>
              )
            })}
          </div>

          {/* Tab content */}
          <div className="space-y-6">

            {activeTab === 'portfolio' && (
              <>
                {/* Status banner (inline mirror of SOLOMON's BotStatusBanner) */}
                <div className={`rounded-lg px-4 py-3 mb-2 border ${isActive
                  ? 'bg-green-500/10 border-green-500/30' : 'bg-gray-500/10 border-gray-500/30'}`}>
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <div className="flex items-center gap-3">
                      <span className="relative flex h-3 w-3">
                        {isActive && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />}
                        <span className={`relative inline-flex rounded-full h-3 w-3 ${isActive ? 'bg-green-500' : 'bg-gray-500'}`} />
                      </span>
                      <span className={`font-bold ${isActive ? 'text-green-400' : 'text-gray-400'}`}>JOSHUA</span>
                      <span className={`text-xs px-2 py-0.5 rounded border ${isActive
                        ? 'bg-green-500/20 text-green-400 border-green-500/30'
                        : 'bg-gray-500/20 text-gray-400 border-gray-500/30'}`}>
                        {isActive ? 'ACTIVE' : 'INACTIVE'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-sm">
                      <Clock className="w-4 h-4 text-gray-400" />
                      <span className="text-gray-400">Last scan:</span>
                      <span className="font-mono text-white">{formatTimeCT(status?.heartbeat)}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="flex items-center gap-1.5">
                        <Zap className="w-4 h-4 text-emerald-400" />
                        <span className="text-gray-400 text-sm">Open:</span>
                        <span className={`font-bold ${openPositions.length > 0 ? 'text-emerald-400' : 'text-gray-500'}`}>
                          {openPositions.length}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Activity className="w-4 h-4 text-blue-400" />
                        <span className="text-gray-400 text-sm">Today:</span>
                        <span className="font-bold text-white">{status?.trades_today ?? 0}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Live unrealized PnL card (inline mirror of UnrealizedPnLCard) */}
                <SectionCard title="Live Unrealized P&L" icon={<TrendingUp className="w-5 h-5" />}>
                  {openPositions.length === 0 ? (
                    <Empty title="No open position" description="Live unrealized P&L appears when JOSHUA holds a trade"
                           icon={<TrendingUp className="w-8 h-8" />} />
                  ) : (
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                      <div className="bg-gray-900/50 rounded-lg p-3">
                        <span className="text-gray-500 text-xs block">Unrealized P&L</span>
                        <span className={`text-xl font-bold ${unrealizedPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {unrealizedPnL >= 0 ? '+' : ''}{formatCurrencyDetail(unrealizedPnL)}
                        </span>
                      </div>
                      <div className="bg-gray-900/50 rounded-lg p-3">
                        <span className="text-gray-500 text-xs block">Open Spread Mark</span>
                        <span className="text-xl font-bold text-white">
                          {openPositions[0]?.mark != null ? `$${openPositions[0].mark.toFixed(4)}` : 'N/A'}
                        </span>
                      </div>
                      <div className="bg-gray-900/50 rounded-lg p-3">
                        <span className="text-gray-500 text-xs block">Debit Paid</span>
                        <span className="text-xl font-bold text-white">
                          ${(openPositions[0]?.debit ?? 0).toFixed(2)}
                        </span>
                      </div>
                    </div>
                  )}
                </SectionCard>

                {/* Equity curve */}
                <JoshuaEquityChart />

                {/* Open Positions */}
                <SectionCard title="Open Positions" icon={<Crosshair className="w-5 h-5" />}>
                  {positionsLoading ? (
                    <div className="text-gray-500 text-sm flex items-center gap-2">
                      <RefreshCw className="w-4 h-4 animate-spin" /> Loading...
                    </div>
                  ) : openPositions.length === 0 ? (
                    <Empty title="No open positions" description="Positions appear here when trades are opened"
                           icon={<Crosshair className="w-8 h-8" />} />
                  ) : (
                    <div className="space-y-4">
                      {openPositions.map((p) => (
                        <PositionCard key={p?.id ?? Math.random()} position={p} isOpen={true} />
                      ))}
                    </div>
                  )}
                </SectionCard>
              </>
            )}

            {activeTab === 'overview' && (
              <SectionCard title="Bot Status" icon={<Server className="w-5 h-5" />}>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Mode</span>
                    <span className="text-xl font-bold text-white">{(status?.mode ?? 'paper').toUpperCase()}</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Ticker</span>
                    <span className="text-xl font-bold text-emerald-400">{status?.ticker ?? 'SPY'}</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Trading Window</span>
                    <span className={`text-xl font-bold ${status?.in_trading_window ? 'text-green-400' : 'text-gray-400'}`}>
                      {status?.in_trading_window ? 'ACTIVE' : 'CLOSED'}
                    </span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Last Scan</span>
                    <span className="text-lg font-bold text-white">{formatTimeCT(status?.heartbeat)}</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Current Time (CT)</span>
                    <span className="text-lg font-bold text-white">{status?.current_time ?? 'Unknown'}</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Trades Today</span>
                    <span className="text-xl font-bold text-white">{status?.trades_today ?? 0}</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Enabled</span>
                    <span className={`text-xl font-bold ${isActive ? 'text-green-400' : 'text-gray-400'}`}>
                      {isActive ? 'YES' : 'NO'}
                    </span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Internal Name</span>
                    <span className="text-xl font-bold text-emerald-400">{status?.internal_name ?? 'HELIOS'}</span>
                  </div>
                </div>

                {/* Performance breakdown by exit reason */}
                {Array.isArray(performance?.by_exit_reason) && performance.by_exit_reason.length > 0 && (
                  <div className="mt-6">
                    <h4 className="text-sm font-semibold text-gray-300 mb-3">P&L by Exit Reason</h4>
                    <div className="space-y-2">
                      {performance.by_exit_reason.map((row: any, idx: number) => (
                        <div key={idx} className="flex items-center justify-between bg-gray-800/40 rounded-lg p-3">
                          <span className="text-gray-300 text-sm font-medium">{row?.exit_reason ?? 'UNKNOWN'}</span>
                          <div className="flex gap-6 text-xs">
                            <span className="text-gray-500">Trades: <span className="text-white font-bold">{row?.trades ?? 0}</span></span>
                            <span className="text-gray-500">Avg: <span className="text-white font-bold">{formatCurrencyDetail(row?.avg_pnl ?? 0)}</span></span>
                            <span className={(row?.total_pnl ?? 0) >= 0 ? 'text-green-400 font-bold' : 'text-red-400 font-bold'}>
                              {(row?.total_pnl ?? 0) >= 0 ? '+' : ''}{formatCurrencyDetail(row?.total_pnl ?? 0)}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </SectionCard>
            )}

            {activeTab === 'activity' && (
              <SectionCard title="Scan Activity" icon={<Activity className="w-5 h-5" />}>
                <ScanActivityList rows={scans} isLoading={scansLoading} />
              </SectionCard>
            )}

            {activeTab === 'history' && (
              <SectionCard
                title="Closed Trades"
                icon={<History className="w-5 h-5" />}
                headerRight={
                  trades.length > 0 ? (
                    <button
                      onClick={() => {
                        const today = new Date().toISOString().split('T')[0]
                        exportTradesToCSV(trades, `joshua-trades-${today}.csv`)
                        addToast({ type: 'success', title: 'Export Complete', message: `Exported ${trades.length} trades to CSV` })
                      }}
                      className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/30 rounded-lg transition-colors text-sm"
                    >
                      <Download className="w-4 h-4" />
                      <span>Export CSV</span>
                    </button>
                  ) : null
                }
              >
                {trades.length === 0 ? (
                  <Empty title="No closed trades yet" description="Trade history will appear here" icon={<History className="w-8 h-8" />} />
                ) : (
                  <div className="space-y-3">
                    {trades.map((t) => (
                      <PositionCard key={t?.id ?? Math.random()} position={t} isOpen={false} />
                    ))}
                  </div>
                )}

                {/* Recent signals (used to inspect why a cycle did/didn't fire) */}
                <div className="mt-6">
                  <h4 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
                    <FileText className="w-4 h-4 text-emerald-400" /> Recent Signals
                  </h4>
                  {signals.length === 0 ? (
                    <p className="text-gray-500 text-sm">No signals recorded yet.</p>
                  ) : (
                    <div className="space-y-1.5 max-h-[400px] overflow-y-auto">
                      {signals.slice(0, 25).map((s, i) => (
                        <div key={s.id ?? i} className="bg-gray-900/40 border border-gray-800 rounded p-2.5 text-xs grid grid-cols-12 gap-2 items-center">
                          <span className="text-gray-500 col-span-3 flex items-center gap-1">
                            <Clock className="w-3 h-3" /> {formatTimeCT(s.cycle_at_ct ?? s.cycle_at)}
                          </span>
                          <span className={`col-span-2 font-bold ${
                            (s.action ?? '').toUpperCase() === 'TRADE'
                              ? 'text-green-400'
                              : (s.action ?? '').toUpperCase() === 'SKIP'
                                ? 'text-gray-400' : 'text-yellow-400'
                          }`}>
                            {(s.action ?? '?').toUpperCase()}
                          </span>
                          <span className="col-span-2 text-emerald-300">{s.spread_type ?? ''}</span>
                          <span className="col-span-2 text-white">
                            {s.long_strike ?? ''}{s.short_strike ? `/${s.short_strike}` : ''}
                          </span>
                          <span className="col-span-3 text-gray-400 truncate">{s.skip_reason ?? ''}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </SectionCard>
            )}

            {activeTab === 'diagnose' && (
              <SectionCard title="Diagnose Last Cycle" icon={<Search className="w-5 h-5" />}>
                {!diagnose?.available ? (
                  <Empty
                    title="No signals recorded yet"
                    description={diagnose?.message ?? 'JOSHUA has not yet logged a signal cycle.'}
                    icon={<Search className="w-8 h-8" />}
                  />
                ) : (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className="bg-gray-800/50 rounded-lg p-3">
                        <span className="text-gray-500 text-xs block">Action</span>
                        <span className={`text-lg font-bold ${
                          (diagnose?.action ?? '').toUpperCase() === 'TRADE' ? 'text-green-400' : 'text-yellow-400'
                        }`}>
                          {(diagnose?.action ?? 'N/A').toUpperCase()}
                        </span>
                      </div>
                      <div className="bg-gray-800/50 rounded-lg p-3">
                        <span className="text-gray-500 text-xs block">Spread Type</span>
                        <span className="text-lg font-bold text-emerald-400">{diagnose?.spread_type ?? 'N/A'}</span>
                      </div>
                      <div className="bg-gray-800/50 rounded-lg p-3">
                        <span className="text-gray-500 text-xs block">Spot</span>
                        <span className="text-lg font-bold text-white">
                          {diagnose?.spot != null ? `$${Number(diagnose.spot).toFixed(2)}` : 'N/A'}
                        </span>
                      </div>
                      <div className="bg-gray-800/50 rounded-lg p-3">
                        <span className="text-gray-500 text-xs block">VIX</span>
                        <span className="text-lg font-bold text-white">
                          {diagnose?.vix != null ? Number(diagnose.vix).toFixed(2) : 'N/A'}
                        </span>
                      </div>
                    </div>

                    {diagnose?.skip_reason && (
                      <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-4">
                        <h4 className="text-yellow-400 font-semibold text-sm mb-2 flex items-center gap-2">
                          <AlertCircle className="w-4 h-4" /> Skip Reason
                        </h4>
                        <p className="text-gray-300 text-sm">{diagnose.skip_reason}</p>
                      </div>
                    )}

                    {diagnose?.detail && (
                      <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-4">
                        <h4 className="text-gray-400 font-semibold text-sm mb-2">Detail</h4>
                        <pre className="text-xs text-gray-300 whitespace-pre-wrap break-words font-mono max-h-96 overflow-y-auto">
                          {typeof diagnose.detail === 'string'
                            ? diagnose.detail
                            : JSON.stringify(diagnose.detail, null, 2)}
                        </pre>
                      </div>
                    )}

                    <div className="text-xs text-gray-500 flex items-center gap-2">
                      <Clock className="w-3 h-3" />
                      Cycle: {formatDateTimeCT(diagnose?.cycle_at_ct)} (signal #{diagnose?.signal_id ?? '?'})
                    </div>
                  </div>
                )}
              </SectionCard>
            )}

            {activeTab === 'config' && (
              <>
                <SectionCard title="Configuration" icon={<Settings className="w-5 h-5" />}>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-gray-800/50 rounded-lg p-4">
                      <span className="text-gray-500 text-sm block">Strategy</span>
                      <span className="text-xl font-bold text-white">1DTE Directional</span>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-4">
                      <span className="text-gray-500 text-sm block">Ticker</span>
                      <span className="text-xl font-bold text-emerald-400">{status?.ticker ?? 'SPY'}</span>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-4">
                      <span className="text-gray-500 text-sm block">Mode</span>
                      <span className="text-xl font-bold text-white">{(status?.mode ?? 'paper').toUpperCase()}</span>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-4">
                      <span className="text-gray-500 text-sm block">Trading Window</span>
                      <span className="text-xl font-bold text-white">{status?.trading_window ?? '08:30-14:30 CT'}</span>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-4">
                      <span className="text-gray-500 text-sm block">Starting Capital</span>
                      <span className="text-xl font-bold text-white">{formatCurrency(startingCapital)}</span>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-4">
                      <span className="text-gray-500 text-sm block">Max Positions</span>
                      <span className="text-xl font-bold text-white">1</span>
                    </div>
                  </div>
                </SectionCard>

                {/* Operator controls */}
                <SectionCard title="Operator Controls" icon={<Power className="w-5 h-5" />}>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <button
                      onClick={handleToggle}
                      className={`flex items-center justify-center gap-2 px-4 py-3 rounded-lg border transition-colors ${
                        isActive
                          ? 'bg-red-500/15 hover:bg-red-500/25 text-red-400 border-red-500/30'
                          : 'bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border-emerald-500/30'
                      }`}
                    >
                      <Power className="w-4 h-4" />
                      {isActive ? 'Disable JOSHUA' : 'Enable JOSHUA'}
                    </button>
                    <button
                      onClick={handleForceTrade}
                      className="flex items-center justify-center gap-2 px-4 py-3 bg-blue-500/15 hover:bg-blue-500/25 text-blue-400 border border-blue-500/30 rounded-lg transition-colors"
                    >
                      <PlayCircle className="w-4 h-4" />
                      Force Trade Cycle
                    </button>
                    <button
                      onClick={handleForceClose}
                      disabled={openPositions.length === 0}
                      className="flex items-center justify-center gap-2 px-4 py-3 bg-yellow-500/15 hover:bg-yellow-500/25 disabled:opacity-30 disabled:cursor-not-allowed text-yellow-400 border border-yellow-500/30 rounded-lg transition-colors"
                    >
                      <StopCircle className="w-4 h-4" />
                      Force-Close Open Position
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mt-3 flex items-center gap-1">
                    <RotateCcw className="w-3 h-3" />
                    Force-close uses MTM via live Tradier quote, falling back to entry debit if quotes are unavailable.
                  </p>
                </SectionCard>
              </>
            )}
          </div>
        </div>
      </main>
    </>
  )
}
