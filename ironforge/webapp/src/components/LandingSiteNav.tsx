'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import './LandingSiteNav.css'

/**
 * Operator site navigation for the marketing landing at "/".
 *
 * The landing renders full-bleed with the global app nav suppressed (see Shell),
 * so without this there's no way to reach the dashboards from the home page.
 * This is a left-edge pull-out drawer (overlay, closed by default) linking to
 * every app route — it does not touch the signed-off landing markup.
 */

const BOTS = [
  { href: '/spark', label: 'SPARK' },
  { href: '/flame', label: 'FLAME' },
  { href: '/inferno', label: 'INFERNO' },
  { href: '/blaze', label: 'BLAZE' },
  { href: '/flare', label: 'FLARE' },
]

const TOOLS = [
  { href: '/gex', label: 'GEX Profile' },
  { href: '/compare', label: 'Compare' },
  { href: '/calendar', label: 'Calendar' },
  { href: '/briefings', label: 'Briefings' },
  { href: '/accounts', label: 'Accounts' },
  { href: '/ember', label: 'EMBER' },
]

export default function LandingSiteNav() {
  const [open, setOpen] = useState(false)
  const close = () => setOpen(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  return (
    <>
      <button className="ifsn-tab" aria-label="Open site menu" onClick={() => setOpen(true)}>
        <span className="ifsn-burger" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <span className="ifsn-tab-label">MENU</span>
      </button>

      <div
        className={`ifsn-overlay${open ? ' open' : ''}`}
        onClick={close}
        aria-hidden={!open}
      />

      <aside
        className={`ifsn-panel${open ? ' open' : ''}`}
        role="dialog"
        aria-label="Site navigation"
        aria-modal={open}
      >
        <div className="ifsn-head">
          <span className="ifsn-brand">
            <b>IRON</b>FORGE <em>// site</em>
          </span>
          <button className="ifsn-close" aria-label="Close menu" onClick={close}>
            ×
          </button>
        </div>
        <nav className="ifsn-nav">
          <Link className="ifsn-link ifsn-home" href="/" onClick={close}>
            Home
          </Link>
          <div className="ifsn-section">Bots</div>
          {BOTS.map((l) => (
            <Link key={l.href} className="ifsn-link" href={l.href} onClick={close}>
              {l.label}
            </Link>
          ))}
          <div className="ifsn-section">Tools</div>
          {TOOLS.map((l) => (
            <Link key={l.href} className="ifsn-link" href={l.href} onClick={close}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="ifsn-foot">Operator access · dashboards</div>
      </aside>
    </>
  )
}
