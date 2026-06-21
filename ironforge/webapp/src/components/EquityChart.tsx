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

export interface CurvePoint {
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
        ? 'rgba(52, 211, 153, 0.15)'
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
    lastEquity >= startingCapital ? 'rgba(52, 211, 153, 0.15)' : 'rgba(239, 68, 68, 0.15)'

  // Hypo color: distinct from the actual equity line so the two are easy
  // to tell apart at a glance. Purple/violet works well against blue/red/amber.
  const hypoColor = '#06b6d4'
  const hypoFill = 'rgba(6, 182, 212, 0.10)'
  const lastHypoCum = lastPoint.cumulative_hypothetical_pnl ?? null
  const lastHypoEquity = lastPoint.hypothetical_equity ?? null
  const botLabel = (bot || 'this bot').toUpperCase()

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3 flex-wrap">
          {title && <h3 className="text-sm font-medium text-gray-400">{title}</h3>}
          <PnlBadge value={lastPoint.cumulative_pnl} label="Cumulative" />
          {hasHypo && lastHypoCum != null && (
            <span
              className="text-xs font-mono px-2 py-0.5 rounded bg-violet-500/20 text-violet-300"
              title={`Hypothetical cumulative P&L if ${botLabel} had held every trade to 2:59 PM CT`}
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

export interface CompareSeries {
  key: string
  label: string
  color: string
  start: number
  data: CurvePoint[]
}

export type CompareMode = 'daily' | 'total'

export function ComparisonChart({
  series,
  period,
  onPeriodChange,
  mode,
  onModeChange,
  showHypo,
  onToggleHypo,
  allowHypo,
}: {
  series: CompareSeries[]
  period: Period
  onPeriodChange: (p: Period) => void
  mode: CompareMode
  onModeChange: (m: CompareMode) => void
  showHypo: boolean
  onToggleHypo: () => void
  allowHypo: boolean
}) {
  const periods: { key: Period; label: string }[] = [
    { key: 'intraday', label: 'Intraday' },
    { key: '1w', label: '1W' },
    { key: '1m', label: '1M' },
    { key: '3m', label: '3M' },
    { key: 'all', label: 'All' },
  ]

  const pct = (v: number, base: number) => (base > 0 ? (v / base - 1) * 100 : 0)
  const hypoKey = (key: string) => `${key}__hypo`
  const isIntradayMode = period === 'intraday'

  // CT calendar date (YYYY-MM-DD) for a timestamp; en-CA gives ISO-style dates.
  const ctDay = (ts: string) => new Date(ts).toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
  const fmtDay = (s: string) => {
    const p = String(s).split('-')
    return p.length === 3 ? `${+p[1]}/${+p[2]}` : s
  }

  let chartData: Record<string, string | number>[] = []

  if (isIntradayMode) {
    // Intraday: rebase each bot to its first snapshot (day open = 0%). Cumulative
    // within the day only — never since inception.
    const map = new Map<string, Record<string, number>>()
    for (const s of series) {
      const base = s.data[0]?.equity ?? s.start
      for (const p of s.data) {
        if (!p.timestamp) continue
        const row = { ...(map.get(p.timestamp) || {}) }
        row[s.key] = pct(p.equity, base)
        map.set(p.timestamp, row)
      }
    }
    const sorted = Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
    const last: Record<string, number> = {}
    for (const s of series) last[s.key] = 0
    chartData = sorted.map(([ts, vals]) => {
      const row: Record<string, string | number> = { timestamp: ts }
      for (const s of series) {
        if (vals[s.key] !== undefined) last[s.key] = vals[s.key]
        row[s.key] = last[s.key]
      }
      return row
    })
  } else if (mode === 'total') {
    // Cumulative % return over the SELECTED window: each bot is rebased to its
    // equity at the START of the window, so every line begins at 0% on the left
    // and shows how much that bot accumulated over the chosen period (1W = this
    // week, 1M = this month, …). 'All' rebases to inception. Switching the
    // timeframe answers "who's best this week / month / all-time".
    const back = period === '1w' ? 7 : period === '1m' ? 30 : period === '3m' ? 90 : null
    const cutoffTs = back ? new Date(Date.now() - back * 86_400_000).toISOString() : null

    // Per-bot baseline = equity at the window start (last point before the cutoff),
    // falling back to its starting capital when it has no pre-window history.
    const base: Record<string, number> = {}
    const hypoBase: Record<string, number> = {}
    for (const s of series) {
      let bse = s.start
      let hbse = s.start
      if (cutoffTs) {
        for (const p of s.data) {
          if (!p.timestamp || p.timestamp >= cutoffTs) break
          bse = p.equity
          if (p.hypothetical_equity != null) hbse = p.hypothetical_equity
        }
      }
      base[s.key] = bse
      hypoBase[s.key] = hbse
    }

    const map = new Map<string, Record<string, number>>()
    // Seed a 0% point at the window's left edge so every line starts aligned.
    const seedTs =
      cutoffTs ?? series.flatMap((s) => s.data.map((d) => d.timestamp)).filter(Boolean).sort()[0]
    if (seedTs) {
      const seed: Record<string, number> = {}
      for (const s of series) {
        seed[s.key] = 0
        if (allowHypo) seed[hypoKey(s.key)] = 0
      }
      map.set(seedTs, seed)
    }
    for (const s of series) {
      for (const p of s.data) {
        if (!p.timestamp) continue
        if (cutoffTs && p.timestamp < cutoffTs) continue
        const row = { ...(map.get(p.timestamp) || {}) }
        row[s.key] = pct(p.equity, base[s.key])
        if (allowHypo && p.hypothetical_equity != null) row[hypoKey(s.key)] = pct(p.hypothetical_equity, hypoBase[s.key])
        map.set(p.timestamp, row)
      }
    }
    const sorted = Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
    const last: Record<string, number> = {}
    for (const s of series) {
      last[s.key] = 0
      if (allowHypo) last[hypoKey(s.key)] = 0
    }
    chartData = sorted.map(([ts, vals]) => {
      const row: Record<string, string | number> = { timestamp: ts }
      for (const s of series) {
        if (vals[s.key] !== undefined) last[s.key] = vals[s.key]
        row[s.key] = last[s.key]
        if (allowHypo) {
          const hk = hypoKey(s.key)
          if (vals[hk] !== undefined) last[hk] = vals[hk]
          row[hk] = last[hk]
        }
      }
      return row
    })
  } else {
    // Daily view: per-DAY % return. Resample to end-of-day equity per CT day, then
    // take the day-over-day change — computed over FULL history so the first day of
    // any window has a correct prior-day baseline. No accumulation since inception,
    // so a bot up +500% all-time doesn't pin the scale; all bots stay comparable.
    const dailyReturns = (data: CurvePoint[], start: number, field: 'equity' | 'hypothetical_equity') => {
      const eod = new Map<string, number>()
      for (const p of data) {
        const v = field === 'equity' ? p.equity : p.hypothetical_equity
        if (v == null || !p.timestamp) continue
        eod.set(ctDay(p.timestamp), v) // data is ASC by close_time → last write = EOD
      }
      const days = Array.from(eod.keys()).sort()
      const out = new Map<string, number>()
      let prev = start
      for (const d of days) {
        const v = eod.get(d) as number
        out.set(d, prev > 0 ? (v / prev - 1) * 100 : 0)
        prev = v
      }
      return out
    }

    const perSeries = series.map((s) => ({
      key: s.key,
      ret: dailyReturns(s.data, s.start, 'equity'),
      hypo: allowHypo ? dailyReturns(s.data, s.start, 'hypothetical_equity') : new Map<string, number>(),
    }))

    let days = Array.from(
      new Set(perSeries.flatMap((s) => Array.from(s.ret.keys()).concat(Array.from(s.hypo.keys())))),
    ).sort()
    if (period !== 'all') {
      const back = period === '1w' ? 7 : period === '1m' ? 30 : 90
      const cutoff = new Date(Date.now() - back * 86_400_000).toLocaleDateString('en-CA', {
        timeZone: 'America/Chicago',
      })
      days = days.filter((d) => d >= cutoff)
    }

    chartData = days.map((d) => {
      const row: Record<string, string | number> = { timestamp: d }
      for (const s of perSeries) {
        row[s.key] = s.ret.get(d) ?? 0
        if (allowHypo) row[hypoKey(s.key)] = s.hypo.get(d) ?? 0
      }
      return row
    })
  }

  const nameMap: Record<string, string> = {}
  for (const s of series) {
    nameMap[s.key] = s.label
    nameMap[hypoKey(s.key)] = `${s.label} (hypo @ 2:59)`
  }

  const header = (
    <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
      <h3 className="text-sm font-medium text-gray-400">
        {isIntradayMode
          ? 'Intraday % return (vs day open)'
          : mode === 'daily'
            ? 'Daily % return per bot'
            : period === 'all'
              ? 'Cumulative % return per bot (since inception)'
              : `Cumulative % return per bot — last ${period === '1w' ? 'week' : period === '1m' ? 'month' : '3 months'}`}
      </h3>
      <div className="flex items-center gap-2">
        {!isIntradayMode && (
          <div className="flex gap-0.5 bg-forge-border/50 rounded-lg p-0.5">
            {([['daily', 'Daily %'], ['total', 'Cumulative']] as const).map(([m, lbl]) => (
              <button
                key={m}
                onClick={() => onModeChange(m)}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                  mode === m ? 'bg-forge-card text-white shadow-sm' : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {lbl}
              </button>
            ))}
          </div>
        )}
        {allowHypo && (
          <button
            onClick={onToggleHypo}
            className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors border ${
              showHypo
                ? 'bg-violet-500/20 text-violet-300 border-violet-500/40'
                : 'bg-transparent text-gray-500 border-forge-border hover:text-gray-300'
            }`}
            title={showHypo ? 'Hide hypothetical 2:59 PM lines' : 'Show hypothetical 2:59 PM lines'}
          >
            Hypo @ 2:59
          </button>
        )}
        <PeriodSelector periods={periods} active={period} onChange={onPeriodChange} />
      </div>
    </div>
  )

  if (!series.some((s) => s.data.length > 0)) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
        {header}
        <div className="flex items-center justify-center h-64">
          <p className="text-forge-muted text-sm">No data for any bot in this period</p>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      {header}
      <ResponsiveContainer width="100%" height={380}>
        <ComposedChart data={chartData}>
          <XAxis
            dataKey="timestamp"
            tickFormatter={isIntradayMode ? formatTime : mode === 'daily' ? fmtDay : formatDate}
            stroke="#44403c"
            tick={{ fill: '#a8a29e', fontSize: 11 }}
          />
          <YAxis
            tickFormatter={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`}
            stroke="#44403c"
            tick={{ fill: '#a8a29e', fontSize: 11 }}
            domain={['auto', 'auto']}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1c1917', border: '1px solid #292524', borderRadius: 8 }}
            formatter={(value: number, name: string) => {
              const v = typeof value === 'number' ? value : 0
              return [`${v >= 0 ? '+' : ''}${v.toFixed(2)}%`, nameMap[name] || name]
            }}
          />
          <ReferenceLine y={0} stroke="#78716c" strokeDasharray="4 4" />
          {series.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              stroke={s.color}
              strokeWidth={2}
              fill={s.color}
              fillOpacity={0.08}
              isAnimationActive={false}
            />
          ))}
          {allowHypo &&
            showHypo &&
            series.map((s) => (
              <Area
                key={hypoKey(s.key)}
                type="monotone"
                dataKey={hypoKey(s.key)}
                stroke={s.color}
                strokeWidth={1.3}
                strokeDasharray="4 3"
                fill={s.color}
                fillOpacity={0}
                isAnimationActive={false}
              />
            ))}
        </ComposedChart>
      </ResponsiveContainer>
      {allowHypo && showHypo && (
        <p className="text-xs text-violet-300/80 mt-2 px-2">
          Dashed = &ldquo;held to 2:59 PM CT every day&rdquo; counterfactual (flat where no hypo data, e.g. BLAZE).
        </p>
      )}
    </div>
  )
}
