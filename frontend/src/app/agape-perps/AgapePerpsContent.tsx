'use client'

// AGAPE Perpetuals — one consolidated page for all six AGAPE perp bots.
// Route: /agape-perps?coin=btc|eth|sol|avax|xrp|doge
// Replaces the six near-identical /agape-{coin}-perp pages.

import { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import { LoadingState } from '@/components/trader'
import { useAgapePerpTrades, type RangePreset } from '@/lib/hooks/useAgapePerpTrades'
import {
  useAGAPEBtcPerpStatus, useAGAPEBtcPerpPerformance, useAGAPEBtcPerpPositions, useAGAPEBtcPerpScanActivity, useAGAPEBtcPerpSnapshot, useAGAPEBtcPerpGexMapping,
  useAGAPEEthPerpStatus, useAGAPEEthPerpPerformance, useAGAPEEthPerpPositions, useAGAPEEthPerpScanActivity, useAGAPEEthPerpSnapshot, useAGAPEEthPerpGexMapping,
  useAGAPESolPerpStatus, useAGAPESolPerpPerformance, useAGAPESolPerpPositions, useAGAPESolPerpScanActivity, useAGAPESolPerpSnapshot, useAGAPESolPerpGexMapping,
  useAGAPEAvaxPerpStatus, useAGAPEAvaxPerpPerformance, useAGAPEAvaxPerpPositions, useAGAPEAvaxPerpScanActivity, useAGAPEAvaxPerpSnapshot, useAGAPEAvaxPerpGexMapping,
  useAGAPEXrpPerpStatus, useAGAPEXrpPerpPerformance, useAGAPEXrpPerpPositions, useAGAPEXrpPerpScanActivity, useAGAPEXrpPerpSnapshot, useAGAPEXrpPerpGexMapping,
  useAGAPEDogePerpStatus, useAGAPEDogePerpPerformance, useAGAPEDogePerpPositions, useAGAPEDogePerpScanActivity, useAGAPEDogePerpSnapshot, useAGAPEDogePerpGexMapping,
} from '@/lib/hooks/useMarketData'

const G = '#10b981'
const R = '#ef4444'
const REFRESH_MS = 15000

type Coin = 'btc' | 'eth' | 'sol' | 'avax' | 'xrp' | 'doge'
const COINS: Coin[] = ['btc', 'eth', 'sol', 'avax', 'xrp', 'doge']
const META: Record<Coin, { sym: string; color: string; d: number }> = {
  btc: { sym: 'BTC', color: '#F7931A', d: 2 },
  eth: { sym: 'ETH', color: '#627EEA', d: 2 },
  sol: { sym: 'SOL', color: '#9945FF', d: 2 },
  avax: { sym: 'AVAX', color: '#E84142', d: 3 },
  xrp: { sym: 'XRP', color: '#94A3B8', d: 4 },
  doge: { sym: 'DOGE', color: '#C2A633', d: 5 },
}

const TABS = [
  { id: 'portfolio', label: 'Portfolio', desc: 'Live P&L and positions' },
  { id: 'overview', label: 'Overview', desc: 'Bot status and metrics' },
  { id: 'market', label: 'Market', desc: 'Crypto microstructure' },
  { id: 'activity', label: 'Activity', desc: 'Scans and decisions' },
  { id: 'history', label: 'History', desc: 'Closed trades' },
  { id: 'config', label: 'Config', desc: 'Settings and GEX mapping' },
] as const
type TabId = typeof TABS[number]['id']

const RANGES: { id: RangePreset; label: string }[] = [
  { id: '7d', label: '7D' }, { id: '30d', label: '30D' }, { id: '90d', label: '90D' }, { id: 'all', label: 'All' },
]

// ------------------------------------------------------------------ helpers

const money = (n: number, sign = false) =>
  (sign ? (n >= 0 ? '+' : '−') : n < 0 ? '−' : '') +
  '$' + Math.abs(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const px = (v: number | undefined | null, d: number) =>
  v == null || isNaN(Number(v)) ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })
const pnlColor = (n: number) => (n > 0 ? G : n < 0 ? R : '#9ca3af')
const sigColor = (s?: string) =>
  !s ? '#9ca3af' : /LONG|BULL/.test(s) ? G : /SHORT|BEAR/.test(s) ? R : s === 'RANGE_BOUND' ? '#eab308' : '#9ca3af'
const riskColor = (r?: string) => (r === 'HIGH' ? R : r === 'ELEVATED' ? '#f97316' : G)
const priceOf = (coin: Coin, obj: any) => obj?.[`current_${coin}_price`] ?? obj?.[`${coin}_price`] ?? obj?.current_price ?? obj?.spot_price

// One hook bundle per coin. Hooks are called in a fixed order every render.
function useBot(coin: Coin, opts: { snapshot: boolean; mapping: boolean }) {
  const H = {
    btc: [useAGAPEBtcPerpStatus, useAGAPEBtcPerpPerformance, useAGAPEBtcPerpPositions, useAGAPEBtcPerpScanActivity, useAGAPEBtcPerpSnapshot, useAGAPEBtcPerpGexMapping],
    eth: [useAGAPEEthPerpStatus, useAGAPEEthPerpPerformance, useAGAPEEthPerpPositions, useAGAPEEthPerpScanActivity, useAGAPEEthPerpSnapshot, useAGAPEEthPerpGexMapping],
    sol: [useAGAPESolPerpStatus, useAGAPESolPerpPerformance, useAGAPESolPerpPositions, useAGAPESolPerpScanActivity, useAGAPESolPerpSnapshot, useAGAPESolPerpGexMapping],
    avax: [useAGAPEAvaxPerpStatus, useAGAPEAvaxPerpPerformance, useAGAPEAvaxPerpPositions, useAGAPEAvaxPerpScanActivity, useAGAPEAvaxPerpSnapshot, useAGAPEAvaxPerpGexMapping],
    xrp: [useAGAPEXrpPerpStatus, useAGAPEXrpPerpPerformance, useAGAPEXrpPerpPositions, useAGAPEXrpPerpScanActivity, useAGAPEXrpPerpSnapshot, useAGAPEXrpPerpGexMapping],
    doge: [useAGAPEDogePerpStatus, useAGAPEDogePerpPerformance, useAGAPEDogePerpPositions, useAGAPEDogePerpScanActivity, useAGAPEDogePerpSnapshot, useAGAPEDogePerpGexMapping],
  }[coin] as any[]
  const [useStatus, usePerf, usePositions, useScans, useSnapshot, useMapping] = H
  const status = useStatus({ refreshInterval: REFRESH_MS })
  const perf = usePerf()
  const positions = usePositions({ refreshInterval: REFRESH_MS })
  const scans = useScans(60, { enabled: true, refreshInterval: REFRESH_MS })
  const snapshot = useSnapshot({ enabled: opts.snapshot, refreshInterval: REFRESH_MS })
  const mapping = useMapping({ enabled: opts.mapping })
  return {
    coin,
    status: status.data?.data,
    loading: status.isLoading && !status.data,
    perf: perf.data?.data,
    positions: (positions.data?.data || []) as any[],
    scans: (scans.data?.data || []) as any[],
    snapshot: snapshot.data?.data,
    mapping: mapping.data?.data,
    refresh: () => { status.mutate?.(); positions.mutate?.(); scans.mutate?.(); snapshot.mutate?.() },
  }
}

// ------------------------------------------------------------------ UI bits

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={`bg-[#11151f] border border-[#1c2233] rounded-xl ${className}`}>{children}</div>
}
function Stat({ label, value, color, big = true }: { label: string; value: React.ReactNode; color?: string; big?: boolean }) {
  return (
    <Card className="p-4 flex flex-col gap-1.5">
      <span className="text-[13px] text-gray-400">{label}</span>
      <span className={`font-mono font-semibold ${big ? 'text-[22px]' : 'text-base'}`} style={{ color: color || '#f3f4f6' }}>{value}</span>
    </Card>
  )
}
const Dot = ({ color, size = 8 }: { color: string; size?: number }) =>
  <span className="inline-block rounded-full shrink-0" style={{ width: size, height: size, background: color }} />
function Pills<T extends string>({ items, value, onChange }: { items: { id: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex gap-1 flex-wrap">
      {items.map(i => (
        <button key={i.id} onClick={() => onChange(i.id)}
          className={`px-2.5 py-1 rounded-md text-xs font-semibold ${value === i.id ? 'bg-yellow-500 text-[#0a0e1a]' : 'bg-[#1c2233] text-gray-400 hover:text-gray-200'}`}>{i.label}</button>
      ))}
    </div>
  )
}
const Row = ({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) => (
  <div className="flex justify-between text-sm"><span className="text-gray-400">{label}</span><span className="font-mono" style={{ color: color || '#f3f4f6' }}>{value}</span></div>
)

// ------------------------------------------------------------------ charts

type Bar = { o: number; h: number; l: number; c: number }

// 5-minute bars from the bot's own scan prices (one scan per 5 min).
function barsFromScans(coin: Coin, scans: any[], max = 48): Bar[] {
  const pts = [...scans]
    .filter(s => priceOf(coin, s))
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    .map(s => Number(priceOf(coin, s)))
  const bars: Bar[] = []
  for (let i = 1; i < pts.length; i++) bars.push({ o: pts[i - 1], c: pts[i], h: Math.max(pts[i - 1], pts[i]), l: Math.min(pts[i - 1], pts[i]) })
  return bars.slice(-max)
}

function CandleChart({ bars, sl, ll, flip, price, d }: { bars: Bar[]; sl?: number; ll?: number; flip?: number; price?: number; d: number }) {
  if (bars.length < 2) return <div className="h-[300px] flex items-center justify-center text-sm text-gray-500">Waiting for scan prices to build bars…</div>
  const W = 700, H = 360, R0 = 78
  const lv = [sl, ll, flip].filter((v): v is number => !!v)
  let lo = Math.min(...bars.map(b => b.l), ...lv), hi = Math.max(...bars.map(b => b.h), ...lv)
  const pad = (hi - lo) * 0.07 || Math.abs(hi) * 0.001; lo -= pad; hi += pad
  const y = (v: number) => ((hi - v) / (hi - lo)) * H
  const cw = (W - R0) / bars.length
  const lines: [string, number | undefined, string, string | undefined][] = [
    ['SHORT LIQ CLUSTER', sl, '#3b82f6', undefined], ['GEX FLIP', flip, '#f59e0b', '6 4'], ['LONG LIQ CLUSTER', ll, '#8b5cf6', undefined],
  ]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block">
      {[0, 1, 2, 3, 4].map(i => { const v = lo + (hi - lo) * (i + 0.5) / 5; return (
        <g key={i}><line x1={0} x2={W - R0} y1={y(v)} y2={y(v)} stroke="#1c2233" /><text x={W - R0 + 8} y={y(v) + 4} fill="#6b7280" fontSize={11} className="font-mono">{px(v, d)}</text></g>
      ) })}
      {lines.map(([l, v, col, dash]) => v ? (
        <g key={l}>
          {!dash && <rect x={0} y={y(v) - 6} width={W - R0} height={12} fill={col} opacity={0.07} />}
          <line x1={0} x2={W - R0} y1={y(v)} y2={y(v)} stroke={col} strokeWidth={1.5} strokeDasharray={dash} />
          <text x={8} y={y(v) - 8} fill={col} fontSize={11} fontWeight={600} letterSpacing={1}>{l}  {px(v, d)}</text>
        </g>
      ) : null)}
      {bars.map((b, i) => { const x = i * cw + cw / 2, col = b.c >= b.o ? G : R; return (
        <g key={i}><line x1={x} x2={x} y1={y(b.h)} y2={y(b.l)} stroke={col} /><rect x={x - cw * 0.32} width={cw * 0.64} y={y(Math.max(b.o, b.c))} height={Math.max(1, Math.abs(y(b.o) - y(b.c)))} fill={col} rx={1} /></g>
      ) })}
      {price ? (
        <g>
          <line x1={0} x2={W - R0} y1={y(price)} y2={y(price)} stroke="#eab308" strokeDasharray="2 3" />
          <rect x={W - R0 + 2} y={y(price) - 10} width={R0 - 2} height={20} rx={4} fill="#eab308" />
          <text x={W - R0 + 6} y={y(price) + 4} fill="#0a0e1a" fontSize={11} fontWeight={700} className="font-mono">{px(price, d)}</text>
        </g>
      ) : null}
    </svg>
  )
}

function EquityChart({ points, start, animKey }: { points: number[]; start: number; animKey: string }) {
  if (points.length < 2) return <div className="h-full flex items-center justify-center text-sm text-gray-500">Equity will appear after trades close</div>
  const mn = Math.min(start, ...points), mx = Math.max(start, ...points), pad = (mx - mn) * 0.12 || 50
  const y = (v: number) => 200 - ((v - mn + pad) / (mx - mn + 2 * pad)) * 200
  const line = points.map((v, i) => `${i ? 'L' : 'M'}${(i / (points.length - 1) * 1000).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  return (
    <div className="relative h-full">
      <svg key={animKey} viewBox="0 0 1000 200" preserveAspectRatio="none" className="w-full h-full block">
        <line x1={0} x2={1000} y1={y(start)} y2={y(start)} stroke="#ef4444" strokeDasharray="5 5" vectorEffect="non-scaling-stroke" />
        <path d={`${line} L1000 200 L0 200 Z`} fill="rgba(234,179,8,.10)" className="ag-fade" />
        <path d={line} pathLength={1} strokeDasharray={1} fill="none" stroke="#eab308" strokeWidth={2} vectorEffect="non-scaling-stroke" className="ag-draw" />
      </svg>
      <span className="absolute -right-1 w-2 h-2 rounded-full bg-yellow-500 ag-pulse" style={{ top: `calc(${(y(points[points.length - 1]) / 2).toFixed(1)}% - 4px)` }} />
    </div>
  )
}

// ------------------------------------------------------------------ page

export default function AgapePerpsContent() {
  const sidebarPadding = useSidebarPadding()
  const router = useRouter()
  const params = useSearchParams()
  const initialCoin = (params.get('coin') || 'btc').toLowerCase() as Coin
  const [sel, setSelState] = useState<Coin>(COINS.includes(initialCoin) ? initialCoin : 'btc')
  const [tab, setTab] = useState<TabId>((params.get('tab') as TabId) || 'portfolio')
  const [range, setRange] = useState<RangePreset>('30d')
  const [histFilter, setHistFilter] = useState<'all' | Coin>('all')
  const [now, setNow] = useState(Date.now())

  const setSel = (c: Coin) => {
    setSelState(c)
    const q = new URLSearchParams(params.toString()); q.set('coin', c); router.replace(`?${q.toString()}`, { scroll: false })
  }

  const o = (c: Coin) => ({ snapshot: sel === c && (tab === 'market' || tab === 'portfolio'), mapping: sel === c && tab === 'config' })
  const bots = {
    btc: useBot('btc', o('btc')), eth: useBot('eth', o('eth')), sol: useBot('sol', o('sol')),
    avax: useBot('avax', o('avax')), xrp: useBot('xrp', o('xrp')), doge: useBot('doge', o('doge')),
  }
  const list = COINS.map(c => bots[c])
  const cur = bots[sel]

  const { trades, hasMore, loadMore, isLoading: tradesLoading } = useAgapePerpTrades({
    bots: histFilter === 'all' || tab !== 'history' ? [...COINS] : [histFilter], range,
  })

  useEffect(() => { const i = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(i) }, [])

  const startOf = (b: typeof cur) => b.status?.paper_account?.starting_capital ?? b.status?.starting_capital ?? 12500
  const realizedOf = (b: typeof cur) => b.perf?.realized_pnl ?? b.status?.paper_account?.realized_pnl ?? b.status?.paper_account?.cumulative_pnl ?? 0
  const unrealOf = (b: typeof cur) => b.status?.total_unrealized_pnl ?? b.positions.reduce((a, p) => a + (p.unrealized_pnl || 0), 0)
  const totalStart = list.reduce((a, b) => a + startOf(b), 0)
  const realized = list.reduce((a, b) => a + realizedOf(b), 0)
  const unreal = list.reduce((a, b) => a + unrealOf(b), 0)
  const totTrades = list.reduce((a, b) => a + (b.perf?.total_trades ?? b.status?.paper_account?.total_trades ?? 0), 0)
  const wAvg = totTrades ? list.reduce((a, b) => a + (b.perf?.win_rate ?? 0) * (b.perf?.total_trades ?? 0), 0) / totTrades : 0

  const firstPrice = (b: typeof cur) => { const bars = barsFromScans(b.coin, b.scans); return bars.length ? bars[0].o : undefined }
  const livePrice = (b: typeof cur) => priceOf(b.coin, b.status) ?? priceOf(b.coin, b.scans[0])
  const change = (b: typeof cur) => { const p = livePrice(b), f = firstPrice(b); return p && f ? (p - f) / f * 100 : null }

  const bars = useMemo(() => barsFromScans(sel, cur.scans), [sel, cur.scans])
  const snap = cur.snapshot
  const lastScan = cur.status?.heartbeat?.last_scan_iso || cur.status?.last_scan_iso
  const secsToScan = lastScan ? Math.max(0, 300 - Math.floor((now - new Date(lastScan).getTime()) / 1000) % 300) : null

  const allPositions = list.flatMap(b => b.positions.map(p => ({ ...p, coin: b.coin })))
  const allScans = list.flatMap(b => b.scans.map(s => ({ ...s, coin: b.coin })))
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())

  const equityPoints = useMemo(() => {
    const closed = [...trades].filter(t => t.close_time).sort((a, b) => new Date(a.close_time!).getTime() - new Date(b.close_time!).getTime())
    let eq = totalStart + realized - closed.reduce((a, t) => a + (t.realized_pnl || 0), 0)
    const pts = [eq]; for (const t of closed) { eq += t.realized_pnl || 0; pts.push(eq) }
    pts.push(eq + unreal)
    return pts
  }, [trades, totalStart, realized, unreal])

  const hist = trades
  const wins = hist.filter(t => t.realized_pnl > 0), losses = hist.filter(t => t.realized_pnl < 0)
  const histTotal = hist.reduce((a, t) => a + (t.realized_pnl || 0), 0)
  const avg = (xs: typeof hist) => (xs.length ? xs.reduce((a, t) => a + t.realized_pnl, 0) / xs.length : 0)

  if (list.every(b => b.loading)) return (<><Navigation /><div className="flex items-center justify-center h-screen bg-[#0a0e1a]"><LoadingState message="Loading AGAPE perpetuals..." /></div></>)

  const m = META[sel]
  const tabMeta = TABS.find(t => t.id === tab)!
  const aggressive = cur.status?.aggressive_features || {}
  const dir = aggressive.direction_tracker || {}

  return (
    <>
      <Navigation />
      <style>{`
        @keyframes ag-tape{from{transform:translateX(0)}to{transform:translateX(-50%)}}
        @keyframes ag-draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
        @keyframes ag-fade{from{opacity:0}to{opacity:1}}
        @keyframes ag-pulse{0%{box-shadow:0 0 0 0 rgba(234,179,8,.6)}100%{box-shadow:0 0 0 10px rgba(234,179,8,0)}}
        .ag-tape{animation:ag-tape 45s linear infinite}.ag-draw{animation:ag-draw 1.4s ease-out both}
        .ag-fade{animation:ag-fade 1.4s ease both}.ag-pulse{animation:ag-pulse 1.2s ease-out infinite}
      `}</style>
      <main className={`min-h-screen bg-[#0a0e1a] text-gray-100 pt-16 transition-all duration-300 ${sidebarPadding}`}>
        <div className="h-10 border-b border-[#1c2233] bg-[#080b14] overflow-hidden flex items-center">
          <div className="ag-tape flex w-max">
            {[0, 1, 2, 3].map(k => (
              <div key={k} className="flex gap-10 pr-10">
                {list.map(b => { const ch = change(b); return (
                  <span key={b.coin} className="flex gap-2.5 text-[13px] whitespace-nowrap">
                    <span className="font-semibold">{META[b.coin].sym}-PERP</span>
                    <span className="font-mono">{px(livePrice(b), META[b.coin].d)}</span>
                    {ch != null && <span className="font-mono" style={{ color: pnlColor(ch) }}>{ch >= 0 ? '+' : ''}{ch.toFixed(2)}%</span>}
                  </span>
                ) })}
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)]">
          <aside className="border-r border-[#1c2233] bg-[#0c1019] px-3.5 py-5 flex flex-col gap-6">
            <div className="grid grid-cols-2 gap-1 bg-[#11151f] border border-[#1c2233] rounded-[10px] p-[3px]">
              <Link href="/valor" className="text-center py-1.5 rounded-md text-[13px] font-semibold text-gray-400 hover:text-gray-100">VALOR</Link>
              <span className="text-center py-1.5 rounded-md text-[13px] font-semibold bg-yellow-500 text-[#0a0e1a]">AGAPE</span>
            </div>
            <div className="px-2 flex flex-col gap-1.5">
              <div className="text-xl font-bold tracking-[.06em]">AGAPE PERPS</div>
              <div className="flex items-center gap-2 text-[13px] text-emerald-500"><Dot color={G} size={7} />
                24/7{secsToScan != null ? ` · next scan ${Math.floor(secsToScan / 60)}:${String(secsToScan % 60).padStart(2, '0')}` : ''}</div>
            </div>
            <nav className="flex lg:flex-col gap-0.5 overflow-x-auto">
              {TABS.map(t => (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={`text-left px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap ${tab === t.id ? 'text-yellow-500 bg-yellow-500/10' : 'text-gray-400 hover:text-gray-100'}`}>{t.label}</button>
              ))}
            </nav>
            <div className="flex flex-col gap-1">
              <div className="text-xs tracking-[.1em] uppercase text-gray-500 px-3 pb-1.5">Bots</div>
              {list.map(b => {
                const mm = META[b.coin], on = b.coin === sel, ch = change(b), tot = realizedOf(b) + unrealOf(b)
                return (
                  <button key={b.coin} onClick={() => setSel(b.coin)}
                    className={`flex flex-col gap-0.5 px-3 py-2 rounded-lg text-left border-l-2 hover:bg-[#1a1f2e] ${on ? 'bg-[#1a1f2e]' : ''}`} style={{ borderColor: on ? mm.color : 'transparent' }}>
                    <span className="flex justify-between items-center">
                      <span className="flex items-center gap-2 text-sm font-semibold"><Dot color={mm.color} />{mm.sym}
                        {b.status?.status && b.status.status !== 'ACTIVE' && <span className="text-[10px] text-orange-400">{b.status.status}</span>}</span>
                      <span className="font-mono text-[13px]">{px(livePrice(b), mm.d)}</span>
                    </span>
                    <span className="flex justify-between text-xs font-mono">
                      <span style={{ color: pnlColor(tot) }}>{money(tot, true)}</span>
                      {ch != null && <span style={{ color: pnlColor(ch) }}>{ch >= 0 ? '+' : ''}{ch.toFixed(2)}%</span>}
                    </span>
                  </button>
                )
              })}
            </div>
            <div className="text-xs text-yellow-500 border border-yellow-500/35 rounded-lg px-3 py-2.5 leading-relaxed">Paper trading mode. Six AGAPE perpetual bots.</div>
          </aside>

          <section className="px-4 md:px-8 pt-7 pb-10 flex flex-col gap-6 min-w-0">
            <div className="flex items-baseline gap-3"><h1 className="text-xl font-semibold">{tabMeta.label}</h1><span className="text-sm text-gray-500">{tabMeta.desc}</span></div>

            {tab === 'portfolio' && (
              <div className="flex flex-col gap-6">
                <div className="flex flex-wrap justify-between items-end gap-6">
                  <div className="flex flex-col gap-2">
                    <span className="text-sm text-gray-400">Combined equity · 6 bots · live</span>
                    <span className="font-mono text-5xl md:text-[56px] font-semibold tracking-tight leading-none">{money(totalStart + realized + unreal)}</span>
                    <span className="flex flex-wrap gap-4 font-mono text-[15px]">
                      <span className="font-semibold" style={{ color: pnlColor(realized) }}>{money(realized, true)} realized</span>
                      <span style={{ color: pnlColor(unreal) }}>{money(unreal, true)} open</span>
                      <span className="text-gray-500">from {money(totalStart)}</span>
                    </span>
                  </div>
                  <div className="flex gap-7">
                    {[['Win rate', `${wAvg.toFixed(1)}%`, wAvg >= 50 ? G : R], ['Trades', totTrades, '#f3f4f6'], ['Return', `${((realized + unreal) / (totalStart || 1) * 100).toFixed(2)}%`, pnlColor(realized + unreal)]].map(([l, v, c]) => (
                      <div key={l as string} className="flex flex-col gap-1 items-end"><span className="text-xs text-gray-500">{l}</span><span className="font-mono text-lg font-semibold" style={{ color: c as string }}>{v}</span></div>
                    ))}
                  </div>
                </div>

                <Card className="overflow-hidden">
                  <div className="flex flex-wrap justify-between items-center gap-3 px-5 py-4 border-b border-[#1c2233]">
                    <div className="flex items-baseline gap-3.5">
                      <span className="flex items-center gap-2 text-base font-semibold"><Dot color={m.color} size={9} />{m.sym}-PERP</span>
                      <span className="text-[13px] text-gray-400">5m</span>
                      <span className="font-mono text-[22px] font-semibold">{px(livePrice(cur), m.d)}</span>
                    </div>
                    <div className="flex flex-wrap gap-3.5 text-xs font-semibold tracking-wide">
                      <span className="text-blue-500">— Short liq cluster</span><span className="text-amber-500">- - GEX flip</span><span className="text-violet-500">— Long liq cluster</span>
                      {snap?.signals?.combined_signal && <span style={{ color: sigColor(snap.signals.combined_signal) }}>{snap.signals.combined_signal}</span>}
                    </div>
                  </div>
                  <div className="flex flex-wrap">
                    <div className="flex-[1_1_480px] min-w-0 pl-4 pr-2 pt-3 pb-2">
                      <CandleChart bars={bars} sl={snap?.liquidations?.nearest_short_liq} ll={snap?.liquidations?.nearest_long_liq} flip={snap?.crypto_gex?.flip_point} price={livePrice(cur)} d={m.d} />
                    </div>
                    <div className="flex-[1_0_220px] border-l border-[#1c2233] p-4 flex flex-col gap-1">
                      <div className="text-[13px] font-semibold mb-1.5">Liquidation clusters</div>
                      {(() => {
                        const cl: any[] = (snap?.liquidations?.top_clusters || []).slice(0, 12)
                        if (!cl.length) return <div className="text-xs text-gray-500">No cluster data yet</div>
                        const p = livePrice(cur) || 0
                        const w = (c: any) => c.intensity === 'HIGH' ? 100 : c.intensity === 'ELEVATED' ? 66 : 33
                        return [...cl].sort((a, b) => b.price - a.price).map((c, i) => (
                          <div key={i} className="grid grid-cols-[76px_1fr_44px] items-center gap-1.5 h-[22px]">
                            <span className="font-mono text-[11px] text-gray-400 pl-1">{px(c.price, m.d)}</span>
                            <span className="h-2.5 rounded-sm" style={{ width: `${w(c)}%`, background: c.price > p ? '#3b82f6' : '#8b5cf6' }} />
                            <span className="font-mono text-[10px] text-gray-500 text-right">{c.distance_pct}%</span>
                          </div>
                        ))
                      })()}
                      <div className="text-[11px] text-gray-500 mt-1.5 leading-snug">Blue: shorts liquidated above price. Violet: longs below.</div>
                    </div>
                  </div>
                </Card>

                <div className="grid gap-5 grid-cols-[repeat(auto-fit,minmax(340px,1fr))]">
                  <Card className="px-5 py-4 flex flex-col gap-3.5">
                    <div className="flex justify-between items-center"><span className="text-base font-semibold">Equity curve</span><Pills items={RANGES} value={range} onChange={setRange} /></div>
                    <div className="h-[180px]"><EquityChart points={equityPoints} start={totalStart} animKey={range} /></div>
                  </Card>
                  <Card className="flex flex-col">
                    <div className="px-5 py-4 text-base font-semibold flex justify-between"><span>Open positions ({allPositions.length})</span><span className="text-xs text-gray-500 font-normal">all bots · live</span></div>
                    {allPositions.length === 0 && <div className="px-5 py-5 border-t border-[#1c2233] text-sm text-gray-500">No open positions. The bots are scanning for opportunities.</div>}
                    {allPositions.map(p => { const mm = META[p.coin as Coin]; return (
                      <div key={`${p.coin}-${p.position_id}`} className="flex justify-between items-center px-5 py-3 border-t border-[#1c2233]">
                        <div className="flex flex-col gap-1">
                          <span className="flex items-center gap-2 font-semibold text-sm"><Dot color={mm.color} />{mm.sym}
                            <span className="text-xs" style={{ color: p.side === 'long' ? G : R }}>{p.side?.toUpperCase()} × {p.quantity}</span>
                            {p.trailing_active && <span className="text-[11px] text-yellow-500 font-medium">TRAILING @ {px(p.current_stop, mm.d)}</span>}</span>
                          <span className="text-xs text-gray-500 font-mono">{px(p.entry_price, mm.d)} → {px(p.current_price ?? livePrice(bots[p.coin as Coin]), mm.d)} · {p.funding_regime_at_entry}</span>
                        </div>
                        <span className="font-mono text-base font-semibold" style={{ color: pnlColor(p.unrealized_pnl || 0) }}>{money(p.unrealized_pnl || 0, true)}</span>
                      </div>
                    ) })}
                  </Card>
                </div>

                <Card className="overflow-hidden">
                  <div className="px-5 py-4 text-base font-semibold border-b border-[#1c2233]">All bots</div>
                  <div className="overflow-x-auto"><div className="min-w-[860px]">
                    <div className="grid grid-cols-[minmax(150px,1fr)_80px_120px_90px_90px_120px_100px_70px] gap-3.5 px-5 py-2.5 text-xs text-gray-500 uppercase tracking-wider">
                      <span>Bot</span><span>Mode</span><span>Status</span><span className="text-right">Trades</span><span className="text-right">Win rate</span><span className="text-right">P&amp;L</span><span className="text-right">Return</span><span className="text-right">Open</span></div>
                    {list.map(b => { const mm = META[b.coin], tot = realizedOf(b) + unrealOf(b), wr = b.perf?.win_rate ?? b.status?.paper_account?.win_rate; return (
                      <button key={b.coin} onClick={() => setSel(b.coin)} className={`w-full grid grid-cols-[minmax(150px,1fr)_80px_120px_90px_90px_120px_100px_70px] gap-3.5 px-5 py-3 border-t border-[#1c2233] text-sm items-center text-left hover:bg-[#1a1f2e] ${b.coin === sel ? 'bg-[#1a1f2e]' : ''}`}>
                        <span className="flex items-center gap-2.5"><Dot color={mm.color} /><span className="font-semibold">AGAPE-{mm.sym}-PERP</span></span>
                        <span className="text-xs font-semibold" style={{ color: b.status?.mode === 'live' ? G : '#eab308' }}>{(b.status?.mode || 'paper').toUpperCase()}</span>
                        <span className="text-xs font-semibold" style={{ color: b.status?.aggressive_features?.loss_streak_paused ? R : b.status?.status === 'ACTIVE' ? G : '#9ca3af' }}>{b.status?.aggressive_features?.loss_streak_paused ? 'PAUSED' : b.status?.status || '—'}</span>
                        <span className="font-mono text-right text-gray-300">{b.perf?.total_trades ?? 0}</span>
                        <span className="font-mono text-right" style={{ color: (wr || 0) >= 50 ? G : R }}>{wr != null ? `${Number(wr).toFixed(1)}%` : '—'}</span>
                        <span className="font-mono text-right font-semibold" style={{ color: pnlColor(tot) }}>{money(tot, true)}</span>
                        <span className="font-mono text-right" style={{ color: pnlColor(tot) }}>{(tot / startOf(b) * 100).toFixed(2)}%</span>
                        <span className="font-mono text-right text-gray-300">{b.positions.length}</span>
                      </button>
                    ) })}
                  </div></div>
                </Card>
              </div>
            )}

            {tab === 'overview' && (
              <div className="flex flex-col gap-5">
                {aggressive.loss_streak_paused ? (
                  <div className="flex items-center gap-3 border border-red-500/50 bg-red-900/30 rounded-xl px-4 py-3 text-sm"><Dot color={R} size={9} />
                    <span className="text-red-400 font-semibold">PAUSED - Loss Streak Protection Active</span>
                    <span className="text-gray-400">AGAPE-{m.sym}-PERP paused after {aggressive.consecutive_losses} consecutive losses. Will resume automatically.</span></div>
                ) : aggressive.consecutive_losses > 0 ? (
                  <div className="flex items-center gap-3 border border-orange-500/45 bg-orange-500/10 rounded-xl px-4 py-3 text-sm"><Dot color="#f97316" size={9} />
                    <span className="text-orange-300 font-semibold">{m.sym} Loss Streak: {aggressive.consecutive_losses}</span><span className="text-gray-400">(pauses after 3 consecutive losses)</span></div>
                ) : null}
                <div className="text-sm text-gray-400">Aggressive Mode - Perpetual Contract Trading · showing <span className="font-semibold" style={{ color: m.color }}>AGAPE-{m.sym}-PERP</span></div>
                <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(180px,1fr))]">
                  <Stat label="No-Loss Trailing" value={aggressive.use_no_loss_trailing ? 'ACTIVE' : 'OFF'} color={aggressive.use_no_loss_trailing ? G : '#6b7280'} />
                  <Stat label="Stop-and-Reverse" value={aggressive.use_sar ? 'ACTIVE' : 'OFF'} color={aggressive.use_sar ? G : '#6b7280'} />
                  <Stat label="Consecutive Losses" value={aggressive.consecutive_losses || 0} color={(aggressive.consecutive_losses || 0) >= 3 ? R : undefined} />
                  <Stat label="Direction Tracker" value={`L ${dir.long_win_rate != null ? (dir.long_win_rate * 100).toFixed(0) + '%' : '--'}  S ${dir.short_win_rate != null ? (dir.short_win_rate * 100).toFixed(0) + '%' : '--'}`} />
                </div>
                <Card className="px-5 py-4 flex flex-col gap-4">
                  <span className="text-base font-semibold">Performance</span>
                  <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(150px,1fr))]">
                    {[
                      ['Profit Factor', cur.perf?.profit_factor ?? '---', undefined],
                      ['Avg Win', cur.perf?.avg_win != null ? money(cur.perf.avg_win) : '---', G],
                      ['Avg Loss', cur.perf?.avg_loss != null ? money(-Math.abs(cur.perf.avg_loss)) : '---', R],
                      ['Return', `${cur.perf?.return_pct ?? cur.status?.paper_account?.return_pct ?? 0}%`, pnlColor(cur.perf?.return_pct ?? 0)],
                      ['Realized P&L', money(realizedOf(cur), true), pnlColor(realizedOf(cur))],
                      ['Unrealized P&L', money(unrealOf(cur), true), pnlColor(unrealOf(cur))],
                      ['Best Trade', cur.perf?.best_trade != null ? money(cur.perf.best_trade) : '---', G],
                      ['Worst Trade', cur.perf?.worst_trade != null ? money(cur.perf.worst_trade) : '---', R],
                    ].map(([l, v, c]) => (
                      <div key={l as string} className="flex flex-col gap-1"><span className="text-[13px] text-gray-500">{l}</span><span className="font-mono text-[17px] font-semibold" style={{ color: (c as string) || '#f3f4f6' }}>{v as any}</span></div>
                    ))}
                  </div>
                </Card>
                <Card className="px-5 py-4 flex flex-col gap-4">
                  <span className="text-base font-semibold">Direction tracker · all bots</span>
                  <div className="grid gap-x-8 gap-y-3.5 grid-cols-[repeat(auto-fit,minmax(260px,1fr))]">
                    {list.map(b => { const dt = b.status?.aggressive_features?.direction_tracker || {}, l = dt.long_win_rate ?? 0, s = dt.short_win_rate ?? 0; return (
                      <div key={b.coin} className="grid grid-cols-[52px_1fr] gap-3 items-center">
                        <span className="flex items-center gap-1.5 text-[13px] font-semibold"><Dot color={META[b.coin].color} size={7} />{META[b.coin].sym}</span>
                        <div className="flex flex-col gap-1">
                          <div className="flex h-2 rounded-full overflow-hidden bg-[#1c2233]"><div style={{ width: `${l * 50}%`, background: G }} /><div className="flex-1" /><div style={{ width: `${s * 50}%`, background: R }} /></div>
                          <div className="flex justify-between font-mono text-[11px] text-gray-400"><span>L {(l * 100).toFixed(0)}%</span><span>S {(s * 100).toFixed(0)}%</span></div>
                        </div>
                      </div>
                    ) })}
                  </div>
                </Card>
              </div>
            )}

            {tab === 'market' && (
              !snap ? <Card className="p-8 text-center text-gray-500">Waiting for crypto market data</Card> : (
                <div className="flex flex-col gap-5">
                  <Card className="px-5 py-4 flex flex-wrap justify-between items-center gap-4">
                    <div className="flex items-baseline gap-3.5"><span className="flex items-center gap-2 text-lg font-semibold"><Dot color={m.color} size={9} />{snap.symbol || m.sym}</span><span className="font-mono text-2xl font-semibold">{px(snap.spot_price, m.d)}</span></div>
                    <span className="text-sm font-bold px-3.5 py-1.5 rounded-full" style={{ color: sigColor(snap.signals?.combined_signal), background: sigColor(snap.signals?.combined_signal) + '22' }}>{snap.signals?.combined_signal} ({snap.signals?.combined_confidence})</span>
                  </Card>
                  <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(170px,1fr))]">
                    <Stat big={false} label="Leverage Regime" value={snap.signals?.leverage_regime || '—'} />
                    <Stat big={false} label="Direction Bias" value={snap.signals?.directional_bias || '—'} color={sigColor(snap.signals?.directional_bias)} />
                    <Stat big={false} label="Squeeze Risk" value={snap.signals?.squeeze_risk || '—'} color={riskColor(snap.signals?.squeeze_risk)} />
                    <Stat big={false} label="Volatility" value={snap.signals?.volatility_regime || '—'} />
                  </div>
                  <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(320px,1fr))]">
                    <Card className="px-5 py-4 flex flex-col gap-3"><div><div className="text-base font-semibold">Funding Rate</div><div className="text-xs text-gray-500">Replaces: Gamma Regime (POSITIVE/NEGATIVE)</div></div>
                      <Row label="Current Rate" value={snap.funding?.rate != null ? `${(snap.funding.rate * 100).toFixed(4)}%` : '---'} />
                      <Row label="Predicted" value={snap.funding?.predicted != null ? `${(snap.funding.predicted * 100).toFixed(4)}%` : '---'} />
                      <Row label="Regime" value={snap.funding?.regime || '—'} color={sigColor(snap.funding?.regime)} />
                      <Row label="Annualized" value={snap.funding?.annualized != null ? `${(snap.funding.annualized * 100).toFixed(1)}%` : '---'} /></Card>
                    <Card className="px-5 py-4 flex flex-col gap-3"><div><div className="text-base font-semibold">Long/Short Ratio</div><div className="text-xs text-gray-500">Replaces: GEX Directional Bias</div></div>
                      <Row label="Ratio" value={snap.long_short?.ratio?.toFixed(2) || '---'} />
                      <Row label="Long %" value={`${snap.long_short?.long_pct?.toFixed(1) || '---'}%`} color={G} />
                      <Row label="Short %" value={`${snap.long_short?.short_pct?.toFixed(1) || '---'}%`} color={R} />
                      <Row label="Bias" value={snap.long_short?.bias || '—'} color={sigColor(snap.long_short?.bias)} /></Card>
                    <Card className="px-5 py-4 flex flex-col gap-3"><div><div className="text-base font-semibold">Liquidation Clusters</div><div className="text-xs text-gray-500">Replaces: Gamma Walls / Price Magnets</div></div>
                      <Row label="Nearest Long Liq" value={snap.liquidations?.nearest_long_liq ? `$${px(snap.liquidations.nearest_long_liq, m.d)}` : '---'} color="#c4b5fd" />
                      <Row label="Nearest Short Liq" value={snap.liquidations?.nearest_short_liq ? `$${px(snap.liquidations.nearest_short_liq, m.d)}` : '---'} color="#93c5fd" />
                      <Row label="Cluster Count" value={snap.liquidations?.cluster_count || 0} /></Card>
                    <Card className="px-5 py-4 flex flex-col gap-3"><div><div className="text-base font-semibold">Crypto GEX (Deribit)</div><div className="text-xs text-gray-500">Direct equivalent of Net GEX</div></div>
                      <Row label="Net GEX" value={snap.crypto_gex?.net_gex?.toFixed(2) || '---'} color={pnlColor(snap.crypto_gex?.net_gex || 0)} />
                      <Row label="Regime" value={snap.crypto_gex?.regime || '—'} color={sigColor(snap.crypto_gex?.regime)} />
                      <Row label="Call GEX" value={snap.crypto_gex?.call_gex?.toFixed(2) || '---'} color={G} />
                      <Row label="Put GEX" value={snap.crypto_gex?.put_gex?.toFixed(2) || '---'} color={R} />
                      <Row label="Max Pain / Flip" value={snap.crypto_gex?.flip_point ? `$${px(snap.crypto_gex.flip_point, m.d)}` : '---'} /></Card>
                  </div>
                </div>
              )
            )}

            {tab === 'activity' && (
              <Card className="overflow-hidden">
                <div className="px-5 py-4 text-base font-semibold border-b border-[#1c2233]">Scan activity · all bots ({allScans.length})</div>
                <div className="overflow-x-auto"><div className="min-w-[860px]">
                  <div className="grid grid-cols-[90px_70px_110px_130px_160px_100px_minmax(140px,1fr)] gap-3.5 px-5 py-2.5 text-xs text-gray-500 uppercase tracking-wider"><span>Time</span><span>Coin</span><span className="text-right">Price</span><span>Funding</span><span>Signal</span><span>Prophet</span><span>Outcome</span></div>
                  {allScans.length === 0 && <div className="px-5 py-5 border-t border-[#1c2233] text-sm text-gray-500">No scan activity yet</div>}
                  {allScans.slice(0, 150).map((s, i) => { const mm = META[s.coin as Coin], oc: string = s.outcome || ''; return (
                    <div key={i} className="grid grid-cols-[90px_70px_110px_130px_160px_100px_minmax(140px,1fr)] gap-3.5 px-5 py-2.5 border-t border-[#1c2233] text-sm items-center">
                      <span className="font-mono text-[13px] text-gray-400">{s.timestamp ? new Date(s.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '---'}</span>
                      <span className="flex items-center gap-2 font-semibold"><Dot color={mm.color} size={7} />{mm.sym}</span>
                      <span className="font-mono text-right">{px(priceOf(s.coin, s), mm.d)}</span>
                      <span className="text-xs text-gray-400">{s.funding_regime}</span>
                      <span className="text-xs font-semibold" style={{ color: sigColor(s.combined_signal) }}>{s.combined_signal} {s.combined_confidence && `(${s.combined_confidence})`}</span>
                      <span className="text-xs text-gray-400">{s.oracle_advice || 'Advisory'}</span>
                      <span><span className={`text-[11px] font-bold tracking-wide px-2 py-0.5 rounded-md ${oc.includes('TRADED') ? 'bg-yellow-500/15 text-yellow-500' : oc.includes('SAR') ? 'bg-violet-500/20 text-violet-300' : oc.includes('ERROR') ? 'bg-red-500/15 text-red-300' : oc.includes('LOSS_STREAK') ? 'bg-orange-500/15 text-orange-300' : 'bg-[#1c2233] text-gray-400'}`}>{oc}</span></span>
                    </div>
                  ) })}
                </div></div>
              </Card>
            )}

            {tab === 'history' && (
              <div className="flex flex-col gap-5">
                <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(140px,1fr))]">
                  <Stat label="Trades" value={hist.length} />
                  <Stat label="Win Rate" value={hist.length ? `${(wins.length / hist.length * 100).toFixed(1)}%` : '—'} color={wins.length / (hist.length || 1) >= 0.5 ? G : R} />
                  <Stat label="Total P&L" value={money(histTotal, true)} color={pnlColor(histTotal)} />
                  <Stat label="Avg Win" value={money(avg(wins), true)} color={G} />
                  <Stat label="Avg Loss" value={money(avg(losses), true)} color={R} />
                </div>
                <Card className="overflow-hidden">
                  <div className="flex flex-wrap justify-between items-center gap-3 px-5 py-3.5 border-b border-[#1c2233]">
                    <span className="text-base font-semibold">Trade history</span>
                    <div className="flex gap-3 flex-wrap">
                      <Pills items={[{ id: 'all' as const, label: 'ALL' }, ...COINS.map(c => ({ id: c, label: META[c].sym }))]} value={histFilter} onChange={v => setHistFilter(v as any)} />
                      <Pills items={RANGES} value={range} onChange={setRange} />
                    </div>
                  </div>
                  <div className="overflow-x-auto"><div className="min-w-[920px]">
                    <div className="grid grid-cols-[130px_70px_70px_90px_1fr_1fr_110px_80px_140px] gap-3 px-5 py-2.5 text-xs text-gray-500 uppercase tracking-wider"><span>Closed</span><span>Coin</span><span>Side</span><span className="text-right">Qty</span><span className="text-right">Entry</span><span className="text-right">Close</span><span className="text-right">P&amp;L</span><span className="text-right">%</span><span>Reason</span></div>
                    {tradesLoading && <div className="px-5 py-5 border-t border-[#1c2233] text-sm text-gray-500">Loading trades…</div>}
                    {!tradesLoading && hist.length === 0 && <div className="px-5 py-5 border-t border-[#1c2233] text-sm text-gray-500">No closed trades in this range.</div>}
                    {hist.map(t => { const c = (t.bot_id || 'btc').toLowerCase().replace(/.*(btc|eth|sol|avax|xrp|doge).*/, '$1') as Coin, mm = META[c] || META.btc; return (
                      <div key={`${t.bot_id}-${t.position_id}`} className="grid grid-cols-[130px_70px_70px_90px_1fr_1fr_110px_80px_140px] gap-3 px-5 py-2.5 border-t border-[#1c2233] text-sm items-center">
                        <span className="font-mono text-[13px] text-gray-400">{t.close_time ? new Date(t.close_time).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}</span>
                        <span className="flex items-center gap-2 font-semibold"><Dot color={mm.color} size={7} />{mm.sym}</span>
                        <span className="text-[13px] font-semibold" style={{ color: t.side === 'long' ? G : R }}>{t.side?.toUpperCase()}</span>
                        <span className="font-mono text-right">{t.quantity}</span>
                        <span className="font-mono text-right">{px(t.entry_price, mm.d)}</span>
                        <span className="font-mono text-right">{px(t.close_price, mm.d)}</span>
                        <span className="font-mono text-right font-semibold" style={{ color: pnlColor(t.realized_pnl) }}>{money(t.realized_pnl, true)}</span>
                        <span className="font-mono text-right text-[13px]" style={{ color: pnlColor(t.realized_pnl) }}>{t.realized_pnl_pct != null ? `${t.realized_pnl_pct.toFixed(2)}%` : '—'}</span>
                        <span className="text-[13px] text-gray-400">{t.close_reason}</span>
                      </div>
                    ) })}
                    {hasMore && <button onClick={loadMore} className="w-full py-3 border-t border-[#1c2233] text-sm text-yellow-500 hover:bg-[#1a1f2e]">Load more</button>}
                  </div></div>
                </Card>
              </div>
            )}

            {tab === 'config' && (
              <div className="flex flex-col gap-5">
                <Card className="px-5 py-4 flex flex-col gap-4">
                  <span className="text-base font-semibold">Bot configuration · <span style={{ color: m.color }}>AGAPE-{m.sym}-PERP</span></span>
                  <div className="grid gap-px bg-[#1c2233] border border-[#1c2233] rounded-lg overflow-hidden grid-cols-[repeat(auto-fit,minmax(180px,1fr))]">
                    {[
                      ['Instrument', cur.status?.instrument || `${m.sym}-PERP`],
                      ['Starting Capital', `$${(cur.status?.starting_capital ?? 12500).toLocaleString()}`],
                      ['Risk Per Trade', `${cur.status?.risk_per_trade_pct || 5}%`],
                      ['Max Quantity', cur.status?.max_contracts || 10],
                      ['Cooldown', `${cur.status?.cooldown_minutes || 5} min`],
                      ['Prophet', cur.status?.require_oracle ? 'Required' : 'Advisory'],
                      ['Cycles Run', cur.status?.cycle_count || 0],
                      ['Mode', (cur.status?.mode || 'paper').toUpperCase()],
                    ].map(([l, v]) => (
                      <div key={l as string} className="bg-[#11151f] px-4 py-3.5 flex flex-col gap-1.5"><span className="text-[13px] text-gray-400">{l}</span><span className="font-mono text-base font-semibold">{v as any}</span></div>
                    ))}
                  </div>
                </Card>
                {cur.mapping && (
                  <Card className="px-5 py-4 flex flex-col gap-3.5">
                    <div><div className="text-base font-semibold">{cur.mapping.title || 'GEX Mapping'}</div>{cur.mapping.description && <div className="text-[13px] text-gray-500 mt-1">{cur.mapping.description}</div>}</div>
                    {cur.mapping.mappings?.map((mp: any, i: number) => (
                      <div key={i} className="border border-[#1c2233] rounded-lg px-4 py-3.5 flex flex-col gap-2">
                        <div className="grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] gap-3 items-center">
                          <div className="flex flex-col gap-0.5"><span className="text-xs text-gray-500">Equity GEX</span><span className="font-mono text-sm text-gray-400">{mp.gex_concept}</span></div>
                          <span className="text-gray-500 text-center">→</span>
                          <div className="flex flex-col gap-0.5"><span className="text-xs text-yellow-500">Crypto equivalent</span><span className="text-sm font-semibold">{mp.crypto_equivalent}</span></div>
                        </div>
                        {mp.explanation && <p className="text-xs text-gray-400">{mp.explanation}</p>}
                        {mp.data_source && <p className="text-xs text-gray-500">Source: {mp.data_source}</p>}
                      </div>
                    ))}
                  </Card>
                )}
              </div>
            )}
          </section>
        </div>
      </main>
    </>
  )
}
