'use client'

import { useState, useEffect } from 'react'

// Animated banner showing a pilgrim's journey through trials to the cross
export default function PilgrimJourney() {
  const [isVisible, setIsVisible] = useState(true)
  const [animationPhase, setAnimationPhase] = useState(0)

  // Check if banner was dismissed this session
  useEffect(() => {
    const dismissed = sessionStorage.getItem('pilgrimBannerDismissed')
    if (dismissed === 'true') {
      setIsVisible(false)
    }
  }, [])

  // Progress through animation phases
  useEffect(() => {
    const interval = setInterval(() => {
      setAnimationPhase((prev) => (prev + 1) % 100)
    }, 300) // Update every 300ms for smooth animation

    return () => clearInterval(interval)
  }, [])

  const handleDismiss = () => {
    setIsVisible(false)
    sessionStorage.setItem('pilgrimBannerDismissed', 'true')
  }

  if (!isVisible) return null

  // Calculate pilgrim position (0-100%)
  const pilgrimProgress = animationPhase
  const isKneeling = pilgrimProgress >= 90

  return (
    <div className="relative bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 border-b border-amber-500/20 overflow-hidden">
      {/* Sky gradient */}
      <div className="absolute inset-0 bg-gradient-to-b from-slate-700/50 via-amber-900/20 to-slate-900/80" />

      <div className="relative h-12 max-w-full mx-auto">
        <svg
          viewBox="0 0 1200 48"
          className="w-full h-full"
          preserveAspectRatio="xMidYMid slice"
        >
          <defs>
            {/* Gradient for the ground/hills */}
            <linearGradient id="groundGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#1e293b" />
              <stop offset="50%" stopColor="#334155" />
              <stop offset="100%" stopColor="#1e293b" />
            </linearGradient>

            {/* Gradient for storm clouds */}
            <linearGradient id="stormGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#475569" />
              <stop offset="100%" stopColor="#1e293b" />
            </linearGradient>

            {/* Golden glow for the cross */}
            <radialGradient id="crossGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#fbbf24" stopOpacity="0.6" />
              <stop offset="50%" stopColor="#f59e0b" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#f59e0b" stopOpacity="0" />
            </radialGradient>

            {/* Rain pattern */}
            <pattern id="rain" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
              <line x1="10" y1="0" x2="8" y2="10" stroke="#64748b" strokeWidth="0.5" opacity="0.5">
                <animate attributeName="y1" values="0;20;0" dur="0.8s" repeatCount="indefinite" />
                <animate attributeName="y2" values="10;30;10" dur="0.8s" repeatCount="indefinite" />
              </line>
            </pattern>
          </defs>

          {/* Background hills - distant mountains */}
          <path
            d="M0,40 Q100,25 200,35 T400,30 T600,38 T800,28 T1000,35 T1200,32 L1200,48 L0,48 Z"
            fill="#1e293b"
            opacity="0.5"
          />

          {/* Storm clouds in the middle section */}
          <g opacity={pilgrimProgress > 30 && pilgrimProgress < 70 ? 0.8 : 0.3}>
            {/* Cloud 1 */}
            <ellipse cx="400" cy="8" rx="60" ry="8" fill="url(#stormGradient)">
              <animate attributeName="cx" values="380;420;380" dur="8s" repeatCount="indefinite" />
            </ellipse>
            <ellipse cx="430" cy="10" rx="40" ry="6" fill="url(#stormGradient)">
              <animate attributeName="cx" values="420;450;420" dur="6s" repeatCount="indefinite" />
            </ellipse>

            {/* Cloud 2 */}
            <ellipse cx="550" cy="6" rx="50" ry="7" fill="url(#stormGradient)">
              <animate attributeName="cx" values="540;570;540" dur="7s" repeatCount="indefinite" />
            </ellipse>
            <ellipse cx="580" cy="9" rx="35" ry="5" fill="url(#stormGradient)">
              <animate attributeName="cx" values="570;600;570" dur="5s" repeatCount="indefinite" />
            </ellipse>

            {/* Cloud 3 */}
            <ellipse cx="700" cy="7" rx="45" ry="6" fill="url(#stormGradient)">
              <animate attributeName="cx" values="690;720;690" dur="9s" repeatCount="indefinite" />
            </ellipse>
          </g>

          {/* Rain in storm section */}
          {pilgrimProgress > 35 && pilgrimProgress < 65 && (
            <rect x="350" y="15" width="400" height="30" fill="url(#rain)" opacity="0.4" />
          )}

          {/* Main terrain path with hills and valleys */}
          <path
            d="M0,42
               Q50,40 100,38
               Q150,36 200,40
               Q250,44 300,38
               Q350,32 400,42
               Q450,48 500,40
               Q550,32 600,44
               Q650,48 700,38
               Q750,30 800,36
               Q850,42 900,34
               Q950,28 1000,32
               Q1050,36 1100,30
               L1200,28 L1200,48 L0,48 Z"
            fill="url(#groundGradient)"
          />

          {/* Thorns/obstacles in the valley sections */}
          <g stroke="#475569" strokeWidth="0.5" fill="none" opacity="0.6">
            <path d="M280,42 l5,-4 l-3,0 l4,-3" />
            <path d="M480,44 l4,-5 l-2,1 l3,-4" />
            <path d="M620,46 l5,-4 l-3,1 l4,-3" />
          </g>

          {/* Small rocks/obstacles */}
          <g fill="#475569">
            <circle cx="320" cy="41" r="2" />
            <circle cx="520" cy="43" r="1.5" />
            <circle cx="680" cy="42" r="2" />
          </g>

          {/* The Cross at the end - with glow */}
          <g transform="translate(1100, 10)">
            {/* Glow behind cross */}
            <circle cx="0" cy="12" r="25" fill="url(#crossGlow)">
              <animate attributeName="r" values="20;28;20" dur="3s" repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.6;1;0.6" dur="3s" repeatCount="indefinite" />
            </circle>

            {/* Hill under cross */}
            <ellipse cx="0" cy="25" rx="30" ry="8" fill="#334155" />

            {/* Cross */}
            <g stroke="#fbbf24" strokeWidth="2.5" strokeLinecap="round">
              {/* Vertical beam */}
              <line x1="0" y1="0" x2="0" y2="22">
                <animate attributeName="stroke" values="#fbbf24;#fcd34d;#fbbf24" dur="2s" repeatCount="indefinite" />
              </line>
              {/* Horizontal beam */}
              <line x1="-10" y1="6" x2="10" y2="6">
                <animate attributeName="stroke" values="#fbbf24;#fcd34d;#fbbf24" dur="2s" repeatCount="indefinite" />
              </line>
            </g>

            {/* Light rays from cross */}
            <g stroke="#fbbf24" strokeWidth="0.5" opacity="0.4">
              <line x1="0" y1="10" x2="-25" y2="0">
                <animate attributeName="opacity" values="0.2;0.5;0.2" dur="2s" repeatCount="indefinite" />
              </line>
              <line x1="0" y1="10" x2="25" y2="0">
                <animate attributeName="opacity" values="0.3;0.6;0.3" dur="2.5s" repeatCount="indefinite" />
              </line>
              <line x1="0" y1="10" x2="-20" y2="25">
                <animate attributeName="opacity" values="0.2;0.4;0.2" dur="1.8s" repeatCount="indefinite" />
              </line>
              <line x1="0" y1="10" x2="20" y2="25">
                <animate attributeName="opacity" values="0.3;0.5;0.3" dur="2.2s" repeatCount="indefinite" />
              </line>
            </g>
          </g>

          {/* The Pilgrim figure */}
          <g
            transform={`translate(${50 + (pilgrimProgress * 10.5)}, 0)`}
            className="transition-transform duration-300"
          >
            {/* Calculate Y position based on terrain */}
            {(() => {
              // Terrain heights at different points (matching the path)
              const getTerrainY = (progress: number) => {
                if (progress < 10) return 38 + (progress * 0.2)
                if (progress < 20) return 40 - ((progress - 10) * 0.4)
                if (progress < 30) return 36 + ((progress - 20) * 0.6)
                if (progress < 40) return 42 - ((progress - 30) * 0.4)
                if (progress < 50) return 38 + ((progress - 40) * 0.6)
                if (progress < 60) return 44 - ((progress - 50) * 0.4)
                if (progress < 70) return 40 + ((progress - 60) * 0.2)
                if (progress < 80) return 42 - ((progress - 70) * 0.4)
                if (progress < 90) return 38 - ((progress - 80) * 0.6)
                return 32 // At the cross
              }

              const yPos = getTerrainY(pilgrimProgress)

              if (isKneeling) {
                // Kneeling figure at the cross
                return (
                  <g transform={`translate(0, ${yPos - 12})`}>
                    {/* Head */}
                    <circle cx="0" cy="2" r="3" fill="#d4a574" />
                    {/* Body - bent forward */}
                    <path
                      d="M0,5 Q-2,8 -4,10"
                      stroke="#64748b"
                      strokeWidth="2"
                      fill="none"
                      strokeLinecap="round"
                    />
                    {/* Arms - reaching toward cross */}
                    <path
                      d="M-2,7 Q2,5 6,4"
                      stroke="#d4a574"
                      strokeWidth="1.5"
                      fill="none"
                      strokeLinecap="round"
                    />
                    {/* Kneeling legs */}
                    <path
                      d="M-4,10 L-3,14 L0,14"
                      stroke="#475569"
                      strokeWidth="2"
                      fill="none"
                      strokeLinecap="round"
                    />
                  </g>
                )
              } else {
                // Walking figure with animation
                const walkCycle = pilgrimProgress % 10
                const legOffset = Math.sin(walkCycle * 0.6) * 3
                const armOffset = Math.cos(walkCycle * 0.6) * 2
                const bobOffset = Math.abs(Math.sin(walkCycle * 0.6)) * 1

                // Struggling more in storm section
                const isInStorm = pilgrimProgress > 35 && pilgrimProgress < 65
                const leanAngle = isInStorm ? -10 : 0

                return (
                  <g transform={`translate(0, ${yPos - 14 - bobOffset}) rotate(${leanAngle})`}>
                    {/* Head */}
                    <circle cx="0" cy="0" r="3" fill="#d4a574" />

                    {/* Body */}
                    <line
                      x1="0" y1="3" x2="0" y2="10"
                      stroke="#64748b"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />

                    {/* Arms swinging */}
                    <line
                      x1="0" y1="4"
                      x2={-2 + armOffset} y2={7 + Math.abs(armOffset) * 0.5}
                      stroke="#d4a574"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    />
                    <line
                      x1="0" y1="4"
                      x2={2 - armOffset} y2={7 + Math.abs(armOffset) * 0.5}
                      stroke="#d4a574"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    />

                    {/* Legs walking */}
                    <line
                      x1="0" y1="10"
                      x2={-2 + legOffset} y2="16"
                      stroke="#475569"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                    <line
                      x1="0" y1="10"
                      x2={2 - legOffset} y2="16"
                      stroke="#475569"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />

                    {/* Walking stick (shows struggle) */}
                    {isInStorm && (
                      <line
                        x1="3" y1="5"
                        x2="6" y2="16"
                        stroke="#78716c"
                        strokeWidth="1"
                        strokeLinecap="round"
                      />
                    )}
                  </g>
                )
              }
            })()}
          </g>

          {/* Footprints left behind (fading) */}
          <g fill="#475569" opacity="0.3">
            {[...Array(8)].map((_, i) => {
              const footX = 50 + (pilgrimProgress * 10.5) - (i + 1) * 40
              if (footX < 50 || footX > 1050) return null
              return (
                <ellipse
                  key={i}
                  cx={footX}
                  cy="44"
                  rx="2"
                  ry="1"
                  opacity={1 - i * 0.12}
                />
              )
            })}
          </g>

          {/* Text overlay */}
          <text
            x="600"
            y="46"
            textAnchor="middle"
            fill="#94a3b8"
            fontSize="8"
            fontStyle="italic"
            opacity="0.6"
          >
            {isKneeling
              ? "Come to me, all who are weary and burdened — Matthew 11:28"
              : pilgrimProgress > 35 && pilgrimProgress < 65
                ? "Though I walk through the valley of the shadow... — Psalm 23:4"
                : "I press on toward the goal — Philippians 3:14"
            }
          </text>
        </svg>

        {/* Close button */}
        <button
          onClick={handleDismiss}
          className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-700/50 transition-colors"
          title="Dismiss for this session"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Bottom gradient line */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-amber-500/30 to-transparent" />
    </div>
  )
}
