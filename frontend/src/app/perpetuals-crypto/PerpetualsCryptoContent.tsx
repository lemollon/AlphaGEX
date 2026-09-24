'use client'

// Crypto Perps — one consolidated hub for the seven AGAPE perpetual bots.
// Route: /perpetuals-crypto?coin=btc|eth|xrp|sol|doge|avax|shib&tab=overview|market|activity|history|config
// Replaces the old "ALL coins dashboard" (PerpetualsCryptoContent) and the
// six-bot /agape-perps hub (AgapePerpsContent) with a single overview +
// coin-detail view, per the Crypto Perps design handoff.

import { useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import { LoadingState } from '@/components/trader'
import { useAgapePerpTrades, type RangePreset, type Trade } from '@/lib/hooks/useAgapePerpTrades'
import {
  useAGAPEBtcPerpStatus, useAGAPEBtcPerpPerformance, useAGAPEBtcPerpPositions, useAGAPEBtcPerpScanActivity, useAGAPEBtcPerpSnapshot, useAGAPEBtcPerpGexMapping,
  useAGAPEEthPerpStatus, useAGAPEEthPerpPerformance, useAGAPEEthPerpPositions, useAGAPEEthPerpScanActivity, useAGAPEEthPerpSnapshot, useAGAPEEthPerpGexMapping,
  useAGAPEXrpPerpStatus, useAGAPEXrpPerpPerformance, useAGAPEXrpPerpPositions, useAGAPEXrpPerpScanActivity, useAGAPEXrpPerpSnapshot, useAGAPEXrpPerpGexMapping,
  useAGAPESolPerpStatus, useAGAPESolPerpPerformance, useAGAPESolPerpPositions, useAGAPESolPerpScanActivity, useAGAPESolPerpSnapshot, useAGAPESolPerpGexMapping,
  useAGAPEDogePerpStatus, useAGAPEDogePerpPerformance, useAGAPEDogePerpPositions, useAGAPEDogePerpScanActivity, useAGAPEDogePerpSnapshot, useAGAPEDogePerpGexMapping,
  useAGAPEAvaxPerpStatus, useAGAPEAvaxPerpPerformance, useAGAPEAvaxPerpPositions, useAGAPEAvaxPerpScanActivity, useAGAPEAvaxPerpSnapshot, useAGAPEAvaxPerpGexMapping,
  useAGAPEShibPerpStatus, useAGAPEShibPerpPerformance, useAGAPEShibPerpPositions, useAGAPEShibPerpScanActivity, useAGAPEShibPerpSnapshot, useAGAPEShibPerpGexMapping,
} from '@/lib/hooks/useMarketData'

const G = '#10b981'
const R = '#ef4444'
const REFRESH_MS = 15000
const MONO = "font-[Geist_Mono,monospace]"

type Coin = 'btc' | 'eth' | 'xrp' | 'sol' | 'doge' | 'avax' | 'shib'

const PERP_COINS: Coin[] = ['btc', 'eth', 'xrp', 'sol', 'doge', 'avax', 'shib']
const COINS: Coin[] = [...PERP_COINS]

const META: Record<Coin, { sym: string; name: string; color: string; d: number; type: 'PERP' | 'FUT'; instrument: string; cap: number }> = {
  btc:  { sym: 'BTC',  name: 'Bitcoin',      color: '#F7931A', d: 2, type: 'PERP', instrument: 'BTC-PERP',     cap: 25000 },
  eth:  { sym: 'ETH',  name: 'Ethereum',     color: '#627EEA', d: 2, type: 'PERP', instrument: 'ETH-PERP',     cap: 12500 },
  xrp:  { sym: 'XRP',  name: 'Ripple',       color: '#94A3B8', d: 4, type: 'PERP', instrument: 'XRP-PERP',     cap: 9000 },
  sol:  { sym: 'SOL',  name: 'Solana',       color: '#9945FF', d: 2, type: 'PERP', instrument: 'SOL-PERP',     cap: 5000 },
  doge: { sym: 'DOGE', name: 'Dogecoin',     color: '#C2A633', d: 5, type: 'PERP', instrument: 'DOGE-PERP',    cap: 2500 },
  avax: { sym: 'AVAX', name: 'Avalanche',    color: '#E84142', d: 3, type: 'PERP', instrument: 'AVAX-PERP',    cap: 2500 },
  shib: { sym: 'SHIB', name: 'Shiba Inu',    color: '#F43F5E', d: 8, type: 'PERP', instrument: 'SHIB-PERP',    cap: 1000 },
}

// bot_id slug used by /api/agape-perpetuals/trades
const BOT_ID: Record<Coin, string> = {
  btc: 'btc', eth: 'eth', xrp: 'xrp', sol: 'sol', doge: 'doge', avax: 'avax', shib: 'shib',
}
const COIN_OF_BOT_ID: Record<string, Coin> = Object.fromEntries(COINS.map(c => [BOT_ID[c], c])) as Record<string, Coin>

const TABS = [
  { id: 'overview' as const, label: 'Overview' },
  { id: 'market' as const,   label: 'Market' },
  { id: 'activity' as const, label: 'Activity' },
  { id: 'history' as const,  label: 'History' },
  { id: 'config' as const,   label: 'Config' },
]
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
const pct = (v: number | undefined | null) => (v == null || isNaN(Number(v)) ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`)
const pnlColor = (n: number) => (n > 0 ? G : n < 0 ? R : '#9ca3af')
const sigColor = (s?: string) =>
  !s ? '#9ca3af' : /LONG|BULL|POSITIVE/.test(s) ? G : /SHORT|BEAR|NEGATIVE/.test(s) ? R : s === 'RANGE_BOUND' ? '#eab308' : '#9ca3af'
const riskColor = (r?: string) => (r === 'HIGH' ? R : r === 'ELEVATED' ? '#f97316' : G)
const priceOf = (coin: Coin, obj: any): number | null => obj?.[`current_${coin}_price`] ?? obj?.[`${coin}_price`] ?? obj?.current_price ?? obj?.spot_price ?? null

// ------------------------------------------------------------------ bot data hook

interface BotData {
  coin: Coin
  status: any
  loading: boolean
  perf: any
  positions: any[]
  scans: any[]
  snapshot: any
  mapping: any
}

function useBot(coin: Coin, opts: { snapshot: boolean; mapping: boolean }): BotData {
  const H = {
    btc:  [useAGAPEBtcPerpStatus, useAGAPEBtcPerpPerformance, useAGAPEBtcPerpPositions, useAGAPEBtcPerpScanActivity, useAGAPEBtcPerpSnapshot, useAGAPEBtcPerpGexMapping],
    eth:  [useAGAPEEthPerpStatus, useAGAPEEthPerpPerformance, useAGAPEEthPerpPositions, useAGAPEEthPerpScanActivity, useAGAPEEthPerpSnapshot, useAGAPEEthPerpGexMapping],
    xrp:  [useAGAPEXrpPerpStatus, useAGAPEXrpPerpPerformance, useAGAPEXrpPerpPositions, useAGAPEXrpPerpScanActivity, useAGAPEXrpPerpSnapshot, useAGAPEXrpPerpGexMapping],
    sol:  [useAGAPESolPerpStatus, useAGAPESolPerpPerformance, useAGAPESolPerpPositions, useAGAPESolPerpScanActivity, useAGAPESolPerpSnapshot, useAGAPESolPerpGexMapping],
    doge: [useAGAPEDogePerpStatus, useAGAPEDogePerpPerformance, useAGAPEDogePerpPositions, useAGAPEDogePerpScanActivity, useAGAPEDogePerpSnapshot, useAGAPEDogePerpGexMapping],
    avax: [useAGAPEAvaxPerpStatus, useAGAPEAvaxPerpPerformance, useAGAPEAvaxPerpPositions, useAGAPEAvaxPerpScanActivity, useAGAPEAvaxPerpSnapshot, useAGAPEAvaxPerpGexMapping],
    shib: [useAGAPEShibPerpStatus, useAGAPEShibPerpPerformance, useAGAPEShibPerpPositions, useAGAPEShibPerpScanActivity, useAGAPEShibPerpSnapshot, useAGAPEShibPerpGexMapping],
  }[coin] as any[]
  const [useStatus, usePerf, usePositions, useScans, useSnapshot, useMapping] = H
  const status = useStatus({ refreshInterval: REFRESH_MS })
  const perf = usePerf({ refreshInterval: REFRESH_MS })
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
  }
}

function startOf(b: BotData): number {
  return b.status?.paper_account?.starting_capital ?? b.status?.starting_capital ?? META[b.coin].cap
}
function realizedOf(b: BotData): number {
  return b.perf?.realized_pnl ?? b.status?.paper_account?.realized_pnl ?? b.status?.paper_account?.cumulative_pnl ?? 0
}
function unrealOf(b: BotData): number {
  return b.status?.total_unrealized_pnl ?? b.positions.reduce((a: number, p: any) => a + (p.unrealized_pnl || 0), 0)
}
function livePrice(b: BotData): number | null {
  return priceOf(b.coin, b.status) ?? priceOf(b.coin, b.scans[0])
}
function firstPrice(b: BotData): number | null {
  const bars = barsFromScans(b.coin, b.scans)
  return bars.length ? bars[0].o : null
}

// ------------------------------------------------------------------ UI atoms

function Card({ children, className = '', style }: { children: React.ReactNode; className?: string; style?: React.CSSProperties }) {
  return <div className={`bg-[#11151f] border border-[#1c2233] rounded-xl ${className}`} style={style}>{children}</div>
}
const Dot = ({ color, size = 8 }: { color: string; size?: number }) =>
  <span className="inline-block rounded-full shrink-0" style={{ width: size, height: size, background: color }} />
function Pills<T extends string>({ items, value, onChange }: { items: { id: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex gap-1">
      {items.map(i => (
        <button key={i.id} onClick={() => onChange(i.id)}
          className={`border-0 rounded-md px-2.5 py-1 text-xs font-semibold cursor-pointer ${value === i.id ? 'bg-[#eab308] text-[#0a0e1a]' : 'bg-[#1c2233] text-[#9ca3af] hover:text-gray-200'}`}>{i.label}</button>
      ))}
    </div>
  )
}
const Row = ({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) => (
  <div className="flex justify-between text-sm"><span className="text-[#9ca3af]">{label}</span><span className={MONO} style={{ color: color || '#f3f4f6' }}>{value}</span></div>
)
function StatCell({ label, value, color, size = 20 }: { label: string; value: React.ReactNode; color?: string; size?: number }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-[#6b7280]">{label}</span>
      <span className={`${MONO} font-semibold`} style={{ color: color || '#f3f4f6', fontSize: size }}>{value}</span>
    </div>
  )
}
function MarketTile({ l, v, c }: { l: string; v: string; c?: string }) {
  return <Card className="p-[14px_16px] flex flex-col gap-1.5"><span className="text-xs text-[#6b7280]">{l}</span><span className="text-[15px] font-semibold" style={{ color: c || '#f3f4f6' }}>{v}</span></Card>
}
function MarketCard({ title, sub, rows }: { title: string; sub: string; rows: { l: string; v: React.ReactNode; c?: string }[] }) {
  return (
    <Card className="p-[18px_20px] flex flex-col gap-3">
      <div className="flex flex-col gap-0.5"><span className="text-[15px] font-semibold">{title}</span><span className="text-xs text-[#6b7280]">{sub}</span></div>
      {rows.map(r => <Row key={r.l} label={r.l} value={r.v} color={r.c} />)}
    </Card>
  )
}

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

function CandleChart({ bars, sl, ll, flip, price, d }: { bars: Bar[]; sl?: number | null; ll?: number | null; flip?: number | null; price?: number | null; d: number }) {
  if (bars.length < 2) return <div className="h-[320px] flex items-center justify-center text-sm text-[#6b7280]">Waiting for scan prices to build bars…</div>
  const W = 700, H = 320, R0 = 80
  const lv = [sl, ll, flip].filter((v): v is number => !!v)
  let lo = Math.min(...bars.map(b => b.l), ...lv), hi = Math.max(...bars.map(b => b.h), ...lv)
  const pad = (hi - lo) * 0.07 || Math.abs(hi) * 0.001; lo -= pad; hi += pad
  const y = (v: number) => ((hi - v) / (hi - lo)) * H
  const cw = (W - R0) / bars.length
  const lines: [string, number | undefined | null, string, string | undefined][] = [
    ['SHORT LIQ', sl, '#3b82f6', undefined], ['GEX FLIP', flip, '#f59e0b', '6 4'], ['LONG LIQ', ll, '#8b5cf6', undefined],
  ]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block">
      {[0, 1, 2, 3, 4].map(i => { const v = lo + (hi - lo) * (i + 0.5) / 5; return (
        <g key={i}><line x1={0} x2={W - R0} y1={y(v)} y2={y(v)} stroke="#161b28" /><text x={W - R0 + 8} y={y(v) + 4} fill="#6b7280" fontSize={11} className="font-[Geist_Mono,monospace]">{px(v, d)}</text></g>
      ) })}
      {lines.map(([l, v, col, dash]) => v ? (
        <g key={l}>
          <line x1={0} x2={W - R0} y1={y(v)} y2={y(v)} stroke={col} strokeWidth={1.5} strokeDasharray={dash} />
          <text x={8} y={y(v) - 8} fill={col} fontSize={10} fontWeight={600} letterSpacing={0.8}>{l}  {px(v, d)}</text>
        </g>
      ) : null)}
      {bars.map((b, i) => { const x = i * cw + cw / 2, col = b.c >= b.o ? G : R; return (
        <g key={i}><line x1={x} x2={x} y1={y(b.h)} y2={y(b.l)} stroke={col} /><rect x={x - cw * 0.32} width={cw * 0.64} y={y(Math.max(b.o, b.c))} height={Math.max(1, Math.abs(y(b.o) - y(b.c)))} fill={col} rx={1} /></g>
      ) })}
      {price ? (
        <g>
          <line x1={0} x2={W - R0} y1={y(price)} y2={y(price)} stroke="#eab308" strokeDasharray="2 3" />
          <rect x={W - R0 + 2} y={y(price) - 10} width={R0 - 2} height={20} rx={4} fill="#eab308" />
          <text x={W - R0 + 6} y={y(price) + 4} fill="#0a0e1a" fontSize={11} fontWeight={700} className="font-[Geist_Mono,monospace]">{px(price, d)}</text>
        </g>
      ) : null}
    </svg>
  )
}

// Dashed baseline sits at starting capital (design token #4b5563).
function EquityChart({ points, start, animKey }: { points: number[]; start: number; animKey: string }) {
  if (points.length < 2) return <div className="h-full flex items-center justify-center text-sm text-[#6b7280]">Equity will appear after trades close</div>
  const mn = Math.min(start, ...points), mx = Math.max(start, ...points), pad = (mx - mn) * 0.12 || 50
  const y = (v: number) => 200 - ((v - mn + pad) / (mx - mn + 2 * pad)) * 200
  const line = points.map((v, i) => `${i ? 'L' : 'M'}${(i / (points.length - 1) * 1000).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  return (
    <div className="relative h-full">
      <svg key={animKey} viewBox="0 0 1000 200" preserveAspectRatio="none" className="w-full h-full block">
        <line x1={0} x2={1000} y1={y(start)} y2={y(start)} stroke="#4b5563" strokeDasharray="4 5" vectorEffect="non-scaling-stroke" />
        <path d={`${line} L1000 200 L0 200 Z`} fill="rgba(234,179,8,.10)" className="ag-fade" />
        <path d={line} pathLength={1} strokeDasharray={1} fill="none" stroke="#eab308" strokeWidth={2} vectorEffect="non-scaling-stroke" className="ag-draw" />
      </svg>
    </div>
  )
}

function CoinChip({ coin, active, price, chg, onClick }: { coin: Coin; active: boolean; price: number | null; chg: number | null; onClick: () => void }) {
  const m = META[coin]
  return (
    <button onClick={onClick} className={`flex-none flex items-center gap-[7px] rounded-lg px-2.5 py-2 whitespace-nowrap transition-colors ${active ? 'bg-[#1a1f2e]' : 'hover:bg-[#1a1f2e]'}`} title={px(price, m.d)}>
      <Dot color={m.color} size={7} />
      <span className="text-[13px] font-semibold">{m.sym}</span>
      <span className={`${MONO} text-xs`} style={{ color: chg == null ? '#9ca3af' : pnlColor(chg) }}>{pct(chg)}</span>
    </button>
  )
}

// ------------------------------------------------------------------ page

export default function PerpetualsCryptoContent() {
  const sidebarPadding = useSidebarPadding()
  const router = useRouter()
  const params = useSearchParams()

  const initialCoin = (params.get('coin') || '').toLowerCase()
  const initialTab = (params.get('tab') || 'overview') as TabId
  const [view, setView] = useState<'overview' | Coin>(
    (COINS as string[]).includes(initialCoin) ? (initialCoin as Coin) : 'overview'
  )
  const [tab, setTab] = useState<TabId>(TABS.some(t => t.id === initialTab) ? initialTab : 'overview')
  const [range, setRange] = useState<RangePreset>('30d')
  const [openGroup, setOpenGroup] = useState<Coin | null>(null)
  const [now, setNow] = useState(Date.now())

  const isCoinView = view !== 'overview'
  const curCoin: Coin = isCoinView ? (view as Coin) : 'btc'

  const goOverview = () => {
    setView('overview')
    router.replace('/perpetuals-crypto', { scroll: false })
  }
  const goCoin = (c: Coin) => {
    setView(c)
    setTab('overview')
    router.replace(`?coin=${c}&tab=overview`, { scroll: false })
  }
  const changeTab = (t: TabId) => {
    setTab(t)
    if (isCoinView) router.replace(`?coin=${curCoin}&tab=${t}`, { scroll: false })
  }

  // Only fetch the heavier per-coin endpoints (snapshot / GEX mapping) for
  // whichever bot is actually on screen.
  const o = (c: Coin) => ({ snapshot: view === c && (tab === 'market' || tab === 'overview'), mapping: view === c && tab === 'config' })
  const bots: Record<Coin, BotData> = {
    btc: useBot('btc', o('btc')), eth: useBot('eth', o('eth')), xrp: useBot('xrp', o('xrp')),
    sol: useBot('sol', o('sol')), doge: useBot('doge', o('doge')), avax: useBot('avax', o('avax')),
    shib: useBot('shib', o('shib')),
  }
  const list = COINS.map(c => bots[c])
  const cur = bots[curCoin]

  const { trades, hasMore, loadMore, isLoading: tradesLoading } = useAgapePerpTrades({
    bots: COINS.map(c => BOT_ID[c]), range,
  })

  useMemo(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  // ---- derived stats, per bot ----
  const stat = (b: BotData) => {
    const realized = realizedOf(b), unreal = unrealOf(b)
    const price = livePrice(b), first = firstPrice(b)
    return {
      realized, unreal, tot: realized + unreal,
      wr: (b.perf?.win_rate ?? b.status?.paper_account?.win_rate ?? null) as number | null,
      trades: (b.perf?.total_trades ?? b.status?.paper_account?.total_trades ?? 0) as number,
      price, chg: first && price ? (price / first - 1) * 100 : null,
    }
  }
  const S: Record<Coin, ReturnType<typeof stat>> = Object.fromEntries(COINS.map(c => [c, stat(bots[c])])) as any

  const totalStart = list.reduce((a, b) => a + startOf(b), 0)
  const realized = list.reduce((a, b) => a + S[b.coin].realized, 0)
  const unreal = list.reduce((a, b) => a + S[b.coin].unreal, 0)
  const totTrades = list.reduce((a, b) => a + S[b.coin].trades, 0)
  const wAvg = totTrades ? list.reduce((a, b) => a + (S[b.coin].wr ?? 0) * S[b.coin].trades, 0) / totTrades : 0
  const allPositions = list.flatMap(b => b.positions.map(p => ({ ...p, coin: b.coin })))
  // One summary row per bot; individual lots shown only when expanded.
  const positionGroups = list
    .filter(b => b.positions.length > 0)
    .map(b => {
      const ps = b.positions
      const qty = (p: any) => Math.abs(Number(p.quantity) || 0)
      const totalQty = ps.reduce((a: number, p: any) => a + qty(p), 0)
      const avgEntry = totalQty > 0 ? ps.reduce((a: number, p: any) => a + qty(p) * (Number(p.entry_price) || 0), 0) / totalQty : null
      return {
        coin: b.coin,
        positions: ps,
        longs: ps.filter((p: any) => p.side === 'long').length,
        shorts: ps.filter((p: any) => p.side === 'short').length,
        trailing: ps.filter((p: any) => p.trailing_active).length,
        avgEntry,
        upl: ps.reduce((a: number, p: any) => a + (Number(p.unrealized_pnl) || 0), 0),
      }
    })

  // Overview: combined equity curve + last 12 closed trades across all bots.
  const equityPoints = useMemo(() => {
    const closed = [...trades].filter(t => t.close_time).sort((a, b) => new Date(a.close_time!).getTime() - new Date(b.close_time!).getTime())
    let eq = totalStart + realized - closed.reduce((a, t) => a + (t.realized_pnl || 0), 0)
    const pts = [eq]; for (const t of closed) { eq += t.realized_pnl || 0; pts.push(eq) }
    pts.push(eq + unreal)
    return pts
  }, [trades, totalStart, realized, unreal])

  const recentTrades = useMemo(
    () => [...trades].filter(t => t.close_time).sort((a, b) => new Date(b.close_time!).getTime() - new Date(a.close_time!).getTime()).slice(0, 12),
    [trades]
  )

  // Coin view: this bot's trades only, from the same shared fetch/range.
  const coinTradesList = useMemo(() => trades.filter(t => t.bot_id === BOT_ID[curCoin]), [trades, curCoin])
  const coinStart = startOf(cur), coinRealized = S[curCoin].realized, coinUnreal = S[curCoin].unreal
  const coinEquityPoints = useMemo(() => {
    const closed = [...coinTradesList].filter(t => t.close_time).sort((a, b) => new Date(a.close_time!).getTime() - new Date(b.close_time!).getTime())
    let eq = coinStart + coinRealized - closed.reduce((a, t) => a + (t.realized_pnl || 0), 0)
    const pts = [eq]; for (const t of closed) { eq += t.realized_pnl || 0; pts.push(eq) }
    pts.push(eq + coinUnreal)
    return pts
  }, [coinTradesList, coinStart, coinRealized, coinUnreal])

  const curPrice = S[curCoin].price
  const curBars = useMemo(() => barsFromScans(curCoin, cur.scans), [curCoin, cur.scans])
  const snap = cur.snapshot
  const aggressive = cur.status?.aggressive_features || {}

  const perfMetrics = useMemo(() => {
    const wins = coinTradesList.filter(t => t.realized_pnl > 0)
    const losses = coinTradesList.filter(t => t.realized_pnl < 0)
    const sumWin = wins.reduce((a, t) => a + t.realized_pnl, 0)
    const sumLoss = losses.reduce((a, t) => a + t.realized_pnl, 0)
    const dir = cur.status?.aggressive_features?.direction_tracker || {}
    return [
      { l: 'Profit factor', v: losses.length ? (sumWin / -sumLoss).toFixed(2) : '—' },
      { l: 'Avg win', v: wins.length ? money(sumWin / wins.length) : '—', c: G },
      { l: 'Avg loss', v: losses.length ? money(sumLoss / losses.length) : '—', c: R },
      { l: 'Realized', v: money(coinRealized, true), c: pnlColor(coinRealized) },
      { l: 'Unrealized', v: money(coinUnreal, true), c: pnlColor(coinUnreal) },
      { l: 'Best trade', v: coinTradesList.length ? money(Math.max(...coinTradesList.map(t => t.realized_pnl)), true) : '—', c: G },
      { l: 'Worst trade', v: coinTradesList.length ? money(Math.min(...coinTradesList.map(t => t.realized_pnl)), true) : '—', c: R },
      { l: 'Direction L / S', v: dir.long_win_rate != null ? `${(dir.long_win_rate * 100).toFixed(0)}% / ${(dir.short_win_rate * 100).toFixed(0)}%` : '—' },
    ]
  }, [coinTradesList, coinRealized, coinUnreal, cur.status])

  const riskRows = useMemo(() => {
    const aggr = cur.status?.aggressive_features || {}
    return [
      { l: 'Mode', v: (cur.status?.mode || 'paper').toUpperCase(), c: '#eab308' },
      { l: 'Capital', v: money(META[curCoin].cap) },
      { l: 'No-loss trailing', v: aggr.use_no_loss_trailing ? 'ACTIVE' : 'OFF', c: aggr.use_no_loss_trailing ? G : '#6b7280' },
      { l: 'Stop-and-reverse', v: aggr.use_sar ? 'ACTIVE' : 'OFF', c: aggr.use_sar ? G : '#6b7280' },
      { l: 'Loss-streak pause', v: 'after 3 consecutive losses' },
      { l: 'Consecutive losses', v: aggr.consecutive_losses ?? 0, c: (aggr.consecutive_losses || 0) >= 3 ? R : undefined },
      { l: 'Scan interval', v: `${cur.status?.scan_interval_minutes ?? 5} min` },
    ]
  }, [cur.status, curCoin])

  const mapRows = useMemo(() => {
    if (cur.mapping?.mappings?.length) {
      return cur.mapping.mappings.map((m: any) => ({ a: m.gex_concept, b: m.crypto_equivalent }))
    }
    // GEX -> crypto concept mapping is a fixed design mapping (not a live
    // metric) — used only when a bot hasn't returned its own mapping yet.
    return [
      { a: 'Gamma regime', b: 'Funding rate' },
      { a: 'GEX directional bias', b: 'Long / short ratio' },
      { a: 'Gamma walls / magnets', b: 'Liquidation clusters' },
      { a: 'Net GEX', b: 'Crypto GEX (Deribit)' },
    ]
  }, [cur.mapping])

  const primaryLastScan = bots.btc.status?.heartbeat?.last_scan_iso || bots.btc.status?.last_scan_iso
    || list.map(b => b.status?.heartbeat?.last_scan_iso || b.status?.last_scan_iso).find(Boolean)
  const lastScan = isCoinView
    ? (cur.status?.heartbeat?.last_scan_iso || cur.status?.last_scan_iso || primaryLastScan)
    : primaryLastScan
  const secsToScan = lastScan ? Math.max(0, 300 - Math.floor((now - new Date(lastScan).getTime()) / 1000) % 300) : null
  const nextScanLabel = secsToScan != null ? `${Math.floor(secsToScan / 60)}:${String(secsToScan % 60).padStart(2, '0')}` : '—:—'

  if (list.every(b => b.loading)) {
    return (
      <>
        <Navigation />
        <div className="flex items-center justify-center h-screen bg-[#0a0e1a]">
          <LoadingState message="Loading AGAPE Derivatives..." />
        </div>
      </>
    )
  }

  const tradeRow = (t: Trade) => {
    const c = COIN_OF_BOT_ID[t.bot_id] || 'btc'
    const m = META[c]
    return {
      id: `${t.bot_id}-${t.position_id}`,
      time: t.close_time ? new Date(t.close_time).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—',
      sym: m.sym, dot: m.color,
      side: (t.side || '').toUpperCase(), sideColor: t.side === 'long' ? G : R,
      qty: t.quantity,
      entry: px(t.entry_price, m.d), close: px(t.close_price, m.d),
      pnl: money(t.realized_pnl, true), pnlColor: pnlColor(t.realized_pnl),
      pctv: t.realized_pnl_pct != null ? pct(t.realized_pnl_pct) : '—',
      reason: t.close_reason || '—',
    }
  }

  const botRow = (c: Coin) => {
    const st = S[c], m = META[c], b = bots[c]
    return {
      coin: c, sym: m.sym, name: m.name, dot: m.color,
      price: px(st.price, m.d), cap: money(m.cap),
      pnl: money(st.tot, true), pnlColor: pnlColor(st.tot),
      ret: pct(st.tot / m.cap * 100),
      wr: st.wr == null ? '—' : `${Number(st.wr).toFixed(1)}%`,
      trades: st.trades, open: b.positions.length,
      status: b.status?.status || 'IDLE', statusColor: b.status?.status === 'ACTIVE' ? G : '#6b7280',
    }
  }

  const BOT_ROW_COLS = 'minmax(200px,1.6fr) repeat(6,minmax(84px,1fr)) 56px 84px'

  return (
    <>
      <Navigation />
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap" />
      <style>{`
        @keyframes ag-draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
        @keyframes ag-fade{from{opacity:0}to{opacity:1}}
        .ag-draw{animation:ag-draw 1.4s ease-out both}
        .ag-fade{animation:ag-fade 1.4s ease both}
      `}</style>
      <main
        className={`min-h-screen bg-[#0a0e1a] text-[#f3f4f6] pt-16 transition-all duration-300 ${sidebarPadding}`}
        style={{ fontFamily: "'Geist', system-ui, sans-serif" }}
      >
        <div className="max-w-[1280px] mx-auto flex flex-col gap-6" style={{ padding: '28px 24px 72px' }}>

          {/* PAGE HEADER */}
          <div className="flex flex-wrap justify-between items-end gap-4">
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 text-[13px] text-[#6b7280]">
                <span className="cursor-pointer text-[#9ca3af] hover:text-[#f3f4f6]" onClick={goOverview}>Crypto Perps</span>
                {isCoinView && <><span>/</span><span className="text-[#f3f4f6]">{META[curCoin].instrument}</span></>}
              </div>
              <h1 className="m-0 text-[26px] font-semibold tracking-[-0.02em]">AGAPE Derivatives</h1>
            </div>
            <div className="flex items-center gap-4 text-[13px] text-[#9ca3af]">
              <span className="flex items-center gap-2 text-[#10b981]"><span className="w-[7px] h-[7px] rounded-full bg-[#10b981]" />24/7 · next scan {nextScanLabel}</span>
              <span className="text-[#eab308] border border-[rgba(234,179,8,0.35)] rounded-md px-2 py-[3px] text-xs font-semibold">PAPER</span>
            </div>
          </div>

          {/* COIN STRIP */}
          <div className="flex items-stretch gap-1 bg-[#0c1019] border border-[#1c2233] rounded-xl p-1 overflow-x-auto" style={{ scrollbarWidth: 'none' }}>
            <button onClick={goOverview} className={`flex-none rounded-lg px-3.5 py-2 text-[13px] font-semibold transition-colors ${!isCoinView ? 'bg-[#1a1f2e] text-[#f3f4f6]' : 'text-[#9ca3af] hover:text-[#f3f4f6]'}`}>All bots</button>
            <span className="flex-none w-px bg-[#1c2233] my-1.5 mx-1" />
            {PERP_COINS.map(c => <CoinChip key={c} coin={c} active={view === c} price={S[c].price} chg={S[c].chg} onClick={() => goCoin(c)} />)}
          </div>

          {/* ================= OVERVIEW ================= */}
          {!isCoinView && (
            <div className="flex flex-col gap-6">

              {/* Summary row */}
              <div className="flex flex-wrap justify-between items-end gap-6">
                <div className="flex flex-col gap-2.5">
                  <span className="text-[13px] text-[#9ca3af]">Combined equity · {COINS.length} bots</span>
                  <span className={`${MONO} text-[52px] font-semibold tracking-[-0.03em] leading-none`}>{money(totalStart + realized + unreal)}</span>
                  <span className={`flex flex-wrap gap-4 ${MONO} text-sm`}>
                    <span className="font-semibold" style={{ color: pnlColor(realized) }}>{money(realized, true)} realized</span>
                    <span style={{ color: pnlColor(unreal) }}>{money(unreal, true)} open</span>
                    <span className="text-[#6b7280]">from {money(totalStart)}</span>
                  </span>
                </div>
                <div className="flex flex-wrap gap-8">
                  <StatCell label="Return" value={pct((realized + unreal) / (totalStart || 1) * 100)} color={pnlColor(realized + unreal)} />
                  <StatCell label="Win rate" value={totTrades ? `${wAvg.toFixed(1)}%` : '—'} />
                  <StatCell label="Trades" value={totTrades} />
                  <StatCell label="Open" value={allPositions.length} />
                </div>
              </div>

              {/* Equity curve + Open positions */}
              <div className="grid gap-5 items-start" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))' }}>
                <Card className="p-[18px_20px] flex flex-col gap-3.5">
                  <div className="flex justify-between items-center gap-3">
                    <span className="text-[15px] font-semibold">Equity curve</span>
                    <Pills items={RANGES} value={range} onChange={setRange} />
                  </div>
                  <div className="h-[200px]"><EquityChart points={equityPoints} start={totalStart} animKey={range} /></div>
                </Card>
                <Card className="flex flex-col">
                  <div className="flex justify-between items-baseline px-5 pt-[18px] pb-3.5">
                    <span className="text-[15px] font-semibold">Open positions</span>
                    <span className="text-xs text-[#6b7280]">{allPositions.length} open · {positionGroups.length} bots</span>
                  </div>
                  {positionGroups.length === 0 && <div className="px-5 py-5 border-t border-[#1c2233] text-sm text-[#6b7280]">No open positions. The bots are scanning.</div>}
                  {positionGroups.map(g => {
                    const m = META[g.coin]
                    const expanded = openGroup === g.coin
                    return (
                      <div key={g.coin} className="border-t border-[#1c2233]">
                        <div onClick={() => setOpenGroup(expanded ? null : g.coin)} className="flex justify-between items-center gap-3 px-5 py-3.5 cursor-pointer hover:bg-[#1a1f2e]">
                          <div className="flex flex-col gap-1">
                            <span className="flex items-center gap-2 text-sm font-semibold">
                              <span className="text-[10px] text-[#6b7280] w-2.5">{expanded ? '▾' : '▸'}</span>
                              <Dot color={m.color} size={7} />{m.sym}
                              <span className="text-xs font-medium text-[#9ca3af]">{g.positions.length} open</span>
                              {g.longs > 0 && <span className="text-xs" style={{ color: G }}>{g.longs}L</span>}
                              {g.shorts > 0 && <span className="text-xs" style={{ color: R }}>{g.shorts}S</span>}
                              {g.trailing > 0 && <span className="text-[11px] text-[#eab308] font-medium">{g.trailing} trailing</span>}
                            </span>
                            <span className={`${MONO} text-xs text-[#6b7280]`}>avg {px(g.avgEntry, m.d)} → {px(S[g.coin].price, m.d)}</span>
                          </div>
                          <span className={`${MONO} text-[15px] font-semibold`} style={{ color: pnlColor(g.upl) }}>{money(g.upl, true)}</span>
                        </div>
                        {expanded && (
                          <div className="bg-[#0c1019] max-h-[280px] overflow-y-auto">
                            {g.positions.map((p: any) => (
                              <div key={`${g.coin}-${p.position_id}`} onClick={() => goCoin(g.coin)} className="flex justify-between items-center gap-3 pl-11 pr-5 py-2 border-t border-[#161b28] cursor-pointer hover:bg-[#1a1f2e]">
                                <span className="flex items-center gap-2 text-xs">
                                  <span style={{ color: p.side === 'long' ? G : R }}>{(p.side || '').toUpperCase()} × {p.quantity}</span>
                                  <span className={`${MONO} text-[#6b7280]`}>{px(p.entry_price, m.d)}</span>
                                  {p.trailing_active && <span className="text-[11px] text-[#eab308]">TRAIL @ {px(p.current_stop, m.d)}</span>}
                                </span>
                                <span className={`${MONO} text-[13px] font-semibold`} style={{ color: pnlColor(p.unrealized_pnl || 0) }}>{money(p.unrealized_pnl || 0, true)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </Card>
              </div>

              {/* Bots table */}
              <Card className="overflow-hidden">
                <div className="flex justify-between items-baseline px-5 pt-[18px] pb-3.5">
                  <span className="text-[15px] font-semibold">Bots</span>
                  <span className="text-xs text-[#6b7280]">Select a bot for detail</span>
                </div>
                <div className="overflow-x-auto"><div className="min-w-[960px]">
                  <div className="grid gap-3.5 px-5 py-2.5 text-[11px] uppercase tracking-[0.08em] text-[#6b7280] border-t border-[#1c2233]" style={{ gridTemplateColumns: BOT_ROW_COLS }}>
                    <span>Bot</span><span className="text-right">Price</span><span className="text-right">Capital</span><span className="text-right">P&amp;L</span><span className="text-right">Return</span><span className="text-right">Win rate</span><span className="text-right">Trades</span><span className="text-right">Open</span><span className="text-right">Status</span>
                  </div>
                  <div className="px-5 py-2 bg-[#0c1019] border-t border-[#1c2233] text-[11px] font-semibold tracking-[0.12em] text-[#9ca3af]">PERPETUALS</div>
                  {PERP_COINS.map(c => {
                    const row = botRow(c)
                    return (
                      <div key={c} onClick={() => goCoin(c)} className="grid gap-3.5 items-center px-5 py-3 border-t border-[#1c2233] text-sm cursor-pointer hover:bg-[#1a1f2e]" style={{ gridTemplateColumns: BOT_ROW_COLS }}>
                        <span className="flex items-center gap-2.5"><Dot color={row.dot} /><span className="font-semibold">{row.sym}</span><span className="text-[13px] text-[#6b7280]">{row.name}</span></span>
                        <span className={`${MONO} text-right`}>{row.price}</span>
                        <span className={`${MONO} text-right text-[#9ca3af]`}>{row.cap}</span>
                        <span className={`${MONO} text-right font-semibold`} style={{ color: row.pnlColor }}>{row.pnl}</span>
                        <span className={`${MONO} text-right`} style={{ color: row.pnlColor }}>{row.ret}</span>
                        <span className={`${MONO} text-right`}>{row.wr}</span>
                        <span className={`${MONO} text-right text-[#9ca3af]`}>{row.trades}</span>
                        <span className={`${MONO} text-right text-[#9ca3af]`}>{row.open}</span>
                        <span className="text-right text-[11px] font-semibold tracking-[0.06em]" style={{ color: row.statusColor }}>{row.status}</span>
                      </div>
                    )
                  })}
                </div></div>
              </Card>

              {/* Recent trades */}
              <Card className="overflow-hidden">
                <div className="flex flex-wrap justify-between items-center gap-3 px-5 py-4">
                  <span className="text-[15px] font-semibold">Recent trades</span>
                  <Pills items={RANGES} value={range} onChange={setRange} />
                </div>
                <div className="overflow-x-auto"><div className="min-w-[840px]">
                  <div className="grid gap-3 px-5 py-2.5 text-[11px] uppercase tracking-[0.08em] text-[#6b7280] border-t border-[#1c2233]" style={{ gridTemplateColumns: '130px 80px 70px minmax(90px,1fr) minmax(90px,1fr) 110px 80px 130px' }}>
                    <span>Closed</span><span>Bot</span><span>Side</span><span className="text-right">Entry</span><span className="text-right">Exit</span><span className="text-right">P&amp;L</span><span className="text-right">%</span><span>Reason</span>
                  </div>
                  {recentTrades.length === 0 && <div className="px-5 py-[22px] border-t border-[#1c2233] text-sm text-[#6b7280]">No closed trades in this range.</div>}
                  {recentTrades.map(tradeRow).map(t => (
                    <div key={t.id} className="grid gap-3 items-center px-5 py-[11px] border-t border-[#1c2233] text-sm" style={{ gridTemplateColumns: '130px 80px 70px minmax(90px,1fr) minmax(90px,1fr) 110px 80px 130px' }}>
                      <span className={`${MONO} text-[13px] text-[#9ca3af]`}>{t.time}</span>
                      <span className="flex items-center gap-2 font-semibold"><Dot color={t.dot} size={7} />{t.sym}</span>
                      <span className="text-xs font-semibold" style={{ color: t.sideColor }}>{t.side}</span>
                      <span className={`${MONO} text-right`}>{t.entry}</span>
                      <span className={`${MONO} text-right`}>{t.close}</span>
                      <span className={`${MONO} text-right font-semibold`} style={{ color: t.pnlColor }}>{t.pnl}</span>
                      <span className={`${MONO} text-right text-[13px]`} style={{ color: t.pnlColor }}>{t.pctv}</span>
                      <span className="text-xs text-[#9ca3af]">{t.reason}</span>
                    </div>
                  ))}
                </div></div>
              </Card>
            </div>
          )}

          {/* ================= COIN VIEW ================= */}
          {isCoinView && (
            <div className="flex flex-col gap-5">

              {/* Coin header */}
              <div className="flex flex-wrap justify-between items-end gap-6">
                <div className="flex flex-col gap-2.5">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <span className="w-[10px] h-[10px] rounded-full" style={{ background: META[curCoin].color }} />
                    <span className="text-xl font-semibold">{META[curCoin].instrument}</span>
                    <span className="text-sm text-[#6b7280]">{META[curCoin].name} · {META[curCoin].type === 'PERP' ? 'Perpetual' : 'Monthly future'}</span>
                    <span className="text-[11px] font-semibold tracking-[0.06em] border border-[#1c2233] rounded-md px-2 py-[3px]" style={{ color: cur.status?.status === 'ACTIVE' ? G : '#6b7280' }}>{cur.status?.status || 'IDLE'}</span>
                  </div>
                  <div className="flex items-baseline gap-3.5">
                    <span className={`${MONO} text-[44px] font-semibold tracking-[-0.03em] leading-none`}>{curPrice == null ? '—' : `$${px(curPrice, META[curCoin].d)}`}</span>
                    <span className={`${MONO} text-base`} style={{ color: pnlColor(S[curCoin].chg || 0) }}>{pct(S[curCoin].chg)}</span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-8">
                  <StatCell label="Capital" value={money(META[curCoin].cap)} size={18} />
                  <StatCell label="P&L" value={money(S[curCoin].tot, true)} color={pnlColor(S[curCoin].tot)} size={18} />
                  <StatCell label="Return" value={pct(S[curCoin].tot / META[curCoin].cap * 100)} color={pnlColor(S[curCoin].tot)} size={18} />
                  <StatCell label="Win rate" value={S[curCoin].wr == null ? '—' : `${Number(S[curCoin].wr).toFixed(1)}%`} size={18} />
                  <StatCell label="Trades" value={S[curCoin].trades} size={18} />
                </div>
              </div>

              {/* Tabs */}
              <div className="flex gap-1 overflow-x-auto" style={{ boxShadow: 'inset 0 -1px 0 #1c2233', scrollbarWidth: 'none' }}>
                {TABS.map(t => (
                  <button key={t.id} onClick={() => changeTab(t.id)} className="flex-none border-0 bg-transparent px-3.5 py-2.5 text-sm font-semibold cursor-pointer"
                    style={{ color: tab === t.id ? '#f3f4f6' : '#9ca3af', borderBottom: `2px solid ${tab === t.id ? '#eab308' : 'transparent'}` }}>
                    {t.label}
                  </button>
                ))}
              </div>

              {/* Overview tab */}
              {tab === 'overview' && (
                <div className="flex flex-col gap-5">
                  {(aggressive.consecutive_losses || 0) > 0 && (
                    <div className="flex items-center gap-2.5 border rounded-xl px-4 py-3 text-sm" style={{ borderColor: 'rgba(249,115,22,0.45)', background: 'rgba(249,115,22,0.08)' }}>
                      <Dot color="#f97316" size={8} />
                      <span className="font-semibold" style={{ color: '#fdba74' }}>{META[curCoin].sym} loss streak: {aggressive.consecutive_losses}</span>
                      <span className="text-[#9ca3af]">Bot pauses after 3 consecutive losses.</span>
                    </div>
                  )}

                  <Card className="overflow-hidden">
                    <div className="flex flex-wrap justify-between items-center gap-3 px-5 py-3.5 border-b border-[#1c2233]">
                      <div className="flex items-baseline gap-3">
                        <span className="text-[15px] font-semibold">Price · 5m</span>
                        <span className="text-xs text-[#6b7280]">built from bot scan prices</span>
                      </div>
                      <div className="flex flex-wrap gap-3.5 text-xs font-semibold">
                        <span style={{ color: '#3b82f6' }}>— Short liq</span>
                        <span style={{ color: '#f59e0b' }}>- - GEX flip</span>
                        <span style={{ color: '#8b5cf6' }}>— Long liq</span>
                        {snap?.signals?.combined_signal && <span style={{ color: sigColor(snap.signals.combined_signal) }}>{snap.signals.combined_signal}{snap.signals.combined_confidence ? ` (${snap.signals.combined_confidence})` : ''}</span>}
                      </div>
                    </div>
                    <div className="flex flex-wrap">
                      <div className="flex-[1_1_520px] min-w-0 pt-4 pb-2 pl-5 pr-2">
                        <CandleChart bars={curBars} sl={snap?.liquidations?.nearest_short_liq} ll={snap?.liquidations?.nearest_long_liq} flip={snap?.crypto_gex?.flip_point} price={curPrice} d={META[curCoin].d} />
                      </div>
                      <div className="flex-[1_0_240px] border-l border-[#1c2233] p-4 flex flex-col gap-1">
                        <div className="text-[13px] font-semibold mb-1.5">Liquidation clusters</div>
                        {(() => {
                          const cl: any[] = (snap?.liquidations?.top_clusters || []).slice(0, 12)
                          if (!cl.length) return <div className="text-xs text-[#6b7280]">No cluster data yet</div>
                          const p = curPrice || 0
                          const w = (c: any) => c.intensity === 'HIGH' ? 100 : c.intensity === 'ELEVATED' ? 66 : 33
                          return [...cl].sort((a, b) => b.price - a.price).map((c, i) => (
                            <div key={i} className="grid items-center gap-1.5 h-[24px]" style={{ gridTemplateColumns: '84px 1fr 48px' }}>
                              <span className={`${MONO} text-[11px] text-[#9ca3af]`}>{px(c.price, META[curCoin].d)}</span>
                              <span className="h-2.5 rounded-sm" style={{ width: `${w(c)}%`, background: c.price > p ? '#3b82f6' : '#8b5cf6' }} />
                              <span className={`${MONO} text-[10px] text-[#6b7280] text-right`}>{c.distance_pct}%</span>
                            </div>
                          ))
                        })()}
                        <div className="text-[11px] text-[#6b7280] mt-1.5 leading-snug">Blue: shorts liquidated above price. Violet: longs below.</div>
                      </div>
                    </div>
                  </Card>

                  <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))' }}>
                    <Card className="flex flex-col">
                      <span className="px-5 pt-[18px] pb-3.5 text-[15px] font-semibold">Open position</span>
                      {cur.positions.length === 0 && <div className="px-5 py-5 border-t border-[#1c2233] text-sm text-[#6b7280]">Flat. Scanning every 5 minutes.</div>}
                      {cur.positions.map((p: any) => (
                        <div key={p.position_id} className="grid gap-4 px-5 py-4 border-t border-[#1c2233]" style={{ gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
                          <div className="flex flex-col gap-1"><span className="text-xs text-[#6b7280]">Side</span><span className="text-[15px] font-semibold" style={{ color: p.side === 'long' ? G : R }}>{(p.side || '').toUpperCase()} × {p.quantity}</span></div>
                          <div className="flex flex-col gap-1"><span className="text-xs text-[#6b7280]">Unrealized</span><span className={`${MONO} text-[15px] font-semibold`} style={{ color: pnlColor(p.unrealized_pnl || 0) }}>{money(p.unrealized_pnl || 0, true)}</span></div>
                          <div className="flex flex-col gap-1"><span className="text-xs text-[#6b7280]">Entry</span><span className={`${MONO} text-[15px]`}>{px(p.entry_price, META[curCoin].d)}</span></div>
                          <div className="flex flex-col gap-1"><span className="text-xs text-[#6b7280]">Stop</span><span className={`${MONO} text-[15px] text-[#eab308]`}>{p.current_stop != null ? px(p.current_stop, META[curCoin].d) : '—'}</span></div>
                        </div>
                      ))}
                    </Card>
                    <Card className="p-[18px_20px] flex flex-col gap-3.5">
                      <div className="flex justify-between items-center gap-3"><span className="text-[15px] font-semibold">Equity</span><Pills items={RANGES} value={range} onChange={setRange} /></div>
                      <div className="h-[150px]"><EquityChart points={coinEquityPoints} start={coinStart} animKey={range + curCoin} /></div>
                    </Card>
                  </div>

                  <Card className="p-[18px_20px] flex flex-col gap-4">
                    <span className="text-[15px] font-semibold">Performance</span>
                    <div className="grid gap-[18px]" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px,1fr))' }}>
                      {perfMetrics.map(m => <StatCell key={m.l} label={m.l} value={m.v} color={m.c} size={16} />)}
                    </div>
                  </Card>
                </div>
              )}

              {/* Market tab */}
              {tab === 'market' && (
                !snap ? <Card className="p-10 text-center text-sm text-[#6b7280]">Waiting for crypto market data</Card> : (
                  <div className="flex flex-col gap-5">
                    <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px,1fr))' }}>
                      <MarketTile l="Combined signal" v={snap.signals?.combined_signal ? `${snap.signals.combined_signal}${snap.signals.combined_confidence ? ' · ' + snap.signals.combined_confidence : ''}` : '—'} c={sigColor(snap.signals?.combined_signal)} />
                      <MarketTile l="Leverage regime" v={snap.signals?.leverage_regime || '—'} />
                      <MarketTile l="Direction bias" v={snap.signals?.directional_bias || '—'} c={sigColor(snap.signals?.directional_bias)} />
                      <MarketTile l="Squeeze risk" v={snap.signals?.squeeze_risk || '—'} c={riskColor(snap.signals?.squeeze_risk)} />
                      <MarketTile l="Volatility" v={snap.signals?.volatility_regime || '—'} />
                    </div>
                    <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px,1fr))' }}>
                      <MarketCard title="Funding rate" sub="Replaces: Gamma regime" rows={[
                        { l: 'Current', v: snap.funding?.rate != null ? `${(snap.funding.rate * 100).toFixed(4)}%` : '—' },
                        { l: 'Predicted', v: snap.funding?.predicted != null ? `${(snap.funding.predicted * 100).toFixed(4)}%` : '—' },
                        { l: 'Regime', v: snap.funding?.regime || '—', c: sigColor(snap.funding?.regime) },
                        { l: 'Annualized', v: snap.funding?.annualized != null ? `${(snap.funding.annualized * 100).toFixed(1)}%` : '—' },
                      ]} />
                      <MarketCard title="Long / short ratio" sub="Replaces: GEX directional bias" rows={[
                        { l: 'Ratio', v: snap.long_short?.ratio != null ? snap.long_short.ratio.toFixed(2) : '—' },
                        { l: 'Long', v: snap.long_short?.long_pct != null ? `${snap.long_short.long_pct.toFixed(1)}%` : '—', c: G },
                        { l: 'Short', v: snap.long_short?.short_pct != null ? `${snap.long_short.short_pct.toFixed(1)}%` : '—', c: R },
                        { l: 'Bias', v: snap.long_short?.bias || '—', c: sigColor(snap.long_short?.bias) },
                      ]} />
                      <MarketCard title="Liquidation clusters" sub="Replaces: Gamma walls / price magnets" rows={[
                        { l: 'Nearest short liq', v: snap.liquidations?.nearest_short_liq ? `$${px(snap.liquidations.nearest_short_liq, META[curCoin].d)}` : '—', c: '#93c5fd' },
                        { l: 'Nearest long liq', v: snap.liquidations?.nearest_long_liq ? `$${px(snap.liquidations.nearest_long_liq, META[curCoin].d)}` : '—', c: '#c4b5fd' },
                        { l: 'Cluster count', v: snap.liquidations?.cluster_count ?? '—' },
                      ]} />
                      <MarketCard title="Crypto GEX (Deribit)" sub="Direct equivalent of Net GEX" rows={[
                        { l: 'Net GEX', v: snap.crypto_gex?.net_gex != null ? snap.crypto_gex.net_gex.toFixed(2) : '—', c: pnlColor(snap.crypto_gex?.net_gex || 0) },
                        { l: 'Call GEX', v: snap.crypto_gex?.call_gex != null ? snap.crypto_gex.call_gex.toFixed(2) : '—', c: G },
                        { l: 'Put GEX', v: snap.crypto_gex?.put_gex != null ? snap.crypto_gex.put_gex.toFixed(2) : '—', c: R },
                        { l: 'Flip point', v: snap.crypto_gex?.flip_point ? `$${px(snap.crypto_gex.flip_point, META[curCoin].d)}` : '—' },
                      ]} />
                    </div>
                  </div>
                )
              )}

              {/* Activity tab */}
              {tab === 'activity' && (
                <Card className="overflow-hidden">
                  <div className="px-5 py-4 text-[15px] font-semibold border-b border-[#1c2233]">Scan activity</div>
                  <div className="overflow-x-auto"><div className="min-w-[680px]">
                    <div className="grid gap-3 px-5 py-2.5 text-[11px] uppercase tracking-[0.08em] text-[#6b7280] border-t border-[#1c2233]" style={{ gridTemplateColumns: '90px 120px 170px minmax(140px,1fr) 150px' }}>
                      <span>Time</span><span className="text-right">Price</span><span>Funding</span><span>Signal</span><span>Outcome</span>
                    </div>
                    {cur.scans.length === 0 && <div className="px-5 py-[22px] border-t border-[#1c2233] text-sm text-[#6b7280]">No scan activity yet</div>}
                    {cur.scans.slice(0, 150).map((s: any, i: number) => {
                      const oc: string = s.outcome || ''
                      return (
                        <div key={i} className="grid gap-3 items-center px-5 py-2.5 border-t border-[#1c2233] text-sm" style={{ gridTemplateColumns: '90px 120px 170px minmax(140px,1fr) 150px' }}>
                          <span className={`${MONO} text-[13px] text-[#9ca3af]`}>{s.timestamp ? new Date(s.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</span>
                          <span className={`${MONO} text-right`}>{px(priceOf(curCoin, s), META[curCoin].d)}</span>
                          <span className="text-xs text-[#9ca3af]">{s.funding_regime || '—'}</span>
                          <span className="text-xs font-semibold" style={{ color: sigColor(s.combined_signal) }}>{s.combined_signal || '—'}{s.combined_confidence ? ` (${s.combined_confidence})` : ''}</span>
                          <span><span className="text-[11px] font-semibold tracking-[0.04em] px-2 py-[3px] rounded-md" style={{ background: oc === 'TRADED' ? 'rgba(234,179,8,0.15)' : '#1c2233', color: oc === 'TRADED' ? '#eab308' : '#9ca3af' }}>{oc || '—'}</span></span>
                        </div>
                      )
                    })}
                  </div></div>
                </Card>
              )}

              {/* History tab */}
              {tab === 'history' && (
                <Card className="overflow-hidden">
                  <div className="flex flex-wrap justify-between items-center gap-3 px-5 py-4">
                    <span className="text-[15px] font-semibold">Closed trades</span>
                    <Pills items={RANGES} value={range} onChange={setRange} />
                  </div>
                  <div className="overflow-x-auto"><div className="min-w-[820px]">
                    <div className="grid gap-3 px-5 py-2.5 text-[11px] uppercase tracking-[0.08em] text-[#6b7280] border-t border-[#1c2233]" style={{ gridTemplateColumns: '130px 70px 90px minmax(90px,1fr) minmax(90px,1fr) 110px 80px 130px' }}>
                      <span>Closed</span><span>Side</span><span className="text-right">Qty</span><span className="text-right">Entry</span><span className="text-right">Exit</span><span className="text-right">P&amp;L</span><span className="text-right">%</span><span>Reason</span>
                    </div>
                    {tradesLoading && <div className="px-5 py-5 border-t border-[#1c2233] text-sm text-[#6b7280]">Loading trades…</div>}
                    {!tradesLoading && coinTradesList.length === 0 && <div className="px-5 py-[22px] border-t border-[#1c2233] text-sm text-[#6b7280]">No closed trades in this range.</div>}
                    {[...coinTradesList].sort((a, b) => new Date(b.close_time || 0).getTime() - new Date(a.close_time || 0).getTime()).map(t => (
                      <div key={`${t.bot_id}-${t.position_id}`} className="grid gap-3 items-center px-5 py-2.5 border-t border-[#1c2233] text-sm" style={{ gridTemplateColumns: '130px 70px 90px minmax(90px,1fr) minmax(90px,1fr) 110px 80px 130px' }}>
                        <span className={`${MONO} text-[13px] text-[#9ca3af]`}>{t.close_time ? new Date(t.close_time).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}</span>
                        <span className="text-xs font-semibold" style={{ color: t.side === 'long' ? G : R }}>{(t.side || '').toUpperCase()}</span>
                        <span className={`${MONO} text-right`}>{t.quantity}</span>
                        <span className={`${MONO} text-right`}>{px(t.entry_price, META[curCoin].d)}</span>
                        <span className={`${MONO} text-right`}>{px(t.close_price, META[curCoin].d)}</span>
                        <span className={`${MONO} text-right font-semibold`} style={{ color: pnlColor(t.realized_pnl) }}>{money(t.realized_pnl, true)}</span>
                        <span className={`${MONO} text-right text-[13px]`} style={{ color: pnlColor(t.realized_pnl) }}>{t.realized_pnl_pct != null ? pct(t.realized_pnl_pct) : '—'}</span>
                        <span className="text-xs text-[#9ca3af]">{t.close_reason || '—'}</span>
                      </div>
                    ))}
                    {hasMore && <button onClick={loadMore} className="w-full py-3 border-t border-[#1c2233] text-sm text-[#eab308] hover:bg-[#1a1f2e]">Load more</button>}
                  </div></div>
                </Card>
              )}

              {/* Config tab */}
              {tab === 'config' && (
                <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(340px,1fr))' }}>
                  <Card className="p-[18px_20px] flex flex-col gap-3">
                    <span className="text-[15px] font-semibold">Risk controls</span>
                    {riskRows.map(r => <Row key={r.l} label={r.l} value={r.v} color={r.c} />)}
                  </Card>
                  <Card className="p-[18px_20px] flex flex-col gap-3">
                    <div className="flex flex-col gap-0.5"><span className="text-[15px] font-semibold">GEX → crypto signal mapping</span><span className="text-xs text-[#6b7280]">How options-market concepts translate for this bot</span></div>
                    {mapRows.map((r: { a: string; b: string }, i: number) => (
                      <div key={i} className="grid gap-2 items-center pt-3 border-t border-[#1c2233]" style={{ gridTemplateColumns: 'minmax(0,1fr) 20px minmax(0,1fr)' }}>
                        <span className="text-sm text-[#9ca3af]">{r.a}</span><span className="text-[#6b7280] text-center">→</span><span className="text-sm">{r.b}</span>
                      </div>
                    ))}
                  </Card>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </>
  )
}
