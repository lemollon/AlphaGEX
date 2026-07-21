'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { BOT_COLORS } from '@/lib/botColors'
import { LIVE_BOTS, LIVE_BOT_PILL, LIVE_BOT_MODE } from '@/lib/live/bots'

/* Admin-only "Bots" menu for the public homepage nav.
 *
 * The customer masthead deliberately links only customer-facing pages, so an
 * operator browsing ironforge.trade had no way to jump straight to a bot without
 * hand-editing the URL. This adds a single dropdown — rendered ONLY when the
 * operator status probe answers operator:true, and hidden while impersonating a
 * customer (you're looking at the customer's site then). For visitors and
 * customers the probe reveals nothing and this renders null.
 *
 * IT MUST ONLY LINK CUSTOMER-SURFACE ROUTES. The operator consoles (/spark,
 * /flame, /inferno, /compare …) are served by the OTHER deployment and are 404
 * here by design — see lib/surface.ts. So the entries are the live bots from
 * lib/live/bots.ts, pointed at the Live page's account view, which this surface
 * does serve. Deriving the list from LIVE_BOTS means a bot added there shows up
 * here automatically and a link can never point at a route we 404. */

type BotLink = { href: string; label: string; dot?: string; note?: string }

// The live bots, in registry order, each linking to its Live account view.
// '/live' with no param is SPARK — matches how LiveClient normalises the URL.
const BOT_LINKS: ReadonlyArray<BotLink> = LIVE_BOTS.map((bot) => ({
  href: bot === 'spark' ? '/live' : `/live?account=${bot}`,
  label: LIVE_BOT_PILL[bot],
  dot: BOT_COLORS[bot],
  note: LIVE_BOT_MODE[bot] === 'paper' ? 'paper' : 'live money',
}))

function useIsOperator(): boolean {
  const [isOperator, setIsOperator] = useState(false)
  useEffect(() => {
    fetch('/api/ops/impersonate?status=true')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setIsOperator(Boolean(d?.operator) && !d?.impersonating))
      .catch(() => setIsOperator(false))
  }, [])
  return isOperator
}

function Dot({ color }: { color?: string }) {
  if (!color) return <span className="inline-block h-1.5 w-1.5 shrink-0" />
  return (
    <span
      className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
      style={{ background: color, boxShadow: `0 0 6px ${color}` }}
    />
  )
}

/** Desktop: a "Bots" dropdown that sits inline with the other nav links. */
export function AdminBotsMenu() {
  const isOperator = useIsOperator()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (!isOperator) return null

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-1 text-sm text-amber-500 transition-colors hover:text-amber-400"
      >
        Bots
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          aria-hidden="true"
          className={`transition-transform ${open ? 'rotate-180' : ''}`}
        >
          <path d="M2 4 L5 7 L8 4" stroke="currentColor" strokeWidth="1.2" fill="none" />
        </svg>
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-3 min-w-[220px] rounded-lg border border-amber-500/30 bg-black/95 py-2 shadow-2xl shadow-black/60 backdrop-blur"
        >
          <p className="px-4 pb-2 text-[10px] font-bold uppercase tracking-wider text-amber-500/70">
            Admin only
          </p>
          {BOT_LINKS.map((bot) => (
            <Link
              key={bot.href}
              href={bot.href}
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 px-4 py-2 text-sm text-gray-300 transition-colors hover:bg-white/5 hover:text-white"
            >
              <Dot color={bot.dot} />
              <span className="font-medium">{bot.label}</span>
              {bot.note ? <span className="ml-auto text-[11px] text-gray-500">{bot.note}</span> : null}
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  )
}

/** Mobile: the same links, stacked flat inside the hamburger drawer. */
export function AdminBotsMobileLinks({ onNavigate }: { onNavigate?: () => void }) {
  const isOperator = useIsOperator()
  if (!isOperator) return null

  return (
    <>
      <p className="pt-2 text-[10px] font-bold uppercase tracking-wider text-amber-500/70">
        Bots — admin only
      </p>
      {BOT_LINKS.map((bot) => (
        <Link
          key={bot.href}
          href={bot.href}
          onClick={onNavigate}
          className="flex items-center gap-2.5 text-sm text-gray-300"
        >
          <Dot color={bot.dot} />
          {bot.label}
        </Link>
      ))}
    </>
  )
}
