'use client'

import { useEffect, useRef, useState } from 'react'

const SPY_IDS = ['home-agents', 'home-how']
const LOCK_MS = 900

/**
 * Tracks which home-page section is currently in view so the nav can mark
 * "Agents" / "How it works" as active while scrolling (ps-nav #41: "threshold
 * 140px ... locks the spy for ~900ms" after a nav click, so a smooth-scroll
 * in flight doesn't get fought by the observer mid-animation).
 *
 * Only runs on the home page — `ids` is empty (and this is a no-op) anywhere
 * else, since #home-agents/#home-how only exist there.
 */
export function useHomeScrollSpy(enabled: boolean) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const lockedUntil = useRef(0)

  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return
    const elements = SPY_IDS.map((id) => document.getElementById(id)).filter(
      (el): el is HTMLElement => el != null
    )
    if (elements.length === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (Date.now() < lockedUntil.current) return
        const visible = entries.filter((e) => e.isIntersecting)
        if (visible.length === 0) return
        // Topmost visible section wins when more than one crosses the line.
        const top = visible.reduce((a, b) => (a.boundingClientRect.top <= b.boundingClientRect.top ? a : b))
        setActiveId(top.target.id)
      },
      { rootMargin: '-140px 0px -60% 0px', threshold: 0 }
    )
    elements.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [enabled])

  /** Call right before a nav click's smooth scroll starts. */
  function lockAndSet(id: string) {
    lockedUntil.current = Date.now() + LOCK_MS
    setActiveId(id)
  }

  return { activeId: enabled ? activeId : null, lockAndSet }
}
