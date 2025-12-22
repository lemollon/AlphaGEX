'use client'

import { useState, useEffect, useCallback } from 'react'
import { Pause, Play, X } from 'lucide-react'

// Scriptures for the journey
const scriptures = [
  { verse: "Well done, good and faithful servant! You have been faithful with a few things.", reference: "Matthew 25:21" },
  { verse: "From everyone who has been given much, much will be demanded.", reference: "Luke 12:48" },
  { verse: "I press on toward the goal for the prize of the upward call.", reference: "Philippians 3:14" },
  { verse: "Though I walk through the valley of the shadow of death, I will fear no evil.", reference: "Psalm 23:4" },
  { verse: "Come to me, all who are weary and burdened, and I will give you rest.", reference: "Matthew 11:28" },
  { verse: "The earth is the LORD's, and everything in it.", reference: "Psalm 24:1" },
]

// Gold-themed banner with pilgrim walking toward the cross
export default function PilgrimJourney() {
  const [isVisible, setIsVisible] = useState(true)
  const [isPaused, setIsPaused] = useState(false)
  const [progress, setProgress] = useState(0)
  const [scriptureIndex, setScriptureIndex] = useState(0)

  // Check if dismissed this session
  useEffect(() => {
    const dismissed = sessionStorage.getItem('pilgrimBannerDismissed')
    if (dismissed === 'true') {
      setIsVisible(false)
    }
  }, [])

  // Animation progress
  useEffect(() => {
    if (isPaused || !isVisible) return

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          // Stay kneeling for a moment, then restart
          setTimeout(() => setProgress(0), 2500)
          return 100
        }
        return prev + 0.5
      })
    }, 50) // Smooth 50ms updates

    return () => clearInterval(interval)
  }, [isPaused, isVisible])

  // Rotate scriptures
  useEffect(() => {
    if (isPaused) return
    const interval = setInterval(() => {
      setScriptureIndex((prev) => (prev + 1) % scriptures.length)
    }, 12000)
    return () => clearInterval(interval)
  }, [isPaused])

  const handleDismiss = useCallback(() => {
    setIsVisible(false)
    sessionStorage.setItem('pilgrimBannerDismissed', 'true')
  }, [])

  if (!isVisible) return null

  const isKneeling = progress >= 92
  const isInTrial = progress > 25 && progress < 65

  return (
    <div
      className="relative bg-gradient-to-r from-amber-950/40 via-amber-900/20 to-amber-950/40 border-b border-amber-500/30"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
    >
      {/* Subtle background glow */}
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-amber-500/5 to-transparent" />

      <div className="relative h-14">
        {/* SVG Animation Layer */}
        <svg
          className="absolute inset-0 w-full h-full"
          viewBox="0 0 1200 56"
          preserveAspectRatio="xMidYMid slice"
        >
          <defs>
            {/* Gold gradients */}
            <linearGradient id="groundGold" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#78350f" stopOpacity="0.3" />
              <stop offset="50%" stopColor="#92400e" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#78350f" stopOpacity="0.3" />
            </linearGradient>

            <linearGradient id="skyGold" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#451a03" stopOpacity="0.2" />
              <stop offset="40%" stopColor="#78350f" stopOpacity="0.15" />
              <stop offset="60%" stopColor="#78350f" stopOpacity="0.15" />
              <stop offset="100%" stopColor="#fbbf24" stopOpacity="0.1" />
            </linearGradient>

            <radialGradient id="crossLight" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#fbbf24" stopOpacity="0.9" />
              <stop offset="40%" stopColor="#f59e0b" stopOpacity="0.5" />
              <stop offset="100%" stopColor="#f59e0b" stopOpacity="0" />
            </radialGradient>

            <linearGradient id="trialClouds" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#44403c" stopOpacity="0.7" />
              <stop offset="100%" stopColor="#292524" stopOpacity="0.5" />
            </linearGradient>
          </defs>

          {/* Sky background */}
          <rect x="0" y="0" width="1200" height="56" fill="url(#skyGold)" />

          {/* Distant hills */}
          <path
            d="M0,45 Q150,35 300,42 Q450,50 600,40 Q750,32 900,44 Q1050,38 1200,35 L1200,56 L0,56 Z"
            fill="url(#groundGold)"
            opacity="0.5"
          />

          {/* Main terrain with valleys */}
          <path
            d="M0,48
               Q75,44 150,47
               Q225,52 300,46
               Q375,40 450,50
               Q525,54 600,48
               Q675,42 750,52
               Q825,48 900,44
               Q975,40 1050,42
               Q1125,44 1200,38
               L1200,56 L0,56 Z"
            fill="url(#groundGold)"
          />

          {/* Trial clouds - appear during middle section */}
          <g opacity={isInTrial ? 0.8 : 0.15} style={{ transition: 'opacity 1.5s ease' }}>
            <ellipse cx="400" cy="12" rx="80" ry="10" fill="url(#trialClouds)">
              <animate attributeName="cx" values="380;420;380" dur="12s" repeatCount="indefinite" />
            </ellipse>
            <ellipse cx="500" cy="8" rx="60" ry="8" fill="url(#trialClouds)">
              <animate attributeName="cx" values="490;530;490" dur="10s" repeatCount="indefinite" />
            </ellipse>
            <ellipse cx="620" cy="14" rx="70" ry="9" fill="url(#trialClouds)">
              <animate attributeName="cx" values="600;650;600" dur="14s" repeatCount="indefinite" />
            </ellipse>
            <ellipse cx="720" cy="10" rx="50" ry="7" fill="url(#trialClouds)">
              <animate attributeName="cx" values="710;750;710" dur="11s" repeatCount="indefinite" />
            </ellipse>
          </g>

          {/* Subtle rain during trials */}
          {isInTrial && (
            <g stroke="#a8a29e" strokeWidth="0.5" opacity="0.3">
              {[...Array(20)].map((_, i) => {
                const x = 350 + i * 25
                const delay = (i % 5) * 0.15
                return (
                  <line key={i} x1={x} y1="18" x2={x - 3} y2="35">
                    <animate
                      attributeName="y1"
                      values="15;45;15"
                      dur="0.7s"
                      begin={`${delay}s`}
                      repeatCount="indefinite"
                    />
                    <animate
                      attributeName="y2"
                      values="30;56;30"
                      dur="0.7s"
                      begin={`${delay}s`}
                      repeatCount="indefinite"
                    />
                  </line>
                )
              })}
            </g>
          )}

          {/* The Cross at destination - positioned to align with CrossButton */}
          <g transform="translate(1120, 8)">
            {/* Divine light rays */}
            <g opacity="0.4">
              {[0, 30, 60, 90, 120, 150].map((angle) => (
                <line
                  key={angle}
                  x1="0"
                  y1="18"
                  x2={Math.cos((angle - 90) * Math.PI / 180) * 40}
                  y2={18 + Math.sin((angle - 90) * Math.PI / 180) * 40}
                  stroke="#fbbf24"
                  strokeWidth="1"
                  opacity="0.5"
                >
                  <animate
                    attributeName="opacity"
                    values="0.3;0.7;0.3"
                    dur={`${2 + (angle % 3) * 0.5}s`}
                    repeatCount="indefinite"
                  />
                </line>
              ))}
            </g>

            {/* Glow */}
            <circle cx="0" cy="20" r="30" fill="url(#crossLight)">
              <animate attributeName="r" values="25;35;25" dur="3s" repeatCount="indefinite" />
            </circle>

            {/* Hill of Calvary */}
            <ellipse cx="0" cy="38" rx="35" ry="10" fill="#92400e" opacity="0.6" />

            {/* The Cross */}
            <g stroke="#fbbf24" strokeWidth="3" strokeLinecap="round">
              <line x1="0" y1="8" x2="0" y2="36">
                <animate attributeName="stroke" values="#fbbf24;#fcd34d;#fbbf24" dur="2.5s" repeatCount="indefinite" />
              </line>
              <line x1="-14" y1="16" x2="14" y2="16">
                <animate attributeName="stroke" values="#fbbf24;#fcd34d;#fbbf24" dur="2.5s" repeatCount="indefinite" />
              </line>
            </g>
          </g>

          {/* The Pilgrim - smooth natural walking */}
          <g transform={`translate(${60 + progress * 10.5}, 0)`}>
            {(() => {
              // Natural terrain following
              const getTerrainY = (p: number) => {
                const x = p / 100
                // Sinusoidal terrain matching the path
                return 44 + Math.sin(x * Math.PI * 4) * 4 + Math.cos(x * Math.PI * 2) * 2
              }

              const y = getTerrainY(progress)

              if (isKneeling) {
                // Kneeling figure - reverent pose
                return (
                  <g transform={`translate(0, ${y - 18})`}>
                    {/* Head - bowed */}
                    <ellipse cx="2" cy="4" rx="4" ry="4.5" fill="#d4a574" />
                    {/* Hair */}
                    <ellipse cx="2" cy="2" rx="3.5" ry="2.5" fill="#78350f" />

                    {/* Body - bent in prayer */}
                    <path
                      d="M2,8 Q0,14 -4,18"
                      stroke="#b45309"
                      strokeWidth="5"
                      fill="none"
                      strokeLinecap="round"
                    />

                    {/* Robe/cloak */}
                    <path
                      d="M-2,10 Q-6,14 -8,20 Q-4,22 0,20"
                      fill="#92400e"
                      opacity="0.8"
                    />

                    {/* Arms - extended toward cross in prayer */}
                    <path
                      d="M0,10 Q8,6 16,4"
                      stroke="#d4a574"
                      strokeWidth="2.5"
                      fill="none"
                      strokeLinecap="round"
                    />
                    <path
                      d="M-1,11 Q6,8 14,6"
                      stroke="#d4a574"
                      strokeWidth="2.5"
                      fill="none"
                      strokeLinecap="round"
                    />

                    {/* Hands together */}
                    <circle cx="15" cy="5" r="2" fill="#d4a574" />

                    {/* Kneeling legs */}
                    <path
                      d="M-4,18 L-2,24 L4,24"
                      stroke="#78350f"
                      strokeWidth="4"
                      fill="none"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </g>
                )
              }

              // Walking animation - natural gait
              const time = progress * 0.15
              const walkCycle = Math.sin(time * Math.PI)
              const walkCycle2 = Math.cos(time * Math.PI)

              // Natural bob - slight up/down with each step
              const verticalBob = Math.abs(Math.sin(time * Math.PI)) * 1.5

              // Lean into the wind during trials
              const leanAngle = isInTrial ? -5 : 0

              // Arm and leg swing
              const armSwing = walkCycle * 8
              const legSwing = walkCycle * 10

              return (
                <g transform={`translate(0, ${y - 22 - verticalBob})`}>
                  {/* Shadow */}
                  <ellipse
                    cx="0"
                    cy={22 + verticalBob}
                    rx="6"
                    ry="2"
                    fill="#000"
                    opacity="0.2"
                  />

                  <g transform={`rotate(${leanAngle}, 0, 12)`}>
                    {/* Cloak/robe flowing */}
                    <path
                      d={`M-3,8 Q${-6 - walkCycle2},14 ${-8 - walkCycle2 * 2},22 Q-2,24 2,22 Q3,14 2,8`}
                      fill="#92400e"
                      opacity="0.7"
                    />

                    {/* Head */}
                    <ellipse cx="0" cy="2" rx="4" ry="4.5" fill="#d4a574" />

                    {/* Hair */}
                    <ellipse cx="0" cy="0" rx="3.5" ry="2.5" fill="#78350f" />

                    {/* Body */}
                    <line
                      x1="0" y1="6"
                      x2="0" y2="14"
                      stroke="#b45309"
                      strokeWidth="5"
                      strokeLinecap="round"
                    />

                    {/* Back arm */}
                    <line
                      x1="0" y1="7"
                      x2={-3 - armSwing * 0.4} y2={12 + Math.abs(armSwing) * 0.1}
                      stroke="#d4a574"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                    />

                    {/* Front arm */}
                    <line
                      x1="0" y1="7"
                      x2={3 + armSwing * 0.4} y2={12 + Math.abs(armSwing) * 0.1}
                      stroke="#d4a574"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                    />

                    {/* Walking stick during trials */}
                    {isInTrial && (
                      <line
                        x1={4 + armSwing * 0.3}
                        y1={11}
                        x2={8 + armSwing * 0.2}
                        y2={22}
                        stroke="#78716c"
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                    )}

                    {/* Back leg */}
                    <line
                      x1="0" y1="14"
                      x2={-3 - legSwing * 0.3} y2="22"
                      stroke="#78350f"
                      strokeWidth="4"
                      strokeLinecap="round"
                    />

                    {/* Front leg */}
                    <line
                      x1="0" y1="14"
                      x2={3 + legSwing * 0.3} y2="22"
                      stroke="#78350f"
                      strokeWidth="4"
                      strokeLinecap="round"
                    />

                    {/* Feet */}
                    <ellipse
                      cx={-3 - legSwing * 0.3}
                      cy="23"
                      rx="2.5"
                      ry="1"
                      fill="#5c4033"
                    />
                    <ellipse
                      cx={3 + legSwing * 0.3}
                      cy="23"
                      rx="2.5"
                      ry="1"
                      fill="#5c4033"
                    />
                  </g>
                </g>
              )
            })()}
          </g>

          {/* Fading footprints */}
          <g fill="#78350f" opacity="0.25">
            {[...Array(6)].map((_, i) => {
              const footX = 60 + progress * 10.5 - (i + 1) * 50
              if (footX < 50 || footX > 1050) return null
              const footY = 50 + Math.sin((footX / 100) * Math.PI * 0.4) * 2
              return (
                <g key={i} opacity={1 - i * 0.15}>
                  <ellipse cx={footX - 4} cy={footY} rx="3" ry="1.2" />
                  <ellipse cx={footX + 4} cy={footY + 1} rx="3" ry="1.2" />
                </g>
              )
            })}
          </g>
        </svg>

        {/* Scripture overlay - centered */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center px-4">
            <span className="text-amber-200/90 text-sm font-medium">
              "{scriptures[scriptureIndex].verse}"
            </span>
            <span className="text-amber-500 text-xs ml-2">
              — {scriptures[scriptureIndex].reference}
            </span>
          </div>
        </div>

        {/* Controls */}
        <div className="absolute left-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
          {/* Pause/Play */}
          <button
            onClick={() => setIsPaused(!isPaused)}
            className="p-1.5 rounded-full bg-amber-900/30 text-amber-400/70 hover:text-amber-300 hover:bg-amber-800/40 transition-colors"
            title={isPaused ? 'Resume journey' : 'Pause journey'}
          >
            {isPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
          </button>
        </div>

        {/* Close button */}
        <button
          onClick={handleDismiss}
          className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded text-amber-500/50 hover:text-amber-400 hover:bg-amber-500/10 transition-colors"
          title="Dismiss for this session"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Bottom gradient line */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-amber-500/40 to-transparent" />
    </div>
  )
}
