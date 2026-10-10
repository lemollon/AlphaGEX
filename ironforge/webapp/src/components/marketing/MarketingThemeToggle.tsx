'use client'

import { useEffect, useState } from 'react'

const STORAGE_KEY = 'if-theme'

type Theme = 'light' | 'dark'

/**
 * Light/dark toggle for the 10.4 marketing design. Matches the spec's
 * pattern: OS preference by default, explicit pick persisted per device.
 *
 * Sets `data-theme` on `<html>` (not the `.ifw-marketing` wrapper) because
 * `forge-tokens.css`'s `:root[data-theme="dark"]` selector — copied
 * byte-identical from the design — only matches there.
 */
export default function MarketingThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null)

  useEffect(() => {
    let stored: Theme | null = null
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      if (raw) stored = JSON.parse(raw)
    } catch {
      /* ignore — falls back to OS preference */
    }
    if (stored === 'light' || stored === 'dark') {
      setTheme(stored)
      document.documentElement.setAttribute('data-theme', stored)
    }
  }, [])

  function toggle() {
    const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches
    const current = theme ?? (prefersDark ? 'dark' : 'light')
    const next: Theme = current === 'dark' ? 'light' : 'dark'
    setTheme(next)
    document.documentElement.setAttribute('data-theme', next)
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      /* ignore — theme still applies for this page view */
    }
  }

  return (
    <button className="icon-btn theme" type="button" onClick={toggle} aria-label="Switch light or dark mode">
      <svg className="sun">
        <use href="#i-sun" />
      </svg>
      <svg className="moon">
        <use href="#i-moon" />
      </svg>
    </button>
  )
}
