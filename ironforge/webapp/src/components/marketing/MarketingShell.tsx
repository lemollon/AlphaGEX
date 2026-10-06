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
 */
export default function MarketingShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="ifw-marketing">
      <MarketingIcons />
      <WaitlistModalProvider>
        <MarketingNav />
        <main>{children}</main>
        <MarketingFooter />
      </WaitlistModalProvider>
    </div>
  )
}
