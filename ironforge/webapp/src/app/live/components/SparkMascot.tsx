'use client'

import { useEffect, useRef, useState } from 'react'

// Animated mascot: the gentle-flicker loop idles, and every 15s one of the
// variant loops plays through a full pass before handing back to the idle.
// A SINGLE <img> hard-swaps between clips — the card renders this with
// mix-blend-screen, which never occludes, so stacked/crossfaded layers would
// show both flames superimposed. Every clip's first frame is the same base
// pose (the original still), so a src swap reads as continuous animation.
const IDLE_SRC = '/spark-anim/01-gentle-flicker-v3.webp'
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
// Flame is the SAME mascot as Spark, recoloured to orange with a CSS filter, so
// it animates using Spark's clips instead of sitting on a static PNG. Tuned
// against the old orange still (/home/flame-mascot-glow.png): hue-rotate lands
// the blue body on Forge orange, the light saturation bump keeps it vivid.
const FLAME_FILTER = 'hue-rotate(165deg) saturate(1.3)'
const ROTATE_EVERY_MS = 15_000
const VARIANT_PLAY_MS = 7_200 // one full loop pass (86 frames @ 12fps)

export default function SparkMascot({
  className,
  variant = 'spark',
}: {
  className: string
  /** Which strategy's mascot — Flame is orange, Spark is the animated blue. */
  variant?: 'spark' | 'flame'
}) {
  const isFlame = variant === 'flame'
  const [src, setSrc] = useState(IDLE_SRC)
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
    // Flame animates too — same clips as Spark, recoloured by CSS below.
    if (reducedMotion || failed) return
    let playTimer: ReturnType<typeof setTimeout> | undefined
    const rotateTimer = setInterval(() => {
      const variant = VARIANT_SRCS[nextIdx.current % VARIANT_SRCS.length]
      nextIdx.current += 1
      // Preload so the swap starts on the variant's base-pose first frame
      const preload = new window.Image()
      preload.onload = () => {
        setSrc(variant)
        playTimer = setTimeout(() => setSrc(IDLE_SRC), VARIANT_PLAY_MS)
      }
      preload.src = variant // onerror: skip this rotation, idle keeps playing
    }, ROTATE_EVERY_MS)
    return () => {
      clearInterval(rotateTimer)
      if (playTimer) clearTimeout(playTimer)
    }
  }, [reducedMotion, failed])

  const effectiveSrc = reducedMotion || failed ? STATIC_SRC : src

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={effectiveSrc}
      alt={isFlame ? 'Flame' : 'Spark'}
      width={96}
      height={96}
      className={className}
      style={isFlame ? { filter: FLAME_FILTER } : undefined}
      onError={() => setFailed(true)}
    />
  )
}
