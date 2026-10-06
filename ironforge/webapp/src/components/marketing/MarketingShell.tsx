import { GeistSans } from 'geist/font/sans'
import { GeistMono } from 'geist/font/mono'
import MarketingIcons from './MarketingIcons'
import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { WaitlistModalProvider } from './WaitlistModal'

/**
 * Wraps every 10.4 marketing page in the `.ifw-marketing` scope that
 * `forge-marketing.css` styles target, plus the shared nav/footer/icon defs.
 *
 * WaitlistModalProvider is mounted here (not in the layout) so it's in scope for
 * every CTA the nav, footer and page bodies render — one modal instance for the
 * whole marketing site, not one per page (ps-ctas "Join the waitlist -> Opens
 * waitlist modal, no navigation").
 *
 * Geist (body/UI) and Geist Mono (clock/numeric displays) are loaded here via
 * next/font (the `geist` package, built on `next/font/local`) and scoped to
 * these public pages only — `forge-tokens.css`'s `--sans`/`--mono` pick up
 * the `--font-geist-sans`/`--font-geist-mono` variables set by these classes.
 * Dashboard/enroll keep their existing Inter/Oswald typography untouched.
 * The Barlow Condensed wordmark (`--brand`) is unaffected.
 */
export default function MarketingShell({ children }: { children: React.ReactNode }) {
  return (
    <div className={`ifw-marketing ${GeistSans.variable} ${GeistMono.variable}`}>
      <MarketingIcons />
      <WaitlistModalProvider>
        <MarketingNav />
        <main>{children}</main>
        <MarketingFooter />
      </WaitlistModalProvider>
    </div>
  )
}
