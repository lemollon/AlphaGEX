'use client'

import { useState, useEffect } from 'react'
import { getCTNow, getCTMinutes, isMarketOpen } from '@/lib/pt-tiers'

/**
 * Horizontal timeline showing PT zones with a real-time "you are here" marker.
 *
 * Default (SPARK/FLAME):
 *   Morning  30%  8:30 – 10:30   (120 min)
 *   Midday   20%  10:30 – 1:00   (150 min)
 *   Afternoon 15%  1:00 – 2:45   (105 min)
 *   EOD           2:45 – 3:00    (15 min)
 *
 * INFERNO (0DTE):
 *   Morning  50%  8:30 – 10:30   (120 min)
 *   Midday   30%  10:30 – 1:00   (150 min)
 *   Afternoon 10%  1:00 – 2:45   (105 min)
 *   EOD           2:45 – 3:00    (15 min)
 */

const MARKET_OPEN = 510   // 8:30 AM
const MIDDAY_START = 630  // 10:30 AM
const AFTERNOON_START = 780 // 1:00 PM
const EOD_START = 885     // 2:45 PM
const MARKET_CLOSE = 900  // 3:00 PM
const TOTAL = MARKET_CLOSE - MARKET_OPEN // 390 min

function pct(minutes: number): string {
  return `${((minutes - MARKET_OPEN) / TOTAL) * 100}%`
}

function widthPct(startMin: number, endMin: number): string {
  return `${((endMin - startMin) / TOTAL) * 100}%`
}

interface PTZone {
  label: string
  color: string
  barColor: string
  start: number
  end: number
}

const DEFAULT_ZONES: PTZone[] = [
  { label: 'Morning 30%', color: 'text-emerald-400', barColor: 'bg-emerald-500/30', start: MARKET_OPEN, end: MIDDAY_START },
  { label: 'Midday 20%', color: 'text-yellow-400', barColor: 'bg-yellow-500/25', start: MIDDAY_START, end: AFTERNOON_START },
  { label: 'PM 15%', color: 'text-orange-400', barColor: 'bg-orange-500/25', start: AFTERNOON_START, end: EOD_START },
  { label: 'EOD', color: 'text-red-400', barColor: 'bg-red-500/30', start: EOD_START, end: MARKET_CLOSE },
]

const INFERNO_ZONES: PTZone[] = [
  { label: 'Morning 50%', color: 'text-emerald-400', barColor: 'bg-emerald-500/30', start: MARKET_OPEN, end: MIDDAY_START },
  { label: 'Midday 30%', color: 'text-yellow-400', barColor: 'bg-yellow-500/25', start: MIDDAY_START, end: AFTERNOON_START },
  { label: 'PM 10%', color: 'text-orange-400', barColor: 'bg-orange-500/25', start: AFTERNOON_START, end: EOD_START },
  { label: 'EOD', color: 'text-red-400', barColor: 'bg-red-500/30', start: EOD_START, end: MARKET_CLOSE },
]

export default function PTTimeline({ variant = 'default' }: { variant?: 'default' | 'inferno' }) {
  const [ctMins, setCtMins] = useState(getCTMinutes)
  const [open, setOpen] = useState(isMarketOpen)

  useEffect(() => {
    const timer = setInterval(() => {
      const d = getCTNow()
      setCtMins(getCTMinutes(d))
      setOpen(isMarketOpen(d))
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  const zones = variant === 'inferno' ? INFERNO_ZONES : DEFAULT_ZONES

  // Marker position (clamped to bar range)
  const markerMin = Math.max(MARKET_OPEN, Math.min(MARKET_CLOSE, ctMins))
  const markerPct = ((markerMin - MARKET_OPEN) / TOTAL) * 100

  // Format current CT time for the "You are here" label
  const ctNow = getCTNow()
  const timeStr = ctNow.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })

  const grayed = !open

  return (
    <div className={`rounded-xl border border-forge-border bg-forge-card/60 px-4 py-3 ${grayed ? 'opacity-40' : ''}`}>
      {/* Zone labels above bar */}
      <div className="relative h-4 text-[10px] font-medium mb-0.5" style={{ marginLeft: '0', marginRight: '0' }}>
        {zones.map((zone) => (
          <span
            key={zone.label}
            className={`absolute ${zone.color}`}
            style={{ left: pct(zone.start), width: widthPct(zone.start, zone.end), textAlign: 'center', display: 'inline-block' }}
          >
            {zone.label}
          </span>
        ))}
      </div>

      {/* Bar */}
      <div className="relative h-3 rounded-full overflow-hidden bg-forge-border">
        {zones.map((zone, i) => (
          <div
            key={zone.label}
            className={`absolute inset-y-0 ${zone.barColor} ${i === 0 ? 'rounded-l-full' : ''} ${i === zones.length - 1 ? 'rounded-r-full' : ''}`}
            style={{ left: pct(zone.start), width: widthPct(zone.start, zone.end) }}
          />
        ))}

        {/* "You are here" marker */}
        {open && (
          <div
            className="absolute top-0 h-full w-1 bg-white rounded shadow-sm shadow-white/50"
            style={{ left: `${markerPct}%`, transform: 'translateX(-50%)' }}
          />
        )}
      </div>

      {/* Time labels below bar */}
      <div className="relative h-4 text-[9px] text-forge-muted mt-0.5 font-mono">
        <span className="absolute" style={{ left: '0%' }}>8:30</span>
        <span className="absolute -translate-x-1/2" style={{ left: pct(MIDDAY_START) }}>10:30</span>
        <span className="absolute -translate-x-1/2" style={{ left: pct(AFTERNOON_START) }}>1:00</span>
        <span className="absolute -translate-x-1/2" style={{ left: pct(EOD_START) }}>2:45</span>
        <span className="absolute right-0">3:00</span>
      </div>

      {/* "You are here" label */}
      {open && (
        <p className="text-[10px] text-forge-muted text-center -mt-0.5">
          ▲ {timeStr} CT
        </p>
      )}
    </div>
  )
}
