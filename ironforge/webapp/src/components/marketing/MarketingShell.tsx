import { GeistSans } from 'geist/font/sans'
import { GeistMono } from 'geist/font/mono'
import MarketingIcons from './MarketingIcons'
import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'

/**
 * Wraps every 10.4 marketing page in the `.ifw-marketing` scope that
 * `forge-marketing.css` styles target, plus the shared nav/footer/icon defs.
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
      <MarketingNav />
      <main>{children}</main>
      <MarketingFooter />
    </div>
  )
}
