import { NextResponse } from 'next/server'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Lists the brokerages a customer can connect through SnapTrade — the source of truth for the
 * "Choose your broker" dropdown on the onboarding page. When SnapTrade is provisioned we return
 * exactly the brokerages enabled for OUR client id (getPartnerInfo → allowed_brokerages), filtered
 * to ones that are live and trade-capable. When the keys aren't set yet we fall back to a curated
 * list of popular SnapTrade brokers so the dropdown still renders (connecting is what 503s, not the
 * list). Tradier is NOT here — it has its own OAuth and is offered separately by the client.
 */

export interface BrokerOption {
  slug: string
  name: string
}

// IronForge runs US equity-OPTIONS strategies (SPX/SPY iron condors), so the dropdown must only
// offer brokers that can actually place those trades. SnapTrade's raw partner list also includes
// crypto exchanges (Coinbase, Binance, Kraken) and international brokers (Wealthsimple, Questrade,
// Trading212, Stake AU, Webull Canada, moomoo) — connecting one of those would succeed but the bot
// could never trade, so we filter to this allowlist of US options-capable SnapTrade slugs. Keep it
// a superset: brokers not yet enabled on our SnapTrade account simply won't appear until they are.
const OPTIONS_CAPABLE_SLUGS = new Set<string>([
  'TASTYTRADE',
  'ETRADE',
  'WEBULL-US',
  'PUBLIC',
  'ROBINHOOD',
  'SCHWAB',
  'FIDELITY',
  'TRADESTATION',
  'INTERACTIVE-BROKERS',
  'IBKR',
])

function isOptionsCapable(slug: string): boolean {
  return OPTIONS_CAPABLE_SLUGS.has(slug.toUpperCase())
}

// Shown only when the live partner list is unavailable (keys unset / API error). Options-capable
// US brokers only, same rationale as the allowlist above.
const FALLBACK_BROKERS: BrokerOption[] = [
  { slug: 'TASTYTRADE', name: 'tastytrade' },
  { slug: 'ETRADE', name: 'E*TRADE' },
  { slug: 'WEBULL-US', name: 'Webull' },
  { slug: 'PUBLIC', name: 'Public' },
]

interface Brokerage {
  slug?: string
  name?: string
  display_name?: string
  enabled?: boolean
  maintenance_mode?: boolean
  is_degraded?: boolean
  allows_trading?: boolean | null
}

export async function GET() {
  if (!isSnapTradeConfigured()) {
    return NextResponse.json({ ok: true, configured: false, brokers: FALLBACK_BROKERS })
  }

  try {
    const snaptrade = getSnapTrade()
    const info = await snaptrade.referenceData.getPartnerInfo()
    const allowed = (info.data?.allowed_brokerages ?? []) as Brokerage[]

    const brokers: BrokerOption[] = allowed
      // Live, connectable, trade-capable, US options-capable brokers only. allows_trading is null
      // for some brokers that still support trading, so only exclude an explicit false.
      .filter(
        (b) =>
          b.slug &&
          b.enabled !== false &&
          !b.maintenance_mode &&
          b.allows_trading !== false &&
          isOptionsCapable(b.slug),
      )
      .map((b) => ({ slug: b.slug as string, name: b.display_name || b.name || (b.slug as string) }))
      .sort((a, b) => a.name.localeCompare(b.name))

    // If the partner list somehow comes back empty, still give the dropdown something.
    return NextResponse.json({
      ok: true,
      configured: true,
      brokers: brokers.length ? brokers : FALLBACK_BROKERS,
    })
  } catch (e) {
    console.error('[brokerage/brokerages] failed:', e)
    return NextResponse.json({ ok: true, configured: false, brokers: FALLBACK_BROKERS })
  }
}
