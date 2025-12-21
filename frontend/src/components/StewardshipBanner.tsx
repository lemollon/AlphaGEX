'use client'

import { useState, useEffect, useCallback } from 'react'
import { X, Heart, Sparkles } from 'lucide-react'

// Latin Cross icon component - outline style with proper proportions
const CrossIcon = ({ className, animated = false }: { className?: string; animated?: boolean }) => (
  <svg
    className={`${className} ${animated ? 'animate-pulse' : ''}`}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {/* Vertical beam */}
    <path d="M12 2v20" />
    {/* Horizontal beam - positioned at 1/3 from top */}
    <path d="M5 7h14" />
  </svg>
)

// Scripture verses about stewardship
const scriptures = [
  {
    verse: "From everyone who has been given much, much will be demanded.",
    reference: "Luke 12:48",
    theme: "stewardship"
  },
  {
    verse: "The earth is the LORD's, and everything in it.",
    reference: "Psalm 24:1",
    theme: "ownership"
  },
  {
    verse: "Each of you should use whatever gift you have received to serve others.",
    reference: "1 Peter 4:10",
    theme: "service"
  },
  {
    verse: "Well done, good and faithful servant! You have been faithful with a few things.",
    reference: "Matthew 25:21",
    theme: "faithfulness"
  },
  {
    verse: "Honor the LORD with your wealth, with the firstfruits of all your crops.",
    reference: "Proverbs 3:9",
    theme: "honor"
  },
  {
    verse: "But remember the LORD your God, for it is he who gives you the ability to produce wealth.",
    reference: "Deuteronomy 8:18",
    theme: "gratitude"
  },
  {
    verse: "A good person leaves an inheritance for their children's children.",
    reference: "Proverbs 13:22",
    theme: "legacy"
  },
  {
    verse: "Whoever can be trusted with very little can also be trusted with much.",
    reference: "Luke 16:10",
    theme: "trust"
  }
]

interface DedicationModalProps {
  isOpen: boolean
  onClose: () => void
}

// Dedication Modal Component
export function DedicationModal({ isOpen, onClose }: DedicationModalProps) {
  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-[100] p-4"
      onClick={onClose}
    >
      <div
        className="bg-gradient-to-b from-background-card to-background-deep rounded-2xl max-w-lg w-full border border-amber-500/30 shadow-2xl shadow-amber-500/10"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header with glow effect */}
        <div className="relative p-6 pb-4 text-center border-b border-amber-500/20">
          <div className="absolute inset-0 bg-gradient-to-b from-amber-500/10 to-transparent rounded-t-2xl" />
          <button
            onClick={onClose}
            className="absolute top-4 right-4 p-1.5 rounded-full text-text-secondary hover:text-text-primary hover:bg-background-hover transition-colors"
          >
            <X className="w-5 h-5" />
          </button>

          <div className="relative">
            {/* Cross with rays and glow */}
            <div className="relative w-24 h-24 mx-auto mb-4">
              {/* Outer glow */}
              <div className="absolute inset-0 rounded-full bg-amber-400/20 blur-xl animate-pulse" />

              {/* Rays of light */}
              <div className="absolute inset-0 flex items-center justify-center">
                {[...Array(8)].map((_, i) => (
                  <div
                    key={i}
                    className="absolute w-1 h-12 bg-gradient-to-t from-amber-400/40 to-transparent origin-bottom"
                    style={{
                      transform: `rotate(${i * 45}deg) translateY(-20px)`,
                    }}
                  />
                ))}
              </div>

              {/* Inner glow ring */}
              <div className="absolute inset-2 rounded-full bg-amber-500/10 blur-md" />

              {/* Main cross circle */}
              <div className="absolute inset-3 rounded-full bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center shadow-lg shadow-amber-500/50">
                <CrossIcon className="w-9 h-9 text-white drop-shadow-lg" animated />
              </div>
            </div>

            <h2 className="text-2xl font-bold text-amber-400">
              Dedicated to God's Glory
            </h2>
            <p className="text-amber-500/70 text-sm mt-1">Soli Deo Gloria</p>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5">
          <div className="text-center">
            <p className="text-text-primary leading-relaxed">
              <span className="text-amber-400 font-semibold">AlphaGEX</span> was designed with purpose and gratitude,
              acknowledging that all wisdom, knowledge, and opportunity come from God.
            </p>
          </div>

          <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-4">
            <h3 className="text-amber-400 font-semibold mb-2 flex items-center gap-2">
              <Heart className="w-4 h-4" />
              Our Stewardship Commitment
            </h3>
            <ul className="space-y-2 text-sm text-text-secondary">
              <li className="flex items-start gap-2">
                <Sparkles className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                <span>Use the blessings and rewards wisely, not for selfish gain alone</span>
              </li>
              <li className="flex items-start gap-2">
                <Sparkles className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                <span>Remember that we are stewards, not owners, of what we receive</span>
              </li>
              <li className="flex items-start gap-2">
                <Sparkles className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                <span>Give generously, invest faithfully, and honor God with our increase</span>
              </li>
              <li className="flex items-start gap-2">
                <Sparkles className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                <span>Build a legacy that blesses others and glorifies the Creator</span>
              </li>
            </ul>
          </div>

          <blockquote className="text-center italic text-text-secondary border-l-2 border-amber-500 pl-4 py-2">
            "From everyone who has been given much, much will be demanded;
            and from the one who has been entrusted with much, much more will be asked."
            <footer className="text-amber-500 text-sm mt-2 not-italic font-medium">
              — Luke 12:48
            </footer>
          </blockquote>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-800 text-center">
          <button
            onClick={onClose}
            className="px-6 py-2.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-white font-medium rounded-lg transition-all shadow-lg shadow-amber-500/20 hover:shadow-amber-500/30"
          >
            I Accept This Stewardship
          </button>
        </div>
      </div>
    </div>
  )
}

// Rotating Scripture Banner Component
export function StewardshipBanner() {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isVisible, setIsVisible] = useState(true)
  const [isPaused, setIsPaused] = useState(false)
  const [isFading, setIsFading] = useState(false)

  // Rotate scriptures every 10 seconds
  useEffect(() => {
    if (isPaused) return

    const interval = setInterval(() => {
      setIsFading(true)
      setTimeout(() => {
        setCurrentIndex((prev) => (prev + 1) % scriptures.length)
        setIsFading(false)
      }, 500) // Wait for fade out before changing
    }, 10000)

    return () => clearInterval(interval)
  }, [isPaused])

  const handleDismiss = useCallback(() => {
    setIsVisible(false)
    // Store dismissal in session (not permanent - shows again on reload)
    sessionStorage.setItem('stewardshipBannerDismissed', 'true')
  }, [])

  // Check if banner was dismissed this session
  useEffect(() => {
    const dismissed = sessionStorage.getItem('stewardshipBannerDismissed')
    if (dismissed === 'true') {
      setIsVisible(false)
    }
  }, [])

  if (!isVisible) return null

  const currentScripture = scriptures[currentIndex]

  return (
    <div
      className="relative bg-gradient-to-r from-amber-900/20 via-amber-800/10 to-amber-900/20 border-b border-amber-500/20"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
    >
      {/* Subtle animated background glow */}
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-amber-500/5 to-transparent animate-pulse" />

      <div className="relative max-w-7xl mx-auto px-4 py-1.5">
        <div className="flex items-center justify-center gap-3">
          {/* Scripture dots indicator */}
          <div className="hidden sm:flex items-center gap-1">
            {scriptures.map((_, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setIsFading(true)
                  setTimeout(() => {
                    setCurrentIndex(idx)
                    setIsFading(false)
                  }, 300)
                }}
                className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${
                  idx === currentIndex
                    ? 'bg-amber-400 w-3'
                    : 'bg-amber-500/30 hover:bg-amber-500/50'
                }`}
              />
            ))}
          </div>

          {/* Scripture text */}
          <div
            className={`flex-1 text-center transition-opacity duration-500 ${
              isFading ? 'opacity-0' : 'opacity-100'
            }`}
          >
            <span className="text-amber-200/90 text-sm">
              "{currentScripture.verse}"
            </span>
            <span className="text-amber-500 text-xs ml-2 font-medium">
              — {currentScripture.reference}
            </span>
          </div>

          {/* Close button */}
          <button
            onClick={handleDismiss}
            className="p-1 rounded text-amber-500/50 hover:text-amber-400 hover:bg-amber-500/10 transition-colors"
            title="Dismiss for this session"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Bottom gradient line */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-amber-500/30 to-transparent" />
    </div>
  )
}

// Interactive Cross Button for Navigation
interface CrossButtonProps {
  onClick: () => void
}

export function CrossButton({ onClick }: CrossButtonProps) {
  const [isHovered, setIsHovered] = useState(false)

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className="relative p-1.5 rounded-lg transition-all duration-300 group"
      title="Dedicated to God's Glory - Click to learn more"
    >
      {/* Glow effect on hover */}
      <div className={`absolute inset-0 rounded-lg bg-amber-500/20 transition-opacity duration-300 ${
        isHovered ? 'opacity-100' : 'opacity-0'
      }`} />

      {/* Cross icon */}
      <CrossIcon className={`w-5 h-5 relative z-10 transition-all duration-300 ${
        isHovered
          ? 'text-amber-400 scale-110'
          : 'text-amber-500/70'
      }`} />

      {/* Tooltip */}
      <div className={`absolute left-1/2 -translate-x-1/2 top-full mt-2 px-3 py-1.5 bg-background-card border border-amber-500/30 rounded-lg shadow-xl whitespace-nowrap transition-all duration-300 ${
        isHovered
          ? 'opacity-100 translate-y-0'
          : 'opacity-0 -translate-y-1 pointer-events-none'
      }`}>
        <span className="text-xs text-amber-400">Dedicated to God's Glory</span>
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 border-4 border-transparent border-b-background-card" />
      </div>
    </button>
  )
}

// Tagline Component for under logo
export function StewardshipTagline() {
  return (
    <span className="text-[10px] text-amber-500/60 tracking-wide hidden md:block">
      Dedicated to God · Steward Your Blessings
    </span>
  )
}
