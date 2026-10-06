'use client'

import Image from 'next/image'
import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import MarketStatusBadge from './MarketStatusBadge'
import { AGENTS } from '@/lib/marketing/agents'
import { defaultHeroTab, heroAgentStripState, isMarketOpenNow, minutesSinceMidnightCT } from '@/lib/marketing/marketStatus'

type Tab = 'spark' | 'flame'

const MARKET_OPEN_MIN = 8 * 60 + 30 // 8:30 AM CT — matches AXIS_TICKS' left edge (x=10)
const MARKET_CLOSE_MIN = 15 * 60 // 3:00 PM CT — matches AXIS_TICKS' right edge (x=510)
const CHART_X_START = 10
const CHART_X_END = 510
const VIEWBOX_WIDTH = 520

/** Minutes-since-midnight CT -> chart x (viewBox units), clamped to the session. */
function minutesToChartX(minutes: number): number {
  const clamped = Math.min(Math.max(minutes, MARKET_OPEN_MIN), MARKET_CLOSE_MIN)
  const frac = (clamped - MARKET_OPEN_MIN) / (MARKET_CLOSE_MIN - MARKET_OPEN_MIN)
  return CHART_X_START + frac * (CHART_X_END - CHART_X_START)
}

function formatNowLabel(minutes: number): string {
  const h24 = Math.floor(minutes / 60)
  const m = minutes % 60
  const period = h24 >= 12 ? 'PM' : 'AM'
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12
  return `${h12}:${String(m).padStart(2, '0')} ${period} Central`
}

/** Chart x-axis ticks, in viewBox units (0 0 520 290) — 8:30 AM through 3 PM. */
const AXIS_TICKS: Array<{ x: number; label: string; anchor: 'start' | 'middle' | 'end' }> = [
  { x: 10, label: '8:30 AM', anchor: 'start' },
  { x: 135, label: '10 AM', anchor: 'middle' },
  { x: 260, label: 'Noon', anchor: 'middle' },
  { x: 385, label: '1:30 PM', anchor: 'middle' },
  { x: 510, label: '3 PM', anchor: 'end' },
]

const SELL_LINE_Y = 160
const PROTECTION_LINE_Y = 195

/**
 * Illustrative-only paths — NOT trading results. Each tab's session window
 * (shaded box) roughly follows that agent's real entry window; the dip-then-
 * recover shape inside it, and the flat gray line outside it, are made up.
 * Both scenarios stay above the sell line throughout — the "keeps full
 * credit" outcome the green end-of-session dot illustrates.
 */
const SESSION: Record<Tab, { startX: number; startY: number; endX: number; endY: number }> = {
  spark: { startX: 140, startY: 95, endX: 260, endY: 25 },
  flame: { startX: 365, startY: 80, endX: 495, endY: 30 },
}

const PATHS: Record<Tab, { pre: string; session: string; post: string }> = {
  spark: {
    pre: 'M10 60 C 40 58, 70 65, 100 78 S 130 90, 140 95',
    session: 'M140 95 C 160 115, 175 135, 190 145 S 220 120, 235 80 S 250 35, 260 25',
    post: 'M260 25 C 300 35, 340 42, 380 45 S 460 48, 510 42',
  },
  flame: {
    pre: 'M10 55 C 60 50, 100 65, 150 60 S 220 50, 260 58 S 320 65, 365 80',
    session: 'M365 80 C 390 85, 410 92, 430 95 S 460 70, 480 45 S 492 35, 495 30',
    post: 'M495 30 L 510 32',
  },
}

const EXPLAIN = [
  { color: 'var(--up)', title: 'Above the sell line', body: 'The trade keeps the credit it collected up front.' },
  {
    color: 'var(--warn)',
    title: 'Between the lines',
    body: 'Part of the credit is given back, or a small loss.',
  },
  { color: 'var(--bad)', title: 'Below protection', body: "The loss stops growing. It's capped from the start." },
]

/** Hero card — "How a put spread works" tabs, home page only. */
export default function PutSpreadHeroCard() {
  const [tab, setTab] = useState<Tab>('spark')
  const [nowMinutes, setNowMinutes] = useState<number | null>(null)
  const [nowTipOpen, setNowTipOpen] = useState(false)
  const didInitTab = useRef(false)

  // Default tab follows the current Central time on first paint (ps-hero #46)
  // — but only once, and never once the visitor has clicked a tab themselves.
  useEffect(() => {
    if (didInitTab.current) return
    didInitTab.current = true
    setTab(defaultHeroTab())
  }, [])

  useEffect(() => {
    const tick = () => setNowMinutes(minutesSinceMidnightCT())
    tick()
    const id = setInterval(tick, 30_000)
    return () => clearInterval(id)
  }, [])

  const path = PATHS[tab]
  const session = SESSION[tab]
  const agent = AGENTS.find((a) => a.slug === tab)!
  const colorVar = tab === 'spark' ? 'var(--spark)' : 'var(--flame)'
  const showNowMarker = nowMinutes != null && isMarketOpenNow()
  const nowX = nowMinutes != null ? minutesToChartX(nowMinutes) : null

  return (
    <div className="card" aria-label="How a trading day plays out">
      <div className="live-top">
        <span className="t">How a put spread works</span>
        <MarketStatusBadge />
      </div>
      <div className="hc-tabs" role="tablist" aria-label="Choose an agent">
        {(['spark', 'flame'] as Tab[]).map((t) => {
          const a = AGENTS.find((x) => x.slug === t)!
          return (
            <button
              key={t}
              className="hc-tab"
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              type="button"
            >
              <Image src={a.mascot} alt="" width={22} height={22} />
              {a.name}
              <span className="hc-when"> · {t === 'spark' ? 'morning' : 'afternoon'}</span>
            </button>
          )
        })}
      </div>
      <div className="hc-wrap">
        <svg
          id="dayChart"
          viewBox="0 0 520 290"
          role="img"
          aria-label={`Illustration of a put spread: the market line stays above the sell line during ${agent.name}'s session, so the trade keeps its credit. Losses are capped at the protection line.`}
        >
          <rect x={0} y={0} width={520} height={SELL_LINE_Y} fill="var(--up-soft)" opacity={0.5} />
          <rect
            x={0}
            y={SELL_LINE_Y}
            width={520}
            height={PROTECTION_LINE_Y - SELL_LINE_Y}
            fill="var(--accent-soft)"
            opacity={0.5}
          />
          <rect x={0} y={PROTECTION_LINE_Y} width={520} height={250 - PROTECTION_LINE_Y} fill="var(--bg-2)" />

          <rect
            x={session.startX}
            y={0}
            width={session.endX - session.startX}
            height={250}
            fill="var(--up)"
            fillOpacity={0.07}
          />
          <text x={session.startX + 10} y={18} className="hc-session-label">
            {agent.name}&apos;s session
          </text>

          <line x1={10} x2={510} y1={SELL_LINE_Y} y2={SELL_LINE_Y} stroke="var(--up)" strokeWidth={1.5} strokeDasharray="4 4" />
          <text x={510} y={SELL_LINE_Y - 4} textAnchor="end" className="hc-line-label" fill="var(--up)">
            Sell line
          </text>
          <line
            x1={10}
            x2={510}
            y1={PROTECTION_LINE_Y}
            y2={PROTECTION_LINE_Y}
            stroke="var(--bad)"
            strokeWidth={1.5}
            strokeDasharray="4 4"
          />
          <text x={510} y={PROTECTION_LINE_Y - 4} textAnchor="end" className="hc-line-label" fill="var(--bad)">
            Protection line
          </text>

          <path d={path.pre} fill="none" stroke="var(--muted)" strokeWidth={2} strokeLinecap="round" />
          <path d={path.session} fill="none" stroke={colorVar} strokeWidth={2.5} strokeLinecap="round" />
          <path d={path.post} fill="none" stroke="var(--muted)" strokeWidth={2} strokeLinecap="round" />

          <text
            x={session.startX - 10}
            y={session.startY - 28}
            textAnchor="end"
            className="hc-line-label"
            fill="var(--muted)"
          >
            Trade opens
          </text>
          <circle cx={session.startX} cy={session.startY} r={4} fill="var(--bg)" stroke={colorVar} strokeWidth={2} />
          <circle cx={session.endX} cy={session.endY} r={4.5} fill="var(--up)" />

          {AXIS_TICKS.map((t) => (
            <text key={t.label} x={t.x} y={272} textAnchor={t.anchor} className="hc-axis-label">
              {t.label}
            </text>
          ))}

          {/* "Now" marker during market hours — hover or tap for the time and zone (ps-hero #48). */}
          {showNowMarker && nowX != null && (
            <g
              className="hc-now"
              onMouseEnter={() => setNowTipOpen(true)}
              onMouseLeave={() => setNowTipOpen(false)}
              onClick={() => setNowTipOpen((v) => !v)}
              style={{ cursor: 'pointer' }}
            >
              <line x1={nowX} x2={nowX} y1={0} y2={250} stroke="var(--fg)" strokeWidth={1} strokeDasharray="2 3" opacity={0.55} />
              <circle cx={nowX} cy={250} r={4} fill="var(--fg)" />
            </g>
          )}
        </svg>
        {showNowMarker && nowX != null && nowTipOpen && nowMinutes != null && (
          <div
            className="hc-tip"
            role="status"
            style={{ left: `${(nowX / VIEWBOX_WIDTH) * 100}%`, top: '2px' }}
          >
            <b>Now</b>
            <span>{formatNowLabel(nowMinutes)}</span>
          </div>
        )}
      </div>
      <div className="hc-explain">
        {EXPLAIN.map((e) => (
          <div key={e.title}>
            <b>
              <i style={{ background: e.color }} />
              {e.title}
            </b>
            {e.body}
          </div>
        ))}
      </div>
      <div className="hc-agents">
        {AGENTS.map((a) => {
          // Live state once mounted ("Trading now" / "Starts …" / "Done for
          // today" — ps-hero #49); the static tagline covers SSR/first paint
          // so there's no clock-dependent hydration mismatch.
          const live =
            nowMinutes != null && (a.slug === 'spark' || a.slug === 'flame')
              ? heroAgentStripState(a.slug)
              : null
          return (
            <Link key={a.slug} className="hc-agent" href={`/agents#${a.slug}`}>
              <Image src={a.mascot} alt="" width={34} height={34} />
              <div>
                <b>{a.name}</b>
                <div className="state">
                  {a.slug === 'ember' ? <span className="muted">Smaller accounts</span> : live ?? a.tagline}
                </div>
              </div>
            </Link>
          )
        })}
      </div>
      <p className="hc-cap">Simplified illustration of a put spread at the end of a session. Not trading results.</p>
    </div>
  )
}
