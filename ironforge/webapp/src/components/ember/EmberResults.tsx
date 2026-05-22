'use client'

import { useState } from 'react'
import {
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  ComposedChart,
} from 'recharts'
import { type EvaluateResult, type SummaryStats, type PolicyResult, type TradeRow, type EquityCurvePoint } from '@/app/ember/page'

/* ------------------------------------------------------------------ */
/*  Skeleton                                                            */
/* ------------------------------------------------------------------ */

function Skeleton({ h = 'h-4', w = 'w-full' }: { h?: string; w?: string }) {
  return <div className={`${h} ${w} rounded skeleton skeleton-pulse`} />
}

/* ------------------------------------------------------------------ */
/*  Summary stat card                                                   */
/* ------------------------------------------------------------------ */

function StatBlock({
  label,
  value,
  color,
  sub,
}: {
  label: string
  value: string
  color?: string
  sub?: string
}) {
  return (
    <div>
      <p className="text-xs text-forge-muted">{label}</p>
      <p className={`text-base font-semibold tabular-nums ${color ?? 'text-gray-200'}`}>{value}</p>
      {sub && <p className="text-[10px] text-forge-muted">{sub}</p>}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Pnl color helper                                                    */
/* ------------------------------------------------------------------ */

function pnlColor(v: number | null | undefined): string {
  if (v == null) return 'text-gray-400'
  if (v > 0) return 'text-emerald-400'
  if (v < 0) return 'text-red-400'
  return 'text-gray-400'
}

function fmtPnl(v: number | null | undefined): string {
  if (v == null) return '—'
  const sign = v >= 0 ? '+' : ''
  return `${sign}$${Math.abs(v).toFixed(2)}`
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(1)}%`
}

function fmtNum(v: number | null | undefined, decimals = 2): string {
  if (v == null) return '—'
  return v.toFixed(decimals)
}

/* ------------------------------------------------------------------ */
/*  Summary panel (Chosen vs Baseline)                                  */
/* ------------------------------------------------------------------ */

interface SummaryPanelProps {
  stats: SummaryStats
  label: string
  isChosen?: boolean
  period: 'in_sample' | 'oos'
}

function SummaryPanel({ stats, label, isChosen, period }: SummaryPanelProps) {
  const borderCls = isChosen
    ? 'border-amber-500/40'
    : 'border-forge-border'
  const headerColor = isChosen ? 'text-amber-300' : 'text-gray-400'
  const badge = period === 'oos'
    ? <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-300 ml-2">OOS</span>
    : <span className="text-[10px] px-1.5 py-0.5 rounded bg-forge-border text-gray-400 ml-2">In-Sample</span>

  const evColor = stats.ev_per_contract > 0 ? 'text-emerald-400' : 'text-red-400'

  return (
    <div className={`rounded-xl border ${borderCls} bg-forge-card/80 p-4`}>
      <div className="flex items-center gap-2 mb-3">
        {isChosen && (
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" className="shrink-0">
            <polygon points="6.5,1 8.1,5.1 12.5,5.5 9.3,8.3 10.3,12.5 6.5,10.2 2.7,12.5 3.7,8.3 0.5,5.5 4.9,5.1" fill="#f59e0b" />
          </svg>
        )}
        <span className={`text-sm font-semibold ${headerColor}`}>{label}</span>
        {badge}
      </div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <StatBlock
          label="EV / contract"
          value={fmtPnl(stats.ev_per_contract)}
          color={evColor}
        />
        <StatBlock
          label="Win Rate"
          value={fmtPct(stats.win_rate)}
          color={stats.win_rate >= 60 ? 'text-emerald-400' : stats.win_rate >= 50 ? 'text-gray-200' : 'text-red-400'}
        />
        <StatBlock
          label="Total P&L"
          value={fmtPnl(stats.total_pnl)}
          color={pnlColor(stats.total_pnl)}
          sub={`${stats.n} trades`}
        />
        <StatBlock
          label="Sharpe"
          value={fmtNum(stats.sharpe)}
          color={stats.sharpe == null ? 'text-gray-400' : stats.sharpe >= 1 ? 'text-emerald-400' : stats.sharpe >= 0 ? 'text-gray-300' : 'text-red-400'}
        />
      </div>

      <div className="grid grid-cols-3 gap-3 pt-3 border-t border-forge-border/40 text-xs">
        <div>
          <p className="text-forge-muted">Max DD</p>
          <p className={`font-medium ${stats.max_drawdown != null && stats.max_drawdown < 0 ? 'text-red-400' : 'text-gray-300'}`}>
            {stats.max_drawdown != null ? fmtPnl(stats.max_drawdown) : '—'}
          </p>
        </div>
        <div>
          <p className="text-forge-muted">Avg Hold</p>
          <p className="font-medium text-gray-300">
            {stats.avg_hold_min != null ? `${stats.avg_hold_min.toFixed(0)}min` : '—'}
          </p>
        </div>
        <div>
          <p className="text-forge-muted">EOD exits</p>
          <p className="font-medium text-gray-300">
            {stats.pct_eod != null ? `${stats.pct_eod.toFixed(0)}%` : '—'}
          </p>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Equity Chart (custom — EMBER-specific OOS shading)                  */
/* ------------------------------------------------------------------ */

function EmberEquityChart({ curve }: { curve: EquityCurvePoint[] }) {
  if (!curve.length) {
    return (
      <div className="flex items-center justify-center h-48 text-forge-muted text-sm">
        No equity curve data
      </div>
    )
  }

  // Build cumulative starting from 0
  const chartData = curve.map((pt) => ({
    date: pt.date,
    cum_pnl: pt.cum_pnl ?? 0,
    is_oos: pt.is_oos,
    // OOS channel — only show when is_oos = true
    oos_value: pt.is_oos ? (pt.cum_pnl ?? 0) : undefined,
    is_fill: pt.cum_pnl,
  }))

  const last = curve[curve.length - 1]
  const isPositive = (last?.cum_pnl ?? 0) >= 0
  const fillColor = isPositive ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)'
  const lineColor = isPositive ? '#10b981' : '#ef4444'

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-400">Equity Curve — Chosen Policy</h3>
        <div className="flex items-center gap-3 text-xs text-forge-muted">
          <span className="flex items-center gap-1">
            <span className="inline-block w-8 h-0.5 bg-current" />
            In-sample
          </span>
          <span className="flex items-center gap-1 text-violet-300">
            <span className="inline-block w-8 h-0.5 bg-current" />
            OOS
          </span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={chartData}>
          <XAxis
            dataKey="date"
            tickFormatter={(d: string) => {
              if (!d) return ''
              return new Date(d).toLocaleDateString('en-US', { month: 'numeric', day: 'numeric' })
            }}
            stroke="#44403c"
            tick={{ fill: '#a8a29e', fontSize: 11 }}
            interval="preserveStartEnd"
          />
          <YAxis
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
            stroke="#44403c"
            tick={{ fill: '#a8a29e', fontSize: 11 }}
            domain={['auto', 'auto']}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #292524', borderRadius: 8 }}
            labelStyle={{ color: '#a8a29e', fontSize: 11 }}
            formatter={(value: unknown, name: string) => {
              const v = typeof value === 'number' ? value : 0
              const label = name === 'oos_value' ? 'OOS cum P&L' : 'Cum P&L'
              return [`${v >= 0 ? '+' : ''}$${v.toFixed(2)}`, label]
            }}
            labelFormatter={(label: string) => label ? `${label}` : ''}
          />
          <ReferenceLine y={0} stroke="#78716c" strokeDasharray="4 4" />
          {/* Main equity line */}
          <Area
            type="monotone"
            dataKey="cum_pnl"
            stroke={lineColor}
            strokeWidth={2}
            fill={fillColor}
            dot={false}
            isAnimationActive={false}
          />
          {/* OOS overlay — violet tint */}
          <Area
            type="monotone"
            dataKey="oos_value"
            stroke="#8b5cf6"
            strokeWidth={2.5}
            fill="rgba(139,92,246,0.15)"
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="text-[10px] text-forge-muted mt-2 px-1">
        Violet = out-of-sample (OOS) segment. OOS is a held-out date range not used in policy selection.
      </p>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Grid Sweep table                                                    */
/* ------------------------------------------------------------------ */

function EmberGrid({ grid }: { grid: PolicyResult[] }) {
  const [sortKey, setSortKey] = useState<'ev_is' | 'ev_oos' | 'wr_is' | 'wr_oos'>('ev_is')
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 20

  if (!grid.length) {
    return (
      <div className="flex items-center justify-center h-24 text-forge-muted text-sm">
        No grid data
      </div>
    )
  }

  type SortKey = 'ev_is' | 'ev_oos' | 'wr_is' | 'wr_oos'
  const getValue = (row: PolicyResult, k: SortKey): number => {
    if (k === 'ev_is') return row.in_sample?.ev_per_contract ?? -999
    if (k === 'ev_oos') return row.oos?.ev_per_contract ?? -999
    if (k === 'wr_is') return row.in_sample?.win_rate ?? 0
    if (k === 'wr_oos') return row.oos?.win_rate ?? 0
    return 0
  }

  const sorted = [...grid].sort((a, b) => getValue(b, sortKey) - getValue(a, sortKey))
  const maxEvIs = Math.max(...grid.map((r) => r.in_sample?.ev_per_contract ?? -999))
  const pageRows = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)

  function ColHeader({ k, label }: { k: SortKey; label: string }) {
    const active = sortKey === k
    return (
      <th
        className="text-right p-2.5 cursor-pointer select-none hover:text-gray-200 transition-colors"
        onClick={() => { setSortKey(k); setPage(0) }}
      >
        <span className={active ? 'text-amber-300 font-semibold' : ''}>
          {label}
          {active && (
            <svg width="10" height="10" viewBox="0 0 10 10" className="inline ml-1 mb-0.5">
              <path d="M2 3L5 7L8 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" fill="none" />
            </svg>
          )}
        </span>
      </th>
    )
  }

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-forge-border text-forge-muted text-xs">
              <th className="text-left p-2.5">Policy</th>
              <ColHeader k="ev_is" label="EV/c (IS)" />
              <ColHeader k="wr_is" label="WR (IS)" />
              <ColHeader k="ev_oos" label="EV/c (OOS)" />
              <ColHeader k="wr_oos" label="WR (OOS)" />
              <th className="text-right p-2.5">P&L (IS)</th>
              <th className="text-right p-2.5">P&L (OOS)</th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row) => {
              const isBest = (row.in_sample?.ev_per_contract ?? -999) === maxEvIs
              const isLive = row.policy === 'spark_live'
              const evIs = row.in_sample?.ev_per_contract ?? null
              const evOos = row.oos?.ev_per_contract ?? null
              return (
                <tr
                  key={row.policy}
                  className={`border-b border-forge-border/50 ${
                    isBest ? 'bg-amber-500/8' : isLive ? 'bg-blue-500/8' : 'hover:bg-forge-border/20'
                  }`}
                >
                  <td className="p-2.5 font-mono text-xs">
                    {isBest && (
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" className="inline mr-1.5 mb-0.5">
                        <polygon points="5,1 6.2,3.9 9.5,4.2 7.1,6.4 7.9,9.7 5,8 2.1,9.7 2.9,6.4 0.5,4.2 3.8,3.9" fill="#f59e0b" />
                      </svg>
                    )}
                    {isLive && (
                      <span className="text-[9px] px-1 py-0.5 rounded bg-blue-500/20 text-blue-300 mr-1.5">LIVE</span>
                    )}
                    <span className={isBest ? 'text-amber-300' : isLive ? 'text-blue-300' : 'text-gray-300'}>
                      {row.policy}
                    </span>
                  </td>
                  <td className={`p-2.5 text-right font-mono text-xs ${pnlColor(evIs)}`}>
                    {evIs != null ? fmtPnl(evIs) : '—'}
                  </td>
                  <td className="p-2.5 text-right text-xs text-gray-300">
                    {row.in_sample?.win_rate != null ? `${row.in_sample.win_rate.toFixed(1)}%` : '—'}
                  </td>
                  <td className={`p-2.5 text-right font-mono text-xs ${pnlColor(evOos)}`}>
                    {evOos != null ? fmtPnl(evOos) : '—'}
                  </td>
                  <td className="p-2.5 text-right text-xs text-gray-300">
                    {row.oos?.win_rate != null ? `${row.oos.win_rate.toFixed(1)}%` : '—'}
                  </td>
                  <td className={`p-2.5 text-right font-mono text-xs ${pnlColor(row.in_sample?.total_pnl)}`}>
                    {row.in_sample?.total_pnl != null ? fmtPnl(row.in_sample.total_pnl) : '—'}
                  </td>
                  <td className={`p-2.5 text-right font-mono text-xs ${pnlColor(row.oos?.total_pnl)}`}>
                    {row.oos?.total_pnl != null ? fmtPnl(row.oos.total_pnl) : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-2 border-t border-forge-border text-xs text-forge-muted">
          <span>{sorted.length} policies</span>
          <div className="flex items-center gap-2">
            <button
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              className="px-2.5 py-1 rounded border border-forge-border disabled:opacity-30 hover:bg-forge-border/40 transition-colors"
            >
              Prev
            </button>
            <span>{page + 1} / {totalPages}</span>
            <button
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              className="px-2.5 py-1 rounded border border-forge-border disabled:opacity-30 hover:bg-forge-border/40 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Per-trade table                                                      */
/* ------------------------------------------------------------------ */

function minuteToTime(minute: number | null | undefined): string {
  if (minute == null) return '—'
  const totalMin = 9 * 60 + 30 + minute
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  const h12 = h > 12 ? h - 12 : h === 0 ? 12 : h
  const ampm = h < 12 ? 'AM' : 'PM'
  return `${h12}:${String(m).padStart(2, '0')} ${ampm}`
}

function EmberTradeTable({ trades }: { trades: TradeRow[] }) {
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 30

  if (!trades.length) {
    return (
      <div className="flex items-center justify-center h-24 text-forge-muted text-sm">
        No trades
      </div>
    )
  }

  const pageRows = trades.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(trades.length / PAGE_SIZE)

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-forge-border text-forge-muted">
              <th className="text-left p-2.5">Date</th>
              <th className="text-right p-2.5">Entry</th>
              <th className="text-right p-2.5">Exit</th>
              <th className="text-left p-2.5">Reason</th>
              <th className="text-right p-2.5">Credit</th>
              <th className="text-right p-2.5">Close</th>
              <th className="text-right p-2.5">P&L</th>
              <th className="text-right p-2.5">Max Fav</th>
              <th className="text-right p-2.5">Max Adv</th>
              <th className="text-center p-2.5">OOS</th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((trade, i) => {
              const positive = (trade.pnl ?? 0) >= 0
              return (
                <tr
                  key={`${trade.trade_date}-${i}`}
                  className={`border-b border-forge-border/50 ${
                    trade.is_oos
                      ? 'bg-violet-500/5 hover:bg-violet-500/10'
                      : 'hover:bg-forge-border/20'
                  }`}
                >
                  <td className="p-2.5 text-gray-400">{trade.trade_date ?? '—'}</td>
                  <td className="p-2.5 text-right text-gray-400 font-mono">{minuteToTime(trade.entry_minute)}</td>
                  <td className="p-2.5 text-right text-gray-400 font-mono">{minuteToTime(trade.exit_minute)}</td>
                  <td className="p-2.5">
                    <ExitReasonBadge reason={trade.exit_reason} />
                  </td>
                  <td className="p-2.5 text-right font-mono text-gray-300">
                    ${(trade.entry_credit ?? 0).toFixed(2)}
                  </td>
                  <td className="p-2.5 text-right font-mono text-gray-300">
                    ${(trade.exit_cost ?? 0).toFixed(2)}
                  </td>
                  <td className={`p-2.5 text-right font-mono font-medium ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
                    {positive ? '+' : ''}${(trade.pnl ?? 0).toFixed(2)}
                  </td>
                  <td className="p-2.5 text-right font-mono text-emerald-300/70">
                    {trade.max_favorable != null ? `$${trade.max_favorable.toFixed(2)}` : '—'}
                  </td>
                  <td className="p-2.5 text-right font-mono text-red-300/70">
                    {trade.max_adverse != null ? `$${trade.max_adverse.toFixed(2)}` : '—'}
                  </td>
                  <td className="p-2.5 text-center">
                    {trade.is_oos && (
                      <span className="text-[9px] px-1 py-0.5 rounded bg-violet-500/20 text-violet-300">OOS</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-2 border-t border-forge-border text-xs text-forge-muted">
          <span>{trades.length} trades</span>
          <div className="flex items-center gap-2">
            <button
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              className="px-2.5 py-1 rounded border border-forge-border disabled:opacity-30 hover:bg-forge-border/40 transition-colors"
            >
              Prev
            </button>
            <span>{page + 1} / {totalPages}</span>
            <button
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              className="px-2.5 py-1 rounded border border-forge-border disabled:opacity-30 hover:bg-forge-border/40 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function ExitReasonBadge({ reason }: { reason: string }) {
  const r = reason ?? ''
  const isPt = r.includes('profit') || r.includes('pt')
  const isSl = r.includes('stop') || r.includes('sl')
  const isEod = r.includes('eod') || r.includes('time')
  const isTrail = r.includes('trail')
  const color = isPt
    ? 'text-emerald-400'
    : isSl
      ? 'text-red-400'
      : isEod
        ? 'text-amber-400'
        : isTrail
          ? 'text-blue-400'
          : 'text-gray-400'
  return <span className={`font-medium ${color}`}>{r || '—'}</span>
}

/* ------------------------------------------------------------------ */
/*  Main Results Component                                               */
/* ------------------------------------------------------------------ */

type ActiveTab = 'summary' | 'equity' | 'sweep' | 'trades'

export default function EmberResults({
  result,
  loading,
}: {
  result: EvaluateResult | null
  loading: boolean
}) {
  const [tab, setTab] = useState<ActiveTab>('summary')
  const [summaryPeriod, setSummaryPeriod] = useState<'in_sample' | 'oos'>('in_sample')

  const tabs: { key: ActiveTab; label: string }[] = [
    { key: 'summary', label: 'Summary' },
    { key: 'equity', label: 'Equity Curve' },
    { key: 'sweep', label: 'Policy Sweep' },
    { key: 'trades', label: 'Trade Log' },
  ]

  return (
    <div className="space-y-4">
      {/* Results header + tab bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {/* Chart glyph */}
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-amber-400">
            <rect x="1" y="10" width="3" height="5" rx="0.5" fill="currentColor" />
            <rect x="6" y="6" width="3" height="9" rx="0.5" fill="currentColor" />
            <rect x="11" y="2" width="3" height="13" rx="0.5" fill="currentColor" />
            <path d="M2.5 10L7.5 6L12.5 2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          <h2 className="text-sm font-semibold text-gray-300">Results</h2>
          {loading && (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="animate-spin text-amber-400 ml-1">
              <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.5" strokeDasharray="26" strokeDashoffset="10" />
            </svg>
          )}
        </div>

        {/* Tab selector */}
        <div className="flex gap-0.5 bg-forge-border/50 rounded-lg p-0.5">
          {tabs.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                tab === key
                  ? 'bg-forge-card text-white shadow-sm'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Loading skeleton */}
      {loading && !result && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4 space-y-2">
              <Skeleton h="h-3" w="w-24" />
              <Skeleton h="h-6" w="w-32" />
              <Skeleton h="h-3" w="w-20" />
            </div>
            <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4 space-y-2">
              <Skeleton h="h-3" w="w-24" />
              <Skeleton h="h-6" w="w-32" />
              <Skeleton h="h-3" w="w-20" />
            </div>
          </div>
          <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
            <Skeleton h="h-48" />
          </div>
        </div>
      )}

      {/* Results content */}
      {result && (
        <>
          {/* Summary tab */}
          {tab === 'summary' && (
            <div className="space-y-4">
              {/* Period toggle */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-forge-muted">Period:</span>
                <div className="flex gap-0.5 bg-forge-border/50 rounded-lg p-0.5">
                  {(['in_sample', 'oos'] as const).map((p) => (
                    <button
                      key={p}
                      onClick={() => setSummaryPeriod(p)}
                      className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                        summaryPeriod === p
                          ? 'bg-forge-card text-white shadow-sm'
                          : 'text-gray-500 hover:text-gray-300'
                      }`}
                    >
                      {p === 'in_sample' ? 'In-Sample' : 'Out-of-Sample'}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <SummaryPanel
                  stats={result.chosen[summaryPeriod]}
                  label="Chosen Policy"
                  isChosen
                  period={summaryPeriod}
                />
                <SummaryPanel
                  stats={result.baseline[summaryPeriod]}
                  label={`SPARK Live (${result.baseline.policy})`}
                  period={summaryPeriod}
                />
              </div>

              {/* Policy name display */}
              <div className="flex flex-wrap gap-3 text-xs text-forge-muted">
                <span>
                  Chosen: <span className="font-mono text-amber-300">{result.chosen.policy}</span>
                </span>
                <span className="text-forge-border">|</span>
                <span>
                  Baseline: <span className="font-mono text-blue-300">{result.baseline.policy}</span>
                </span>
              </div>

              {/* Negative-EV callout */}
              {(result.chosen.in_sample?.ev_per_contract ?? 0) < 0 && (
                <div className="rounded-lg border border-red-500/25 bg-red-500/8 px-4 py-3 flex items-start gap-3">
                  {/* Warning glyph */}
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="shrink-0 mt-0.5 text-red-400">
                    <path d="M7 1L1 14h14L7 1Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
                    <path d="M7 6v4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                    <circle cx="7" cy="12" r="0.7" fill="currentColor" />
                  </svg>
                  <div>
                    <p className="text-sm text-red-300 font-medium">Negative expected value on chosen policy</p>
                    <p className="text-xs text-red-400/70 mt-0.5">
                      This strategy does not have a positive edge at these parameters. Optimize for least-bad, not profitability.
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Equity tab */}
          {tab === 'equity' && (
            <EmberEquityChart curve={result.chosen.equity_curve ?? []} />
          )}

          {/* Sweep tab */}
          {tab === 'sweep' && (
            <div className="space-y-3">
              <p className="text-xs text-forge-muted">
                {result.grid.length} policies sorted by in-sample EV/contract.{' '}
                <span className="text-amber-300">Star = best IS EV.</span>{' '}
                <span className="text-blue-300">LIVE = current SPARK live config.</span>{' '}
                Click column headers to resort.
              </p>
              <EmberGrid grid={result.grid} />
            </div>
          )}

          {/* Trades tab */}
          {tab === 'trades' && (
            <div className="space-y-3">
              <p className="text-xs text-forge-muted">
                {(result.chosen.trades ?? []).length} trades for chosen policy.{' '}
                <span className="text-violet-300">Violet rows = OOS.</span>
              </p>
              <EmberTradeTable trades={result.chosen.trades ?? []} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
