'use client'

import { useState, useEffect } from 'react'
import { Pause, Play } from 'lucide-react'

interface PilgrimJourneyProps {
  onReachCross?: () => void
}

// Compact inline animation showing a pilgrim walking toward the cross
export default function PilgrimJourney({ onReachCross }: PilgrimJourneyProps) {
  const [isPaused, setIsPaused] = useState(false)
  const [progress, setProgress] = useState(0)
  const [hasReachedCross, setHasReachedCross] = useState(false)

  // Progress through animation
  useEffect(() => {
    if (isPaused) return

    const interval = setInterval(() => {
      setProgress((prev) => {
        const next = prev + 1
        if (next >= 100) {
          setHasReachedCross(true)
          // Reset after kneeling for a moment
          setTimeout(() => {
            setHasReachedCross(false)
            setProgress(0)
          }, 3000)
          return 100
        }
        return next
      })
    }, 250)

    return () => clearInterval(interval)
  }, [isPaused])

  const isKneeling = progress >= 95
  const isInStorm = progress > 30 && progress < 70

  return (
    <div className="hidden lg:flex items-center space-x-2">
      {/* Pause/Play button */}
      <button
        onClick={() => setIsPaused(!isPaused)}
        className="p-1 rounded text-slate-500 hover:text-amber-400 hover:bg-amber-500/10 transition-colors"
        title={isPaused ? 'Play animation' : 'Pause animation'}
      >
        {isPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
      </button>

      {/* Animation container */}
      <div className="relative w-48 h-10 overflow-hidden rounded-lg bg-gradient-to-r from-slate-800/50 via-slate-700/30 to-amber-900/20 border border-slate-700/50">
        <svg
          viewBox="0 0 200 40"
          className="w-full h-full"
          preserveAspectRatio="xMidYMid slice"
        >
          <defs>
            {/* Golden glow for the cross */}
            <radialGradient id="miniCrossGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#fbbf24" stopOpacity="0.8" />
              <stop offset="70%" stopColor="#f59e0b" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#f59e0b" stopOpacity="0" />
            </radialGradient>

            {/* Storm gradient */}
            <linearGradient id="miniStormGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#475569" />
              <stop offset="100%" stopColor="#1e293b" />
            </linearGradient>
          </defs>

          {/* Background terrain - hills and valleys */}
          <path
            d="M0,35 Q20,30 40,33 Q60,38 80,32 Q100,28 120,34 Q140,38 160,30 Q180,26 200,28 L200,40 L0,40 Z"
            fill="#334155"
            opacity="0.6"
          />

          {/* Storm clouds (visible during storm phase) */}
          <g opacity={isInStorm ? 0.7 : 0.2} className="transition-opacity duration-1000">
            <ellipse cx="80" cy="8" rx="25" ry="6" fill="url(#miniStormGrad)">
              <animate attributeName="cx" values="75;90;75" dur="4s" repeatCount="indefinite" />
            </ellipse>
            <ellipse cx="110" cy="6" rx="20" ry="5" fill="url(#miniStormGrad)">
              <animate attributeName="cx" values="105;120;105" dur="3s" repeatCount="indefinite" />
            </ellipse>
          </g>

          {/* Rain during storm */}
          {isInStorm && (
            <g stroke="#64748b" strokeWidth="0.5" opacity="0.5">
              {[...Array(12)].map((_, i) => (
                <line
                  key={i}
                  x1={60 + i * 8}
                  y1={10 + (i % 3) * 5}
                  x2={58 + i * 8}
                  y2={20 + (i % 3) * 5}
                >
                  <animate
                    attributeName="y1"
                    values={`${10 + (i % 3) * 5};${30 + (i % 3) * 5};${10 + (i % 3) * 5}`}
                    dur="0.6s"
                    repeatCount="indefinite"
                  />
                  <animate
                    attributeName="y2"
                    values={`${20 + (i % 3) * 5};${40 + (i % 3) * 5};${20 + (i % 3) * 5}`}
                    dur="0.6s"
                    repeatCount="indefinite"
                  />
                </line>
              ))}
            </g>
          )}

          {/* The Cross at the destination */}
          <g transform="translate(180, 12)">
            {/* Glow */}
            <circle cx="0" cy="10" r="15" fill="url(#miniCrossGlow)">
              <animate attributeName="r" values="12;18;12" dur="2s" repeatCount="indefinite" />
            </circle>

            {/* Small hill */}
            <ellipse cx="0" cy="20" rx="15" ry="5" fill="#475569" />

            {/* Cross */}
            <g stroke="#fbbf24" strokeWidth="2" strokeLinecap="round">
              <line x1="0" y1="2" x2="0" y2="18">
                <animate attributeName="stroke" values="#fbbf24;#fcd34d;#fbbf24" dur="2s" repeatCount="indefinite" />
              </line>
              <line x1="-7" y1="6" x2="7" y2="6">
                <animate attributeName="stroke" values="#fbbf24;#fcd34d;#fbbf24" dur="2s" repeatCount="indefinite" />
              </line>
            </g>
          </g>

          {/* The Pilgrim */}
          <g transform={`translate(${10 + progress * 1.6}, 0)`}>
            {(() => {
              // Terrain Y position based on progress
              const getY = (p: number) => {
                if (p < 20) return 30 + Math.sin(p * 0.3) * 3
                if (p < 40) return 33 - (p - 20) * 0.15
                if (p < 60) return 30 + (p - 40) * 0.2
                if (p < 80) return 34 - (p - 60) * 0.2
                return 30 - (p - 80) * 0.1
              }

              const yPos = getY(progress)

              if (isKneeling) {
                // Kneeling at the cross
                return (
                  <g transform={`translate(0, ${yPos - 8})`}>
                    {/* Head */}
                    <circle cx="0" cy="0" r="2.5" fill="#d4a574" />
                    {/* Body bent forward */}
                    <path d="M0,2.5 Q-1,5 -3,7" stroke="#64748b" strokeWidth="1.5" fill="none" strokeLinecap="round" />
                    {/* Arms reaching to cross */}
                    <path d="M-1,4 Q3,2 7,1" stroke="#d4a574" strokeWidth="1" fill="none" strokeLinecap="round" />
                    {/* Kneeling legs */}
                    <path d="M-3,7 L-2,10 L1,10" stroke="#475569" strokeWidth="1.5" fill="none" strokeLinecap="round" />
                  </g>
                )
              }

              // Walking figure
              const walkCycle = progress % 8
              const legSwing = Math.sin(walkCycle * 0.8) * 2
              const armSwing = Math.cos(walkCycle * 0.8) * 1.5
              const bob = Math.abs(Math.sin(walkCycle * 0.8)) * 0.5
              const lean = isInStorm ? -8 : 0

              return (
                <g transform={`translate(0, ${yPos - 10 - bob}) rotate(${lean})`}>
                  {/* Head */}
                  <circle cx="0" cy="0" r="2.5" fill="#d4a574" />

                  {/* Body */}
                  <line x1="0" y1="2.5" x2="0" y2="8" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />

                  {/* Arms */}
                  <line
                    x1="0" y1="3.5"
                    x2={-1.5 + armSwing} y2={6}
                    stroke="#d4a574" strokeWidth="1" strokeLinecap="round"
                  />
                  <line
                    x1="0" y1="3.5"
                    x2={1.5 - armSwing} y2={6}
                    stroke="#d4a574" strokeWidth="1" strokeLinecap="round"
                  />

                  {/* Legs */}
                  <line
                    x1="0" y1="8"
                    x2={-1.5 + legSwing} y2="12"
                    stroke="#475569" strokeWidth="1.5" strokeLinecap="round"
                  />
                  <line
                    x1="0" y1="8"
                    x2={1.5 - legSwing} y2="12"
                    stroke="#475569" strokeWidth="1.5" strokeLinecap="round"
                  />

                  {/* Walking stick during storm */}
                  {isInStorm && (
                    <line x1="2" y1="4" x2="5" y2="12" stroke="#78716c" strokeWidth="0.8" strokeLinecap="round" />
                  )}
                </g>
              )
            })()}
          </g>

          {/* Footprints */}
          <g fill="#475569" opacity="0.4">
            {[...Array(5)].map((_, i) => {
              const footX = 10 + progress * 1.6 - (i + 1) * 12
              if (footX < 5 || footX > 160) return null
              return (
                <ellipse
                  key={i}
                  cx={footX}
                  cy="36"
                  rx="1.5"
                  ry="0.8"
                  opacity={1 - i * 0.2}
                />
              )
            })}
          </g>
        </svg>

        {/* Scripture text overlay */}
        <div className="absolute bottom-0 left-0 right-0 text-center">
          <span className="text-[8px] text-slate-400 italic">
            {isKneeling
              ? "Come to me... — Mt 11:28"
              : isInStorm
                ? "Through the valley... — Ps 23:4"
                : "Press on... — Phil 3:14"
            }
          </span>
        </div>
      </div>

      {/* Arrow pointing to cross button */}
      <div className="text-amber-500/50 text-xs">→</div>
    </div>
  )
}
