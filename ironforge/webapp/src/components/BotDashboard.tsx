'use client'

import React, { useState, useCallback, useEffect } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import { isMarketOpen, getCTNow } from '@/lib/pt-tiers'
import StatusCard from './StatusCard'
import PerformanceCard from './PerformanceCard'
import EquityChart, { type Period } from './EquityChart'
import PositionTable from './PositionTable'
import TradeHistory from './TradeHistory'
import LogsTable from './LogsTable'
import PTTimeline from './PTTimeline'
import PdtCard from './PdtCard'

/* Error boundary to catch component crashes without breaking the whole page */
class ComponentErrorBoundary extends React.Component<
  { fallback: string; children: React.ReactNode },
  { hasError: boolean; error: string | null }
> {
  constructor(props: { fallback: string; children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          {this.props.fallback}: {this.state.error}
        </div>
      )
    }
    return this.props.children
  }
}

const TABS = ['Equity Curve', 'Performance', 'Positions', 'Trade History', 'Logs'] as const
type Tab = (typeof TABS)[number]

const STATUS_REFRESH = 15_000   // Status refreshes every 15s
const DATA_REFRESH = 30_000     // Tables/logs refresh every 30s
const LIVE_REFRESH = 10_000     // Live position monitor refreshes every 10s

export default function BotDashboard({
  bot,
  accent,
}: {
  bot: 'flame' | 'spark' | 'inferno'
  accent: 'amber' | 'blue' | 'red'
}) {
  const [tab, setTab] = useState<Tab>('Equity Curve')
  const [equityPeriod, setEquityPeriod] = useState<Period>('intraday')

  /* ---- Status (always fetched) ---- */
  const { data: status, error: statusErr } = useSWR(
    `/api/${bot}/status`,
    fetcher,
    { refreshInterval: STATUS_REFRESH },
  )

  /* ---- Config (always fetched, slow refresh) ---- */
  const { data: config } = useSWR(
    `/api/${bot}/config`,
    fetcher,
    { refreshInterval: 60_000 },
  )

  /* ---- Equity curve (historical, fetched based on period) ---- */
  const historicalPeriod = equityPeriod === 'intraday' ? 'all' : equityPeriod
  const { data: equity } = useSWR(
    tab === 'Equity Curve' ? `/api/${bot}/equity-curve?period=${historicalPeriod}` : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  /* ---- Intraday snapshots ---- */
  const { data: intraday } = useSWR(
    tab === 'Equity Curve' && equityPeriod === 'intraday'
      ? `/api/${bot}/equity-curve/intraday`
      : null,
    fetcher,
    { refreshInterval: LIVE_REFRESH },
  )

  /* ---- Position monitor (live MTM) ---- */
  const { data: positionMonitor } = useSWR(
    tab === 'Positions' ? `/api/${bot}/position-monitor` : null,
    fetcher,
    { refreshInterval: LIVE_REFRESH },
  )

  /* ---- Position detail (per-leg quotes, sandbox P&L, metrics) ---- */
  const { data: positionDetail } = useSWR(
    tab === 'Positions' ? `/api/${bot}/position-detail` : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  /* ---- Performance ---- */
  const { data: perf } = useSWR(
    tab === 'Performance' ? `/api/${bot}/performance` : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  /* ---- Trade history ---- */
  const { data: trades } = useSWR(
    tab === 'Trade History' ? `/api/${bot}/trades` : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  /* ---- Logs ---- */
  const { data: logs } = useSWR(
    tab === 'Logs' ? `/api/${bot}/logs` : null,
    fetcher,
    { refreshInterval: DATA_REFRESH },
  )

  const onPeriodChange = useCallback((p: Period) => setEquityPeriod(p), [])

  if (statusErr) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
        <p className="text-red-400">
          Failed to load {bot.toUpperCase()} status: {statusErr.message}
        </p>
      </div>
    )
  }

  /* ---- Stale scanner banner (removed — not needed) ---- */

  const accentActive =
    accent === 'amber' ? 'border-amber-400 text-amber-400' : 'border-blue-400 text-blue-400'

  return (
    <div className="space-y-6">
      {/* Title */}
      <div>
        <div className="flex items-baseline gap-2">
          <h1
            className={`text-2xl font-bold ${accent === 'amber' ? 'text-amber-400' : accent === 'red' ? 'text-red-400' : 'text-blue-400'}`}
          >
            {bot.toUpperCase()}
          </h1>
          <span className="text-forge-muted">
            {bot === 'flame' ? '2DTE' : bot === 'inferno' ? '0DTE' : '1DTE'} Iron Condor
          </span>
        </div>
      </div>

      {/* Status card */}
      {status && <StatusCard data={status} accent={accent} config={config} bot={bot} />}

      {/* PDT Management */}
      <ComponentErrorBoundary fallback="PDT card error">
        <PdtCard bot={bot} accent={accent} />
      </ComponentErrorBoundary>

      {/* PT Timeline */}
      <PTTimeline />

      {/* Tabs */}
      <div className="flex gap-1 border-b border-forge-border">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? accentActive
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {tab === 'Equity Curve' && (
          <EquityChart
            data={equity?.curve || []}
            intradayData={intraday?.snapshots}
            startingCapital={equity?.starting_capital || status?.account?.starting_capital || 10000}
            color={accent === 'amber' ? '#f59e0b' : '#3b82f6'}
            title={`${bot.toUpperCase()} Equity Curve`}
            period={equityPeriod}
            onPeriodChange={onPeriodChange}
          />
        )}
        {tab === 'Performance' && perf && (
          <PerformanceCard data={perf} label={bot.toUpperCase()} />
        )}
        {tab === 'Positions' && (
          <PositionTable
            positions={positionMonitor?.positions || []}
            spotPrice={positionMonitor?.spot_price}
            tradierConnected={positionMonitor?.tradier_connected}
            detailData={positionDetail}
            bot={bot}
          />
        )}
        {tab === 'Trade History' && trades && <TradeHistory trades={trades.trades} />}
        {tab === 'Logs' && logs && <LogsTable logs={logs.logs} />}
      </div>
    </div>
  )
}
