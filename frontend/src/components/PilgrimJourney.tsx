'use client'

import { useState, useEffect } from 'react'
import { Pause, Play } from 'lucide-react'

// Compact pilgrim animation for the nav bar - walks right to left toward the cross
// Gold themed to match the site design
export default function PilgrimJourney() {
  const [isPaused, setIsPaused] = useState(false)
  const [progress, setProgress] = useState(0)

  // Smooth animation progress (0 = start on right, 100 = at the cross on left)
  useEffect(() => {
    if (isPaused) return

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          // Stay kneeling for 3 seconds, then restart journey
          setTimeout(() => setProgress(0), 3000)
          return 100
        }
        return prev + 0.35 // Smooth, steady pace
      })
    }, 40) // 40ms for smoother animation

    return () => clearInterval(interval)
  }, [isPaused])

  const isKneeling = progress >= 94

  return (
    <div className="hidden lg:flex items-center">
      {/* Animation container - pilgrim walks right to left toward the cross */}
      <div className="relative w-36 h-12 overflow-hidden rounded-lg bg-gradient-to-l from-amber-950/20 to-transparent">
        <svg
          viewBox="0 0 140 48"
          className="w-full h-full"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            {/* Gold gradient for ground */}
            <linearGradient id="goldGround" x1="100%" y1="0%" x2="0%" y2="0%">
              <stop offset="0%" stopColor="#78350f" stopOpacity="0.15" />
              <stop offset="100%" stopColor="#fbbf24" stopOpacity="0.05" />
            </linearGradient>

            {/* Glow effect for when kneeling */}
            <radialGradient id="prayerGlow" cx="0%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#fbbf24" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#fbbf24" stopOpacity="0" />
            </radialGradient>

            {/* Skin tone gradient */}
            <linearGradient id="skinTone" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#e0b090" />
              <stop offset="100%" stopColor="#c49a6c" />
            </linearGradient>

            {/* Robe gradient - gold/amber */}
            <linearGradient id="robeGold" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#b45309" />
              <stop offset="50%" stopColor="#92400e" />
              <stop offset="100%" stopColor="#78350f" />
            </linearGradient>
          </defs>

          {/* Subtle ground with gold tint */}
          <rect x="0" y="42" width="140" height="6" fill="url(#goldGround)" />
          <line x1="0" y1="42" x2="140" y2="42" stroke="#fbbf24" strokeWidth="0.5" opacity="0.2" />

          {/* Prayer glow when kneeling */}
          {isKneeling && (
            <ellipse cx="8" cy="30" rx="20" ry="15" fill="url(#prayerGlow)">
              <animate attributeName="opacity" values="0.3;0.6;0.3" dur="2s" repeatCount="indefinite" />
            </ellipse>
          )}

          {/* The Pilgrim - walks from right (130) to left (8) */}
          <g transform={`translate(${130 - progress * 1.22}, 0)`}>
            {(() => {
              if (isKneeling) {
                // Kneeling figure facing left toward the cross - reverent pose
                return (
                  <g transform="translate(0, 16)">
                    {/* Head - bowed in prayer toward cross (left) */}
                    <ellipse cx="-3" cy="5" rx="5" ry="5.5" fill="url(#skinTone)" />

                    {/* Hair - darker amber */}
                    <ellipse cx="-3" cy="2" rx="4" ry="3" fill="#713f12" />

                    {/* Body bent forward in reverence */}
                    <path
                      d="M-2,10 C2,14 5,18 6,22"
                      stroke="url(#robeGold)"
                      strokeWidth="6"
                      fill="none"
                      strokeLinecap="round"
                    />

                    {/* Flowing robe */}
                    <path
                      d="M-4,12 Q0,16 2,22 Q6,24 8,22 Q6,18 4,14 Q2,12 0,12 Z"
                      fill="#92400e"
                      opacity="0.8"
                    />

                    {/* Arms reaching toward cross in prayer */}
                    <path
                      d="M-3,12 Q-10,8 -18,5"
                      stroke="url(#skinTone)"
                      strokeWidth="3"
                      fill="none"
                      strokeLinecap="round"
                    />

                    {/* Hands clasped in prayer */}
                    <ellipse cx="-18" cy="5" rx="3" ry="2.5" fill="url(#skinTone)" />

                    {/* Kneeling legs */}
                    <path
                      d="M6,22 Q4,26 2,28 L-2,28"
                      stroke="#78350f"
                      strokeWidth="4"
                      fill="none"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />

                    {/* Sandal */}
                    <ellipse cx="-2" cy="29" rx="3" ry="1.5" fill="#5c4033" />
                  </g>
                )
              }

              // Walking animation - smooth natural gait, facing left
              const time = progress * 0.1
              const walkPhase = time * Math.PI * 2

              // Smooth sinusoidal motion for natural walking
              const walkCycle = Math.sin(walkPhase)
              const walkCycle2 = Math.cos(walkPhase)

              // Natural vertical bob - peaks at mid-stride
              const verticalBob = Math.abs(Math.sin(walkPhase)) * 1.5

              // Body sway for realism
              const bodySway = Math.sin(walkPhase * 0.5) * 0.5

              // Arm and leg swing - opposite pairs
              const rightArmSwing = walkCycle * 8
              const leftArmSwing = -walkCycle * 8
              const rightLegSwing = -walkCycle * 10
              const leftLegSwing = walkCycle * 10

              return (
                <g transform={`translate(0, ${14 - verticalBob})`}>
                  {/* Shadow - grows/shrinks with bob */}
                  <ellipse
                    cx="0"
                    cy={28 + verticalBob}
                    rx={6 - verticalBob * 0.3}
                    ry={2 - verticalBob * 0.1}
                    fill="#000"
                    opacity="0.12"
                  />

                  <g transform={`rotate(${bodySway}, 0, 14)`}>
                    {/* Flowing robe - moves with walking */}
                    <path
                      d={`M3,10
                          Q${6 + walkCycle2 * 2},16 ${7 + walkCycle2 * 3},26
                          Q2,28 -3,26
                          Q-3,16 -2,10 Z`}
                      fill="url(#robeGold)"
                      opacity="0.85"
                    />

                    {/* Head */}
                    <ellipse cx="0" cy="4" rx="5" ry="5.5" fill="url(#skinTone)" />

                    {/* Hair */}
                    <ellipse cx="0" cy="1" rx="4" ry="3" fill="#713f12" />

                    {/* Neck/Body core */}
                    <line
                      x1="0" y1="9"
                      x2="0" y2="16"
                      stroke="#b45309"
                      strokeWidth="5"
                      strokeLinecap="round"
                    />

                    {/* Back arm (further from viewer) */}
                    <line
                      x1="0" y1="10"
                      x2={3 + rightArmSwing * 0.35} y2={16 + Math.abs(rightArmSwing) * 0.15}
                      stroke="url(#skinTone)"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                    />

                    {/* Front arm (closer to viewer) */}
                    <line
                      x1="0" y1="10"
                      x2={-3 + leftArmSwing * 0.35} y2={16 + Math.abs(leftArmSwing) * 0.15}
                      stroke="url(#skinTone)"
                      strokeWidth="3"
                      strokeLinecap="round"
                    />

                    {/* Back leg */}
                    <line
                      x1="0" y1="16"
                      x2={2 + rightLegSwing * 0.3} y2="26"
                      stroke="#78350f"
                      strokeWidth="4"
                      strokeLinecap="round"
                    />

                    {/* Front leg */}
                    <line
                      x1="0" y1="16"
                      x2={-2 + leftLegSwing * 0.3} y2="26"
                      stroke="#78350f"
                      strokeWidth="4"
                      strokeLinecap="round"
                    />

                    {/* Back foot/sandal */}
                    <ellipse
                      cx={2 + rightLegSwing * 0.3}
                      cy="27"
                      rx="3"
                      ry="1.2"
                      fill="#5c4033"
                      transform={`rotate(${rightLegSwing * 2}, ${2 + rightLegSwing * 0.3}, 27)`}
                    />

                    {/* Front foot/sandal */}
                    <ellipse
                      cx={-2 + leftLegSwing * 0.3}
                      cy="27"
                      rx="3"
                      ry="1.2"
                      fill="#5c4033"
                      transform={`rotate(${leftLegSwing * 2}, ${-2 + leftLegSwing * 0.3}, 27)`}
                    />
                  </g>
                </g>
              )
            })()}
          </g>

          {/* Fading footprints in gold/amber - trail behind to the right */}
          <g opacity="0.25">
            {[...Array(5)].map((_, i) => {
              const footX = 130 - progress * 1.22 + (i + 1) * 18
              if (footX > 128 || footX < 20 || isKneeling) return null
              const opacity = (1 - i * 0.2) * (progress > 10 ? 1 : progress / 10)
              return (
                <g key={i} opacity={opacity}>
                  <ellipse cx={footX + 2} cy="41" rx="2.5" ry="1" fill="#b45309" />
                  <ellipse cx={footX - 3} cy="41.5" rx="2.5" ry="1" fill="#b45309" />
                </g>
              )
            })}
          </g>
        </svg>
      </div>

      {/* Pause/Play button - gold themed */}
      <button
        onClick={() => setIsPaused(!isPaused)}
        className="p-1.5 rounded-full text-amber-500/60 hover:text-amber-400 hover:bg-amber-500/10 transition-all ml-1"
        title={isPaused ? 'Resume journey' : 'Pause journey'}
      >
        {isPaused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
      </button>
    </div>
  )
}
