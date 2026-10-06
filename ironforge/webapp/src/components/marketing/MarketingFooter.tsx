'use client'

import Link from 'next/link'
import AppStoreBadges from './AppStoreBadges'
import { useWaitlistModal } from './WaitlistModal'

/** Footer shared by every 10.4 marketing page — copy and links verbatim from the design. */
export default function MarketingFooter() {
  const { openWaitlist } = useWaitlistModal()
  return (
    <footer>
      <div className="wrap foot">
        <div>
          <Link className="wordmark" href="/">
            IRON<b>FORGE</b>
          </Link>
          <p className="muted" style={{ margin: '10px 0 16px', maxWidth: '34ch' }}>
            Automated options execution, built on discipline.
          </p>
          <AppStoreBadges />
        </div>
        <div>
          <h4>Agents</h4>
          <ul>
            <li>
              <Link href="/agents#spark">Spark</Link>
            </li>
            <li>
              <Link href="/agents#flame">Flame</Link>
            </li>
            <li>
              <Link href="/agents#ember">Ember</Link>
            </li>
            <li>
              <Link href="/agents#compare">Compare agents</Link>
            </li>
            <li>
              <Link href="/agents#guardrails">Guardrails</Link>
            </li>
          </ul>
        </div>
        <div>
          <h4>How it works</h4>
          <ul>
            <li>
              <Link href="/how-it-works#day">Daily routine</Link>
            </li>
            <li>
              <Link href="/how-it-works#ladder">The Ladder</Link>
            </li>
            <li>
              <Link href="/how-it-works#brokerage">Brokerages</Link>
            </li>
            <li>
              <Link href="/how-it-works#control">Safety &amp; control</Link>
            </li>
            <li>
              <Link href="/pricing#plans">Pricing</Link>
            </li>
            <li>
              <Link href="/pricing#faq">FAQ</Link>
            </li>
          </ul>
        </div>
        <div>
          <h4>Account</h4>
          <ul>
            <li>
              <Link href="/signup?source=site&placement=footer">Create account</Link>
            </li>
            <li>
              <Link href="/login">Log in</Link>
            </li>
            <li>
              <button type="button" className="footer-link-btn" onClick={openWaitlist}>
                Join the waitlist
              </button>
            </li>
            <li>
              <Link href="/about">About</Link>
            </li>
            <li>
              <Link href="/privacy">Privacy Policy</Link>
            </li>
            <li>
              <Link href="/terms">Risk Disclosure</Link>
            </li>
          </ul>
        </div>
        <p className="disclose">
          Options trading involves substantial risk and isn&apos;t suitable for every investor. You can lose some or
          all of the money you invest. Backtested results are hypothetical, produced with the benefit of hindsight,
          and don&apos;t represent actual trading. Past performance, real or hypothetical, doesn&apos;t guarantee
          future results. IronForge provides automated trade execution software and educational content and
          doesn&apos;t provide personalized investment advice. Brokerage services are provided by your connected
          broker. © 2026 IronForge.
        </p>
      </div>
    </footer>
  )
}
