'use client'

import { useEffect } from 'react'
import { LANDING_MARKUP } from './_landing/landingMarkup'
import './_landing/landing.css'

/**
 * IronForge landing page (schematic × forge design, REV B).
 *
 * The design ships as a single self-contained HTML document. To preserve the
 * signed-off visuals byte-for-byte (heavy SVG + inline styles), the body markup
 * is rendered via dangerouslySetInnerHTML, the <style> blocks live in
 * ./_landing/landing.css, and the design's vanilla JS (blocks 1–5: topbar ticker,
 * iron-condor drag/draw/gate-flow, the tweaks panel, tape/cinders/controls/bench/
 * counters/P-L tick, strategy-chips/scrubber/sparklines/find-my-bot quiz) runs
 * verbatim from /public/_landing/landing-runtime.js, injected after mount.
 *
 * The two original waitlist handlers (a dead modal-wiring block + a mailto
 * placeholder) were dropped from the runtime and replaced by the Web3Forms
 * wiring below.
 */

// ── Waitlist delivery ───────────────────────────────────────────────────────
// Paste your free Web3Forms access key here to have every signup emailed to you.
// Get one in ~2 min at https://web3forms.com (enter shairan2016@gmail.com — they
// email you the key; no account/password needed). Until a key is set, the form
// falls back to opening a pre-filled email to you.
const WEB3FORMS_ACCESS_KEY = '' // e.g. '12345678-aaaa-bbbb-cccc-1234567890ab'
const FALLBACK_EMAIL = 'shairan2016@gmail.com'

export default function Home() {
  useEffect(() => {
    // 1) Run the design's vanilla JS against the freshly-mounted markup.
    //    Re-created each mount so React Strict Mode (dev) re-wires the current DOM.
    const script = document.createElement('script')
    script.src = '/_landing/landing-runtime.js'
    script.async = false
    document.body.appendChild(script)

    // 2) Wire the early-access form (#proof .auth-form) to the waitlist delivery.
    const form = document.querySelector<HTMLFormElement>('form.auth-form')
    const thanks = document.getElementById('waitlist-thanks')
    const showThanks = () => {
      if (thanks) {
        thanks.style.display = 'block'
        thanks.style.color = 'var(--accent)'
        thanks.style.fontWeight = '500'
      }
    }
    const onSubmit = (e: Event) => {
      e.preventDefault()
      if (!form) return
      const data = new FormData(form)
      const email = String(data.get('email') || '').trim()
      const experience = String(data.get('experience') || '')
      if (!email) return

      if (WEB3FORMS_ACCESS_KEY) {
        // Email every signup straight to your inbox via Web3Forms (no backend).
        fetch('https://api.web3forms.com/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({
            access_key: WEB3FORMS_ACCESS_KEY,
            subject: 'New IronForge waitlist signup',
            from_name: 'IronForge waitlist',
            email,
            experience,
          }),
        }).catch(() => {})
        showThanks()
        setTimeout(() => form.reset(), 200)
      } else {
        // No key configured yet → graceful fallback: open a pre-filled email to you.
        showThanks()
        const body = encodeURIComponent(`Email: ${email}\nExperience: ${experience}`)
        window.location.href =
          `mailto:${FALLBACK_EMAIL}?subject=IronForge%20waitlist%20signup&body=${body}`
      }
    }
    form?.addEventListener('submit', onSubmit)

    return () => {
      form?.removeEventListener('submit', onSubmit)
      script.remove()
    }
  }, [])

  return (
    <>
      {/* Fonts now match the app design system (system font-sans via landing.css),
          so the IBM Plex / Cormorant Google Fonts <link> is no longer needed. */}
      <div className="ironforge-landing" dangerouslySetInnerHTML={{ __html: LANDING_MARKUP }} />
    </>
  )
}
