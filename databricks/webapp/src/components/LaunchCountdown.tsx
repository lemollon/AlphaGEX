'use client'

import { useEffect, useState } from 'react'

/* ── Configuration ──────────────────────────────────────────────── */

/** Go-live date: March 16, 2026 at 8:30 AM Central Time (market open)
 *  John 3:16 — "For God so loved the world that he gave his one and only Son,
 *  that whoever believes in him shall not perish but have eternal life."
 *  3/16 → John 3:16. The Forge is reborn. */
const LAUNCH_DATE = new Date('2026-03-16T14:30:00Z') // 8:30 AM CT = 14:30 UTC

/* ── Helpers ────────────────────────────────────────────────────── */

interface TimeLeft {
  days: number
  hours: number
  minutes: number
  seconds: number
  total: number
}

function getTimeLeft(): TimeLeft {
  const total = Math.max(0, LAUNCH_DATE.getTime() - Date.now())
  return {
    days: Math.floor(total / (1000 * 60 * 60 * 24)),
    hours: Math.floor((total / (1000 * 60 * 60)) % 24),
    minutes: Math.floor((total / (1000 * 60)) % 60),
    seconds: Math.floor((total / 1000) % 60),
    total,
  }
}

/* ── Ember particle (pure CSS) ──────────────────────────────────── */

function Ember({ style }: { style: React.CSSProperties }) {
  return <div className="countdown-ember" style={style} />
}

/* ── Single digit card with flip animation ──────────────────────── */

function DigitCard({ value, label }: { value: number; label: string }) {
  const display = String(value).padStart(2, '0')

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="relative">
        {/* Glow behind the card */}
        <div className="absolute -inset-2 rounded-2xl bg-amber-500/10 blur-xl animate-pulse-slow" />

        <div className="relative flex gap-1">
          {display.split('').map((digit, i) => (
            <div
              key={i}
              className="
                w-[44px] h-[56px] md:w-[56px] md:h-[72px]
                rounded-lg
                bg-gradient-to-b from-forge-card via-forge-card to-[#0f0d0c]
                border border-amber-500/20
                flex items-center justify-center
                shadow-[0_0_15px_rgba(245,158,11,0.1),inset_0_1px_0_rgba(255,255,255,0.05)]
                relative overflow-hidden
              "
            >
              {/* Hot metal seam across middle */}
              <div className="absolute inset-x-0 top-1/2 h-px bg-gradient-to-r from-transparent via-amber-500/30 to-transparent" />

              <span
                className="
                  text-3xl md:text-4xl font-extrabold tabular-nums
                  text-transparent bg-clip-text
                  bg-gradient-to-b from-amber-300 via-orange-400 to-red-500
                  drop-shadow-[0_0_8px_rgba(245,158,11,0.6)]
                  relative z-10
                "
              >
                {digit}
              </span>
            </div>
          ))}
        </div>
      </div>

      <span className="text-[10px] md:text-xs uppercase tracking-[0.2em] text-amber-500/60 font-medium">
        {label}
      </span>
    </div>
  )
}

/* ── Separator (colon) ──────────────────────────────────────────── */

function Separator() {
  return (
    <div className="flex flex-col gap-2.5 pt-1 md:pt-2">
      <div className="w-1.5 h-1.5 rounded-full bg-amber-500/60 shadow-[0_0_6px_rgba(245,158,11,0.5)] animate-pulse" />
      <div className="w-1.5 h-1.5 rounded-full bg-amber-500/60 shadow-[0_0_6px_rgba(245,158,11,0.5)] animate-pulse" />
    </div>
  )
}

/* ── Main Component ─────────────────────────────────────────────── */

export default function LaunchCountdown() {
  const [time, setTime] = useState<TimeLeft>(getTimeLeft)
  const [embers, setEmbers] = useState<React.CSSProperties[]>([])
  const [mounted, setMounted] = useState(false)

  // Tick every second
  useEffect(() => {
    setMounted(true)
    const interval = setInterval(() => setTime(getTimeLeft()), 1000)
    return () => clearInterval(interval)
  }, [])

  // Generate embers on mount (client only to avoid hydration mismatch)
  useEffect(() => {
    const particles: React.CSSProperties[] = Array.from({ length: 20 }, (_, i) => ({
      left: `${5 + Math.random() * 90}%`,
      animationDelay: `${Math.random() * 4}s`,
      animationDuration: `${2 + Math.random() * 3}s`,
      opacity: 0.4 + Math.random() * 0.6,
      width: `${2 + Math.random() * 3}px`,
      height: `${2 + Math.random() * 3}px`,
    }))
    setEmbers(particles)
  }, [])

  if (time.total <= 0) {
    return (
      <div className="relative rounded-xl border border-amber-500/40 bg-forge-card/80 p-6 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-amber-500/10 to-transparent" />
        <div className="relative text-center">
          <p className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-amber-300 via-orange-400 to-red-500">
            THE FORGE IS LIVE
          </p>
          <p className="text-sm text-amber-500/60 mt-1">Iron has been tempered. Trading has begun.</p>
          <p className="text-xs text-forge-muted mt-4 italic max-w-lg mx-auto">
            &ldquo;For God so loved the world that he gave his one and only Son, that whoever believes in him shall not perish but have eternal life.&rdquo;
          </p>
          <p className="text-[10px] text-amber-500/50 mt-2 max-w-md mx-auto leading-relaxed">
            John 3:16 &middot; Iron is forged through fire, faith is refined through trials.
            On 3/16, the Forge is born again &mdash; tested by paper, tempered by patience, now alive.
          </p>
        </div>
      </div>
    )
  }

  // Progress bar: how far through the countdown (from announcement to launch)
  const totalCountdownMs = 10 * 24 * 60 * 60 * 1000
  const elapsed = totalCountdownMs - time.total
  const progressPct = Math.min(100, Math.max(0, (elapsed / totalCountdownMs) * 100))

  return (
    <div className="relative rounded-xl border border-amber-500/20 bg-forge-card/80 overflow-hidden">
      {/* ── Animated background heat ── */}
      <div className="absolute inset-0 bg-gradient-to-t from-red-900/10 via-transparent to-amber-500/5" />
      <div className="absolute bottom-0 inset-x-0 h-24 bg-gradient-to-t from-orange-600/8 to-transparent" />

      {/* ── Rising ember particles ── */}
      {mounted && embers.map((style, i) => (
        <Ember key={i} style={style} />
      ))}

      <div className="relative px-4 py-6 md:py-8">
        {/* Title */}
        <div className="text-center mb-5 md:mb-6">
          <p className="text-[10px] md:text-xs uppercase tracking-[0.3em] text-amber-500/50 font-medium mb-1">
            Forging in Progress
          </p>
          <h2 className="text-lg md:text-xl font-bold">
            <span className="text-gray-300">Days Until </span>
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-300 via-orange-400 to-red-500">
              Live Trading
            </span>
          </h2>
        </div>

        {/* Countdown digits */}
        <div className="flex items-start justify-center gap-2 md:gap-4">
          <DigitCard value={time.days} label="Days" />
          <Separator />
          <DigitCard value={time.hours} label="Hours" />
          <Separator />
          <DigitCard value={time.minutes} label="Minutes" />
          <Separator />
          <DigitCard value={time.seconds} label="Seconds" />
        </div>

        {/* Scripture reference */}
        <p className="text-center text-xs text-forge-muted mt-5 italic max-w-lg mx-auto">
          &ldquo;For God so loved the world that he gave his one and only Son, that whoever believes in him shall not perish but have eternal life.&rdquo;
        </p>
        <p className="text-center text-[10px] text-amber-500/50 mt-2 max-w-md mx-auto leading-relaxed">
          John 3:16 &middot; Iron is forged through fire, faith is refined through trials.
          On 3/16, the Forge is born again &mdash; tested by paper, tempered by patience, ready to live.
        </p>

        {/* Progress bar */}
        <div className="mt-5 md:mt-6 max-w-md mx-auto">
          <div className="flex justify-between text-[10px] text-forge-muted mb-1.5">
            <span>Paper Testing</span>
            <span>Live Trading</span>
          </div>
          <div className="h-1.5 rounded-full bg-forge-border/60 overflow-hidden relative">
            <div
              className="h-full rounded-full bg-gradient-to-r from-amber-600 via-orange-500 to-red-500 transition-all duration-1000 relative"
              style={{ width: `${progressPct}%` }}
            >
              {/* Moving glow at the tip */}
              <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-amber-400 blur-sm animate-pulse" />
            </div>
          </div>
        </div>

        {/* Launch date footer */}
        <p className="text-center text-[10px] text-forge-muted mt-3">
          Target: March 16, 2026 &middot; 8:30 AM CT &middot; Market Open
        </p>
      </div>
    </div>
  )
}
