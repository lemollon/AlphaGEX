'use client'

import { useEffect, useRef, useState } from 'react'

// Animated mascot: the gentle-flicker loop idles, and every 15s one of the
// variant loops plays through a full pass before handing back to the idle.
// The idle is a forward-only loop with a crossfaded seam (no visible rewind);
// variants are boomerangs so they end back on the shared base pose, and the
// opacity crossfade between layers reads as one continuous animation.
const IDLE_SRC = '/spark-anim/01-gentle-flicker-v2.webp'
const VARIANT_SRCS = [
  '/spark-anim/02-breathing-glow.webp',
  '/spark-anim/03-ember-rise.webp',
  '/spark-anim/04-wind-sway.webp',
  '/spark-anim/05-charge-up.webp',
  '/spark-anim/06-electric-arc.webp',
  '/spark-anim/07-liquid-fire.webp',
  '/spark-anim/09-heartbeat-flare.webp',
]
const STATIC_SRC = '/spark-mascot.png'
const ROTATE_EVERY_MS = 15_000
const VARIANT_PLAY_MS = 7_200 // one full loop pass (86 frames @ 12fps)

export default function SparkMascot({ className }: { className: string }) {
  const [variantSrc, setVariantSrc] = useState<string | null>(null)
  const [variantVisible, setVariantVisible] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  const [failed, setFailed] = useState(false)
  const nextIdx = useRef(0)

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReducedMotion(mq.matches)
    const onChange = (e: MediaQueryListEvent) => setReducedMotion(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    if (reducedMotion || failed) return
    let playTimer: ReturnType<typeof setTimeout> | undefined
    const rotateTimer = setInterval(() => {
      const src = VARIANT_SRCS[nextIdx.current % VARIANT_SRCS.length]
      nextIdx.current += 1
      // Preload so the variant starts on its base-pose first frame, not a blank
      const preload = new window.Image()
      preload.onload = () => {
        setVariantSrc(src)
        setVariantVisible(true)
        playTimer = setTimeout(() => setVariantVisible(false), VARIANT_PLAY_MS)
      }
      preload.src = src // onerror: skip this rotation, idle keeps playing
    }, ROTATE_EVERY_MS)
    return () => {
      clearInterval(rotateTimer)
      if (playTimer) clearTimeout(playTimer)
    }
  }, [reducedMotion, failed])

  if (reducedMotion || failed) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={STATIC_SRC} alt="Spark" width={96} height={96} className={className} />
  }

  return (
    <div className="relative h-full w-full">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={IDLE_SRC}
        alt="Spark"
        width={96}
        height={96}
        className={`${className} absolute inset-0`}
        onError={() => setFailed(true)}
      />
      {variantSrc && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={variantSrc}
          alt=""
          aria-hidden="true"
          width={96}
          height={96}
          className={`${className} absolute inset-0 transition-opacity duration-500 ${
            variantVisible ? 'opacity-100' : 'opacity-0'
          }`}
        />
      )}
    </div>
  )
}
