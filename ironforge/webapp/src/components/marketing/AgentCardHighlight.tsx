'use client'

import { useEffect } from 'react'

const HIGHLIGHT_MS = 1600

/**
 * "Clicking an agent link briefly highlights that agent's card" (ps-nav #42).
 * Agent cards (home grid and /agents) share `id={agent.slug}` (spark/flame/
 * ember) via AgentCard.tsx. This watches the URL hash — on load and on every
 * in-page hash change, including clicking an already-active anchor again —
 * and flashes `.hl` on the matching card for ~1.6s, then removes it.
 * No UI of its own; mounted once per marketing page via MarketingShell.
 */
export default function AgentCardHighlight() {
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined

    function flash() {
      const hash = window.location.hash.slice(1)
      if (!hash) return
      const el = document.getElementById(hash)
      if (!el || !el.classList.contains('agent')) return
      if (timer) clearTimeout(timer)
      el.classList.remove('hl')
      // Re-trigger the CSS animation even if the same card was just flashed.
      void el.offsetWidth
      el.classList.add('hl')
      timer = setTimeout(() => el.classList.remove('hl'), HIGHLIGHT_MS)
    }

    flash()
    window.addEventListener('hashchange', flash)
    return () => {
      window.removeEventListener('hashchange', flash)
      if (timer) clearTimeout(timer)
    }
  }, [])

  return null
}
