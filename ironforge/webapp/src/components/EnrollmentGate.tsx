'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { usePathname, useRouter } from 'next/navigation'

/**
 * EnrollmentGate — blocking "enrollment closed → join the waitlist" overlay
 * (8/1 "Enrollment Waitlist Overlay" handoff). Mounted ONCE at the app shell
 * (layout.tsx) with `enabled` fed by the server flag; it self-limits to the
 * enrollment routes via the pathname, so it is completely inert everywhere else
 * and whenever the flag is off.
 *
 * The overlay is UX only — closure is also enforced server-side on every
 * account-creation endpoint (see lib/enrollment-mode.ts). Approved visual:
 * dimmed Create-Account page behind a near-black panel with a thin Forge-Orange
 * border, "THE FORGE IS BEING BUILT" headline, body copy, an orange
 * JOIN THE WAITLIST button, and an underlined Return to Home link. No close
 * icon; Escape and backdrop click never dismiss.
 */

// z-index token: above every nav (~z-60), the Sparky chat widget (z-40), and any
// third-party embed. Documented single value so it is never guessed at again.
const Z_ENROLLMENT_GATE = 2147480000

// Campaign/referral params preserved onto /waitlist (handoff INT-02, §5).
const PRESERVED_PARAMS = [
  'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
  'ref', 'referral', 'referralCode', 'code',
]

const HEADLINE = 'THE FORGE IS BEING BUILT'
const BODY = "We're putting the final pieces in place. Join the waitlist for early access and launch updates."

/** The routes the gate blocks: Create Account and every enrollment step. */
function isEnrollmentRoute(pathname: string | null): boolean {
  if (!pathname) return false
  return pathname === '/signup' || pathname === '/enroll' || pathname.startsWith('/enroll/')
}

/** Best-effort analytics — no-ops unless a dataLayer/gtag sink exists. */
function track(event: string, props: Record<string, unknown> = {}) {
  if (typeof window === 'undefined') return
  const w = window as unknown as { dataLayer?: unknown[]; gtag?: (...a: unknown[]) => void }
  try {
    if (Array.isArray(w.dataLayer)) w.dataLayer.push({ event, ...props })
    else if (typeof w.gtag === 'function') w.gtag('event', event, props)
  } catch { /* analytics must never break the gate */ }
}

export default function EnrollmentGate({
  enabled,
  waitlistUrl = '/waitlist',
  homeUrl = '/',
}: {
  enabled: boolean
  waitlistUrl?: string
  homeUrl?: string
}) {
  const pathname = usePathname()
  const router = useRouter()
  const active = enabled && isEnrollmentRoute(pathname)

  const primaryRef = useRef<HTMLButtonElement>(null)
  const secondaryRef = useRef<HTMLAnchorElement>(null)

  // Portal host, created once client-side and appended to <body> while active.
  const [host] = useState<HTMLElement | null>(() =>
    typeof document === 'undefined' ? null : document.createElement('div'),
  )
  useEffect(() => {
    if (host) host.setAttribute('data-enrollment-gate', '')
  }, [host])

  // Attach host, lock scroll (no layout shift), inert + hide the rest of the
  // page, trap focus, and fire the view event — all torn down on exit.
  useEffect(() => {
    if (!active || !host) return
    const body = document.body
    body.appendChild(host)

    const prevActive = document.activeElement as HTMLElement | null

    // Scroll lock without layout shift: pad for the reclaimed scrollbar width.
    const scrollbar = window.innerWidth - document.documentElement.clientWidth
    const prevOverflow = body.style.overflow
    const prevPad = body.style.paddingRight
    body.style.overflow = 'hidden'
    if (scrollbar > 0) body.style.paddingRight = `${scrollbar}px`

    // Make the background inert + removed from the a11y tree. The host is a body
    // child, excluded here, so the modal stays interactive and announceable.
    const restore: Array<() => void> = []
    for (const el of Array.from(body.children)) {
      if (el === host) continue
      const node = el as HTMLElement
      const hadInert = node.hasAttribute('inert')
      const prevAria = node.getAttribute('aria-hidden')
      node.setAttribute('inert', '')
      node.setAttribute('aria-hidden', 'true')
      restore.push(() => {
        if (!hadInert) node.removeAttribute('inert')
        if (prevAria === null) node.removeAttribute('aria-hidden')
        else node.setAttribute('aria-hidden', prevAria)
      })
    }

    const focusTimer = window.setTimeout(() => primaryRef.current?.focus(), 0)

    // Trap focus between the two actions; swallow Escape (must not dismiss).
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); return }
      if (e.key !== 'Tab') return
      const nodes = [primaryRef.current, secondaryRef.current].filter(Boolean) as HTMLElement[]
      if (nodes.length === 0) return
      const first = nodes[0]
      const last = nodes[nodes.length - 1]
      const current = document.activeElement
      const inModal = nodes.includes(current as HTMLElement)
      if (e.shiftKey) {
        if (current === first || !inModal) { e.preventDefault(); last.focus() }
      } else {
        if (current === last || !inModal) { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', onKeyDown, true)

    track('enrollment_gate_viewed', { route: pathname })

    return () => {
      window.clearTimeout(focusTimer)
      document.removeEventListener('keydown', onKeyDown, true)
      body.style.overflow = prevOverflow
      body.style.paddingRight = prevPad
      for (const undo of restore) undo()
      if (host.parentNode) host.parentNode.removeChild(host)
      // Restore focus only if the originating control still exists (handoff §9).
      if (prevActive && document.contains(prevActive)) prevActive.focus()
    }
  }, [active, host, pathname])

  const goWaitlist = () => {
    const params = new URLSearchParams()
    if (typeof window !== 'undefined') {
      const cur = new URLSearchParams(window.location.search)
      for (const k of PRESERVED_PARAMS) {
        const v = cur.get(k)
        if (v) params.set(k, v)
      }
    }
    const qs = params.toString()
    const dest = qs ? `${waitlistUrl}?${qs}` : waitlistUrl
    track('enrollment_gate_waitlist_clicked', { route: pathname, destination: dest })
    router.push(dest)
  }

  const onHome = () => track('enrollment_gate_home_clicked', { route: pathname, destination: homeUrl })

  const modal = useMemo(() => (
    <div
      // Backdrop: fixed to viewport, ~72% black. Click does nothing (no dismiss).
      className="fixed inset-0 flex items-center justify-center bg-black/[.72] p-4 backdrop-blur-[2px] motion-safe:transition-opacity"
      style={{ zIndex: Z_ENROLLMENT_GATE }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="enrollment-gate-title"
        aria-describedby="enrollment-gate-body"
        className="w-[min(580px,calc(100vw-32px))] max-h-[calc(100vh-32px)] overflow-y-auto rounded-[18px] border border-amber-500 bg-[#0c0c0f] px-6 py-9 text-center shadow-2xl shadow-black/60 sm:px-10 sm:py-11 md:px-12"
      >
        <h2
          id="enrollment-gate-title"
          className="text-[26px] font-extrabold uppercase leading-tight tracking-wide text-white sm:text-[30px]"
        >
          {HEADLINE}
        </h2>
        <p
          id="enrollment-gate-body"
          className="mx-auto mt-4 max-w-[26rem] text-[15px] leading-relaxed text-gray-300"
        >
          {BODY}
        </p>

        <button
          ref={primaryRef}
          type="button"
          onClick={goWaitlist}
          className="mx-auto mt-8 flex h-[50px] w-full max-w-[320px] items-center justify-center rounded-lg bg-amber-500 px-6 text-[15px] font-bold uppercase tracking-wide text-black transition-colors hover:bg-amber-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300"
        >
          Join the Waitlist
        </button>

        <div className="mt-5">
          <a
            ref={secondaryRef}
            href={homeUrl}
            onClick={onHome}
            className="inline-flex min-h-[44px] items-center justify-center text-sm text-gray-300 underline decoration-gray-500 underline-offset-4 transition-colors hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300"
          >
            Return to Home
          </a>
        </div>
      </div>
    </div>
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ), [homeUrl, pathname])

  if (!active || !host) return null
  return createPortal(modal, host)
}
