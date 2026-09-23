'use client'

// VALOR — "Live terminal" redesign (option 2a).
// Drop-in replacement for frontend/src/app/valor/ValorContent.tsx.
// Uses the same data hooks and ML/A-B actions as the previous version.

import { useState, useEffect, useMemo, useRef } from 'react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import { LoadingState } from '@/components/trader'
import {
  useValorStatus,
  useValorPositions,
  useValorClosedTrades,
  useValorEquityCurve,
  useValorIntradayEquity,
  useValorScanActivity,
  useValorMLTrainingDataStats,
  useValorMLStatus,
  useValorMLApprovalStatus,
  useValorABTestStatus,
  trainValorML,
  approveValorML,
  revokeValorML,
  rejectValorML,
  enableValorABTest,
  disableValorABTest,
  useUnifiedBotSummary,
  useValorTickers,
  useValorTickerStats,
  useValorGexProfile,
} from '@/lib/hooks/useMarketData'

const G = '#10b981'
const R = '#ef4444'
const REFRESH_MS = 15000

const TABS = [
  { id: 'portfolio', label: 'Portfolio', desc: 'Live P&L and positions' },
  { id: 'overview', label: 'Overview', desc: 'Bot status and metrics' },
  { id: 'activity', label: 'Activity', desc: 'Scans and signals' },
  { id: 'history', label: 'History', desc: 'Closed trades' },
  { id: 'config', label: 'Config', desc: 'Settings' },
] as const
type TabId = typeof TABS[number]['id']

const TIMEFRAMES = [
  { id: 'intraday', label: 'Today', days: 0 },
  { id: '7d', label: '7D', days: 7 },
  { id: '14d', label: '14D', days: 14 },
  { id: '30d', label: '30D', days: 30 },
  { id: '90d', label: '90D', days: 90 },
]

const TICKERS = ['MES', 'MNQ', 'CL', 'NG', 'RTY', 'MGC'] as const
const META: Record<string, { label: string; color: string; d: number }> = {
  MES: { label: 'Micro S&P 500', color: '#A855F7', d: 2 },
  MNQ: { label: 'Micro Nasdaq', color: '#06B6D4', d: 2 },
  CL: { label: 'Crude Oil', color: '#F59E0B', d: 2 },
  NG: { label: 'Natural Gas', color: '#22C55E', d: 3 },
  RTY: { label: 'Micro Russell', color: '#F97316', d: 2 },
  MGC: { label: 'Micro Gold', color: '#EAB308', d: 2 },
}
const meta = (t?: string) => META[t || 'MES'] || META.MES

const SPECS: Record<string, [string, string, string, string]> = {
  MES: ['$5.00/point', '0.25 points', '$1.25/tick', '~$1,500'],
  MNQ: ['$2.00/point', '0.25 points', '$0.50/tick', '~$1,800'],
  CL: ['$100/point (MCL)', '0.01 points', '$1.00/tick', '~$1,100'],
  NG: ['$100/point (MNG)', '0.001 points', '$0.10/tick', '~$500'],
  RTY: ['$5.00/point', '0.10 points', '$0.50/tick', '~$800'],
  MGC: ['$10.00/point', '0.10 points', '$1.00/tick', '~$1,100'],
}

const money = (n: number, sign = false) =>
  (sign ? (n >= 0 ? '+' : '−') : n < 0 ? '−' : '') +
  '$' + Math.abs(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const pct = (n: number, sign = true) => (sign && n >= 0 ? '+' : '') + (n || 0).toFixed(2) + '%'
const pnlColor = (n: number) => (n > 0 ? G : n < 0 ? R : '#9ca3af')
const zoneColor = (u: number) => (u < 50 ? G : u < 70 ? '#eab308' : u < 80 ? '#f97316' : R)

// ------------------------------------------------------------------ small UI

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={`bg-[#11151f] border border-[#1c2233] rounded-xl ${className}`}>{children}</div>
}
function Stat({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <Card className="p-4 flex flex-col gap-1.5">
      <span className="text-[13px] text-gray-400">{label}</span>
      <span className="font-mono text-2xl font-semibold" style={{ color: color || '#f3f4f6' }}>{value}</span>
    </Card>
  )
}
function Dot({ color, size = 8 }: { color: string; size?: number }) {
  return <span className="inline-block rounded-full shrink-0" style={{ width: size, height: size, background: color }} />
}
function Pills<T extends string>({ items, value, onChange }: { items: { id: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex gap-1 flex-wrap">
      {items.map(i => (
        <button key={i.id} onClick={() => onChange(i.id)}
          className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-colors ${value === i.id ? 'bg-yellow-500 text-[#0a0e1a]' : 'text-gray-400 hover:text-gray-200'}`}>
          {i.label}
        </button>
      ))}
    </div>
  )
}

// ------------------------------------------------------------------ charts

type Bar = { o: number; h: number; l: number; c: number }

const BUCKET_MS = 5 * 60 * 1000 // 5-minute bars

// 5-minute OHLC bars built from VALOR's own scan prices (scans fire every few seconds).
function barsFromScans(scans: any[], ticker: string, max = 48): Bar[] {
  const pts = scans
    .filter(s => (s.ticker || 'MES') === ticker && s.underlying_price)
    .sort((a, b) => new Date(a.scan_time).getTime() - new Date(b.scan_time).getTime())
    .map(s => ({ t: new Date(s.scan_time).getTime(), p: Number(s.underlying_price) }))

  const buckets = new Map<number, { o: number; h: number; l: number; c: number }>()
  for (const { t, p } of pts) {
    const key = Math.floor(t / BUCKET_MS)
    const b = buckets.get(key)
    if (!b) {
      buckets.set(key, { o: p, h: p, l: p, c: p })
    } else {
      b.h = Math.max(b.h, p)
      b.l = Math.min(b.l, p)
      b.c = p
    }
  }

  const bars = Array.from(buckets.keys())
    .sort((a, b) => a - b)
    .map(key => buckets.get(key)!)

  return bars.slice(-max)
}

type GexStrike = { strike: number; net_gex: number }
type Levels = { cw?: number; pw?: number; flip?: number }

// Render the chart at real pixel size (not a stretched viewBox) so its text
// matches the rest of the page on any screen width.
function CandleChart(props: { bars: Bar[]; levels: Levels; price?: number; d: number; gex?: any }) {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    setWidth(Math.floor(el.clientWidth))
    const ro = new ResizeObserver(entries => setWidth(Math.floor(entries[0].contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return (
    <div ref={ref} className="w-full">
      {width > 0 ? <CandleSvg {...props} width={width} /> : <div className="h-[320px]" />}
    </div>
  )
}

function CandleSvg({ bars, levels, price, d, gex, width }: { bars: Bar[]; levels: Levels; price?: number; d: number; gex?: any; width: number }) {
  if (bars.length < 2) {
    return <div className="h-[320px] flex items-center justify-center text-sm text-gray-500">Waiting for scan prices to build 5m bars…</div>
  }
  // Layout (px): candles 0..PW | price axis PW..PW+AX | gap | Net GEX column GX..W
  const H = 320, TOP = 22, BOT = 8
  const GW = width >= 700 ? 120 : 80, AX = 80, GAP = 12
  const W = width
  const PW = Math.max(160, W - GW - GAP - AX)
  const GX = PW + AX + GAP

  const barLo = Math.min(...bars.map(b => b.l))
  const barHi = Math.max(...bars.map(b => b.h))
  const barRange = barHi - barLo || 1
  // Show a level if it's within 4% of price or within 2x the visible bar range.
  const ref = price || bars[bars.length - 1].c
  const nearRange = (v: number) =>
    (ref > 0 && Math.abs(v - ref) / ref <= 0.04) ||
    (v >= barLo - barRange * 2 && v <= barHi + barRange * 2)
  const keep = (v?: number) => (v != null && v > 0 && nearRange(v) ? v : undefined)
  const cwLevel = keep(levels.cw), pwLevel = keep(levels.pw), flipLevel = keep(levels.flip)
  // Size the chart to the candles; levels farther than 1x the candle range
  // are pinned to the top/bottom edge as ▲/▼ tags instead of stretching the axis.
  const inView = (v: number) => v >= barLo - barRange && v <= barHi + barRange
  const lvl = [cwLevel, pwLevel, flipLevel].filter((v): v is number => !!v && inView(v))
  let lo = Math.min(barLo, ...lvl), hi = Math.max(barHi, ...lvl)
  const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad
  const y = (v: number) => TOP + ((hi - v) / (hi - lo)) * (H - TOP - BOT)
  const cw = PW / bars.length
  const bodyW = Math.max(2, Math.min(12, cw * 0.62))

  const lines: [string, number | undefined, string, string | undefined][] = [
    ['Call wall', cwLevel, '#3b82f6', undefined],
    ['Gamma flip', flipLevel, '#f59e0b', '6 4'],
    ['Put wall', pwLevel, '#8b5cf6', undefined],
  ]

  // Right-axis tags (levels + price), nudged apart so they never overlap.
  const TAG_H = 18
  const tags = [
    ...lines.filter(([, v]) => v).map(([l, v, col]) => ({ key: l, v: v as number, col, text: '#fff' })),
    ...(price ? [{ key: 'Price', v: price, col: '#eab308', text: '#0a0e1a' }] : []),
  ].map(t => {
    const above = t.v > hi, below = t.v < lo
    const ty = above ? TOP + TAG_H / 2 : below ? H - BOT - TAG_H / 2 : y(t.v)
    return { ...t, ty, arrow: above ? '▲ ' : below ? '▼ ' : '' }
  }).sort((a, b) => a.ty - b.ty)
  for (let i = 1; i < tags.length; i++) {
    if (tags[i].ty - tags[i - 1].ty < TAG_H + 2) tags[i].ty = tags[i - 1].ty + TAG_H + 2
  }
  for (let i = tags.length - 1; i >= 0; i--) {
    const maxY = i === tags.length - 1 ? H - BOT - TAG_H / 2 : tags[i + 1].ty - TAG_H - 2
    if (tags[i].ty > maxY) tags[i].ty = maxY
  }
  const nearTag = (yy: number) => tags.some(t => Math.abs(t.ty - yy) < TAG_H)

  // Net GEX column: bars from a centre baseline (right = positive, left = negative),
  // on the same y-scale as the candles, only for strikes in view.
  const gexStrikes: GexStrike[] = gex?.available ? (gex.strikes || []) : []
  const visible = gexStrikes.filter(s => s.strike >= lo && s.strike <= hi)
  const gMax = Math.max(1, ...visible.map(s => Math.abs(s.net_gex)))
  const gMid = GX + GW / 2, gHalf = GW / 2 - 4
  const sorted = [...visible].sort((a, b) => a.strike - b.strike)
  const gaps = sorted.slice(1).map((s, i) => s.strike - sorted[i].strike).filter(g => g > 0).sort((a, b) => a - b)
  const stepPx = gaps.length ? Math.abs(y(0) - y(gaps[Math.floor(gaps.length / 2)])) : 6
  const gBarH = Math.max(2, Math.min(8, stepPx * 0.6))

  const MONO = 'ui-monospace, SFMono-Regular, Menlo, monospace'
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="block">
      {[0, 1, 2, 3, 4].map(i => {
        const v = lo + (hi - lo) * (i + 0.5) / 5
        return (
          <g key={i}>
            <line x1={0} x2={PW} y1={y(v)} y2={y(v)} stroke="#161b28" />
            {!nearTag(y(v)) && <text x={PW + 8} y={y(v) + 4} fill="#6b7280" fontSize={11} fontFamily={MONO}>{v.toFixed(d)}</text>}
          </g>
        )
      })}
      {lines.map(([l, v, col, dash]) => v && v >= lo && v <= hi ? (
        <line key={l} x1={0} x2={PW} y1={y(v)} y2={y(v)} stroke={col} strokeWidth={1.25} strokeDasharray={dash} opacity={0.9} />
      ) : null)}
      {bars.map((b, i) => {
        const x = i * cw + cw / 2, col = b.c >= b.o ? G : R
        return (
          <g key={i}>
            <line x1={x} x2={x} y1={y(b.h)} y2={y(b.l)} stroke={col} />
            <rect x={x - bodyW / 2} width={bodyW} y={y(Math.max(b.o, b.c))} height={Math.max(1, Math.abs(y(b.o) - y(b.c)))} fill={col} rx={1} />
          </g>
        )
      })}
      {price ? <line x1={0} x2={PW} y1={y(price)} y2={y(price)} stroke="#eab308" strokeDasharray="2 3" /> : null}
      {tags.map(t => (
        <g key={t.key}>
          <rect x={PW + 2} y={t.ty - TAG_H / 2} width={AX - 4} height={TAG_H} rx={3} fill={t.col} />
          <text x={PW + 6} y={t.ty + 4} fill={t.text} fontSize={11} fontWeight={600} fontFamily={MONO}>{t.arrow}{t.v.toFixed(d)}</text>
        </g>
      ))}
      <g>
        <line x1={GX} x2={GX} y1={0} y2={H} stroke="#1c2233" />
        <text x={GX + 6} y={12} fill="#6b7280" fontSize={10} fontWeight={600} letterSpacing={0.8}>
          NET GEX{gex?.available ? ` · ${gex.is_0dte ? '0DTE' : 'NEAREST'}` : ''}
        </text>
        {visible.length ? (
          <>
            <line x1={gMid} x2={gMid} y1={TOP} y2={H - BOT} stroke="#1c2233" />
            {lines.map(([l, v, col, dash]) => v && v >= lo && v <= hi ? (
              <line key={`g-${l}`} x1={GX} x2={W} y1={y(v)} y2={y(v)} stroke={col} strokeWidth={1} strokeDasharray={dash} opacity={0.5} />
            ) : null)}
            {price ? <line x1={GX} x2={W} y1={y(price)} y2={y(price)} stroke="#eab308" strokeDasharray="2 3" opacity={0.5} /> : null}
            {visible.map((s, i) => {
              const len = (Math.abs(s.net_gex) / gMax) * gHalf
              const pos = s.net_gex >= 0
              return <rect key={i} x={pos ? gMid : gMid - len} width={Math.max(1, len)} y={y(s.strike) - gBarH / 2} height={gBarH} fill={pos ? G : R} rx={1} />
            })}
          </>
        ) : (
          <text x={gMid} y={H / 2} fill="#6b7280" fontSize={11} textAnchor="middle">
            {gex?.available ? 'No strikes in view' : 'Unavailable'}
          </text>
        )}
      </g>
    </svg>
  )
}


function EquityChart({ points, start, animKey }: { points: number[]; start: number; animKey: string }) {
  if (points.length < 2) return <div className="h-full flex items-center justify-center text-sm text-gray-500">Data will appear after trades are executed</div>
  const mn = Math.min(start, ...points), mx = Math.max(start, ...points), pad = (mx - mn) * 0.12 || 50
  const y = (v: number) => 200 - ((v - mn + pad) / (mx - mn + 2 * pad)) * 200
  const line = points.map((v, i) => `${i ? 'L' : 'M'}${(i / (points.length - 1) * 1000).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  const lastY = y(points[points.length - 1])
  return (
    <div className="relative h-full">
      <svg key={animKey} viewBox="0 0 1000 200" preserveAspectRatio="none" className="w-full h-full block">
        <line x1={0} x2={1000} y1={y(start)} y2={y(start)} stroke="#ef4444" strokeDasharray="5 5" vectorEffect="non-scaling-stroke" />
        <path d={`${line} L1000 200 L0 200 Z`} fill="rgba(234,179,8,.10)" className="valor-fade" />
        <path d={line} pathLength={1} strokeDasharray={1} fill="none" stroke="#eab308" strokeWidth={2} vectorEffect="non-scaling-stroke" className="valor-draw" />
      </svg>
      <span className="absolute -right-1 w-2 h-2 rounded-full bg-yellow-500 valor-pulse" style={{ top: `calc(${(lastY / 2).toFixed(1)}% - 4px)` }} />
    </div>
  )
}

// ------------------------------------------------------------------ page

export default function ValorPage() {
  const sidebarPadding = useSidebarPadding()
  const [tab, setTab] = useState<TabId>('portfolio')
  const [sel, setSel] = useState<string>('MES')
  const [tf, setTf] = useState('intraday')
  const [histFilter, setHistFilter] = useState<string>('ALL')
  const [busy, setBusy] = useState<string | null>(null)
  const [now, setNow] = useState(Date.now())

  const tfo = TIMEFRAMES.find(t => t.id === tf) || TIMEFRAMES[0]
  const { data: statusData, error: statusError, isLoading: statusLoading, mutate: refreshStatus } = useValorStatus(undefined)
  const { data: positionsData, mutate: refreshPositions } = useValorPositions(undefined)
  const { data: closedTradesData } = useValorClosedTrades(1000, undefined)
  const { data: equityCurveData } = useValorEquityCurve(tfo.days || 30, undefined)
  const { data: intradayEquityData, mutate: refreshIntraday } = useValorIntradayEquity(undefined)
  const { data: tickersData } = useValorTickers()
  const { data: tickerStatsData } = useValorTickerStats()
  const { data: gexProfileData } = useValorGexProfile(sel)
  const { data: scanData, mutate: refreshScans } = useValorScanActivity(1000, undefined, undefined)
  const { data: mlStats, mutate: refreshTrainingStats } = useValorMLTrainingDataStats()
  const { data: mlStatus, mutate: refreshMLStatus } = useValorMLStatus()
  const { data: mlApproval, mutate: refreshApproval } = useValorMLApprovalStatus()
  const { data: abStatus, mutate: refreshAB } = useValorABTestStatus()
  const { data: unifiedData } = useUnifiedBotSummary('VALOR')

  // Live: 1s clock for the scan countdown + periodic refresh of fast-moving data.
  useEffect(() => {
    const clock = setInterval(() => setNow(Date.now()), 1000)
    const poll = setInterval(() => { refreshStatus(); refreshPositions(); refreshScans(); refreshIntraday() }, REFRESH_MS)
    return () => { clearInterval(clock); clearInterval(poll) }
  }, [refreshStatus, refreshPositions, refreshScans, refreshIntraday])

  // Margin zones (same endpoint as before)
  const [marginZones, setMarginZones] = useState<any>(null)
  useEffect(() => {
    const API = process.env.NEXT_PUBLIC_API_URL || ''
    const load = async () => { try { const r = await fetch(`${API}/api/valor/margin/zones`); if (r.ok) setMarginZones((await r.json()).data) } catch {} }
    load(); const i = setInterval(load, REFRESH_MS); return () => clearInterval(i)
  }, [])

  const status = statusData || {}
  const performance = status.performance || {}
  const winTracker = status.win_tracker || {}
  const config = status.config || {}
  const lossStreak = status.loss_streak || {}
  const paper = status.paper_account || {}
  const unified = unifiedData?.data
  const positions: any[] = positionsData?.positions || status?.positions?.positions || []
  const trades: any[] = closedTradesData?.trades || []
  const scans: any[] = scanData?.scans || []
  const scanSummary = scanData?.summary || {}
  const tickerStats = tickerStatsData?.ticker_stats || {}
  const activeTickers: string[] = tickersData?.active_tickers || [...TICKERS]

  const startingCapital = unified?.starting_capital ?? paper.starting_capital ?? 100000 * activeTickers.length
  const unrealized = positions.reduce((a, p) => a + (p.unrealized_pnl || 0), 0)
  const realized = paper.cumulative_pnl ?? performance.total_pnl ?? 0
  const equity = (paper.current_balance ?? startingCapital + realized) + unrealized

  // Latest scan per ticker → live price + GEX levels
  const latest = useMemo(() => {
    const out: Record<string, any> = {}
    for (const s of scans) {
      // Skip failed scans (no quote → price 0, no walls) so one bad scan doesn't blank the chart
      if (!(Number(s.underlying_price) > 0)) continue
      const t = s.ticker || 'MES'
      if (!out[t] || new Date(s.scan_time) > new Date(out[t].scan_time)) out[t] = s
    }
    return out
  }, [scans])
  const firstPrice = (t: string) => {
    const b = barsFromScans(scans, t); return b.length ? b[0].o : undefined
  }
  const selScan = latest[sel] || {}
  const selPrice: number | undefined = selScan.underlying_price
  const selBars = useMemo(() => barsFromScans(scans, sel), [scans, sel])
  const levels = { cw: selScan.call_wall || undefined, pw: selScan.put_wall || undefined, flip: selScan.flip_point || undefined }
  const lastScanAt = selScan.scan_time ? new Date(selScan.scan_time).getTime() : null
  const nextScan = lastScanAt ? Math.max(0, 60 - Math.floor((now - lastScanAt) / 1000) % 60) : null

  const eqPoints: number[] = (tf === 'intraday' ? intradayEquityData?.equity_curve : equityCurveData?.equity_curve || [])
    ?.map((p: any) => Number(p.equity)).filter((v: number) => !isNaN(v)) || []

  const histTrades = trades.filter(t => histFilter === 'ALL' || (t.ticker || 'MES') === histFilter)
  const wins = histTrades.filter(t => t.realized_pnl > 0), losses = histTrades.filter(t => t.realized_pnl < 0)
  const histTotal = histTrades.reduce((a, t) => a + (t.realized_pnl || 0), 0)
  const avg = (xs: any[]) => (xs.length ? xs.reduce((a, t) => a + t.realized_pnl, 0) / xs.length : 0)

  const run = async (key: string, fn: () => Promise<any>, after: (() => void)[]) => {
    setBusy(key)
    try { const r = await fn(); if (r?.success) after.forEach(f => f()) } catch (e) { console.error(`VALOR ${key} failed`, e) } finally { setBusy(null) }
  }
  const mlApproved = !!mlApproval?.ml_approved
  const accuracy = ((mlStatus?.accuracy || 0) * 100).toFixed(1)

  if (statusLoading) return (<><Navigation /><div className="flex items-center justify-center h-screen bg-[#0a0e1a]"><LoadingState message="Loading VALOR..." /></div></>)
  if (statusError) return (
    <><Navigation />
      <main className={`min-h-screen bg-[#0a0e1a] text-white px-4 pt-24 ${sidebarPadding}`}>
        <div className="max-w-7xl mx-auto bg-red-900/40 border border-red-500/60 rounded-xl p-6">
          <h2 className="text-xl font-bold text-red-400">VALOR Not Available</h2>
          <p className="text-red-300 mt-2">The VALOR futures bot is not currently available. Check backend deployment.</p>
        </div>
      </main></>
  )

  const tabMeta = TABS.find(t => t.id === tab)!

  return (
    <>
      <Navigation />
      <style>{`
        @keyframes valor-tape{from{transform:translateX(0)}to{transform:translateX(-50%)}}
        @keyframes valor-draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
        @keyframes valor-fade{from{opacity:0}to{opacity:1}}
        @keyframes valor-pulse{0%{box-shadow:0 0 0 0 rgba(234,179,8,.6)}100%{box-shadow:0 0 0 10px rgba(234,179,8,0)}}
        .valor-tape{animation:valor-tape 40s linear infinite}.valor-draw{animation:valor-draw 1.4s ease-out both}
        .valor-fade{animation:valor-fade 1.4s ease both}.valor-pulse{animation:valor-pulse 1.2s ease-out infinite}
      `}</style>
      <main className={`min-h-screen bg-[#0a0e1a] text-gray-100 pt-16 transition-all duration-300 ${sidebarPadding}`}>
        {/* Ticker tape */}
        <div className="h-10 border-b border-[#1c2233] bg-[#080b14] overflow-hidden flex items-center">
          <div className="valor-tape flex w-max">
            {[0, 1, 2, 3].map(k => (
              <div key={k} className="flex gap-10 pr-10">
                {activeTickers.map(t => {
                  const p = latest[t]?.underlying_price, o = firstPrice(t), ch = p && o ? (p - o) / o * 100 : 0
                  return (
                    <span key={t} className="flex gap-2.5 text-[13px] whitespace-nowrap">
                      <span className="font-semibold">{t}</span>
                      <span className="font-mono">{p ? Number(p).toFixed(meta(t).d) : '—'}</span>
                      <span className="font-mono" style={{ color: pnlColor(ch) }}>{p && o ? pct(ch) : ''}</span>
                    </span>
                  )
                })}
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)]">
          {/* Rail */}
          <aside className="border-r border-[#1c2233] bg-[#0c1019] px-3.5 py-6 flex flex-col gap-7">
            <div className="px-2 flex flex-col gap-1.5">
              <div className="text-[22px] font-bold tracking-[.08em]">VALOR</div>
              <div className="flex items-center gap-2 text-[13px]" style={{ color: status.market_open ? G : '#6b7280' }}>
                <Dot color={status.market_open ? G : '#6b7280'} size={7} />
                {status.market_open ? `Market open${nextScan !== null ? ` · next scan ${nextScan}s` : ''}` : 'Market closed'}
              </div>
            </div>
            <nav className="flex lg:flex-col gap-0.5 overflow-x-auto">
              {TABS.map(t => (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={`text-left px-3 py-2.5 rounded-lg text-sm font-medium whitespace-nowrap ${tab === t.id ? 'text-yellow-500 bg-yellow-500/10' : 'text-gray-400 hover:text-gray-100'}`}>
                  {t.label}
                </button>
              ))}
            </nav>
            <div className="flex flex-col gap-1">
              <div className="text-xs tracking-[.1em] uppercase text-gray-500 px-3 pb-1.5">Instruments</div>
              {activeTickers.map(t => {
                const m = meta(t), p = latest[t]?.underlying_price, o = firstPrice(t), ch = p && o ? (p - o) / o * 100 : 0, on = t === sel
                return (
                  <button key={t} onClick={() => { setSel(t); setTab('portfolio') }}
                    className={`flex flex-col gap-0.5 px-3 py-2 rounded-lg text-left border-l-2 hover:bg-[#1a1f2e] ${on ? 'bg-[#1a1f2e]' : ''}`}
                    style={{ borderColor: on ? m.color : 'transparent' }}>
                    <span className="flex justify-between items-center">
                      <span className="flex items-center gap-2 text-sm font-semibold"><Dot color={m.color} />{t}</span>
                      <span className="font-mono text-[13px]">{p ? Number(p).toFixed(m.d) : '—'}</span>
                    </span>
                    <span className="flex justify-between text-xs">
                      <span className="text-gray-500">{m.label}</span>
                      <span className="font-mono" style={{ color: pnlColor(ch) }}>{p && o ? pct(ch) : ''}</span>
                    </span>
                  </button>
                )
              })}
            </div>
            <div className="text-xs text-yellow-500 border border-yellow-500/35 rounded-lg px-3 py-2.5 leading-relaxed">Paper trading mode. Simulated trades, not verified returns.</div>
          </aside>

          {/* Main */}
          <section className="px-4 md:px-8 pt-7 pb-10 flex flex-col gap-6 min-w-0">
            <div className="flex items-baseline gap-3">
              <h1 className="text-xl font-semibold">{tabMeta.label}</h1>
              <span className="text-sm text-gray-500">{tabMeta.desc}</span>
            </div>

            {tab === 'portfolio' && (
              <div className="flex flex-col gap-6">
                <div className="flex flex-wrap justify-between items-end gap-6">
                  <div className="flex flex-col gap-2">
                    <span className="text-sm text-gray-400">Account equity · live</span>
                    <span className="font-mono text-5xl md:text-[56px] font-semibold tracking-tight leading-none">{money(equity)}</span>
                    <span className="flex flex-wrap gap-4 font-mono text-[15px]">
                      <span className="font-semibold" style={{ color: pnlColor(realized) }}>{money(realized, true)} realized</span>
                      <span style={{ color: pnlColor(unrealized) }}>{money(unrealized, true)} open</span>
                      <span className="text-gray-500">from {money(startingCapital)}</span>
                    </span>
                  </div>
                  <div className="flex gap-7">
                    {[['Win rate', `${(performance.win_rate || 0).toFixed(1)}%`, (performance.win_rate || 0) >= 50 ? G : R], ['Trades', performance.total_trades || 0, '#f3f4f6'], ['Return', pct(paper.return_pct || 0), pnlColor(paper.return_pct || 0)]].map(([l, v, c]) => (
                      <div key={l as string} className="flex flex-col gap-1 items-end"><span className="text-xs text-gray-500">{l}</span><span className="font-mono text-lg font-semibold" style={{ color: c as string }}>{v}</span></div>
                    ))}
                  </div>
                </div>

                <Card className="overflow-hidden">
                  <div className="flex flex-wrap justify-between items-center gap-3 px-5 py-4 border-b border-[#1c2233]">
                    <div className="flex items-baseline gap-3.5">
                      <span className="flex items-center gap-2 text-base font-semibold"><Dot color={meta(sel).color} size={9} />{sel}</span>
                      <span className="text-[13px] text-gray-400">{meta(sel).label} · 5m</span>
                      <span className="font-mono text-[22px] font-semibold">{selPrice ? Number(selPrice).toFixed(meta(sel).d) : '—'}</span>
                    </div>
                    <div className="flex flex-wrap gap-3.5 text-xs font-semibold tracking-wide">
                      <span className="text-blue-500">— Call wall</span>
                      <span className="text-amber-500">- - Gamma flip</span>
                      <span className="text-violet-500">— Put wall</span>
                      {selScan.gamma_regime && <span style={{ color: selScan.gamma_regime === 'POSITIVE' ? G : '#a855f7' }}>{selScan.gamma_regime} GAMMA</span>}
                    </div>
                  </div>
                  <div className="pl-4 pr-3 pt-3 pb-2">
                    <CandleChart bars={selBars} levels={levels} price={selPrice} d={meta(sel).d} gex={gexProfileData} />
                  </div>
                  <div className="flex flex-wrap items-center gap-x-6 gap-y-1 px-5 py-3 border-t border-[#1c2233] text-[13px]">
                    <span className="text-gray-400">Net GEX{gexProfileData?.available && gexProfileData?.expiration_date ? ` (${gexProfileData.is_0dte ? '0DTE' : 'nearest'} ${gexProfileData.expiration_date})` : ''}</span>
                    <span className="font-mono" style={{ color: pnlColor(selScan.net_gex || 0) }}>{selScan.net_gex != null ? Number(selScan.net_gex).toExponential(2) : '—'}</span>
                    <span className="text-[12px] text-gray-500">Last scan: {selScan.decision_summary || selScan.skip_reason || '—'}</span>
                  </div>
                </Card>

                <div className="grid gap-5 grid-cols-[repeat(auto-fit,minmax(340px,1fr))]">
                  <Card className="px-5 py-4 flex flex-col gap-3.5">
                    <div className="flex justify-between items-center"><span className="text-base font-semibold">Equity curve</span>
                      <Pills items={TIMEFRAMES.map(t => ({ id: t.id, label: t.label }))} value={tf} onChange={setTf} /></div>
                    <div className="h-[180px]"><EquityChart points={eqPoints} start={startingCapital} animKey={tf} /></div>
                  </Card>
                  <Card className="flex flex-col">
                    <div className="px-5 py-4 text-base font-semibold flex justify-between"><span>Open positions ({positions.length})</span><span className="text-xs text-gray-500 font-normal">live</span></div>
                    {positions.length === 0 && <div className="px-5 py-5 border-t border-[#1c2233] text-sm text-gray-500">No open positions. VALOR will open positions when GEX signals meet criteria.</div>}
                    {positions.map(p => (
                      <div key={p.position_id} className="flex justify-between items-center px-5 py-3.5 border-t border-[#1c2233]">
                        <div className="flex flex-col gap-1">
                          <span className="flex items-center gap-2 font-semibold text-sm"><Dot color={meta(p.ticker).color} />{p.ticker || 'MES'}
                            <span className="text-xs" style={{ color: p.direction === 'LONG' ? G : R }}>{p.direction} × {p.contracts}</span>
                            <span className="text-[11px] text-gray-500 font-medium">{p.gamma_regime} GAMMA</span></span>
                          <span className="text-xs text-gray-500 font-mono">{p.entry_price?.toFixed(2)} → {p.current_price?.toFixed(2) ?? '—'}</span>
                        </div>
                        <span className="font-mono text-base font-semibold" style={{ color: pnlColor(p.unrealized_pnl || 0) }}>{money(p.unrealized_pnl || 0, true)}</span>
                      </div>
                    ))}
                  </Card>
                </div>

                <Card className="overflow-hidden">
                  <div className="flex flex-wrap justify-between items-center gap-3 px-5 py-4 border-b border-[#1c2233]">
                    <span className="text-base font-semibold">Per-instrument performance</span>
                    {marginZones?.combined && <span className="text-xs px-2.5 py-1 rounded-full" style={{ color: zoneColor(marginZones.combined.utilization_pct), background: 'rgba(255,255,255,.04)' }}>Portfolio margin {marginZones.combined.utilization_pct}% · {marginZones.combined.zone}</span>}
                  </div>
                  <div className="overflow-x-auto"><div className="min-w-[760px]">
                    <div className="grid grid-cols-[minmax(200px,1.4fr)_90px_100px_130px_minmax(180px,1fr)] gap-4 px-5 py-2.5 text-xs text-gray-500 uppercase tracking-wider">
                      <span>Instrument</span><span className="text-right">Trades</span><span className="text-right">Win rate</span><span className="text-right">P&amp;L</span><span>Margin used</span></div>
                    {activeTickers.map(t => {
                      const s = tickerStats[t] || {}, m = meta(t), util = marginZones?.instruments?.[t]?.utilization_pct || 0
                      return (
                        <button key={t} onClick={() => setSel(t)} className={`w-full grid grid-cols-[minmax(200px,1.4fr)_90px_100px_130px_minmax(180px,1fr)] gap-4 px-5 py-3 border-t border-[#1c2233] text-sm items-center text-left hover:bg-[#1a1f2e] ${t === sel ? 'bg-[#1a1f2e]' : ''}`}>
                          <span className="flex items-center gap-2.5"><Dot color={m.color} /><span className="font-semibold">{t}</span><span className="text-gray-400">{m.label}</span>{t === 'CL' && <span className="text-xs text-amber-500">Entries quarantined</span>}</span>
                          <span className="font-mono text-right text-gray-300">{s.total_trades ?? 0}</span>
                          <span className="font-mono text-right" style={{ color: (s.win_rate || 0) >= 50 ? G : R }}>{s.total_trades ? `${s.win_rate.toFixed(1)}%` : '—'}</span>
                          <span className="font-mono text-right font-semibold" style={{ color: pnlColor(s.total_pnl || 0) }}>{s.total_trades ? money(s.total_pnl, true) : '—'}</span>
                          <span className="grid grid-cols-[1fr_48px] gap-2.5 items-center">
                            <span className="h-1.5 bg-[#1c2233] rounded-full overflow-hidden"><span className="block h-full" style={{ width: `${Math.min(util, 100)}%`, background: zoneColor(util) }} /></span>
                            <span className="font-mono text-xs text-right" style={{ color: zoneColor(util) }}>{util.toFixed(1)}%</span>
                          </span>
                        </button>
                      )
                    })}
                  </div></div>
                </Card>

                <div className="text-[13px] text-gray-400 leading-relaxed flex flex-col gap-1 max-w-[900px]">
                  <span>VALOR uses simulated futures trades. Raw balances include historical trades flagged for data quality and are not verified strategy returns. CL new entries are quarantined by default.</span>
                  <span className="text-gray-500">24/5 trading: Sun 5pm - Fri 4pm CT with 4-5pm daily maintenance break.</span>
                  <a className="text-yellow-500 hover:text-yellow-400" href={`${process.env.NEXT_PUBLIC_API_URL || ''}/api/valor/performance/quality`} target="_blank" rel="noopener noreferrer">View screened performance and excluded-trade counts (JSON)</a>
                </div>
              </div>
            )}

            {tab === 'overview' && (
              <div className="flex flex-col gap-5">
                {lossStreak?.is_paused && (
                  <div className="flex items-center gap-3 border border-red-500/50 bg-red-900/30 rounded-xl px-4 py-3 text-sm">
                    <Dot color={R} size={9} /><span className="text-red-400 font-semibold">PAUSED - Loss Streak Protection Active</span>
                    <span className="text-gray-300">{lossStreak.consecutive_losses} consecutive losses detected. New entries paused for {lossStreak.pause_minutes} minutes.</span>
                  </div>
                )}
                {!lossStreak?.is_paused && lossStreak?.consecutive_losses > 0 && (
                  <div className="flex items-center gap-3 border border-orange-500/45 bg-orange-500/10 rounded-xl px-4 py-3 text-sm">
                    <Dot color="#f97316" size={9} /><span className="text-orange-300 font-semibold">Loss Streak: {lossStreak.consecutive_losses}</span>
                    <span className="text-gray-400">({lossStreak.max_consecutive_losses - lossStreak.consecutive_losses} more before {lossStreak.pause_minutes}min pause)</span>
                  </div>
                )}
                {mlStatus?.model_trained && (
                  <div className={`flex flex-wrap justify-between items-center gap-4 rounded-xl px-5 py-4 border ${mlApproved ? 'border-emerald-500/45 bg-emerald-500/5' : 'border-yellow-500/45 bg-yellow-500/5'}`}>
                    <div className="flex items-center gap-3"><Dot color={mlApproved ? G : '#eab308'} size={10} />
                      <div className="flex flex-col gap-0.5">
                        <span className="font-semibold" style={{ color: mlApproved ? G : '#eab308' }}>{mlApproved ? 'ML Model ACTIVE - Using ML Predictions' : 'ML Model Trained - Awaiting Approval'}</span>
                        <span className="text-sm text-gray-300">{mlApproved ? `Win probability calculated via XGBoost ML (${accuracy}% accuracy)` : `Currently using Bayesian fallback. Approve to use ML (${accuracy}% accuracy)`}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2.5">
                      <span className="text-[13px] font-semibold px-3 py-1 rounded-full bg-[#1c2233] text-gray-300">Source: {mlApproval?.probability_source || 'BAYESIAN'}</span>
                      {mlApproved
                        ? <button disabled={!!busy} onClick={() => run('revoke', revokeValorML, [refreshApproval, refreshMLStatus])} className="text-sm font-semibold px-3.5 py-2 rounded-lg text-red-300 border border-red-500/40 disabled:opacity-50">{busy === 'revoke' ? 'Revoking…' : 'Revoke ML'}</button>
                        : <button disabled={!!busy} onClick={() => run('approve', approveValorML, [refreshApproval, refreshMLStatus])} className="text-sm font-semibold px-3.5 py-2 rounded-lg bg-emerald-500 text-[#0a0e1a] disabled:opacity-50">{busy === 'approve' ? 'Approving…' : 'Approve ML'}</button>}
                    </div>
                  </div>
                )}
                <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(180px,1fr))]">
                  <Stat label="Total P&L" value={money(performance.total_pnl || 0, true)} color={pnlColor(performance.total_pnl || 0)} />
                  <Stat label="Win Rate" value={`${(performance.win_rate || 0).toFixed(1)}%`} color={(performance.win_rate || 0) >= 50 ? G : R} />
                  <Stat label="Total Trades" value={performance.total_trades || 0} />
                  <Stat label="Open Positions" value={positions.length} />
                </div>
                <Card className="px-5 py-4 flex flex-col gap-4">
                  <span className="text-base font-semibold">Win probability</span>
                  <div className="grid gap-5 grid-cols-[repeat(auto-fit,minmax(220px,1fr))]">
                    {[
                      ['Overall Win Probability', (winTracker.win_probability || 0.5) * 100, '#eab308', `Based on ${winTracker.total_trades || 0} trades`],
                      ['Positive Gamma (Mean Reversion)', rate(winTracker.positive_gamma_wins, winTracker.positive_gamma_losses), G, `W: ${winTracker.positive_gamma_wins || 0}  L: ${winTracker.positive_gamma_losses || 0}`],
                      ['Negative Gamma (Momentum)', rate(winTracker.negative_gamma_wins, winTracker.negative_gamma_losses), '#a855f7', `W: ${winTracker.negative_gamma_wins || 0}  L: ${winTracker.negative_gamma_losses || 0}`],
                    ].map(([l, v, c, sub]) => (
                      <div key={l as string} className="flex flex-col gap-2">
                        <div className="flex justify-between text-sm"><span className="text-gray-400">{l}</span><span className="font-mono font-semibold" style={{ color: c as string }}>{(v as number).toFixed(1)}%</span></div>
                        <div className="h-1.5 bg-[#1c2233] rounded-full overflow-hidden"><div className="h-full" style={{ width: `${v}%`, background: c as string }} /></div>
                        <span className="text-xs text-gray-500">{sub}</span>
                      </div>
                    ))}
                  </div>
                </Card>
                <Card className="px-5 py-4 flex flex-col gap-4">
                  <div className="flex flex-wrap justify-between items-center gap-3">
                    <span className="text-base font-semibold">ML training</span>
                    <div className="flex gap-2">
                      <button disabled={!!busy} onClick={() => run('train', () => trainValorML(50), [refreshMLStatus, refreshApproval, refreshTrainingStats])} className="text-[13px] font-semibold px-3.5 py-1.5 rounded-lg bg-yellow-500 text-[#0a0e1a] disabled:opacity-50">{busy === 'train' ? 'Training…' : 'Train model'}</button>
                      <button disabled={!!busy} onClick={() => run('reject', rejectValorML, [refreshApproval, refreshMLStatus])} className="text-[13px] font-semibold px-3.5 py-1.5 rounded-lg border border-[#2a3245] text-gray-300 hover:bg-[#1a1f2e] disabled:opacity-50">{busy === 'reject' ? 'Rejecting…' : 'Reject model'}</button>
                    </div>
                  </div>
                  <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(160px,1fr))]">
                    {[
                      ['New Param Trades', mlStats?.new_parameter_trades?.count || 0, '#f3f4f6'],
                      ['Win/Loss (New)', `${mlStats?.new_parameter_trades?.wins || 0} / ${mlStats?.new_parameter_trades?.losses || 0}`, '#f3f4f6'],
                      ['New Win Rate', `${(mlStats?.new_parameter_trades?.win_rate || 0).toFixed(1)}%`, G],
                      ['Ready for Training', mlStats?.ready_for_ml_training ? 'Yes' : `${mlStats?.trades_needed_for_ml || 50} more`, mlStats?.ready_for_ml_training ? G : '#eab308'],
                    ].map(([l, v, c]) => (
                      <div key={l as string} className="border border-[#1c2233] rounded-lg px-4 py-3.5 flex flex-col gap-1.5"><span className="text-[13px] text-gray-400">{l}</span><span className="font-mono text-xl font-semibold" style={{ color: c as string }}>{v}</span></div>
                    ))}
                  </div>
                  <div className="flex flex-wrap justify-between items-center gap-3 border-t border-[#1c2233] pt-3.5">
                    <div className="flex flex-col gap-0.5"><span className="text-sm font-semibold">A/B test</span><span className="text-[13px] text-gray-400">Split new entries between ML and Bayesian probability</span></div>
                    <button disabled={!!busy} aria-pressed={!!abStatus?.ab_test_enabled}
                      onClick={() => run('ab', abStatus?.ab_test_enabled ? disableValorABTest : enableValorABTest, [refreshAB])}
                      className={`relative w-11 h-6 rounded-full transition-colors disabled:opacity-50 ${abStatus?.ab_test_enabled ? 'bg-yellow-500' : 'bg-[#2a3245]'}`}>
                      <span className={`absolute top-[3px] w-[18px] h-[18px] rounded-full bg-gray-100 transition-all ${abStatus?.ab_test_enabled ? 'left-[23px]' : 'left-[3px]'}`} />
                    </button>
                  </div>
                </Card>
              </div>
            )}

            {tab === 'activity' && (
              <div className="flex flex-col gap-5">
                <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(150px,1fr))]">
                  <Stat label="Total Scans" value={(scanSummary.total ?? scans.length).toLocaleString()} />
                  <Stat label="Traded" value={scanSummary.traded ?? 0} color={G} />
                  <Stat label="No Trade" value={scanSummary.no_trade ?? 0} />
                  <Stat label="Skipped" value={scanSummary.skipped ?? 0} color="#f59e0b" />
                  <Stat label="Trade Rate" value={`${(scanSummary.trade_rate ?? 0).toFixed?.(1) ?? scanSummary.trade_rate}%`} />
                </div>
                <Card className="overflow-hidden">
                  <div className="px-5 py-4 text-base font-semibold border-b border-[#1c2233]">Recent scans</div>
                  <div className="overflow-x-auto"><div className="min-w-[860px]">
                    <div className="grid grid-cols-[100px_80px_120px_110px_100px_minmax(240px,1fr)] gap-4 px-5 py-2.5 text-xs text-gray-500 uppercase tracking-wider"><span>Time</span><span>Ticker</span><span>Outcome</span><span>Regime</span><span className="text-right">Price</span><span>Reason</span></div>
                    {scans.slice(0, 100).map(s => (
                      <div key={s.scan_id} className="grid grid-cols-[100px_80px_120px_110px_100px_minmax(240px,1fr)] gap-4 px-5 py-2.5 border-t border-[#1c2233] text-sm items-center">
                        <span className="font-mono text-[13px] text-gray-400">{new Date(s.scan_time).toLocaleTimeString()}</span>
                        <span className="flex items-center gap-2 font-semibold"><Dot color={meta(s.ticker).color} size={7} />{s.ticker || 'MES'}</span>
                        <span><span className={`text-[11px] font-bold tracking-wide px-2 py-0.5 rounded-md ${s.outcome === 'TRADED' ? 'bg-emerald-500/15 text-emerald-400' : s.outcome === 'SKIP' ? 'bg-amber-500/15 text-amber-400' : s.outcome === 'ERROR' ? 'bg-red-500/15 text-red-400' : 'bg-[#1c2233] text-gray-400'}`}>{String(s.outcome || '').replace('_', ' ')}</span></span>
                        <span className="text-xs text-gray-400">{s.gamma_regime ? `${s.gamma_regime} GAMMA` : '—'}</span>
                        <span className="font-mono text-right">{s.underlying_price?.toFixed(meta(s.ticker).d) || '—'}</span>
                        <span className="text-gray-300 truncate" title={s.decision_summary}>{s.decision_summary || s.skip_reason || '—'}</span>
                      </div>
                    ))}
                  </div></div>
                </Card>
              </div>
            )}

            {tab === 'history' && (
              <div className="flex flex-col gap-5">
                <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(140px,1fr))]">
                  <Stat label="Total Trades" value={histTrades.length} />
                  <Stat label="Win Rate" value={histTrades.length ? `${(wins.length / histTrades.length * 100).toFixed(1)}%` : '—'} color={wins.length / (histTrades.length || 1) >= 0.5 ? G : R} />
                  <Stat label="Total P&L" value={money(histTotal, true)} color={pnlColor(histTotal)} />
                  <Stat label="Avg Win" value={money(avg(wins), true)} color={G} />
                  <Stat label="Avg Loss" value={money(avg(losses), true)} color={R} />
                  <Stat label="W/L" value={`${wins.length} / ${losses.length}`} />
                </div>
                <Card className="overflow-hidden">
                  <div className="flex flex-wrap justify-between items-center gap-3 px-5 py-3.5 border-b border-[#1c2233]">
                    <span className="text-base font-semibold">Closed trades</span>
                    <Pills items={['ALL', ...activeTickers].map(t => ({ id: t, label: t }))} value={histFilter} onChange={setHistFilter} />
                  </div>
                  <div className="overflow-x-auto"><div className="min-w-[960px]">
                    <div className="grid grid-cols-[150px_70px_80px_100px_1fr_1fr_110px_140px] gap-3 px-5 py-2.5 text-xs text-gray-500 uppercase tracking-wider"><span>Time</span><span>Ticker</span><span>Direction</span><span>Regime</span><span className="text-right">Entry</span><span className="text-right">Exit</span><span className="text-right">P&amp;L</span><span>Reason</span></div>
                    {histTrades.length === 0 && <div className="px-5 py-5 border-t border-[#1c2233] text-sm text-gray-500">No closed trades yet.</div>}
                    {histTrades.slice(0, 200).map(t => (
                      <div key={t.position_id} className="grid grid-cols-[150px_70px_80px_100px_1fr_1fr_110px_140px] gap-3 px-5 py-2.5 border-t border-[#1c2233] text-sm items-center">
                        <span className="font-mono text-[13px] text-gray-400">{new Date(t.close_time).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                        <span className="flex items-center gap-2 font-semibold"><Dot color={meta(t.ticker).color} size={7} />{t.ticker || 'MES'}</span>
                        <span className="text-[13px] font-semibold" style={{ color: t.direction === 'LONG' ? G : R }}>{t.direction}</span>
                        <span className="text-xs text-gray-400">{t.gamma_regime}</span>
                        <span className="font-mono text-right">{t.entry_price?.toFixed(meta(t.ticker).d)}</span>
                        <span className="font-mono text-right">{t.exit_price?.toFixed(meta(t.ticker).d)}</span>
                        <span className="font-mono text-right font-semibold" style={{ color: pnlColor(t.realized_pnl) }}>{money(t.realized_pnl || 0, true)}</span>
                        <span className="text-[13px] text-gray-400">{t.close_reason}</span>
                      </div>
                    ))}
                  </div></div>
                </Card>
              </div>
            )}

            {tab === 'config' && (
              <div className="flex flex-col gap-5">
                <Card className="px-5 py-4 flex flex-col gap-4">
                  <span className="text-base font-semibold">Strategy settings</span>
                  <div className="grid gap-px bg-[#1c2233] border border-[#1c2233] rounded-lg overflow-hidden grid-cols-[repeat(auto-fit,minmax(200px,1fr))]">
                    {[
                      ['Instruments', activeTickers.join(', ')],
                      ['Capital / Instrument', '$100,000'],
                      ['Risk/Trade', `${config.risk_per_trade_pct || 1}%`],
                      ['Max Contracts', config.max_contracts || 5],
                      ['Initial Stop', `${config.initial_stop_points || 3} pts`],
                      ['Breakeven At', `+${config.breakeven_activation_points || 2} pts`],
                      ['Trail Distance', `${config.trailing_stop_points || 1} pt`],
                      ['Max Positions', config.max_open_positions || 2],
                    ].map(([l, v]) => (
                      <div key={l as string} className="bg-[#11151f] px-4 py-3.5 flex flex-col gap-1.5"><span className="text-[13px] text-gray-400">{l}</span><span className="font-mono text-base font-semibold">{v}</span></div>
                    ))}
                  </div>
                </Card>
                <Card className="overflow-hidden">
                  <div className="px-5 py-4 text-base font-semibold border-b border-[#1c2233]">Contract specifications</div>
                  <div className="overflow-x-auto"><div className="min-w-[720px]">
                    <div className="grid grid-cols-[minmax(180px,1.3fr)_1fr_1fr_1fr_1fr] gap-3 px-5 py-2.5 text-xs text-gray-500 uppercase tracking-wider"><span>Instrument</span><span>Point value</span><span>Tick size</span><span>Tick value</span><span>Day margin</span></div>
                    {TICKERS.map(t => (
                      <div key={t} className="grid grid-cols-[minmax(180px,1.3fr)_1fr_1fr_1fr_1fr] gap-3 px-5 py-3 border-t border-[#1c2233] text-sm items-center">
                        <span className="flex items-center gap-2.5"><Dot color={meta(t).color} /><span className="font-semibold">{t}</span><span className="text-gray-400">{meta(t).label}</span></span>
                        {SPECS[t].map((v, i) => <span key={i} className="font-mono">{v}</span>)}
                      </div>
                    ))}
                  </div></div>
                </Card>
                <div className="text-[13px] text-gray-400">24/5 trading: Sun 5pm - Fri 4pm CT with 4-5pm daily maintenance break.</div>
              </div>
            )}
          </section>
        </div>
      </main>
    </>
  )
}

function rate(w?: number, l?: number) {
  const t = (w || 0) + (l || 0)
  return t ? ((w || 0) / t) * 100 : 0
}
