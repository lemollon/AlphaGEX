'use client'

import { useState, useEffect } from 'react'
import { getCTNow, getCTMinutes, isMarketOpen } from '@/lib/pt-tiers'

/**
 * Horizontal timeline showing the three PT zones with a real-time "you are here" marker.
 *
 * Zones (CT):
 *   Morning  30%  8:30 – 10:30   (120 min)
 *   Midday   20%  10:30 – 1:00   (150 min)
 *   Afternoon 15%  1:00 – 2:45   (105 min)
 *   EOD           2:45 – 3:00    (15 min)
 *   Total = 390 min
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

export default function PTTimeline() {
  // Initialize with null to avoid hydration mismatch (server has no CT clock)
  const [ctMins, setCtMins] = useState<number | null>(null)
  const [open, setOpen] = useState<boolean | null>(null)
  const [timeStr, setTimeStr] = useState<string | null>(null)

  // Resolve on client only, then tick every second
  useEffect(() => {
    function tick() {
      const d = getCTNow()
      setCtMins(getCTMinutes(d))
      setOpen(isMarketOpen(d))
      setTimeStr(d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }))
    }
    tick() // immediate first tick
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [])

  // Don't render until client-side time is resolved (prevents hydration mismatch)
  if (ctMins === null || open === null) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/60 px-4 py-3 opacity-40">
        <div className="h-3 rounded-full bg-forge-border" />
      </div>
    )
  }

  // Marker position (clamped to bar range)
  const markerMin = Math.max(MARKET_OPEN, Math.min(MARKET_CLOSE, ctMins))
  const markerPct = ((markerMin - MARKET_OPEN) / TOTAL) * 100

  const grayed = !open

  return (
    <div className={`rounded-xl border border-forge-border bg-forge-card/60 px-4 py-3 ${grayed ? 'opacity-40' : ''}`}>
      {/* Zone labels above bar */}
      <div className="relative h-4 text-[10px] font-medium mb-0.5" style={{ marginLeft: '0', marginRight: '0' }}>
        <span
          className="absolute text-emerald-400"
          style={{ left: pct(MARKET_OPEN), width: widthPct(MARKET_OPEN, MIDDAY_START), textAlign: 'center', display: 'inline-block' }}
        >
          Morning 30%
        </span>
        <span
          className="absolute text-yellow-400"
          style={{ left: pct(MIDDAY_START), width: widthPct(MIDDAY_START, AFTERNOON_START), textAlign: 'center', display: 'inline-block' }}
        >
          Midday 20%
        </span>
        <span
          className="absolute text-orange-400"
          style={{ left: pct(AFTERNOON_START), width: widthPct(AFTERNOON_START, EOD_START), textAlign: 'center', display: 'inline-block' }}
        >
          PM 15%
        </span>
        <span
          className="absolute text-red-400"
          style={{ left: pct(EOD_START), width: widthPct(EOD_START, MARKET_CLOSE), textAlign: 'center', display: 'inline-block' }}
        >
          EOD
        </span>
      </div>

      {/* Bar */}
      <div className="relative h-3 rounded-full overflow-hidden bg-forge-border">
        {/* Morning zone */}
        <div
          className="absolute inset-y-0 bg-emerald-500/30 rounded-l-full"
          style={{ left: '0%', width: widthPct(MARKET_OPEN, MIDDAY_START) }}
        />
        {/* Midday zone */}
        <div
          className="absolute inset-y-0 bg-yellow-500/25"
          style={{ left: pct(MIDDAY_START), width: widthPct(MIDDAY_START, AFTERNOON_START) }}
        />
        {/* Afternoon zone */}
        <div
          className="absolute inset-y-0 bg-orange-500/25"
          style={{ left: pct(AFTERNOON_START), width: widthPct(AFTERNOON_START, EOD_START) }}
        />
        {/* EOD zone */}
        <div
          className="absolute inset-y-0 bg-red-500/30 rounded-r-full"
          style={{ left: pct(EOD_START), width: widthPct(EOD_START, MARKET_CLOSE) }}
        />

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
      {open && timeStr && (
        <p className="text-[10px] text-forge-muted text-center -mt-0.5">
          ▲ {timeStr} CT
        </p>
      )}
    </div>
  )
}
