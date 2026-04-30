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

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface CurvePoint {
  timestamp: string
  pnl: number
  cumulative_pnl: number
  equity: number
  // SPARK-only counterfactual fields (Commit M). Populated by the
  // /api/spark/equity-curve route when the position has a computed
  // hypothetical_eod_pnl. Hidden on FLAME/INFERNO.
  hypothetical_pnl?: number | null
  cumulative_hypothetical_pnl?: number | null
  hypothetical_equity?: number | null
}

interface IntradayPoint {
  timestamp: string
  balance: number
  realized_pnl: number
  unrealized_pnl: number
  equity: number
  open_positions: number
  note: string | null
}

export type Period = 'intraday' | '1w' | '1m' | '3m' | 'all'

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */

export default function EquityChart({
  data,
  intradayData,
  startingCapital,
  color = '#3b82f6',
  title,
  period,
  onPeriodChange,
  liveUnrealizedPnl,
  bot,
}: {
  data: CurvePoint[]
  intradayData?: IntradayPoint[]
  startingCapital: number
  color?: string
  title?: string
  period?: Period
  onPeriodChange?: (p: Period) => void
  liveUnrealizedPnl?: number
  /** When any curve point carries hypothetical_equity, render a
   * toggleable second line showing the "if-we-held-to-2:59-PM"
   * cumulative. Available for all three bots. */
  bot?: string
}) {
  const [activePeriod, setActivePeriod] = useState<Period>(period || 'intraday')
  const [showHypo, setShowHypo] = useState(true)
  const hasHypo = data.some((d) => d.hypothetical_equity != null)

  const handlePeriod = (p: Period) => {
    setActivePeriod(p)
    onPeriodChange?.(p)
  }

  const periods: { key: Period; label: string }[] = [
    { key: 'intraday', label: 'Intraday' },
    { key: '1w', label: '1W' },
    { key: '1m', label: '1M' },
    { key: '3m', label: '3M' },
    { key: 'all', label: 'All' },
  ]

  const showIntraday = activePeriod === 'intraday'

  /* ---------- Intraday chart ---------- */
  if (showIntraday) {
    let points = intradayData || []
    if (!points.length) {
      return (
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
          <div className="flex items-center justify-between mb-3">
            {title && <h3 className="text-sm font-medium text-gray-400">{title}</h3>}
            <PeriodSelector periods={periods} active={activePeriod} onChange={handlePeriod} />
          </div>
          <div className="flex items-center justify-center h-64">
            <p className="text-forge-muted text-sm">
              No intraday snapshots yet. Run the bot to generate data.
            </p>
          </div>
        </div>
      )
    }

    // If position-monitor provided live unrealized P&L, correct the last point
    // so the chart line and badge match the header (single source of truth)
    // Guard: liveUnrealizedPnl can be null (production mode with no DB positions) — treat as 0
    if (liveUnrealizedPnl != null && points.length > 0) {
      const last = points[points.length - 1]
      points = [...points.slice(0, -1), {
        ...last,
        unrealized_pnl: liveUnrealizedPnl,
        equity: (last.balance ?? 0) + liveUnrealizedPnl,
      }]
    }

    const latest = points[points.length - 1]
    const unrealizedForBadge = liveUnrealizedPnl ?? latest.unrealized_pnl ?? 0
    const fillColor =
      latest.equity >= startingCapital
        ? 'rgba(16, 185, 129, 0.15)'
        : 'rgba(239, 68, 68, 0.15)'

    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            {title && <h3 className="text-sm font-medium text-gray-400">{title}</h3>}
            <PnlBadge value={unrealizedForBadge} label="Unrealized" />
          </div>
          <PeriodSelector periods={periods} active={activePeriod} onChange={handlePeriod} />
        </div>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={points}>
            <XAxis
              dataKey="timestamp"
              tickFormatter={formatTime}
              stroke="#44403c"
              tick={{ fill: '#a8a29e', fontSize: 11 }}
            />
            <YAxis
              tickFormatter={(v) => `$${v.toLocaleString()}`}
              stroke="#44403c"
              tick={{ fill: '#a8a29e', fontSize: 11 }}
              domain={['auto', 'auto']}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1c1917',
                border: '1px solid #292524',
                borderRadius: 8,
              }}
              labelStyle={{ color: '#a8a29e' }}
              formatter={(value: number, name: string) => {
                const label =
                  name === 'equity'
                    ? 'Equity'
                    : name === 'unrealized_pnl'
                      ? 'Unrealized'
                      : name
                const v = typeof value === 'number' ? value : 0
                return [`$${v.toFixed(2)}`, label]
              }}
              labelFormatter={(label) =>
                label
                  ? new Date(label).toLocaleTimeString('en-US', {
                      hour: 'numeric',
                      minute: '2-digit',
                      timeZone: 'America/Chicago',
                    }) + ' CT'
                  : ''
              }
            />
            <ReferenceLine
              y={startingCapital}
              stroke="#78716c"
              strokeDasharray="4 4"
              label={{
                value: `Start: $${startingCapital.toLocaleString()}`,
                position: 'insideTopLeft',
                fill: '#78716c',
                fontSize: 11,
              }}
            />
            <Area type="monotone" dataKey="equity" stroke={color} strokeWidth={2} fill={fillColor} />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="flex gap-4 mt-2 text-xs text-forge-muted px-2">
          <span>{points.length} snapshots</span>
          <span>Balance: ${(latest.equity ?? latest.balance ?? 0).toFixed(2)}</span>
          <span>Open: {latest.open_positions ?? 0}</span>
        </div>
      </div>
    )
  }

  /* ---------- Historical chart (1W / 1M / 3M / All) ---------- */
  if (!data.length) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
        <div className="flex items-center justify-between mb-3">
          {title && <h3 className="text-sm font-medium text-gray-400">{title}</h3>}
          <PeriodSelector periods={periods} active={activePeriod} onChange={handlePeriod} />
        </div>
        <div className="flex items-center justify-center h-64">
          <p className="text-forge-muted text-sm">No closed trades yet for this period</p>
        </div>
      </div>
    )
  }

  // Seed point at startingCapital so the line begins at the baseline rather
  // than jumping to the first trade's equity. For SPARK we also seed the
  // hypothetical line at the same baseline so both start visually aligned.
  const seedPoint: CurvePoint & { hypothetical_equity?: number | null } = {
    timestamp: data[0].timestamp,
    equity: startingCapital,
    pnl: 0,
    cumulative_pnl: 0,
  }
  if (hasHypo) seedPoint.hypothetical_equity = startingCapital
  const chartData = [seedPoint, ...data]

  const lastPoint = data[data.length - 1]
  const lastEquity = lastPoint.equity
  const fillColor =
    lastEquity >= startingCapital ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)'

  // Hypo color: distinct from the actual equity line so the two are easy
  // to tell apart at a glance. Purple/violet works well against blue/red/amber.
  const hypoColor = '#a78bfa'
  const hypoFill = 'rgba(167, 139, 250, 0.10)'
  const lastHypoCum = lastPoint.cumulative_hypothetical_pnl ?? null
  const lastHypoEquity = lastPoint.hypothetical_equity ?? null

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3 flex-wrap">
          {title && <h3 className="text-sm font-medium text-gray-400">{title}</h3>}
          <PnlBadge value={lastPoint.cumulative_pnl} label="Cumulative" />
          {hasHypo && lastHypoCum != null && (
            <span
              className="text-xs font-mono px-2 py-0.5 rounded bg-violet-500/20 text-violet-300"
              title="Hypothetical cumulative P&L if SPARK had held every trade to 2:59 PM CT"
            >
              Hypo: {lastHypoCum >= 0 ? '+' : ''}${lastHypoCum.toFixed(2)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasHypo && (
            <button
              onClick={() => setShowHypo((v) => !v)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors border ${
                showHypo
                  ? 'bg-violet-500/20 text-violet-300 border-violet-500/40'
                  : 'bg-transparent text-gray-500 border-forge-border hover:text-gray-300'
              }`}
              title={showHypo ? 'Hide hypothetical 2:59 PM line' : 'Show hypothetical 2:59 PM line'}
            >
              Hypo @ 2:59
            </button>
          )}
          <PeriodSelector periods={periods} active={activePeriod} onChange={handlePeriod} />
        </div>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={chartData}>
          <XAxis
            dataKey="timestamp"
            tickFormatter={formatDate}
            stroke="#44403c"
            tick={{ fill: '#a8a29e', fontSize: 11 }}
          />
          <YAxis
            tickFormatter={(v) => `$${v.toLocaleString()}`}
            stroke="#44403c"
            tick={{ fill: '#a8a29e', fontSize: 11 }}
            domain={['auto', 'auto']}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1c1917',
              border: '1px solid #292524',
              borderRadius: 8,
            }}
            labelStyle={{ color: '#a8a29e' }}
            formatter={(value: number, name: string) => {
              const v = typeof value === 'number' ? value : 0
              const label =
                name === 'equity' ? 'Actual Equity'
                : name === 'hypothetical_equity' ? 'Hypo @ 2:59'
                : name
              return [`$${v.toFixed(2)}`, label]
            }}
            labelFormatter={(label) =>
              label
                ? new Date(label).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit',
                    timeZone: 'America/Chicago',
                  })
                : ''
            }
          />
          <ReferenceLine
            y={startingCapital}
            stroke="#78716c"
            strokeDasharray="4 4"
            label={{
              value: `Start: $${startingCapital.toLocaleString()}`,
              position: 'insideTopLeft',
              fill: '#78716c',
              fontSize: 11,
            }}
          />
          <Area type="monotone" dataKey="equity" stroke={color} strokeWidth={2} fill={fillColor} />
          {hasHypo && showHypo && (
            <Area
              type="monotone"
              dataKey="hypothetical_equity"
              stroke={hypoColor}
              strokeWidth={1.5}
              strokeDasharray="4 3"
              fill={hypoFill}
              isAnimationActive={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-2 text-xs text-forge-muted px-2 items-center">
        <span>{data.length} trades</span>
        {hasHypo && lastHypoEquity != null && (
          <span className="text-violet-300/80">
            Hypo line = "held to 2:59 PM CT every day"; flat through trades older than Tradier's 40-day window.
          </span>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Period Selector                                                    */
/* ------------------------------------------------------------------ */

function PeriodSelector({
  periods,
  active,
  onChange,
}: {
  periods: { key: Period; label: string }[]
  active: Period
  onChange: (p: Period) => void
}) {
  return (
    <div className="flex gap-0.5 bg-forge-border/50 rounded-lg p-0.5">
      {periods.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
            active === key
              ? 'bg-forge-card text-white shadow-sm'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  P&L Badge                                                          */
/* ------------------------------------------------------------------ */

function PnlBadge({ value, label }: { value: number | null | undefined; label: string }) {
  const v = value ?? 0
  return (
    <span
      className={`text-xs font-mono px-2 py-0.5 rounded ${
        v >= 0 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
      }`}
    >
      {label}: {v >= 0 ? '+' : ''}${v.toFixed(2)}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/*  Formatters                                                         */
/* ------------------------------------------------------------------ */

function formatDate(ts: string) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleDateString('en-US', {
    month: 'numeric',
    day: 'numeric',
    timeZone: 'America/Chicago',
  })
}

function formatTime(ts: string) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'America/Chicago' })
}

/* ------------------------------------------------------------------ */
/*  Comparison Chart                                                   */
/* ------------------------------------------------------------------ */

export function ComparisonChart({
  flameData,
  sparkData,
  infernoData,
  startingCapital,
}: {
  flameData: CurvePoint[]
  sparkData: CurvePoint[]
  infernoData?: CurvePoint[]
  startingCapital: number
}) {
  const infData = infernoData || []
  if (!flameData.length && !sparkData.length && !infData.length) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
        <p className="text-forge-muted">No closed trades yet for any bot</p>
      </div>
    )
  }

  const map = new Map<string, { flame?: number; spark?: number; inferno?: number }>()
  const allTimestamps = [
    ...flameData.map((d) => d.timestamp),
    ...sparkData.map((d) => d.timestamp),
    ...infData.map((d) => d.timestamp),
  ].sort()
  if (allTimestamps.length) {
    map.set(allTimestamps[0], { flame: startingCapital, spark: startingCapital, inferno: startingCapital })
  }

  let flameCum = startingCapital
  for (const pt of flameData) {
    flameCum = pt.equity
    map.set(pt.timestamp, { ...map.get(pt.timestamp), flame: flameCum })
  }

  let sparkCum = startingCapital
  for (const pt of sparkData) {
    sparkCum = pt.equity
    map.set(pt.timestamp, { ...map.get(pt.timestamp), spark: sparkCum })
  }

  let infernoCum = startingCapital
  for (const pt of infData) {
    infernoCum = pt.equity
    map.set(pt.timestamp, { ...map.get(pt.timestamp), inferno: infernoCum })
  }

  const sorted = Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))

  let lastFlame = startingCapital
  let lastSpark = startingCapital
  let lastInferno = startingCapital
  const chartData = sorted.map(([ts, vals]) => {
    if (vals.flame !== undefined) lastFlame = vals.flame
    if (vals.spark !== undefined) lastSpark = vals.spark
    if (vals.inferno !== undefined) lastInferno = vals.inferno
    return {
      timestamp: ts,
      flame: vals.flame ?? lastFlame,
      spark: vals.spark ?? lastSpark,
      inferno: vals.inferno ?? lastInferno,
    }
  })

  const nameMap: Record<string, string> = { flame: 'FLAME', spark: 'SPARK', inferno: 'INFERNO' }

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <h3 className="text-sm font-medium text-gray-400 mb-3">Equity Comparison</h3>
      <ResponsiveContainer width="100%" height={380}>
        <ComposedChart data={chartData}>
          <XAxis
            dataKey="timestamp"
            tickFormatter={formatDate}
            stroke="#44403c"
            tick={{ fill: '#a8a29e', fontSize: 11 }}
          />
          <YAxis
            tickFormatter={(v) => `$${v.toLocaleString()}`}
            stroke="#44403c"
            tick={{ fill: '#a8a29e', fontSize: 11 }}
            domain={['auto', 'auto']}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #292524', borderRadius: 8 }}
            formatter={(value: number, name: string) => [
              `$${(typeof value === 'number' ? value : 0).toFixed(2)}`,
              nameMap[name] || name,
            ]}
          />
          <ReferenceLine y={startingCapital} stroke="#78716c" strokeDasharray="4 4" />
          <Area type="monotone" dataKey="flame" stroke="#f59e0b" strokeWidth={2} fill="rgba(245, 158, 11, 0.1)" />
          <Area type="monotone" dataKey="spark" stroke="#3b82f6" strokeWidth={2} fill="rgba(59, 130, 246, 0.1)" />
          <Area type="monotone" dataKey="inferno" stroke="#ef4444" strokeWidth={2} fill="rgba(239, 68, 68, 0.1)" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
