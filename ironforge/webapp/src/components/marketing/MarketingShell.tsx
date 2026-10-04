import MarketingIcons from './MarketingIcons'
import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'

/**
 * Wraps every 10.4 marketing page in the `.ifw-marketing` scope that
 * `forge-marketing.css` styles target, plus the shared nav/footer/icon defs.
 */
export default function MarketingShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="ifw-marketing">
      <MarketingIcons />
      <MarketingNav />
      <main>{children}</main>
      <MarketingFooter />
    </div>
  )
}
