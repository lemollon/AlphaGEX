'use client'

import React, { useState, useEffect, useCallback } from 'react'
import {
  Activity, AlertTriangle, BarChart3, CheckCircle2, Clock,
  DollarSign, FileText, Layers, RefreshCw, Settings, Shield,
  Target, TrendingDown, TrendingUp, XCircle, Zap,
} from 'lucide-react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ReferenceLine,
} from 'recharts'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'

const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

// ============================================================================
// FETCH HELPER
// ============================================================================

async function fetchApi<T>(endpoint: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${endpoint}`)
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}

// ============================================================================
// INTERFACES (mirror backend/api/routes/goliath_routes.py response shapes)
// ============================================================================

interface InstanceStatus {
  name: string
  letf_ticker: string
  underlying_ticker: string
  allocation_cap: number
  paper_only: boolean
  last_heartbeat: string | null
  heartbeat_status: string | null
  scan_count: number
  trades_today: number
  open_position_count: number
  killed: boolean
  kill_info: { trigger_id: string; reason: string; killed_at: string } | null
}

interface PlatformStatus {
  platform_killed: boolean
  platform_kill_info: { trigger_id: string; reason: string; killed_at: string } | null
  platform_cap: number
  account_capital: number
  instance_count: number
  instances: InstanceStatus[]
}

interface Position {
  position_id: string
  instance_name: string
  letf_ticker: string
  underlying_ticker: string
  state: string
  opened_at: string | null
  closed_at: string | null
  expiration_date: string | null
  short_put_strike: number | null
  long_put_strike: number | null
  long_call_strike: number | null
  contracts: number | null
  entry_net_cost: number | null
  defined_max_loss: number | null
  realized_pnl: number | null
  close_trigger_id: string | null
}

interface EquityPoint {
  snapshot_at: string | null
  equity?: number | null
  unrealized_pnl?: number
  open_position_count?: number
  starting_capital?: number | null
  cumulative_realized_pnl?: number
}

interface PerformanceInstance {
  instance_name: string
  trades: number
  wins: number
  losses: number
  scratches: number
  total_pnl: number
  avg_pnl: number
  best: number
  worst: number
  win_rate: number | null
  trigger_breakdown: Record<string, number>
}

interface PerformanceResponse {
  days: number
  platform: { trades: number; total_pnl: number; win_rate: number | null; avg_pnl: number }
  instances: PerformanceInstance[]
}

interface AuditEvent {
  id: number
  timestamp: string | null
  instance: string
  event_type: string
  position_id: string | null
  data: Record<string, any>
}

interface GateFailure {
  id: number
  timestamp: string | null
  letf_ticker: string
  underlying_ticker: string
  failed_gate: string
  failure_outcome: string
  gates_passed_before_failure: string[]
  failure_reason: string
}

interface KillState {
  active: Array<{
    scope: string
    instance_name: string | null
    trigger_id: string
    reason: string
    killed_at: string | null
  }>
  active_count: number
  platform_killed: boolean
  killed_instances: string[]
  history: Array<{
    scope: string
    instance_name: string | null
    trigger_id: string
    reason: string
    killed_at: string | null
    cleared_at: string | null
    cleared_by: string | null
  }>
}

interface CalibrationParam {
  value: number
  spec_default: number
  tag: string
  notes: string
}

interface CalibrationResponse {
  phase: string
  last_calibrated: string
  parameters: Record<string, CalibrationParam>
}

// ============================================================================
// FORMATTERS
// ============================================================================

const fmtUSD = (v: number | null | undefined, dp = 2) =>
  v == null ? '—' : `$${v.toFixed(dp)}`
const fmtPct = (v: number | null | undefined, dp = 1) =>
  v == null ? '—' : `${(v * 100).toFixed(dp)}%`
const fmtTime = (iso: string | null | undefined) => {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-US', {
      timeZone: 'America/Chicago',
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

type TabId = 'overview' | 'positions' | 'performance' | 'audit' | 'kills' | 'config'
type RangeId = '7d' | '30d' | '90d' | 'all'

const RANGE_DAYS: Record<RangeId, number> = {
  '7d': 7,
  '30d': 30,
  '90d': 90,
  'all': 365,
}

export default function GoliathContent() {
  const sidebarPadding = useSidebarPadding()
  const [tab, setTab] = useState<TabId>('overview')
  const [selectedInstance, setSelectedInstance] = useState<string>('PLATFORM')
  const [range, setRange] = useState<RangeId>('30d')

  const [platform, setPlatform] = useState<PlatformStatus | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [equity, setEquity] = useState<EquityPoint[]>([])
  const [intraday, setIntraday] = useState<EquityPoint[]>([])
  const [perf, setPerf] = useState<PerformanceResponse | null>(null)
  const [audit, setAudit] = useState<AuditEvent[]>([])
  const [gates, setGates] = useState<GateFailure[]>([])
  const [kills, setKills] = useState<KillState | null>(null)
  const [calibration, setCalibration] = useState<CalibrationResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const refreshAll = useCallback(async () => {
    setRefreshing(true)
    const scopeQS = selectedInstance === 'PLATFORM'
      ? 'scope=PLATFORM'
      : `scope=INSTANCE&instance=${selectedInstance}`

    const days = RANGE_DAYS[range]
    const [
      pStatus, pos, eq, iEq, perfData, auditData,
      gatesData, killData, calibData,
    ] = await Promise.all([
      fetchApi<PlatformStatus>('/api/goliath/status'),
      fetchApi<{ positions: Position[] }>('/api/goliath/positions'),
      fetchApi<{ points: EquityPoint[] }>(`/api/goliath/equity-curve?${scopeQS}&days=${days}`),
      fetchApi<{ points: EquityPoint[] }>(`/api/goliath/equity-curve/intraday?${scopeQS}`),
      fetchApi<PerformanceResponse>(`/api/goliath/performance?days=${days}`),
      fetchApi<{ events: AuditEvent[] }>('/api/goliath/scan-activity?limit=50'),
      fetchApi<{ failures: GateFailure[] }>('/api/goliath/gate-failures?limit=50'),
      fetchApi<KillState>('/api/goliath/kill-state'),
      fetchApi<CalibrationResponse>('/api/goliath/calibration'),
    ])

    if (pStatus) setPlatform(pStatus)
    if (pos) setPositions(pos.positions)
    if (eq) setEquity(eq.points)
    if (iEq) setIntraday(iEq.points)
    if (perfData) setPerf(perfData)
    if (auditData) setAudit(auditData.events)
    if (gatesData) setGates(gatesData.failures)
    if (killData) setKills(killData)
    if (calibData) setCalibration(calibData)
    setLoading(false)
    setRefreshing(false)
  }, [selectedInstance, range])

  useEffect(() => {
    refreshAll()
    const interval = setInterval(refreshAll, 30000)  // 30s auto-refresh
    return () => clearInterval(interval)
  }, [refreshAll])

  if (loading) {
    return (
      <div className="min-h-screen bg-[#030712] text-gray-100">
        <Navigation />
        <main className={`pt-24 pb-12 min-h-screen ${sidebarPadding}`}>
          <div className="max-w-7xl mx-auto px-4">
            <div className="animate-pulse text-gray-400">Loading GOLIATH…</div>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#030712] text-gray-100">
      <Navigation />
      <main className={`pt-24 pb-12 min-h-screen ${sidebarPadding}`}>
       <div className="max-w-7xl mx-auto px-4 space-y-6">

        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <Shield className="w-8 h-8 text-purple-400" />
              <h1 className="text-3xl font-bold text-purple-300">GOLIATH</h1>
              <span className="px-2 py-1 bg-purple-900/30 border border-purple-700/50 rounded text-xs text-purple-300">
                PHASE 1.5 · PAPER
              </span>
              {platform?.platform_killed && (
                <span className="px-2 py-1 bg-red-900/40 border border-red-700/50 rounded text-xs text-red-300 flex items-center gap-1">
                  <XCircle className="w-3 h-3" /> PLATFORM KILLED
                </span>
              )}
            </div>
            <p className="text-sm text-gray-400 mt-1">
              LETF earnings-week defined-risk options · 5 instances ·
              ${platform?.platform_cap?.toFixed(0) ?? '—'} platform cap
            </p>
          </div>
          <button
            onClick={refreshAll}
            disabled={refreshing}
            className="flex items-center gap-2 px-3 py-2 bg-purple-900/30 border border-purple-700/50 rounded text-sm hover:bg-purple-900/50 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {/* Platform kill banner */}
        {platform?.platform_killed && platform.platform_kill_info && (
          <div className="bg-red-950/40 border border-red-700/50 rounded-lg p-4 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
            <div>
              <div className="font-semibold text-red-300">
                Platform killed by {platform.platform_kill_info.trigger_id}
              </div>
              <div className="text-sm text-red-400 mt-1">
                {platform.platform_kill_info.reason}
              </div>
              <div className="text-xs text-red-500 mt-1">
                {fmtTime(platform.platform_kill_info.killed_at)}
              </div>
            </div>
          </div>
        )}

        {/* Instance overview cards (5) */}
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {platform?.instances.map((inst) => {
            const isSelected = selectedInstance === inst.name
            const perfRow = perf?.instances.find(p => p.instance_name === inst.name)
            return (
              <button
                key={inst.name}
                onClick={() => setSelectedInstance(inst.name)}
                className={`text-left rounded-lg p-3 border transition-colors ${
                  isSelected
                    ? 'bg-purple-900/30 border-purple-500'
                    : inst.killed
                      ? 'bg-red-950/20 border-red-800/40 hover:border-red-700/60'
                      : 'bg-gray-900/50 border-gray-800 hover:border-gray-700'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-sm">{inst.letf_ticker}</span>
                  {inst.killed && <XCircle className="w-4 h-4 text-red-400" />}
                  {!inst.killed && inst.heartbeat_status === 'OK' && (
                    <CheckCircle2 className="w-4 h-4 text-green-400" />
                  )}
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  ↑ {inst.underlying_ticker} · ${inst.allocation_cap}
                </div>
                <div className="mt-2 grid grid-cols-2 gap-1 text-xs">
                  <div>
                    <div className="text-gray-500">Open</div>
                    <div className="font-mono">{inst.open_position_count}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">P&L 30d</div>
                    <div className={`font-mono ${
                      (perfRow?.total_pnl ?? 0) > 0 ? 'text-green-400'
                        : (perfRow?.total_pnl ?? 0) < 0 ? 'text-red-400'
                          : 'text-gray-400'
                    }`}>
                      {fmtUSD(perfRow?.total_pnl, 0)}
                    </div>
                  </div>
                </div>
              </button>
            )
          })}
          <button
            onClick={() => setSelectedInstance('PLATFORM')}
            className={`text-left rounded-lg p-3 border transition-colors ${
              selectedInstance === 'PLATFORM'
                ? 'bg-purple-900/30 border-purple-500'
                : 'bg-gray-900/50 border-gray-800 hover:border-gray-700'
            }`}
          >
            <div className="flex items-center gap-1">
              <Layers className="w-4 h-4 text-purple-400" />
              <span className="font-semibold text-sm">PLATFORM</span>
            </div>
            <div className="text-xs text-gray-500 mt-0.5">All 5 aggregated</div>
            <div className="mt-2 grid grid-cols-2 gap-1 text-xs">
              <div>
                <div className="text-gray-500">Open</div>
                <div className="font-mono">
                  {platform?.instances.reduce((s, i) => s + i.open_position_count, 0) ?? 0}
                </div>
              </div>
              <div>
                <div className="text-gray-500">P&L 30d</div>
                <div className={`font-mono ${
                  (perf?.platform.total_pnl ?? 0) > 0 ? 'text-green-400'
                    : (perf?.platform.total_pnl ?? 0) < 0 ? 'text-red-400'
                      : 'text-gray-400'
                }`}>
                  {fmtUSD(perf?.platform.total_pnl, 0)}
                </div>
              </div>
            </div>
          </button>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-800 flex gap-1 overflow-x-auto">
          {([
            ['overview', 'Overview', BarChart3],
            ['positions', 'Positions', Target],
            ['performance', 'Performance', TrendingUp],
            ['audit', 'Scan / Audit Feed', Activity],
            ['kills', 'Kill Switches', Shield],
            ['config', 'Config / Calibration', Settings],
          ] as Array<[TabId, string, React.ComponentType<{ className?: string }>]>).map(
            ([id, label, Icon]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`flex items-center gap-2 px-4 py-2 text-sm whitespace-nowrap border-b-2 transition-colors ${
                  tab === id
                    ? 'border-purple-500 text-purple-300'
                    : 'border-transparent text-gray-400 hover:text-gray-200'
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </button>
            ),
          )}
        </div>

        {/* Tab panels */}
        {tab === 'overview' && (
          <OverviewTab
            equity={equity}
            intraday={intraday}
            scope={selectedInstance}
            platform={platform}
            perf={perf}
            range={range}
            onRangeChange={setRange}
          />
        )}
        {tab === 'positions' && <PositionsTab positions={positions} scope={selectedInstance} />}
        {tab === 'performance' && (
          <PerformanceTab perf={perf} range={range} onRangeChange={setRange} />
        )}
        {tab === 'audit' && <AuditTab audit={audit} gates={gates} />}
        {tab === 'kills' && <KillsTab kills={kills} />}
        {tab === 'config' && <ConfigTab calibration={calibration} platform={platform} />}
       </div>
      </main>
    </div>
  )
}

// ============================================================================
// TAB: OVERVIEW (equity curves)
// ============================================================================

function OverviewTab({
  equity, intraday, scope, platform, perf, range, onRangeChange,
}: {
  equity: EquityPoint[]
  intraday: EquityPoint[]
  scope: string
  platform: PlatformStatus | null
  perf: PerformanceResponse | null
  range: RangeId
  onRangeChange: (r: RangeId) => void
}) {
  const platformPerf = perf?.platform
  const totalOpen = platform?.instances.reduce((s, i) => s + i.open_position_count, 0) ?? 0
  const rangeLabel = range.toUpperCase()

  return (
    <div className="space-y-6">

      {/* Range selector */}
      <RangeSelector range={range} onChange={onRangeChange} />

      {/* Quick stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="Account Capital"
          value={fmtUSD(platform?.account_capital, 0)}
          icon={DollarSign}
        />
        <StatCard
          label="Open Positions"
          value={String(totalOpen)}
          icon={Target}
        />
        <StatCard
          label={`P&L (${rangeLabel})`}
          value={fmtUSD(platformPerf?.total_pnl, 2)}
          icon={platformPerf && platformPerf.total_pnl >= 0 ? TrendingUp : TrendingDown}
          color={
            !platformPerf ? 'text-gray-400'
              : platformPerf.total_pnl > 0 ? 'text-green-400'
                : platformPerf.total_pnl < 0 ? 'text-red-400'
                  : 'text-gray-400'
          }
        />
        <StatCard
          label={`Win Rate (${rangeLabel})`}
          value={fmtPct(platformPerf?.win_rate)}
          icon={Zap}
        />
      </div>

      {/* Intraday equity */}
      <Panel title={`Intraday Equity — ${scope}`} icon={Clock}>
        {intraday.length < 2 ? (
          <EmptyHint
            text="Need 2+ snapshots today (writer fires every management cycle)."
          />
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={intraday}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
                <XAxis
                  dataKey="snapshot_at"
                  tickFormatter={fmtTime}
                  stroke="#6B7280"
                  fontSize={11}
                />
                <YAxis stroke="#6B7280" fontSize={11} domain={['auto', 'auto']} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151' }}
                  labelFormatter={fmtTime}
                />
                <Line
                  type="monotone"
                  dataKey="equity"
                  stroke="#A78BFA"
                  strokeWidth={2}
                  dot={false}
                  name="Equity"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>

      {/* Historical equity */}
      <Panel title={`${rangeLabel} Equity Curve — ${scope}`} icon={BarChart3}>
        {equity.length < 2 ? (
          <EmptyHint text="No closed trades yet." />
        ) : (
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={equity}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
                <XAxis
                  dataKey="snapshot_at"
                  tickFormatter={(v) => fmtTime(v).split(',')[0]}
                  stroke="#6B7280"
                  fontSize={11}
                />
                <YAxis stroke="#6B7280" fontSize={11} domain={['auto', 'auto']} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151' }}
                  labelFormatter={fmtTime}
                />
                {equity[0]?.starting_capital != null && (
                  <ReferenceLine
                    y={equity[0].starting_capital}
                    stroke="#6B7280"
                    strokeDasharray="3 3"
                    label={{ value: 'Start', fill: '#9CA3AF', fontSize: 10 }}
                  />
                )}
                <Line
                  type="monotone"
                  dataKey="equity"
                  stroke="#A78BFA"
                  strokeWidth={2}
                  dot={false}
                  name="Equity"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>
    </div>
  )
}

// ============================================================================
// TAB: POSITIONS
// ============================================================================

function PositionsTab({
  positions, scope,
}: { positions: Position[]; scope: string }) {
  const filtered = scope === 'PLATFORM'
    ? positions
    : positions.filter(p => p.instance_name === scope)

  if (filtered.length === 0) {
    return (
      <Panel title="Open Positions" icon={Target}>
        <EmptyHint text="No open positions on selected scope." />
      </Panel>
    )
  }

  return (
    <Panel title={`Open Positions — ${scope} (${filtered.length})`} icon={Target}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-gray-400 border-b border-gray-800">
            <tr>
              <th className="text-left p-2">Instance</th>
              <th className="text-left p-2">State</th>
              <th className="text-left p-2">Opened</th>
              <th className="text-left p-2">Expiry</th>
              <th className="text-right p-2">SP / LP / LC</th>
              <th className="text-right p-2">Contracts</th>
              <th className="text-right p-2">Net Cost</th>
              <th className="text-right p-2">Max Loss</th>
              <th className="text-right p-2">P&L</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => (
              <tr key={p.position_id} className="border-b border-gray-800/40 hover:bg-gray-900/40">
                <td className="p-2 font-mono">{p.letf_ticker}</td>
                <td className="p-2">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    p.state === 'OPEN' ? 'bg-green-900/30 text-green-300'
                      : p.state === 'MANAGING' ? 'bg-amber-900/30 text-amber-300'
                        : p.state === 'CLOSING' ? 'bg-orange-900/30 text-orange-300'
                          : 'bg-gray-800 text-gray-400'
                  }`}>{p.state}</span>
                </td>
                <td className="p-2 text-gray-400">{fmtTime(p.opened_at)}</td>
                <td className="p-2 text-gray-400">{p.expiration_date ?? '—'}</td>
                <td className="p-2 text-right font-mono">
                  {p.short_put_strike}/{p.long_put_strike}/{p.long_call_strike}
                </td>
                <td className="p-2 text-right font-mono">{p.contracts}</td>
                <td className="p-2 text-right font-mono">{fmtUSD(p.entry_net_cost)}</td>
                <td className="p-2 text-right font-mono text-red-400">
                  {fmtUSD(p.defined_max_loss)}
                </td>
                <td className={`p-2 text-right font-mono ${
                  (p.realized_pnl ?? 0) > 0 ? 'text-green-400'
                    : (p.realized_pnl ?? 0) < 0 ? 'text-red-400'
                      : 'text-gray-500'
                }`}>
                  {p.realized_pnl == null ? '—' : fmtUSD(p.realized_pnl)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

// ============================================================================
// TAB: PERFORMANCE
// ============================================================================

function PerformanceTab({
  perf, range, onRangeChange,
}: {
  perf: PerformanceResponse | null
  range: RangeId
  onRangeChange: (r: RangeId) => void
}) {
  if (!perf) return <EmptyHint text="Performance data unavailable." />
  const rangeLabel = range.toUpperCase()

  return (
    <div className="space-y-6">
      <RangeSelector range={range} onChange={onRangeChange} />
      <Panel title={`Platform Performance (${rangeLabel})`} icon={TrendingUp}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Trades" value={String(perf.platform.trades)} icon={Target} />
          <StatCard label="Total P&L" value={fmtUSD(perf.platform.total_pnl)} icon={DollarSign} />
          <StatCard label="Win Rate" value={fmtPct(perf.platform.win_rate)} icon={Zap} />
          <StatCard label="Avg P&L" value={fmtUSD(perf.platform.avg_pnl)} icon={Activity} />
        </div>
      </Panel>

      <Panel title="Per-Instance Performance" icon={BarChart3}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-gray-400 border-b border-gray-800">
              <tr>
                <th className="text-left p-2">Instance</th>
                <th className="text-right p-2">Trades</th>
                <th className="text-right p-2">W / L / Sc</th>
                <th className="text-right p-2">Win Rate</th>
                <th className="text-right p-2">Total P&L</th>
                <th className="text-right p-2">Avg P&L</th>
                <th className="text-right p-2">Best</th>
                <th className="text-right p-2">Worst</th>
                <th className="text-left p-2">Triggers</th>
              </tr>
            </thead>
            <tbody>
              {perf.instances.map((row) => (
                <tr key={row.instance_name} className="border-b border-gray-800/40">
                  <td className="p-2 font-mono">{row.instance_name}</td>
                  <td className="p-2 text-right font-mono">{row.trades}</td>
                  <td className="p-2 text-right font-mono">
                    <span className="text-green-400">{row.wins}</span>
                    {' / '}
                    <span className="text-red-400">{row.losses}</span>
                    {' / '}
                    <span className="text-gray-400">{row.scratches}</span>
                  </td>
                  <td className="p-2 text-right font-mono">{fmtPct(row.win_rate)}</td>
                  <td className={`p-2 text-right font-mono ${
                    row.total_pnl > 0 ? 'text-green-400'
                      : row.total_pnl < 0 ? 'text-red-400'
                        : 'text-gray-400'
                  }`}>{fmtUSD(row.total_pnl)}</td>
                  <td className="p-2 text-right font-mono">{fmtUSD(row.avg_pnl)}</td>
                  <td className="p-2 text-right font-mono text-green-400">{fmtUSD(row.best)}</td>
                  <td className="p-2 text-right font-mono text-red-400">{fmtUSD(row.worst)}</td>
                  <td className="p-2 text-xs text-gray-400">
                    {Object.entries(row.trigger_breakdown).length === 0
                      ? '—'
                      : Object.entries(row.trigger_breakdown)
                          .map(([t, n]) => `${t}:${n}`).join(' ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}

// ============================================================================
// TAB: AUDIT (scan activity + gate failures)
// ============================================================================

function AuditTab({
  audit, gates,
}: { audit: AuditEvent[]; gates: GateFailure[] }) {
  return (
    <div className="space-y-6">
      <Panel title="Scan Activity (last 50)" icon={Activity}>
        {audit.length === 0 ? (
          <EmptyHint text="No scan activity yet." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-gray-400 border-b border-gray-800">
                <tr>
                  <th className="text-left p-2">Time</th>
                  <th className="text-left p-2">Instance</th>
                  <th className="text-left p-2">Event</th>
                  <th className="text-left p-2">Position</th>
                  <th className="text-left p-2">Detail</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((e) => (
                  <tr key={e.id} className="border-b border-gray-800/40">
                    <td className="p-2 text-gray-400">{fmtTime(e.timestamp)}</td>
                    <td className="p-2 font-mono">{e.instance}</td>
                    <td className="p-2">
                      <span className={`px-2 py-0.5 rounded text-xs ${
                        e.event_type === 'ENTRY_EVAL'
                          ? 'bg-blue-900/30 text-blue-300'
                          : 'bg-purple-900/30 text-purple-300'
                      }`}>{e.event_type}</span>
                    </td>
                    <td className="p-2 font-mono text-gray-500">
                      {e.position_id ? e.position_id.slice(-8) : '—'}
                    </td>
                    <td className="p-2 text-gray-400 max-w-md truncate">
                      {e.data?.decision ?? e.data?.fired_action?.trigger_id ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Recent Gate Failures (last 50)" icon={AlertTriangle}>
        {gates.length === 0 ? (
          <EmptyHint text="No gate failures recorded." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-gray-400 border-b border-gray-800">
                <tr>
                  <th className="text-left p-2">Time</th>
                  <th className="text-left p-2">LETF</th>
                  <th className="text-left p-2">Failed Gate</th>
                  <th className="text-left p-2">Outcome</th>
                  <th className="text-left p-2">Passed Before</th>
                  <th className="text-left p-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                {gates.map((g) => (
                  <tr key={g.id} className="border-b border-gray-800/40">
                    <td className="p-2 text-gray-400">{fmtTime(g.timestamp)}</td>
                    <td className="p-2 font-mono">{g.letf_ticker}</td>
                    <td className="p-2 font-mono text-red-300">{g.failed_gate}</td>
                    <td className="p-2 text-xs text-gray-500">{g.failure_outcome}</td>
                    <td className="p-2 text-gray-500 text-xs">
                      {(g.gates_passed_before_failure ?? []).join(' → ') || '—'}
                    </td>
                    <td className="p-2 text-gray-400 max-w-md truncate">{g.failure_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}

// ============================================================================
// TAB: KILLS
// ============================================================================

function KillsTab({ kills }: { kills: KillState | null }) {
  if (!kills) return <EmptyHint text="Kill state unavailable." />

  return (
    <div className="space-y-6">
      <Panel title={`Active Kills (${kills.active_count})`} icon={Shield}>
        {kills.active.length === 0 ? (
          <div className="flex items-center gap-2 text-green-400">
            <CheckCircle2 className="w-5 h-5" />
            <span>No active kills. All instances trading-eligible.</span>
          </div>
        ) : (
          <div className="space-y-2">
            {kills.active.map((k, i) => (
              <div
                key={i}
                className="bg-red-950/20 border border-red-800/40 rounded p-3 flex items-start gap-3"
              >
                <XCircle className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <div className="font-semibold text-red-300">
                    {k.scope === 'PLATFORM' ? 'PLATFORM-WIDE' : k.instance_name}
                    {' · '}
                    <span className="text-xs font-mono">{k.trigger_id}</span>
                  </div>
                  <div className="text-sm text-red-400 mt-1">{k.reason}</div>
                  <div className="text-xs text-red-500/70 mt-1">{fmtTime(k.killed_at)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Kill History (last 30 days)" icon={Clock}>
        {kills.history.length === 0 ? (
          <EmptyHint text="No prior kills in the last 30 days." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-gray-400 border-b border-gray-800">
                <tr>
                  <th className="text-left p-2">Scope</th>
                  <th className="text-left p-2">Trigger</th>
                  <th className="text-left p-2">Reason</th>
                  <th className="text-left p-2">Killed</th>
                  <th className="text-left p-2">Cleared</th>
                  <th className="text-left p-2">By</th>
                </tr>
              </thead>
              <tbody>
                {kills.history.map((h, i) => (
                  <tr key={i} className="border-b border-gray-800/40">
                    <td className="p-2 font-mono">
                      {h.scope === 'PLATFORM' ? 'PLATFORM' : h.instance_name}
                    </td>
                    <td className="p-2 font-mono text-amber-300">{h.trigger_id}</td>
                    <td className="p-2 text-gray-400 max-w-xs truncate">{h.reason}</td>
                    <td className="p-2 text-gray-500">{fmtTime(h.killed_at)}</td>
                    <td className="p-2 text-gray-500">{fmtTime(h.cleared_at)}</td>
                    <td className="p-2 text-gray-500 text-xs">{h.cleared_by ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}

// ============================================================================
// TAB: CONFIG / CALIBRATION
// ============================================================================

function ConfigTab({
  calibration, platform,
}: { calibration: CalibrationResponse | null; platform: PlatformStatus | null }) {
  return (
    <div className="space-y-6">
      <Panel title="Platform Configuration" icon={Settings}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <ConfigRow label="Account capital" value={fmtUSD(platform?.account_capital, 0)} />
          <ConfigRow label="Platform cap" value={fmtUSD(platform?.platform_cap, 0)} />
          <ConfigRow label="Max concurrent" value="3" />
          <ConfigRow label="Mode" value="PAPER (v0.2)" />
        </div>
      </Panel>

      <Panel
        title={`Phase ${calibration?.phase ?? '1.5'} Calibration${
          calibration?.last_calibrated ? ` · last ${calibration.last_calibrated}` : ''
        }`}
        icon={FileText}
      >
        {!calibration ? (
          <EmptyHint text="Calibration data unavailable." />
        ) : (
          <div className="space-y-3">
            {Object.entries(calibration.parameters).map(([key, p]) => (
              <div
                key={key}
                className="bg-gray-900/50 border border-gray-800 rounded p-3"
              >
                <div className="flex items-center justify-between">
                  <div className="font-mono text-sm text-purple-300">{key}</div>
                  <span className={`px-2 py-0.5 rounded text-xs font-mono ${
                    p.tag === 'CALIB-OK' || p.tag === 'CALIB-SANITY-OK'
                      ? 'bg-green-900/30 text-green-300'
                      : p.tag === 'CALIB-ADJUST'
                        ? 'bg-amber-900/30 text-amber-300'
                        : 'bg-red-900/30 text-red-300'
                  }`}>{p.tag}</span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <div className="text-gray-500">Active value</div>
                    <div className="font-mono text-gray-100">{p.value}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">Spec default</div>
                    <div className="font-mono text-gray-400">{p.spec_default}</div>
                  </div>
                </div>
                <div className="mt-2 text-xs text-gray-400 leading-relaxed">{p.notes}</div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Instances" icon={Layers}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-gray-400 border-b border-gray-800">
              <tr>
                <th className="text-left p-2">Name</th>
                <th className="text-left p-2">LETF</th>
                <th className="text-left p-2">Underlying</th>
                <th className="text-right p-2">Allocation Cap</th>
                <th className="text-left p-2">Mode</th>
              </tr>
            </thead>
            <tbody>
              {platform?.instances.map((i) => (
                <tr key={i.name} className="border-b border-gray-800/40">
                  <td className="p-2 font-mono">{i.name}</td>
                  <td className="p-2 font-mono text-purple-300">{i.letf_ticker}</td>
                  <td className="p-2 font-mono text-gray-400">{i.underlying_ticker}</td>
                  <td className="p-2 text-right font-mono">${i.allocation_cap}</td>
                  <td className="p-2 text-xs">
                    <span className="px-2 py-0.5 rounded bg-blue-900/30 text-blue-300">PAPER</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}

// ============================================================================
// SHARED PRESENTATIONAL COMPONENTS
// ============================================================================

function Panel({
  title, icon: Icon, children,
}: {
  title: string
  icon: React.ComponentType<{ className?: string }>
  children: React.ReactNode
}) {
  return (
    <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3 pb-2 border-b border-gray-800">
        <Icon className="w-4 h-4 text-purple-400" />
        <h2 className="text-sm font-semibold text-gray-200">{title}</h2>
      </div>
      {children}
    </div>
  )
}

function StatCard({
  label, value, icon: Icon, color = 'text-gray-100',
}: {
  label: string
  value: string
  icon: React.ComponentType<{ className?: string }>
  color?: string
}) {
  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-gray-500">{label}</span>
        <Icon className="w-4 h-4 text-gray-600" />
      </div>
      <div className={`text-xl font-semibold font-mono ${color}`}>{value}</div>
    </div>
  )
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div className="text-sm text-gray-500 italic py-4">{text}</div>
  )
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-gray-500">{label}</div>
      <div className="font-mono text-gray-100">{value}</div>
    </div>
  )
}

function RangeSelector({
  range, onChange,
}: { range: RangeId; onChange: (r: RangeId) => void }) {
  const options: Array<[RangeId, string]> = [
    ['7d', '7D'],
    ['30d', '30D'],
    ['90d', '90D'],
    ['all', 'ALL'],
  ]
  return (
    <div className="inline-flex rounded-lg border border-gray-800 bg-gray-900/40 p-0.5">
      {options.map(([id, label]) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          className={`px-3 py-1 text-xs font-mono rounded transition-colors ${
            range === id
              ? 'bg-purple-700/40 text-purple-200'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
