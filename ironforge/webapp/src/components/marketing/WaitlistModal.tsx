'use client'

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { WaitlistForm } from '@/app/waitlist/WaitlistClient'
import { track } from '@/lib/analytics/track'

/**
 * Site-wide waitlist modal (ps-ctas "Join the waitlist -> Opens waitlist modal, no
 * navigation"; ds-a11y "Modals trap focus, close on Esc and backdrop click, and return
 * focus" — previously MISSING entirely, since no modal existed anywhere on the site).
 *
 * Mounted ONCE in MarketingShell. Every "Join the waitlist" CTA calls
 * `useWaitlistModal().openWaitlist()` instead of navigating to /waitlist — the standalone
 * page at that route still renders the same WaitlistForm for direct links/bookmarks.
 */

interface WaitlistModalContextValue {
  openWaitlist: (placement?: string) => void
  /** The placement the modal was last opened from, read by WaitlistForm when it
   *  fires waitlist_submit/waitlist_error — avoids threading a prop through every
   *  call site just for an analytics tag. */
  placement: string
}

const WaitlistModalContext = createContext<WaitlistModalContextValue | null>(null)

export function useWaitlistModal(): WaitlistModalContextValue {
  const ctx = useContext(WaitlistModalContext)
  // Falls back to a no-op rather than throwing: a CTA rendered outside MarketingShell
  // (there shouldn't be one, but a future page is cheap insurance) just does nothing
  // instead of crashing the page.
  return ctx ?? { openWaitlist: () => {}, placement: 'page' }
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function WaitlistModalProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const [placement, setPlacement] = useState('page')
  const returnFocusRef = useRef<HTMLElement | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const openWaitlist = useCallback((p?: string) => {
    // Captures whatever CTA was just activated (button/link), so closing the modal
    // puts focus back exactly where the customer was — the "return focus" half of the
    // ds-a11y requirement.
    returnFocusRef.current = document.activeElement as HTMLElement | null
    setOpen(true)
    if (p) setPlacement(p)
    track('waitlist_open', p ? { placement: p } : undefined)
  }, [])

  const close = useCallback(() => {
    setOpen(false)
    returnFocusRef.current?.focus()
  }, [])

  // Focus trap + Esc-to-close. Runs only while open.
  useEffect(() => {
    if (!open) return
    const panel = panelRef.current
    const focusables = panel ? Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)) : []
    ;(focusables[0] ?? panel)?.focus()

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        close()
        return
      }
      if (e.key !== 'Tab' || focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, close])

  return (
    <WaitlistModalContext.Provider value={{ openWaitlist, placement }}>
      {children}
      {open ? (
        <div
          className="fixed inset-0 z-[100] flex items-start justify-center overflow-y-auto p-4 sm:items-center"
          onMouseDown={(e) => {
            // Backdrop click closes — but only the backdrop itself, never a drag/select
            // that happens to end outside the panel.
            if (e.target === e.currentTarget) close()
          }}
        >
          <div className="absolute inset-0 bg-black/70" aria-hidden />
          <div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-label="Join the waitlist"
            tabIndex={-1}
            className="relative z-10 w-full max-w-[680px] outline-none"
          >
            <button
              type="button"
              onClick={close}
              aria-label="Close"
              className="btn absolute -top-3 -right-3 z-20 flex h-9 w-9 items-center justify-center rounded-full p-0"
            >
              <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="currentColor" strokeWidth="2.2">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
            <WaitlistForm />
          </div>
        </div>
      ) : null}
    </WaitlistModalContext.Provider>
  )
}
